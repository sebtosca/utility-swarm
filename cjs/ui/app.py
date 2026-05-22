from __future__ import annotations

import asyncio
import json
import threading
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
# Background jury thread helpers
# ---------------------------------------------------------------------------

def _stream_graph(
    app: FastAPI,
    run_id: str,
    compiled: Any,
    thread_config: Any,
    run_folder: Path,
) -> None:
    """Stream jury graph from current checkpoint; emit WebSocket events. Runs in thread."""
    from cjs.auction.engine import run_auction  # noqa: PLC0415
    from cjs.report.builder import build_report  # noqa: PLC0415
    from cjs.ui.events import structured_error  # noqa: PLC0415

    pause_event = threading.Event()
    stop_event = threading.Event()
    pause_event.set()  # starts running

    app.state.pause_events[run_id] = pause_event
    app.state.stop_events[run_id] = stop_event

    try:
        for chunk in compiled.stream({}, thread_config):
            if stop_event.is_set():
                break
            pause_event.wait()
            if stop_event.is_set():
                break
            for node_name, update in chunk.items():
                _put_event(app, run_id, {
                    "type": "node_complete",
                    "node": node_name,
                    "update": _safe_update(update),
                })

        if stop_event.is_set():
            return

        snap = compiled.get_state(thread_config)
        final_state = snap.values

        _put_event(app, run_id, {"type": "node_start", "node": "auction"})
        verdict = run_auction(final_state, run_folder)
        build_report(run_folder, final_state, verdict, {})
        _put_event(app, run_id, {
            "type": "done",
            "winner": verdict["winner_video"],
            "report_url": f"/api/runs/{run_id}/report",
        })

    except Exception as exc:
        _put_event(app, run_id, structured_error(exc))
    finally:
        app.state.pause_events.pop(run_id, None)
        app.state.stop_events.pop(run_id, None)


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
        import sqlite3  # noqa: PLC0415

        from langchain_core.runnables import RunnableConfig  # noqa: PLC0415
        from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: PLC0415

        from cjs.graph.jury_graph import build_jury_graph  # noqa: PLC0415
        from cjs.graph.state import JuryState  # noqa: PLC0415
        from cjs.pipelines.brief_ingest import (  # noqa: PLC0415
            extract_brief_raw,
            generate_rubric,
            load_brand_rules_from_yaml,
            parse_brief,
        )
        from cjs.pipelines.video_analysis import analyze_video  # noqa: PLC0415
        from cjs.router.model_router import ModelRouter  # noqa: PLC0415
        from cjs.schemas.brand_rules import BrandRules  # noqa: PLC0415

        router = ModelRouter(
            run_id=run_id,
            run_folder=run_folder,
            config=config,
            emit=lambda e: _put_event(app, run_id, e),
        )
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

        # --- Build and compile graph ---
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
        conn = sqlite3.connect(str(checkpoints_db), check_same_thread=False)
        saver = SqliteSaver(conn=conn)
        compiled = build_jury_graph().compile(checkpointer=saver)
        thread_config: RunnableConfig = {
            "configurable": {
                "thread_id": run_id,
                "router": router,
                "strict_confidence": False,
                "auto_approve": True,
            }
        }

        compiled.update_state(thread_config, initial_state)
        app.state.compiled_refs[run_id] = (compiled, thread_config, run_folder, config)

        _stream_graph(app, run_id, compiled, thread_config, run_folder)

    except Exception as exc:
        from cjs.ui.events import structured_error as _se  # noqa: PLC0415
        _put_event(app, run_id, _se(exc))


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
        result = _config_holder[0]
        assert result is not None
        return result

    @asynccontextmanager
    async def _lifespan(app: FastAPI):
        app.state.queues = {}
        app.state.executor = ThreadPoolExecutor(max_workers=4)
        app.state.loop = asyncio.get_event_loop()
        app.state.pause_events = {}
        app.state.stop_events = {}
        app.state.compiled_refs = {}
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

    @app.post("/api/runs/{run_id}/control")
    async def control_run(run_id: str, body: dict) -> dict:
        action = body.get("action")

        if action == "pause":
            evt = app.state.pause_events.get(run_id)
            if evt:
                evt.clear()
            return {"status": "paused"}

        if action == "resume":
            evt = app.state.pause_events.get(run_id)
            if evt:
                evt.set()
            return {"status": "resumed"}

        if action == "undo":
            stop_evt = app.state.stop_events.get(run_id)
            if stop_evt:
                stop_evt.set()
            await asyncio.sleep(0.25)

            ref = app.state.compiled_refs.get(run_id)
            if not ref:
                raise HTTPException(status_code=404, detail="No active run to undo")

            compiled, thread_config, ref_run_folder, ref_config = ref

            try:
                history = list(compiled.get_state_history(thread_config))
            except Exception as exc:
                raise HTTPException(status_code=500, detail=f"Checkpoint error: {exc}") from exc

            if len(history) < 2:
                raise HTTPException(status_code=400, detail="Nothing to undo")

            prior = history[1]
            compiled.update_state(thread_config, prior.values)

            rewound_to = prior.next[0] if prior.next else "start"
            _put_event(app, run_id, {"type": "run_rewound", "to_node": rewound_to})

            from cjs.router.model_router import ModelRouter  # noqa: PLC0415
            new_router = ModelRouter(
                run_id=run_id,
                run_folder=ref_run_folder,
                config=ref_config,
                emit=lambda e: _put_event(app, run_id, e),
            )
            thread_config["configurable"]["router"] = new_router
            app.state.executor.submit(
                _stream_graph, app, run_id, compiled, thread_config, ref_run_folder
            )
            return {"status": "rewound", "to_node": rewound_to}

        raise HTTPException(status_code=400, detail=f"Unknown action: {action!r}")

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
