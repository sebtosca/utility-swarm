from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from cjs.config import Settings
from cjs.router.model_router import CIRCUIT_THRESHOLD, FALLBACK_MODEL, ModelRouter, RouterResult

# ---------- helpers ----------

def _make_router(tmp_path: Path) -> ModelRouter:
    config = Settings()
    return ModelRouter(run_id="test_run", run_folder=tmp_path, config=config)


def _fake_response(text: str = "ok", model: str = "claude-sonnet-4-6") -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.content = [block]
    resp.model = model
    resp.usage.input_tokens = 10
    resp.usage.output_tokens = 5
    return resp


# ---------- circuit breaker ----------

def test_active_model_returns_preferred_below_threshold(tmp_path):
    router = _make_router(tmp_path)
    preferred = router._config.models.text
    assert router._active_model(preferred) == preferred


def test_active_model_returns_fallback_at_threshold(tmp_path):
    router = _make_router(tmp_path)
    preferred = router._config.models.text
    for _ in range(CIRCUIT_THRESHOLD):
        router._record_failure(preferred)
    assert router._active_model(preferred) == FALLBACK_MODEL


def test_active_model_returns_preferred_below_threshold_after_partial_failures(tmp_path):
    router = _make_router(tmp_path)
    preferred = router._config.models.text
    for _ in range(CIRCUIT_THRESHOLD - 1):
        router._record_failure(preferred)
    assert router._active_model(preferred) == preferred


def test_record_success_resets_failure_count(tmp_path):
    router = _make_router(tmp_path)
    preferred = router._config.models.text
    for _ in range(CIRCUIT_THRESHOLD):
        router._record_failure(preferred)
    router._record_success(preferred)
    assert router._active_model(preferred) == preferred


def test_record_failure_increments_count(tmp_path):
    router = _make_router(tmp_path)
    preferred = router._config.models.text
    router._record_failure(preferred)
    router._record_failure(preferred)
    assert router._failures[preferred] == 2


# ---------- call_text ----------

def test_call_text_returns_router_result(tmp_path):
    router = _make_router(tmp_path)
    router._client.messages.create = MagicMock(return_value=_fake_response("hello"))  # type: ignore[method-assign]
    result = router.call_text(system="sys", user="hi", node="test_node")
    assert isinstance(result, RouterResult)
    assert result.content == "hello"


def test_call_text_uses_configured_text_model(tmp_path):
    router = _make_router(tmp_path)
    router._client.messages.create = MagicMock(return_value=_fake_response())  # type: ignore[method-assign]
    router.call_text(system="s", user="u", node="n")
    kwargs = router._client.messages.create.call_args.kwargs
    assert kwargs["model"] == router._config.models.text


def test_call_text_writes_audit_entry(tmp_path):
    router = _make_router(tmp_path)
    router._client.messages.create = MagicMock(return_value=_fake_response())  # type: ignore[method-assign]
    router.call_text(system="s", user="u", node="scoring", agent="creative_strategist")
    audit_path = tmp_path / "audit.jsonl"
    assert audit_path.exists()
    entry = json.loads(audit_path.read_text().splitlines()[0])
    assert entry["node"] == "scoring"
    assert entry["agent"] == "creative_strategist"


# ---------- call_extended_thinking ----------

def test_call_extended_thinking_passes_thinking_flag(tmp_path):
    router = _make_router(tmp_path)
    router._client.messages.create = MagicMock(return_value=_fake_response())  # type: ignore[method-assign]
    router.call_extended_thinking(system="s", user="u", node="moderator")
    kwargs = router._client.messages.create.call_args.kwargs
    assert kwargs.get("thinking", {}).get("type") == "enabled"


def test_call_extended_thinking_uses_extended_thinking_model(tmp_path):
    router = _make_router(tmp_path)
    router._client.messages.create = MagicMock(return_value=_fake_response())  # type: ignore[method-assign]
    router.call_extended_thinking(system="s", user="u", node="moderator")
    kwargs = router._client.messages.create.call_args.kwargs
    assert kwargs["model"] == router._config.models.extended_thinking


