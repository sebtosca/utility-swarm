import pytest
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from cjs.graph.state import JuryState
from cjs.graph.jury_graph import _fan_out

MINIMAL_STATE: JuryState = {
    "run_id": "resume_test",
    "brief": {}, "rubric": {}, "brand_rules": {},
    "video_dossiers": [],
    "initial_judgements": {}, "consistency_report": None,
    "final_judgements": {}, "verdict": None,
}

AGENT_NAMES = ["creative_strategist_node", "brand_compliance_node",
               "audience_psychology_node", "performance_marketer_node",
               "storytelling_critic_node"]


def test_completed_run_is_idempotent_on_second_invoke():
    """Completed run state is retrievable via get_state and verdict is stable."""
    call_counts: dict[str, int] = {}

    def make_node(name):
        def node(state):
            call_counts[name] = call_counts.get(name, 0) + 1
            return {}
        return node

    def _consistency(s):
        return {"consistency_report": {"flags": [], "checked_agents": [], "checked_videos": []}}

    def _deliberation(s):
        return {"final_judgements": {}}

    def _moderator(s):
        return {"verdict": {"winner_video": "ad1.mp4", "winner_rationale": "x", "ranking": [], "per_video_notes": {}, "confidence": 0.9, "flags_resolved": []}}

    graph = StateGraph(JuryState)
    for name in AGENT_NAMES:
        graph.add_node(name, make_node(name))
    graph.add_node("consistency_checker_node", _consistency)
    graph.add_node("deliberation_round_node", _deliberation)
    graph.add_node("moderator_node", _moderator)
    graph.add_conditional_edges(START, _fan_out)
    for name in AGENT_NAMES:
        graph.add_edge(name, "consistency_checker_node")
    graph.add_edge("consistency_checker_node", "deliberation_round_node")
    graph.add_edge("deliberation_round_node", "moderator_node")
    graph.add_edge("moderator_node", END)

    saver = MemorySaver()
    compiled = graph.compile(checkpointer=saver)
    cfg = {"configurable": {"thread_id": "resume_test_thread"}}

    result1 = compiled.invoke(MINIMAL_STATE, config=cfg)
    first_run_counts = dict(call_counts)

    # Completed run state is retrievable via get_state without re-running nodes
    state_snapshot = compiled.get_state(cfg)

    assert state_snapshot.values["verdict"] == result1["verdict"]
    assert state_snapshot.next == ()  # no pending nodes — run is complete
    # Node call counts should not have increased (get_state does not re-run nodes)
    for name in AGENT_NAMES:
        assert call_counts.get(name, 0) == first_run_counts.get(name, 0)
