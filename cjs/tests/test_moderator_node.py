import json
from typing import Any
from unittest.mock import MagicMock

from cjs.graph.nodes.moderator import moderator_node
from cjs.router.model_router import RouterResult
from cjs.schemas.verdict import Verdict

JUDGEMENT: dict[str, Any] = {
    "agent_name": "creative_strategist", "agent_role": None,
    "video_path": "ad1.mp4", "scores": {"storytelling": 8.0},
    "strengths": [], "weaknesses": [], "evidence": [], "metric_comments": {},
    "confidence": 80, "token_bid": 100, "flags": [], "notes": "Strong hook.", "model_info": {},
}

ALL_AGENTS = ["creative_strategist", "brand_compliance", "audience_psychology",
              "performance_marketer", "storytelling_critic"]

STATE: dict[str, Any] = {
    "run_id": "test",
    "brief": {
        "brand": "TestBrand", "objective": "Drive awareness", "platform": "YouTube",
        "audience": "18-34", "tone": "energetic", "key_message": "Be bold",
        "primary_kpi": "awareness", "emotional_territory": None,
        "mandatory": [], "forbidden": [], "kpi_priority": {}, "constraints": {},
    },
    "rubric": {"name": "test", "description": "", "weights": {"storytelling": 1.0}, "hard_gates": {}},
    "brand_rules": {},
    "video_dossiers": [{"video_path": "/runs/test/input/videos/ad1.mp4", "duration_sec": 30.0,
                        "transcript": "", "hook_summary": "", "scenes": [], "pacing": "fast",
                        "logo_first_appearance_sec": None, "cta_detected": False, "cta_text": None,
                        "frames_analyzed": 0, "metadata": {}}],
    "initial_judgements": {},
    "consistency_report": {"flags": [], "checked_agents": [], "checked_videos": []},
    "final_judgements": {agent: [JUDGEMENT.copy()] for agent in ALL_AGENTS},
    "verdict": None,
}

VALID_VERDICT = {
    "winner_video": "ad1.mp4",
    "winner_rationale": "Strongest creative concept with clear CTA.",
    "ranking": ["ad1.mp4"],
    "per_video_notes": {"ad1.mp4": "Best overall."},
    "confidence": 0.87,
    "flags_resolved": [],
}


def make_mock_router(verdict_dict: dict[str, Any]) -> MagicMock:
    router = MagicMock()
    router.call_extended_thinking.return_value = RouterResult(
        content=json.dumps(verdict_dict),
        tokens_in=500, tokens_out=1000, latency_ms=2000.0, model="claude-opus-4-7",
        thinking="<thinking>deliberation...</thinking>",
    )
    return router


def test_moderator_returns_valid_verdict() -> None:
    router = make_mock_router(VALID_VERDICT)
    config = {"configurable": {"router": router}}  # type: ignore[assignment]
    result = moderator_node(STATE, config)  # type: ignore[arg-type]
    assert "verdict" in result
    verdict = Verdict(**result["verdict"])
    assert verdict.winner_video == "ad1.mp4"
    assert 0 <= verdict.confidence <= 1


def test_moderator_uses_extended_thinking() -> None:
    router = make_mock_router(VALID_VERDICT)
    config = {"configurable": {"router": router}}  # type: ignore[assignment]
    moderator_node(STATE, config)  # type: ignore[arg-type]
    router.call_extended_thinking.assert_called_once()


def test_moderator_includes_winner_video_in_ranking() -> None:
    router = make_mock_router(VALID_VERDICT)
    config = {"configurable": {"router": router}}  # type: ignore[assignment]
    result = moderator_node(STATE, config)  # type: ignore[arg-type]
    verdict = Verdict(**result["verdict"])
    assert verdict.winner_video in verdict.ranking