def test_call_extended_thinking_captures_thinking_block(tmp_path):
    router = _make_router(tmp_path)
    thinking_block = MagicMock()
    thinking_block.type = "thinking"
    thinking_block.thinking = "step by step"
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "conclusion"
    resp = MagicMock()
    resp.content = [thinking_block, text_block]
    resp.model = "claude-opus-4-7"
    resp.usage.input_tokens = 20
    resp.usage.output_tokens = 10
    router._client.messages.create = MagicMock(return_value=resp)  # type: ignore[method-assign]
    result = router.call_extended_thinking(system="s", user="u", node="moderator")
    assert result.thinking == "step by step"
    assert result.content == "conclusion"


# ---------- call_structured ----------

def test_call_structured_builds_tool_definition(tmp_path):
    router = _make_router(tmp_path)
    router._client.messages.create = MagicMock(return_value=_fake_response())  # type: ignore[method-assign]
    schema = {"type": "object", "properties": {"score": {"type": "number"}}}
    router.call_structured(system="s", user="u", node="n", schema=schema, schema_name="ScoreOutput")
    kwargs = router._client.messages.create.call_args.kwargs
    assert kwargs["tools"][0]["name"] == "ScoreOutput"
    assert kwargs["tool_choice"] == {"type": "tool", "name": "ScoreOutput"}


def test_call_structured_tool_use_block_becomes_content(tmp_path):
    router = _make_router(tmp_path)
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = {"score": 8.5}
    resp = MagicMock()
    resp.content = [tool_block]
    resp.model = "claude-sonnet-4-6"
    resp.usage.input_tokens = 10
    resp.usage.output_tokens = 5
    router._client.messages.create = MagicMock(return_value=resp)  # type: ignore[method-assign]
    result = router.call_structured(
        system="s", user="u", node="n",
        schema={}, schema_name="Out",
    )
    assert json.loads(result.content) == {"score": 8.5}


# ---------- failure handling ----------

def test_dispatch_records_failure_and_reraises(tmp_path):
    router = _make_router(tmp_path)
    preferred = router._config.models.text
    router._client.messages.create = MagicMock(  # type: ignore[method-assign]
        side_effect=anthropic.APIError("boom", request=MagicMock(), body=None)
    )
    with pytest.raises(anthropic.APIError):
        router.call_text(system="s", user="u", node="n")
    assert router._failures.get(preferred, 0) >= 1


def test_dispatch_writes_audit_entry_on_failure(tmp_path):
    router = _make_router(tmp_path)
    router._client.messages.create = MagicMock(  # type: ignore[method-assign]
        side_effect=anthropic.APIError("boom", request=MagicMock(), body=None)
    )
    with pytest.raises(anthropic.APIError):
        router.call_text(system="s", user="u", node="scoring")
    audit_path = tmp_path / "audit.jsonl"
    assert audit_path.exists()
    entry = json.loads(audit_path.read_text().splitlines()[0])
    assert entry["error"] == "boom"


def test_dispatch_writes_escalation_when_circuit_open(tmp_path):
    router = _make_router(tmp_path)
    preferred = router._config.models.text
    # Force circuit open
    for _ in range(CIRCUIT_THRESHOLD):
        router._record_failure(preferred)
    router._client.messages.create = MagicMock(return_value=_fake_response(model=FALLBACK_MODEL))  # type: ignore[method-assign]
    router.call_text(system="s", user="u", node="scoring")
    escalation_path = tmp_path / "escalations.jsonl"
    assert escalation_path.exists()
    event = json.loads(escalation_path.read_text().splitlines()[0])
    assert event["type"] == "model_fallback"
    assert event["from_model"] == preferred
    assert event["to_model"] == FALLBACK_MODEL


def test_dispatch_does_not_write_escalation_when_preferred_used(tmp_path):
    router = _make_router(tmp_path)
    router._client.messages.create = MagicMock(return_value=_fake_response())  # type: ignore[method-assign]
    router.call_text(system="s", user="u", node="scoring")
    escalation_path = tmp_path / "escalations.jsonl"
    assert not escalation_path.exists()


