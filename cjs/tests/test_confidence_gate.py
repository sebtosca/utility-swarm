import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from cjs.escalation.confidence_gate import (
    CONFIDENCE_THRESHOLD,
    LowConfidenceError,
    confidence_gate_node,
)

_BASE_STATE = {
    "run_id": "test_run",
    "brief": {}, "rubric": {}, "brand_rules": {},
    "video_dossiers": [], "initial_judgements": {},
    "consistency_report": None, "final_judgements": {},
    "verdict": {"winner_video": "ad1.mp4", "winner_rationale": "Best.",
                "ranking": ["ad1.mp4"], "per_video_notes": {}, "confidence": 0.5,
                "flags_resolved": []},
}


def _make_config(tmp_path: Path, strict: bool = False):
    router = mock.MagicMock()
    router._run_folder = tmp_path
    return {"configurable": {"thread_id": "t", "router": router, "strict_confidence": strict}}


def test_high_confidence_passes_through(tmp_path):
    state = {**_BASE_STATE, "verdict": {**_BASE_STATE["verdict"], "confidence": 0.9}}
    result = confidence_gate_node(state, _make_config(tmp_path))
    assert result == {}
    assert not (tmp_path / "metrics.json").exists()


def test_advisory_writes_metrics(tmp_path):
    result = confidence_gate_node(_BASE_STATE, _make_config(tmp_path, strict=False))
    assert result == {}
    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert metrics["verdict_confidence"] == "low"
    assert abs(metrics["verdict_confidence_value"] - 0.5) < 0.001


def test_advisory_writes_escalation_event(tmp_path):
    confidence_gate_node(_BASE_STATE, _make_config(tmp_path, strict=False))
    line = (tmp_path / "escalations.jsonl").read_text().strip()
    entry = json.loads(line)
    assert entry["type"] == "low_confidence_verdict"
    assert entry["node"] == "confidence_gate"
    assert abs(entry["confidence"] - 0.5) < 0.001


def test_advisory_merges_existing_metrics(tmp_path):
    (tmp_path / "metrics.json").write_text(json.dumps({"previous_key": "value"}))
    confidence_gate_node(_BASE_STATE, _make_config(tmp_path, strict=False))
    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert metrics["previous_key"] == "value"
    assert metrics["verdict_confidence"] == "low"


def test_strict_raises_low_confidence_error(tmp_path):
    with mock.patch("rich.console.Console"), \
         pytest.raises(LowConfidenceError, match="below threshold"):
        confidence_gate_node(_BASE_STATE, _make_config(tmp_path, strict=True))
