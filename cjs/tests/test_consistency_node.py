import json
from typing import Any
from unittest.mock import MagicMock

from langchain_core.runnables import RunnableConfig

from cjs.graph.nodes.consistency import consistency_checker_node
from cjs.graph.state import JuryState
from cjs.router.model_router import RouterResult

DOSSIER = {
    "video_path": "/runs/test/input/videos/ad1.mp4",
    "duration_sec": 30.0, "transcript": "Buy now.",
    "hook_summary": "Bold.", "scenes": [], "pacing": "fast",
    "logo_first_appearance_sec": 2.0, "cta_detected": True,
    "cta_text": "Buy now", "frames_analyzed": 6, "metadata": {},
}

JUDGEMENT_WITH_FACTUAL_ERROR: dict[str, Any] = {
    "agent_name": "creative_strategist", "agent_role": None,
    "video_path": "ad1.mp4",
    "scores": {"storytelling": 8.0}, "strengths": [], "weaknesses": [],
    "evidence": [], "metric_comments": {},
    "confidence": 80, "token_bid": 100, "flags": [],
    "notes": "No CTA was detected in this ad.",  # contradicts dossier cta_detected=True
    "model_info": {},
}

STATE: JuryState = {
    "run_id": "test", "brief": {}, "rubric": {}, "brand_rules": {},
    "video_dossiers": [DOSSIER],
    "initial_judgements": {"creative_strategist": [JUDGEMENT_WITH_FACTUAL_ERROR]},
    "consistency_report": None, "final_judgements": {}, "verdict": None,
}

VALID_REPORT = {
    "flags": [{
        "agent": "creative_strategist",
        "video": "ad1.mp4",
        "claim": "No CTA was detected in this ad.",
        "contradicting_evidence": "dossier.cta_detected=True, cta_text='Buy now'",
        "classification": "FACTUAL_CONTRADICTION",
    }],
    "checked_agents": ["creative_strategist"],
    "checked_videos": ["ad1.mp4"],
}


def make_mock_router(response: dict) -> MagicMock:
    router = MagicMock()
    router.call_structured.return_value = RouterResult(
        content=json.dumps(response),
        tokens_in=50, tokens_out=100, latency_ms=300.0, model="claude-sonnet-4-6",
    )
    return router


def test_consistency_checker_returns_report():
    router = make_mock_router(VALID_REPORT)
    config: RunnableConfig = {"configurable": {"router": router}}
    result = consistency_checker_node(STATE, config)
    assert "consistency_report" in result
    report = result["consistency_report"]
    assert len(report["flags"]) == 1
    assert report["flags"][0]["classification"] == "FACTUAL_CONTRADICTION"


def test_consistency_checker_uses_call_structured():
    router = make_mock_router(VALID_REPORT)
    config: RunnableConfig = {"configurable": {"router": router}}
    consistency_checker_node(STATE, config)
    router.call_structured.assert_called_once()


def test_consistency_checker_no_flags_when_clean():
    clean_report = {"flags": [], "checked_agents": ["creative_strategist"], "checked_videos": ["ad1.mp4"]}
    router = make_mock_router(clean_report)
    config: RunnableConfig = {"configurable": {"router": router}}
    result = consistency_checker_node(STATE, config)
    assert result["consistency_report"]["flags"] == []
