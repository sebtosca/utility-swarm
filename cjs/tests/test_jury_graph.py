from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from cjs.graph.jury_graph import _fan_out, build_jury_graph
from cjs.graph.state import JuryState

MINIMAL_STATE: JuryState = {
    "run_id": "graph_test",
    "brief": {"brand": "T", "objective": "x", "platform": "YouTube", "audience": "x",
              "tone": "x", "key_message": "x", "primary_kpi": "awareness",
              "emotional_territory": None, "mandatory": [], "forbidden": [],
              "kpi_priority": {}, "constraints": {}},
    "rubric": {"name": None, "description": None, "weights": {}, "hard_gates": {}},
    "brand_rules": {"brand_name": "T", "mandatory_elements": [], "forbidden_elements": [],
                    "tone_keywords": [], "approved_claims": [], "prohibited_claims": [],
                    "logo_visible_by_sec": None, "disclaimer_required": False,
                    "source": "brief_extracted"},
    "video_dossiers": [{"video_path": "/runs/test/input/videos/ad1.mp4", "duration_sec": 30.0,
                        "transcript": "", "hook_summary": "", "scenes": [], "pacing": "fast",
                        "logo_first_appearance_sec": None, "cta_detected": False, "cta_text": None,
                        "frames_analyzed": 0, "metadata": {}}],
    "initial_judgements": {},
    "consistency_report": None,
    "final_judgements": {},
    "verdict": None,
}

AGENT_NAMES = ["creative_strategist", "brand_compliance", "audience_psychology",
               "performance_marketer", "storytelling_critic"]

FAKE_JUDGEMENT: dict[str, Any] = {
    "agent_name": "placeholder", "agent_role": None, "video_path": "ad1.mp4",
    "scores": {}, "strengths": [], "weaknesses": [], "evidence": [],
    "metric_comments": {}, "confidence": 70, "token_bid": 20, "flags": [],
    "notes": None, "model_info": {},
}

FAKE_VERDICT = {
    "winner_video": "ad1.mp4", "winner_rationale": "Best.",
    "ranking": ["ad1.mp4"], "per_video_notes": {"ad1.mp4": "Good."},
    "confidence": 0.8, "flags_resolved": [],
}


def _make_mock_agent(name: str):
    def _node(state, config):
        return {"initial_judgements": {name: [{**FAKE_JUDGEMENT, "agent_name": name}]}}
    return _node


def _mock_consistency(state, config):
    return {"consistency_report": {"flags": [], "checked_agents": AGENT_NAMES, "checked_videos": ["ad1.mp4"]}}


def _mock_deliberation(state, config):
    return {"final_judgements": {name: [{**FAKE_JUDGEMENT, "agent_name": name}] for name in AGENT_NAMES}}


def _mock_human_review_gate(state, config):
    return {}


def _mock_moderator(state, config):
    return {"verdict": FAKE_VERDICT}


def _mock_confidence_gate(state, config):
    return {}


def _build_mock_graph():
    """Build a graph wired identically to build_jury_graph() but with mock nodes."""
    graph = StateGraph(JuryState)
    for name in AGENT_NAMES:
        graph.add_node(f"{name}_node", _make_mock_agent(name))
    graph.add_node("consistency_checker_node", _mock_consistency)
    graph.add_node("deliberation_round_node", _mock_deliberation)
    graph.add_node("human_review_gate_node", _mock_human_review_gate)
    graph.add_node("moderator_node", _mock_moderator)
    graph.add_node("confidence_gate_node", _mock_confidence_gate)
    graph.add_conditional_edges(START, _fan_out)
    for name in AGENT_NAMES:
        graph.add_edge(f"{name}_node", "consistency_checker_node")
    graph.add_edge("consistency_checker_node", "deliberation_round_node")
    graph.add_edge("deliberation_round_node", "human_review_gate_node")
    graph.add_edge("human_review_gate_node", "moderator_node")
    graph.add_edge("moderator_node", "confidence_gate_node")
    graph.add_edge("confidence_gate_node", END)
    return graph


def test_all_five_agents_run_and_results_merged():
    saver = MemorySaver()
    compiled = _build_mock_graph().compile(checkpointer=saver)
    result = compiled.invoke(
        MINIMAL_STATE,
        config={"configurable": {"thread_id": "test_thread_1"}},
    )
    assert set(result["initial_judgements"].keys()) == set(AGENT_NAMES)


def test_graph_reaches_moderator_and_produces_verdict():
    saver = MemorySaver()
    compiled = _build_mock_graph().compile(checkpointer=saver)
    result = compiled.invoke(
        MINIMAL_STATE,
        config={"configurable": {"thread_id": "test_thread_2"}},
    )
    assert result["verdict"] is not None
    assert result["verdict"]["winner_video"] == "ad1.mp4"


def test_build_jury_graph_compiles_without_error():
    graph = build_jury_graph()
    saver = MemorySaver()
    compiled = graph.compile(checkpointer=saver)
    assert compiled is not None
