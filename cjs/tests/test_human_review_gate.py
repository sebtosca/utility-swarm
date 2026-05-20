from pathlib import Path
from typing import cast
from unittest import mock

import pytest

from cjs.escalation.human_review import (
    HumanReviewRejectedError,
    _compute_max_score_delta,
    _has_unresolved_flags,
    human_review_gate_node,
)
from cjs.graph.state import JuryState

_BASE_STATE: JuryState = cast(JuryState, {
    "run_id": "test_run",
    "brief": {},
    "rubric": {"weights": {"storytelling": 0.5, "message_clarity": 0.5}},
    "brand_rules": {},
    "video_dossiers": [],
    "initial_judgements": {},
    "consistency_report": {"flags": [], "checked_agents": [], "checked_videos": []},
    "final_judgements": {
        "agent_a": [
            {"video_path": "/run/input/ad1.mp4", "scores": {"storytelling": 8.0, "message_clarity": 7.0},
             "agent_name": "agent_a", "confidence": 70, "token_bid": 20, "flags": [],
             "notes": None, "strengths": [], "weaknesses": [], "evidence": [], "metric_comments": {}, "model_info": {}},
        ],
        "agent_b": [
            {"video_path": "/run/input/ad1.mp4", "scores": {"storytelling": 2.0, "message_clarity": 1.0},
             "agent_name": "agent_b", "confidence": 70, "token_bid": 20, "flags": [],
             "notes": None, "strengths": [], "weaknesses": [], "evidence": [], "metric_comments": {}, "model_info": {}},
        ],
    },
    "verdict": None,
})


def _make_config(tmp_path: Path, auto_approve: bool = False):
    router = mock.MagicMock()
    router._run_folder = tmp_path
    return {"configurable": {"thread_id": "t", "router": router, "auto_approve": auto_approve}}


def test_compute_max_score_delta_returns_zero_with_no_scores():
    state: JuryState = cast(JuryState, {**_BASE_STATE, "final_judgements": {}})
    assert _compute_max_score_delta(state) == 0.0


def test_compute_max_score_delta_single_agent_returns_zero():
    state: JuryState = cast(JuryState, {**_BASE_STATE, "final_judgements": {"agent_a": _BASE_STATE["final_judgements"]["agent_a"]}})
    assert _compute_max_score_delta(state) == 0.0


def test_compute_max_score_delta_two_agents_returns_diff():
    delta = _compute_max_score_delta(_BASE_STATE)
    assert abs(delta - 6.0) < 0.01


def test_has_unresolved_flags_empty():
    assert not _has_unresolved_flags(_BASE_STATE)


def test_has_unresolved_flags_with_flags():
    state: JuryState = cast(JuryState, {**_BASE_STATE, "consistency_report": {
        "flags": [{"agent": "a", "video": "v", "claim": "c",
                   "contradicting_evidence": "e", "classification": "FACTUAL_CONTRADICTION"}],
        "checked_agents": [], "checked_videos": [],
    }})
    assert _has_unresolved_flags(state)


def test_gate_no_escalation_returns_empty(tmp_path):
    state: JuryState = cast(JuryState, {**_BASE_STATE, "final_judgements": {
        "agent_a": [{"video_path": "/r/ad1.mp4", "scores": {"storytelling": 7.0, "message_clarity": 7.0},
                     "agent_name": "agent_a", "confidence": 70, "token_bid": 20, "flags": [],
                     "notes": None, "strengths": [], "weaknesses": [], "evidence": [], "metric_comments": {}, "model_info": {}}],
        "agent_b": [{"video_path": "/r/ad1.mp4", "scores": {"storytelling": 7.5, "message_clarity": 7.0},
                     "agent_name": "agent_b", "confidence": 70, "token_bid": 20, "flags": [],
                     "notes": None, "strengths": [], "weaknesses": [], "evidence": [], "metric_comments": {}, "model_info": {}}],
    }})
    result = human_review_gate_node(state, _make_config(tmp_path))
    assert result == {}


def test_gate_approved_returns_empty(tmp_path):
    with mock.patch("cjs.escalation.human_review.typer.confirm", return_value=True), \
         mock.patch("rich.console.Console"):
        result = human_review_gate_node(_BASE_STATE, _make_config(tmp_path))
    assert result == {}


def test_gate_rejected_raises(tmp_path):
    with mock.patch("cjs.escalation.human_review.typer.confirm", return_value=False), \
         mock.patch("rich.console.Console"):
        with pytest.raises(HumanReviewRejectedError):
            human_review_gate_node(_BASE_STATE, _make_config(tmp_path))


def test_gate_auto_approve_skips_prompt(tmp_path):
    with mock.patch("cjs.escalation.human_review.typer.confirm") as mock_confirm, \
         mock.patch("rich.console.Console"):
        result = human_review_gate_node(_BASE_STATE, _make_config(tmp_path, auto_approve=True))
    mock_confirm.assert_not_called()
    assert result == {}


def test_gate_auto_approve_writes_approved_event(tmp_path):
    with mock.patch("cjs.escalation.human_review.typer.confirm"), \
         mock.patch("rich.console.Console"):
        human_review_gate_node(_BASE_STATE, _make_config(tmp_path, auto_approve=True))
    import json
    events = [json.loads(line) for line in (tmp_path / "escalations.jsonl").read_text().splitlines() if line]
    types = [e["type"] for e in events]
    assert "human_review_approved" in types
