import json
from unittest.mock import MagicMock

from cjs.graph.nodes.deliberation import deliberation_round_node
from cjs.router.model_router import RouterResult

JUDGEMENT = {
    "agent_name": "creative_strategist", "agent_role": None,
    "video_path": "ad1.mp4", "scores": {"storytelling": 8.0},
    "strengths": [], "weaknesses": [], "evidence": [], "metric_comments": {},
    "confidence": 80, "token_bid": 100, "flags": [], "notes": "Good hook.", "model_info": {},
}

CONSISTENCY_REPORT_WITH_FLAG = {
    "flags": [{
        "agent": "brand_compliance",
        "video": "ad1.mp4",
        "claim": "No CTA detected.",
        "contradicting_evidence": "dossier.cta_detected=True",
        "classification": "FACTUAL_CONTRADICTION",
    }],
    "checked_agents": ["creative_strategist", "brand_compliance"],
    "checked_videos": ["ad1.mp4"],
}

ALL_AGENTS = ["creative_strategist", "brand_compliance", "audience_psychology",
              "performance_marketer", "storytelling_critic"]

STATE = {
    "run_id": "test", "brief": {}, "rubric": {}, "brand_rules": {},
    "video_dossiers": [{"video_path": "/runs/test/input/videos/ad1.mp4", "duration_sec": 30.0,
                        "transcript": "", "hook_summary": "", "scenes": [], "pacing": "fast",
                        "logo_first_appearance_sec": None, "cta_detected": False, "cta_text": None,
                        "frames_analyzed": 0, "metadata": {}}],
    "initial_judgements": {agent: [JUDGEMENT.copy()] for agent in ALL_AGENTS},
    "consistency_report": CONSISTENCY_REPORT_WITH_FLAG,
    "final_judgements": {}, "verdict": None,
}


def make_mock_router(revised_judgement: dict | None = None) -> MagicMock:
    j = revised_judgement or JUDGEMENT
    router = MagicMock()
    router.call_structured.return_value = RouterResult(
        content=json.dumps({"judgements": [j]}),
        tokens_in=50, tokens_out=100, latency_ms=200.0, model="claude-sonnet-4-6",
    )
    return router


def test_deliberation_calls_all_five_agents():
    router = make_mock_router()
    config = {"configurable": {"router": router}}
    deliberation_round_node(STATE, config)
    assert router.call_structured.call_count == 5


def test_deliberation_returns_final_judgements_for_all_agents():
    router = make_mock_router()
    config = {"configurable": {"router": router}}
    result = deliberation_round_node(STATE, config)
    assert set(result["final_judgements"].keys()) == set(ALL_AGENTS)


def test_deliberation_flagged_agent_prompt_contains_flag():
    router = make_mock_router()
    config = {"configurable": {"router": router}}
    deliberation_round_node(STATE, config)
    # brand_compliance was flagged — its call should include flag info
    calls = router.call_structured.call_args_list
    # calls are in order of ALL_AGENTS; brand_compliance is index 1
    bc_call_user_prompt = calls[1].kwargs.get("user") or calls[1].args[1]
    assert "No CTA detected" in bc_call_user_prompt


def test_deliberation_unflagged_agent_prompt_has_no_flags_section():
    router = make_mock_router()
    config = {"configurable": {"router": router}}
    deliberation_round_node(STATE, config)
    calls = router.call_structured.call_args_list
    # creative_strategist is index 0, has no flags
    cs_call_user_prompt = calls[0].kwargs.get("user") or calls[0].args[1]
    assert "Flags directed at you" not in cs_call_user_prompt
