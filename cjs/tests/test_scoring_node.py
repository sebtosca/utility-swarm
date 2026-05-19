import json
from unittest.mock import MagicMock

import pytest

from cjs.graph.nodes.scoring import (
    AgentScoringError,
    _run_scoring_agent,
    audience_psychology_node,
    brand_compliance_node,
    creative_strategist_node,
    performance_marketer_node,
    storytelling_critic_node,
)
from cjs.graph.state import JuryState

MINIMAL_STATE: JuryState = {
    "run_id": "test_run",
    "brief": {
        "brand": "TestBrand", "objective": "Drive awareness", "platform": "YouTube",
        "audience": "18-34 urban", "tone": "energetic", "key_message": "Be bold",
        "primary_kpi": "awareness", "emotional_territory": "excitement",
        "mandatory": ["logo visible by 3s"], "forbidden": ["competitor names"],
        "kpi_priority": {}, "constraints": {},
    },
    "rubric": {
        "name": "test", "description": "test rubric",
        "weights": {"storytelling": 0.5, "message_clarity": 0.5}, "hard_gates": {},
    },
    "brand_rules": {
        "brand_name": "TestBrand", "mandatory_elements": [], "forbidden_elements": [],
        "tone_keywords": [], "approved_claims": [], "prohibited_claims": [],
        "logo_visible_by_sec": 3.0, "disclaimer_required": False, "source": "brief_extracted",
    },
    "video_dossiers": [{
        "video_path": "/runs/test/input/videos/ad1.mp4",
        "duration_sec": 30.0, "transcript": "Buy now and save.", "hook_summary": "Bold open.",
        "scenes": [], "pacing": "fast", "logo_first_appearance_sec": 2.0,
        "cta_detected": True, "cta_text": "Buy now", "frames_analyzed": 6, "metadata": {},
    }],
    "initial_judgements": {},
    "consistency_report": None,
    "final_judgements": {},
    "verdict": None,
}

VALID_SCORING_RESPONSE = {
    "judgements": [{
        "agent_name": "creative_strategist",
        "agent_role": "Creative Director",
        "video_path": "ad1.mp4",
        "scores": {"storytelling": 8.0, "message_clarity": 7.5},
        "strengths": ["Strong hook"],
        "weaknesses": ["Logo late"],
        "evidence": ["0:02 — bold visual open"],
        "metric_comments": {},
        "confidence": 80,
        "token_bid": 0,
        "flags": [],
        "notes": "Solid concept.",
        "model_info": {},
    }],
    "conviction_allocation": {"ad1.mp4": 100},
}


def make_mock_router(response_dict: dict) -> MagicMock:
    from cjs.router.model_router import RouterResult
    router = MagicMock()
    result = RouterResult(
        content=json.dumps(response_dict),
        tokens_in=100, tokens_out=200, latency_ms=500.0, model="claude-sonnet-4-6",
    )
    router.call_structured.return_value = result
    router.call_extended_thinking.return_value = result
    return router


def test_run_scoring_agent_returns_initial_judgements():
    router = make_mock_router(VALID_SCORING_RESPONSE)
    config = {"configurable": {"router": router}}
    result = _run_scoring_agent(MINIMAL_STATE, config, "creative_strategist", "You are a CD.", extended_thinking=False)
    assert "initial_judgements" in result
    assert "creative_strategist" in result["initial_judgements"]
    assert len(result["initial_judgements"]["creative_strategist"]) == 1


def test_run_scoring_agent_populates_token_bid_from_conviction():
    router = make_mock_router(VALID_SCORING_RESPONSE)
    config = {"configurable": {"router": router}}
    result = _run_scoring_agent(MINIMAL_STATE, config, "creative_strategist", "You are a CD.", extended_thinking=False)
    judgement = result["initial_judgements"]["creative_strategist"][0]
    assert judgement["token_bid"] == 100


def test_run_scoring_agent_normalises_conviction_not_summing_to_100():
    bad_response = {
        "judgements": [VALID_SCORING_RESPONSE["judgements"][0].copy()],
        "conviction_allocation": {"ad1.mp4": 50},  # only 50, not 100
    }
    router = make_mock_router(bad_response)
    config = {"configurable": {"router": router}}
    result = _run_scoring_agent(MINIMAL_STATE, config, "creative_strategist", "You are a CD.", extended_thinking=False)
    judgement = result["initial_judgements"]["creative_strategist"][0]
    assert judgement["token_bid"] == 100  # normalised: 50/50 * 100


def test_run_scoring_agent_uses_call_structured_for_regular_agents():
    router = make_mock_router(VALID_SCORING_RESPONSE)
    config = {"configurable": {"router": router}}
    _run_scoring_agent(MINIMAL_STATE, config, "creative_strategist", "You are a CD.", extended_thinking=False)
    router.call_structured.assert_called_once()
    router.call_extended_thinking.assert_not_called()


def test_run_scoring_agent_uses_extended_thinking_for_brand_compliance():
    router = make_mock_router(VALID_SCORING_RESPONSE)
    config = {"configurable": {"router": router}}
    _run_scoring_agent(MINIMAL_STATE, config, "brand_compliance", "You are BC.", extended_thinking=True)
    router.call_extended_thinking.assert_called_once()
    router.call_structured.assert_not_called()


def test_run_scoring_agent_raises_on_invalid_json():
    from cjs.router.model_router import RouterResult
    router = MagicMock()
    router.call_structured.return_value = RouterResult(
        content="not valid json {{{{",
        tokens_in=10, tokens_out=10, latency_ms=0.0, model="claude-sonnet-4-6",
    )
    config = {"configurable": {"router": router}}
    with pytest.raises(AgentScoringError):
        _run_scoring_agent(MINIMAL_STATE, config, "creative_strategist", "You are a CD.", extended_thinking=False)


def test_creative_strategist_node_calls_helper():
    router = make_mock_router(VALID_SCORING_RESPONSE)
    config = {"configurable": {"router": router}}
    result = creative_strategist_node(MINIMAL_STATE, config)
    assert "creative_strategist" in result["initial_judgements"]
    router.call_structured.assert_called_once()


def test_brand_compliance_node_uses_call_structured():
    bc_response = {
        "judgements": [{**VALID_SCORING_RESPONSE["judgements"][0], "agent_name": "brand_compliance"}],
        "conviction_allocation": {"ad1.mp4": 100},
    }
    router = make_mock_router(bc_response)
    config = {"configurable": {"router": router}}
    result = brand_compliance_node(MINIMAL_STATE, config)
    assert "brand_compliance" in result["initial_judgements"]
    router.call_structured.assert_called_once()
    router.call_extended_thinking.assert_not_called()


def test_all_five_agent_nodes_exist_and_return_correct_key():
    nodes = [
        (creative_strategist_node, "creative_strategist"),
        (audience_psychology_node, "audience_psychology"),
        (performance_marketer_node, "performance_marketer"),
        (storytelling_critic_node, "storytelling_critic"),
    ]
    for node_fn, expected_key in nodes:
        named_response = {
            "judgements": [{**VALID_SCORING_RESPONSE["judgements"][0], "agent_name": expected_key}],
            "conviction_allocation": {"ad1.mp4": 100},
        }
        router = make_mock_router(named_response)
        config = {"configurable": {"router": router}}
        result = node_fn(MINIMAL_STATE, config)
        assert expected_key in result["initial_judgements"], f"Missing key for {expected_key}"
