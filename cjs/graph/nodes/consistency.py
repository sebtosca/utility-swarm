from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from cjs.schemas.consistency_flag import ConsistencyReport

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from cjs.graph.state import JuryState

_SYSTEM_PROMPT = (
    "You are a factual auditor reviewing jury agent claims against verified video dossier data. "
    "Detect two types of inconsistency:\n"
    "1. FACTUAL_CONTRADICTION — an agent's notes, flags, or evidence directly contradict a "
    "dossier field (e.g. agent writes 'no CTA detected' but dossier has cta_detected=true).\n"
    "2. SCORE_NARRATIVE_MISMATCH — an agent's written notes praise something but the numeric "
    "score for that dimension is low, or vice versa (e.g. 'excellent logo timing' with "
    "brand_alignment score < 5).\n"
    "Only flag clear contradictions — do not flag subjective differences of opinion."
)


def _build_consistency_user_prompt(
    judgements: dict[str, list[dict]], dossiers: list[dict]
) -> str:
    dossier_map = {Path(d["video_path"]).name: d for d in dossiers}
    lines: list[str] = ["Review each agent's judgements against the dossier facts.\n"]

    for agent_name, agent_judgements in judgements.items():
        lines.append(f"## Agent: {agent_name}")
        for j in agent_judgements:
            filename = Path(j["video_path"]).name
            d = dossier_map.get(filename, {})
            lines.append(f"### Video: {filename}")
            lines.append(f"Scores: {j.get('scores', {})}")
            lines.append(f"Notes: {j.get('notes', '')}")
            lines.append(f"Flags: {j.get('flags', [])}")
            lines.append(f"Evidence: {j.get('evidence', [])}")
            lines.append("Dossier facts:")
            lines.append(f"  cta_detected={d.get('cta_detected')}, cta_text={d.get('cta_text')!r}")
            lines.append(f"  logo_first_appearance_sec={d.get('logo_first_appearance_sec')}")
            lines.append(f"  pacing={d.get('pacing')}")
            transcript = (d.get("transcript") or "")[:300]
            lines.append(f"  transcript (first 300 chars): {transcript!r}")
            lines.append("")

    return "\n".join(lines)


def consistency_checker_node(state: JuryState, config: RunnableConfig) -> dict:
    router = config["configurable"]["router"]
    user_prompt = _build_consistency_user_prompt(
        state["initial_judgements"], state["video_dossiers"]
    )
    result = router.call_structured(
        _SYSTEM_PROMPT,
        user_prompt,
        node="consistency_checker",
        schema=ConsistencyReport.model_json_schema(),
        schema_name="consistency_report",
        agent="consistency_checker",
    )
    data = json.loads(result.content)
    report = ConsistencyReport(**data)
    return {"consistency_report": report.model_dump()}
