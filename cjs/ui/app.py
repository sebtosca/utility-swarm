from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket
from fastapi.responses import FileResponse, HTMLResponse

from cjs.config import Settings, load_config
from cjs.storage.runs import create_run_folder, get_runs_dir


# ---------------------------------------------------------------------------
# Thread → asyncio event bridge
# ---------------------------------------------------------------------------

def _put_event(app: FastAPI, run_id: str, event: dict) -> None:
    """Thread-safe: schedule an event put on the server's event loop."""
    queues: dict[str, asyncio.Queue] = getattr(app.state, "queues", {})
    loop: asyncio.AbstractEventLoop | None = getattr(app.state, "loop", None)
    queue = queues.get(run_id)
    if queue is not None and loop is not None and not loop.is_closed():
        asyncio.run_coroutine_threadsafe(queue.put(event), loop)


def _safe_json(v: Any) -> Any:
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return repr(v)


def _safe_update(update: Any) -> dict:
    """Convert a LangGraph node output to a JSON-safe dict."""
    if not isinstance(update, dict):
        return {}
    return {k: _safe_json(v) for k, v in update.items()}


# ---------------------------------------------------------------------------
# Background jury thread
# ---------------------------------------------------------------------------

def _jury_thread(
    app: FastAPI,
    run_id: str,
    brief_path: Path,
    video_paths: list[Path],
    brand_path: Path | None,
    run_folder: Path,
    config: Settings,
) -> None:
    """Run the full jury pipeline in a ThreadPoolExecutor; emit WebSocket events."""
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        from cjs.auction.engine import run_auction
        from cjs.escalation.confidence_gate import LowConfidenceError  # noqa: F401
        from cjs.escalation.human_review import HumanReviewRejectedError  # noqa: F401
        from cjs.graph.jury_graph import build_jury_graph
        from cjs.graph.state import JuryState
        from cjs.pipelines.brief_ingest import (
            extract_brief_raw,
            generate_rubric,
            load_brand_rules_from_yaml,
            parse_brief,
        )
        from cjs.pipelines.video_analysis import analyze_video
        from cjs.report.builder import build_report
        from cjs.router.model_router import ModelRouter
        from cjs.schemas.brand_rules import BrandRules

        router = ModelRouter(run_id=run_id, run_folder=run_folder, config=config)
        _put_event(app, run_id, {"type": "jury_started", "run_id": run_id})

        # --- Brief ingestion ---
        _put_event(app, run_id, {"type": "node_start", "node": "brief_ingest"})
        brief_dir = run_folder / "brief"
        brief_dir.mkdir(exist_ok=True)
        raw_text = extract_brief_raw(brief_path, run_folder, config.limits.max_pdf_pages)
        parsed_brief = parse_brief(raw_text, router)
        (brief_dir / "brief.json").write_text(parsed_brief.model_dump_json(indent=2))
        rubric = generate_rubric(parsed_brief, router)
        (brief_dir / "rubric.json").write_text(rubric.model_dump_json(indent=2))

        if brand_path is not None:
            brand_rules = load_brand_rules_from_yaml(brand_path)
        else:
            brand_rules = BrandRules(
                brand_name=parsed_brief.brand or "Unknown",
                mandatory_elements=list(parsed_brief.mandatory),
                forbidden_elements=list(parsed_brief.forbidden),
                tone_keywords=[parsed_brief.tone] if parsed_brief.tone else [],
                source="brief_extracted",
            )
        (brief_dir / "brand_rules.json").write_text(brand_rules.model_dump_json(indent=2))
        _put_event(app, run_id, {"type": "node_complete", "node": "brief_ingest"})

        # --- Video analysis ---
        dossiers = []
        for vp in video_paths:
            _put_event(app, run_id, {"type": "node_start", "node": f"video_{vp.stem}"})
            dossier = analyze_video(vp, run_folder, router, config)
            dossiers.append(dossier)
            _put_event(app, run_id, {
                "type": "node_complete",
                "node": f"video_{vp.stem}",
                "duration_sec": dossier.duration_sec,
            })

        # --- Jury graph (stream mode for live events) ---
        initial_state: JuryState = {
            "run_id": run_id,
            "brief": parsed_brief.model_dump(),
            "rubric": rubric.model_dump(),
            "brand_rules": brand_rules.model_dump(),
            "video_dossiers": [d.model_dump() for d in dossiers],
            "initial_judgements": {},
            "consistency_report": None,
            "final_judgements": {},
            "verdict": None,
        }
        checkpoints_db = run_folder / "checkpoints.db"
        saver = SqliteSaver.from_conn_string(str(checkpoints_db))
        compiled = build_jury_graph().compile(checkpointer=saver)
        thread_config = {
            "configurable": {
                "thread_id": run_id,
                "router": router,
                "strict_confidence": False,
                "auto_approve": True,
            }
        }

        for chunk in compiled.stream(initial_state, thread_config):
            for node_name, update in chunk.items():
                _put_event(app, run_id, {
                    "type": "node_complete",
                    "node": node_name,
                    "update": _safe_update(update),
                })

        snap = compiled.get_state(thread_config)
        final_state = snap.values

        # --- Auction + report ---
        _put_event(app, run_id, {"type": "node_start", "node": "auction"})
        verdict = run_auction(final_state, run_folder)
        build_report(run_folder, final_state, verdict, {})
        _put_event(app, run_id, {
            "type": "done",
            "winner": verdict["winner_video"],
            "report_url": f"/api/runs/{run_id}/report",
        })

    except Exception as exc:
        _put_event(app, run_id, {"type": "error", "message": str(exc)})


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(config_override: Settings | None = None) -> FastAPI:
    """
    FastAPI app factory. Pass config_override in tests to avoid hitting disk.
    The HTML page is read at creation time from jury_room.html alongside this file.
    """
    _page_html = (Path(__file__).parent / "jury_room.html").read_text()
    _config_holder: list[Settings | None] = [config_override]

    def _get_config() -> Settings:
        if _config_holder[0] is None:
            _config_holder[0] = load_config() or Settings()
        return _config_holder[0]

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        app.state.queues = {}
        app.state.executor = ThreadPoolExecutor(max_workers=4)
        app.state.loop = asyncio.get_event_loop()
        yield
        app.state.executor.shutdown(wait=False)

    app = FastAPI(title="CJS Jury Room", lifespan=_lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def root() -> str:
        return _page_html

    @app.get("/api/runs")
    async def list_runs() -> list[dict]:
        config = _get_config()
        runs_dir = get_runs_dir(config)
        dirs = sorted(
            [d for d in runs_dir.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
        return [{"run_id": d.name, "path": str(d)} for d in dirs]

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> dict:
        config = _get_config()
        run_folder = get_runs_dir(config) / run_id
        if not run_folder.exists():
            raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
        verdict_path = run_folder / "results" / "verdict.json"
        if verdict_path.exists():
            verdict = json.loads(verdict_path.read_text())
            return {
                "run_id": run_id,
                "status": "complete",
                "winner": verdict.get("winner_video"),
            }
        return {"run_id": run_id, "status": "in_progress"}

    @app.get("/api/runs/{run_id}/report")
    async def get_report(run_id: str) -> FileResponse:
        config = _get_config()
        report_path = get_runs_dir(config) / run_id / "results" / "report.html"
        if not report_path.exists():
            raise HTTPException(status_code=404, detail=f"No report for run: {run_id}")
        return FileResponse(str(report_path), media_type="text/html")

    @app.post("/api/run", status_code=202)
    async def start_run(
        brief: UploadFile = File(...),
        videos: list[UploadFile] = File(...),
        brand: UploadFile | None = File(default=None),
    ) -> dict:
        config = _get_config()
        run_folder = create_run_folder(config)
        run_id = run_folder.name

        input_dir = run_folder / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        brief_path = input_dir / (brief.filename or "brief.pdf")
        brief_path.write_bytes(await brief.read())

        videos_dir = input_dir / "videos"
        videos_dir.mkdir(exist_ok=True)
        video_paths: list[Path] = []
        for v in videos:
            vp = videos_dir / (v.filename or "video.mp4")
            vp.write_bytes(await v.read())
            video_paths.append(vp)

        brand_path: Path | None = None
        if brand is not None:
            brand_path = input_dir / (brand.filename or "brand.yaml")
            brand_path.write_bytes(await brand.read())

        queue: asyncio.Queue = asyncio.Queue()
        app.state.queues[run_id] = queue
        app.state.executor.submit(
            _jury_thread, app, run_id, brief_path, video_paths, brand_path, run_folder, config
        )

        return {"run_id": run_id, "ws_url": f"/ws/{run_id}"}

    @app.websocket("/ws/{run_id}")
    async def ws_events(websocket: WebSocket, run_id: str) -> None:
        await websocket.accept()
        if run_id not in app.state.queues:
            app.state.queues[run_id] = asyncio.Queue()
        queue: asyncio.Queue = app.state.queues[run_id]
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=300.0)
                await websocket.send_json(event)
                if event.get("type") in ("done", "error"):
                    break
        except asyncio.TimeoutError:
            await websocket.send_json({"type": "error", "message": "timed out waiting for events"})
        finally:
            app.state.queues.pop(run_id, None)
            await websocket.close()

    return app
