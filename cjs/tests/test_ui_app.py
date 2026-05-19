"""
Tests for cjs.ui.app — FastAPI jury room.

All tests use TestClient (sync). The config is injected via create_app(config_override=...)
so no disk config is needed.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cjs.config import Settings


def _make_config(runs_dir: Path) -> Settings:
    """Settings pointing at a tmp runs directory."""
    config = Settings()
    config.run.out_dir = str(runs_dir)
    return config


async def _make_seeded_queue(event: dict) -> asyncio.Queue:
    """Create an asyncio.Queue pre-loaded with one event (must run on server loop)."""
    q: asyncio.Queue = asyncio.Queue()
    await q.put(event)
    return q


# ── 1. Root returns HTML ──────────────────────────────────────────────────────

def test_root_returns_html(tmp_path):
    from cjs.ui.app import create_app

    app = create_app(config_override=_make_config(tmp_path))
    with TestClient(app) as client:
        resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Jury Room" in resp.text


# ── 2. List runs — empty directory ───────────────────────────────────────────

def test_list_runs_empty(tmp_path):
    from cjs.ui.app import create_app

    app = create_app(config_override=_make_config(tmp_path))
    with TestClient(app) as client:
        resp = client.get("/api/runs")
    assert resp.status_code == 200
    assert resp.json() == []


# ── 3. List runs — two run folders ───────────────────────────────────────────

def test_list_runs_with_runs(tmp_path):
    from cjs.ui.app import create_app

    (tmp_path / "run_001").mkdir()
    (tmp_path / "run_002").mkdir()
    app = create_app(config_override=_make_config(tmp_path))
    with TestClient(app) as client:
        resp = client.get("/api/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    run_ids = {item["run_id"] for item in data}
    assert run_ids == {"run_001", "run_002"}


# ── 4. Get run — not found ────────────────────────────────────────────────────

def test_get_run_not_found(tmp_path):
    from cjs.ui.app import create_app

    app = create_app(config_override=_make_config(tmp_path))
    with TestClient(app) as client:
        resp = client.get("/api/runs/nonexistent")
    assert resp.status_code == 404


# ── 5. Get run — no verdict yet ───────────────────────────────────────────────

def test_get_run_no_verdict(tmp_path):
    from cjs.ui.app import create_app

    (tmp_path / "run_001").mkdir()
    app = create_app(config_override=_make_config(tmp_path))
    with TestClient(app) as client:
        resp = client.get("/api/runs/run_001")
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


# ── 6. Get run — verdict present ─────────────────────────────────────────────

def test_get_run_with_verdict(tmp_path):
    from cjs.ui.app import create_app

    results_dir = tmp_path / "run_001" / "results"
    results_dir.mkdir(parents=True)
    verdict = {"winner_video": "ad1.mp4", "ranking": ["ad1.mp4", "ad2.mp4"]}
    (results_dir / "verdict.json").write_text(json.dumps(verdict))

    app = create_app(config_override=_make_config(tmp_path))
    with TestClient(app) as client:
        resp = client.get("/api/runs/run_001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "complete"
    assert data["winner"] == "ad1.mp4"


# ── 7. Report — not found ─────────────────────────────────────────────────────

def test_report_not_found(tmp_path):
    from cjs.ui.app import create_app

    (tmp_path / "run_001").mkdir()
    app = create_app(config_override=_make_config(tmp_path))
    with TestClient(app) as client:
        resp = client.get("/api/runs/run_001/report")
    assert resp.status_code == 404


# ── 8. Report — returns HTML ──────────────────────────────────────────────────

def test_report_returns_html(tmp_path):
    from cjs.ui.app import create_app

    results_dir = tmp_path / "run_001" / "results"
    results_dir.mkdir(parents=True)
    (results_dir / "report.html").write_text("<html><body>Test Report</body></html>")

    app = create_app(config_override=_make_config(tmp_path))
    with TestClient(app) as client:
        resp = client.get("/api/runs/run_001/report")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


# ── 9. Start run — missing brief → 422 ───────────────────────────────────────

def test_start_run_missing_brief(tmp_path):
    from cjs.ui.app import create_app

    app = create_app(config_override=_make_config(tmp_path))
    with TestClient(app) as client:
        # Send videos but no brief
        resp = client.post(
            "/api/run",
            files={"videos": ("ad1.mp4", b"fake-video-bytes", "video/mp4")},
        )
    assert resp.status_code == 422


# ── 10. WebSocket — receives pre-seeded done event ───────────────────────────

def test_websocket_receives_done_event(tmp_path):
    from cjs.ui.app import create_app

    app = create_app(config_override=_make_config(tmp_path))
    run_id = "ws_test_run"

    with TestClient(app) as client:
        # Seed the queue on the server's event loop before connecting
        loop: asyncio.AbstractEventLoop = app.state.loop
        future = asyncio.run_coroutine_threadsafe(
            _make_seeded_queue({"type": "done", "winner": "ad1.mp4", "report_url": f"/api/runs/{run_id}/report"}),
            loop,
        )
        seeded_queue = future.result(timeout=5)
        app.state.queues[run_id] = seeded_queue

        with client.websocket_connect(f"/ws/{run_id}") as ws:
            event = ws.receive_json()

    assert event["type"] == "done"
    assert event["winner"] == "ad1.mp4"
