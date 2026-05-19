from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from cjs.graph.state import JuryState
from cjs.graph.nodes.scoring import (
    creative_strategist_node,
    brand_compliance_node,
    audience_psychology_node,
    performance_marketer_node,
    storytelling_critic_node,
)
from cjs.graph.nodes.consistency import consistency_checker_node
from cjs.graph.nodes.deliberation import deliberation_round_node
from cjs.graph.nodes.moderator import moderator_node

_AGENT_NODES = [
    "creative_strategist_node",
    "brand_compliance_node",
    "audience_psychology_node",
    "performance_marketer_node",
    "storytelling_critic_node",
]


def _fan_out(state: JuryState) -> list[Send]:
    return [Send(name, state) for name in _AGENT_NODES]


def build_jury_graph() -> StateGraph:
    graph = StateGraph(JuryState)

    graph.add_node("creative_strategist_node", creative_strategist_node)
    graph.add_node("brand_compliance_node", brand_compliance_node)
    graph.add_node("audience_psychology_node", audience_psychology_node)
    graph.add_node("performance_marketer_node", performance_marketer_node)
    graph.add_node("storytelling_critic_node", storytelling_critic_node)
    graph.add_node("consistency_checker_node", consistency_checker_node)
    graph.add_node("deliberation_round_node", deliberation_round_node)
    graph.add_node("moderator_node", moderator_node)

    graph.add_conditional_edges(START, _fan_out)
    for name in _AGENT_NODES:
        graph.add_edge(name, "consistency_checker_node")
    graph.add_edge("consistency_checker_node", "deliberation_round_node")
    graph.add_edge("deliberation_round_node", "moderator_node")
    graph.add_edge("moderator_node", END)

    return graph
