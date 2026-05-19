from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from cjs.graph.state import JuryState

from cjs.schemas.verdict import Verdict

_MODERATOR_PERSONA = """You are the chair of this creative jury and the author of the final verdict.
You have deep experience across creative strategy, brand management, and media effectiveness.
You have chaired creative review panels and know how to synthesise competing expert opinions
into a clear, defensible decision.

Your role is not to add another score to the pile — it is to read the full jury record,
identify where agents agree and where they diverge, weigh the evidence, and deliver a verdict
the client can act on.

Your responsibilities:
1. Review all agent scorecards and consistency flags.
2. Identify the most significant points of agreement and disagreement across agents.
3. Apply the auction formula outcome (provided to you) as the primary quantitative signal.
4. Produce a ranked list of all ads (best to worst) in the ranking field.
5. Write a winner verdict in the rationale field: why this ad wins and what makes it the best
   choice for this brief.
6. Write per-video bullet summaries covering strengths, weaknesses, and one improvement recommendation.
7. Populate unresolved_concerns with any finding the client must act on: unresolved hard flags,
   split jury decisions with no clear resolution, or low-confidence scores that limit verdict certainty.

Use your extended reasoning to work through genuine disagreements carefully.
A verdict that papers over a hard call is worse than a verdict that names the uncertainty.

Write with authority. Your final narrative is the document the client will read.
It must be clear, specific, and grounded in evidence from the jury record."""

_VERDICT_SCHEMA_HINT = """{
  "winner_video": "<filename of winning video>",
  "winner_rationale": "<narrative explanation>",
  "ranking": ["<best>", "<second>", ...],
  "per_video_notes": {"<filename>": "<moderator note>"},
  "confidence": <float 0.0-1.0>,
  "flags_resolved": ["<flag claim text that was addressed>"]
}"""


def _build_moderator_user_prompt(state: JuryState) -> str:
    brief = state["brief"]
    brief_block = (
        f"Brand: {brief.get('brand')} | Platform: {brief.get('platform')} | "
        f"Objective: {brief.get('objective')}\n"
        f"Key message: {brief.get('key_message')} | Primary KPI: {brief.get('primary_kpi')}"
    )

    score_lines: list[str] = []
    for agent_name, judgements in state["final_judgements"].items():
        for j in judgements:
            filename = Path(j["video_path"]).name
            scores_str = ", ".join(f"{k}={v:.1f}" for k, v in j.get("scores", {}).items())
            score_lines.append(
                f"  {agent_name} on {filename}: {scores_str}, "
                f"confidence={j.get('confidence')}, token_bid={j.get('token_bid')}\n"
                f"    Notes: {j.get('notes', '')}"
            )

    flags_section = ""
    consistency_report = state.get("consistency_report")
    if consistency_report:
        flags = consistency_report.get("flags", [])
        if flags:
            flag_lines = [
                f"  [{f['classification']}] {f['agent']} on "
                f"{Path(f['video']).name}: {f['claim']}"
                for f in flags
            ]
            flags_section = "\n## Unresolved consistency flags\n" + "\n".join(flag_lines)

    video_filenames = [Path(d["video_path"]).name for d in state["video_dossiers"]]

    return (
        f"## Brief\n{brief_block}\n\n"
        f"## Agent final scores\n" + "\n".join(score_lines) + "\n"
        f"{flags_section}\n\n"
        f"## Videos evaluated\n{', '.join(video_filenames)}\n\n"
        f"Synthesise the jury's assessment. Identify the winning video, produce a ranked verdict "
        f"with narrative rationale. Address any unresolved consistency flags.\n\n"
        f"Respond with JSON only, matching this schema:\n{_VERDICT_SCHEMA_HINT}"
    )


def moderator_node(state: JuryState, config: RunnableConfig) -> dict:
    router = config["configurable"]["router"]
    user_prompt = _build_moderator_user_prompt(state)
    result = router.call_extended_thinking(
        _MODERATOR_PERSONA,
        user_prompt,
        node="moderator",
        agent="moderator",
    )
    data = json.loads(result.content)
    verdict = Verdict(**data)
    return {"verdict": verdict.model_dump()}