# ---------- _encode_image ----------

def test_encode_image_jpeg(tmp_path):
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    block = ModelRouter._encode_image(img)
    assert block["source"]["media_type"] == "image/jpeg"
    assert base64.standard_b64decode(block["source"]["data"]) == b"\xff\xd8\xff"


def test_encode_image_png(tmp_path):
    img = tmp_path / "frame.png"
    img.write_bytes(b"\x89PNG")
    block = ModelRouter._encode_image(img)
    assert block["source"]["media_type"] == "image/png"


def test_encode_image_unknown_extension_defaults_to_jpeg(tmp_path):
    img = tmp_path / "frame.bmp"
    img.write_bytes(b"BM")
    block = ModelRouter._encode_image(img)
    assert block["source"]["media_type"] == "image/jpeg"


# ---------- retry behaviour ----------

def test_call_with_retry_retries_on_api_error(tmp_path):
    router = _make_router(tmp_path)
    call_count = 0

    def flaky(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise anthropic.APIError("transient", request=MagicMock(), body=None)
        return _fake_response()

    router._client.messages.create = flaky  # type: ignore[method-assign]
    # Patch wait to avoid sleeping in tests
    with patch("cjs.router.model_router.wait_exponential", return_value=MagicMock(return_value=0)):
        result = router._call_with_retry(
            system="s", user="u", model="claude-sonnet-4-6",
            extra_content=[], thinking=False,
        )
    assert result.content == "ok"
    assert call_count == 3


def test_call_with_retry_reraises_after_max_attempts(tmp_path):
    router = _make_router(tmp_path)
    router._client.messages.create = MagicMock(  # type: ignore[method-assign]
        side_effect=anthropic.APIError("permanent", request=MagicMock(), body=None)
    )
    with patch("cjs.router.model_router.wait_exponential", return_value=MagicMock(return_value=0)):
        with pytest.raises(anthropic.APIError):
            router._call_with_retry(
                system="s", user="u", model="claude-sonnet-4-6",
                extra_content=[], thinking=False,
            )


# ── emit callback ──────────────────────────────────────────────────────────────

def test_emit_called_with_start_and_complete(tmp_path):
    emitted: list[dict] = []
    router = ModelRouter(
        run_id="test_run", run_folder=tmp_path,
        config=Settings(), emit=emitted.append,
    )
    fake_result = RouterResult(
        content="hello", tokens_in=10, tokens_out=5, latency_ms=0.0, model="claude-sonnet-4-6"
    )
    with patch.object(router, "_call_with_retry", return_value=fake_result):
        router.call_text(system="s", user="u", node="test_node", agent="test_agent")

    types = [e["type"] for e in emitted]
    assert types == ["llm_call_start", "llm_call_complete"]
    assert emitted[0]["node"] == "test_node"
    assert emitted[0]["agent"] == "test_agent"
    assert emitted[1]["tokens_in"] == 10
    assert emitted[1]["latency_ms"] >= 0


def test_emit_not_required(tmp_path):
    router = ModelRouter(run_id="test_run", run_folder=tmp_path, config=Settings())
    fake_result = RouterResult(
        content="ok", tokens_in=5, tokens_out=2, latency_ms=0.0, model="claude-sonnet-4-6"
    )
    with patch.object(router, "_call_with_retry", return_value=fake_result):
        result = router.call_text(system="s", user="u", node="n")
    assert result.content == "ok"


def test_emit_receives_thinking_on_extended_call(tmp_path):
    emitted: list[dict] = []
    router = ModelRouter(
        run_id="test_run", run_folder=tmp_path,
        config=Settings(), emit=emitted.append,
    )
    with patch.object(
        router, "_call_with_retry",
        return_value=RouterResult(
            content="verdict", tokens_in=500, tokens_out=100,
            latency_ms=0.0, model="claude-opus-4-7",
            thinking="Step 1: review scores",
        ),
    ):
        router.call_extended_thinking(system="s", user="u", node="moderator_node")

    complete = next(e for e in emitted if e["type"] == "llm_call_complete")
    assert complete["thinking"] == "Step 1: review scores"
