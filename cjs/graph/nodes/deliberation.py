from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from cjs.graph.nodes.scoring import _CROSS_CUTTING, AGENT_PERSONAS
from cjs.schemas.judgement import AgentJudgement

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from cjs.graph.state import JuryState


class _DeliberationResponse(BaseModel):
    judgements: list[AgentJudgement]


_DELIBERATION_INSTRUCTION = (
    "You are reviewing your initial scores in light of the full jury's assessment. "
    "If you have flags listed below, address them specifically and revise the affected scores "
    "if warranted. If your confidence is high and no flags apply to you, returning your scores "
    "unchanged is the correct response. Be direct — do not change scores to please the group."
)


def _group_flags_by_agent(consistency_report: dict | None) -> dict[str, list[dict]]:
    if not consistency_report:
        return {}
    result: dict[str, list[dict]] = {}
    for flag in consistency_report.get("flags", []):
        result.setdefault(flag["agent"], []).append(flag)
    return result


def _build_group_summary(initial_judgements: dict[str, list[dict]]) -> str:
    lines: list[str] = []
    for agent_name, judgements in initial_judgements.items():
        for j in judgements:
            filename = Path(j["video_path"]).name
            scores_str = ", ".join(f"{k}={v:.1f}" for k, v in j.get("scores", {}).items())
            lines.append(
                f"  {agent_name} on {filename}: {scores_str}, confidence={j.get('confidence')}"
            )
    return "\n".join(lines)


def _build_deliberation_user_prompt(
    own_judgements: list[dict],
    group_summary: str,
    agent_flags: list[dict],
) -> str:
    own_scores = "\n".join(
        f"  {Path(j['video_path']).name}: {j.get('scores', {})}, confidence={j.get('confidence')}"
        for j in own_judgements
    )
    flags_section = ""
    if agent_flags:
        flag_lines = [
            f"  - {f['claim']} (contradicted by: {f['contradicting_evidence']})"
            for f in agent_flags
        ]
        flags_section = "\n## Flags directed at you\n" + "\n".join(flag_lines) + "\n"

    return (
        f"## Your initial scores\n{own_scores}\n\n"
        f"## All agents' initial scores\n{group_summary}\n"
        f"{flags_section}"
    )


def deliberation_round_node(state: JuryState, config: RunnableConfig) -> dict:
    router = config["configurable"]["router"]
    flags_by_agent = _group_flags_by_agent(state["consistency_report"])
    group_summary = _build_group_summary(state["initial_judgements"])
    final_judgements: dict[str, list[dict]] = {}

    for agent_name, persona in AGENT_PERSONAS.items():
        own_judgements = state["initial_judgements"].get(agent_name, [])
        agent_flags = flags_by_agent.get(agent_name, [])
        system_prompt = persona + "\n\n" + _CROSS_CUTTING + "\n\n" + _DELIBERATION_INSTRUCTION
        user_prompt = _build_deliberation_user_prompt(own_judgements, group_summary, agent_flags)

        result = router.call_structured(
            system_prompt,
            user_prompt,
            node=f"deliberation_{agent_name}",
            schema=_DeliberationResponse.model_json_schema(),
            schema_name="deliberation_response",
            agent=agent_name,
        )
        data = json.loads(result.content)
        response = _DeliberationResponse(**data)
        final_judgements[agent_name] = [j.model_dump() for j in response.judgements]

    return {"final_judgements": final_judgements}
