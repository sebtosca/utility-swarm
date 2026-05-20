from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from cjs.observability.langsmith import (
    build_run_config,
    invoke_with_tracing,
    tracing_enabled,
    write_langsmith_url,
)


def test_tracing_disabled_when_no_env(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    assert tracing_enabled() is False


def test_tracing_disabled_when_only_tracing_v2_set(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)
    assert tracing_enabled() is False


def test_tracing_disabled_when_only_api_key_set(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls__test")
    assert tracing_enabled() is False


def test_tracing_enabled_when_both_vars_set(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls__test")
    assert tracing_enabled() is True


def test_build_run_config_structure():
    cfg = build_run_config(run_id="r1", video_count=3)
    assert cfg["metadata"]["cjs_run_id"] == "r1"
    assert cfg["metadata"]["video_count"] == 3
    assert "creative-jury-swarm" in cfg["tags"]


def test_invoke_with_tracing_no_tracing_calls_invoke_directly(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    compiled = MagicMock()
    compiled.invoke.return_value = {"verdict": {}}
    config = {"configurable": {"thread_id": "r1"}}

    result, url = invoke_with_tracing(compiled, {"state": 1}, config, "r1", 2)

    compiled.invoke.assert_called_once_with({"state": 1}, config=config)
    assert result == {"verdict": {}}
    assert url is None


def test_invoke_with_tracing_no_tracing_returns_none_url(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    compiled = MagicMock()
    compiled.invoke.return_value = {}
    _, url = invoke_with_tracing(compiled, {}, {}, "r1", 1)
    assert url is None


def test_invoke_with_tracing_enabled_wraps_invoke(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls__test")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "test-project")

    compiled = MagicMock()
    compiled.invoke.return_value = {"verdict": {"winner_video": "ad1.mp4"}}

    fake_rt = MagicMock()
    fake_trace_cm = MagicMock()
    fake_trace_cm.__enter__ = MagicMock(return_value=fake_rt)
    fake_trace_cm.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.get_run_url.return_value = "https://smith.langchain.com/o/x/runs/abc"

    with patch("cjs.observability.langsmith.ls_trace", return_value=fake_trace_cm) as mock_trace, \
         patch("cjs.observability.langsmith.Client", return_value=mock_client):
        result, url = invoke_with_tracing(
            compiled, {"s": 1}, {"configurable": {}}, "r1", 3
        )

    assert result == {"verdict": {"winner_video": "ad1.mp4"}}
    assert url == "https://smith.langchain.com/o/x/runs/abc"
    mock_trace.assert_called_once()
    compiled.invoke.assert_called_once()


def test_invoke_with_tracing_url_error_returns_none(monkeypatch):
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "ls__test")

    compiled = MagicMock()
    compiled.invoke.return_value = {}

    fake_trace_cm = MagicMock()
    fake_trace_cm.__enter__ = MagicMock(return_value=MagicMock())
    fake_trace_cm.__exit__ = MagicMock(return_value=False)

    mock_client = MagicMock()
    mock_client.get_run_url.side_effect = Exception("network error")

    with patch("cjs.observability.langsmith.ls_trace", return_value=fake_trace_cm), \
         patch("cjs.observability.langsmith.Client", return_value=mock_client):
        _, url = invoke_with_tracing(compiled, {}, {}, "r1", 1)

    assert url is None


def test_write_langsmith_url_creates_file(tmp_path):
    metrics_path = tmp_path / "results" / "metrics.json"
    metrics_path.parent.mkdir()
    write_langsmith_url(metrics_path, "https://smith.langchain.com/runs/x")
    data = json.loads(metrics_path.read_text())
    assert data["langsmith_url"] == "https://smith.langchain.com/runs/x"


def test_write_langsmith_url_merges_existing(tmp_path):
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps({"verdict_confidence": "high", "total_tokens": 5000}))
    write_langsmith_url(metrics_path, "https://smith.langchain.com/runs/y")
    data = json.loads(metrics_path.read_text())
    assert data["verdict_confidence"] == "high"
    assert data["total_tokens"] == 5000
    assert data["langsmith_url"] == "https://smith.langchain.com/runs/y"


def test_write_langsmith_url_overwrites_existing_url(tmp_path):
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps({"langsmith_url": "old_url"}))
    write_langsmith_url(metrics_path, "new_url")
    data = json.loads(metrics_path.read_text())
    assert data["langsmith_url"] == "new_url"
