from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import typer

from cjs.escalation.events import write_escalation_event
from cjs.observability.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from cjs.graph.state import JuryState

logger = get_logger(__name__)

SCORE_DELTA_THRESHOLD = 3.0


class HumanReviewRejectedError(Exception):
    pass


def _compute_max_score_delta(state: JuryState) -> float:
    weights: dict[str, float] = state["rubric"].get("weights", {})
    total_weight = sum(weights.values()) or 1.0
    per_video_scores: dict[str, list[float]] = {}
    for agent_judgements in state["final_judgements"].values():
        for j in agent_judgements:
            filename = Path(j["video_path"]).name
            scores: dict[str, float] = j.get("scores", {})
            if not scores:
                continue
            weighted = sum(scores.get(dim, 0.0) * w for dim, w in weights.items())
            per_video_scores.setdefault(filename, []).append(weighted / total_weight)
    if not per_video_scores:
        return 0.0
    return max(
        (max(v) - min(v) for v in per_video_scores.values() if len(v) > 1),
        default=0.0,
    )


def _has_unresolved_flags(state: JuryState) -> bool:
    report = state.get("consistency_report") or {}
    return bool(report.get("flags"))


def human_review_gate_node(state: JuryState, config: RunnableConfig) -> dict:
    configurable = config["configurable"]
    router = configurable["router"]
    auto_approve: bool = bool(configurable.get("auto_approve", False))
    escalations_path = router._run_folder / "escalations.jsonl"

    max_delta = _compute_max_score_delta(state)
    has_flags = _has_unresolved_flags(state)

    if max_delta <= SCORE_DELTA_THRESHOLD and not has_flags:
        return {}

    reasons = []
    if max_delta > SCORE_DELTA_THRESHOLD:
        reasons.append(f"score delta {max_delta:.2f} exceeds threshold {SCORE_DELTA_THRESHOLD}")
    if has_flags:
        flag_count = len((state.get("consistency_report") or {}).get("flags", []))
        reasons.append(f"{flag_count} unresolved consistency flag(s)")

    write_escalation_event(
        escalations_path,
        type="human_review_required",
        run_id=state["run_id"],
        node="human_review_gate",
        reasons=reasons,
        max_score_delta=max_delta,
    )
    logger.warning("human_review_required", run_id=state["run_id"], reasons=reasons)

    from rich.console import Console
    from rich.panel import Panel
    reason_text = "\n".join(f"  • {r}" for r in reasons)
    Console().print(Panel(
        f"[bold yellow]Jury review flagged:[/bold yellow]\n{reason_text}\n\n"
        "Run [bold]cjs resume <run_id>[/bold] to retry after reviewing.",
        title="[bold red]Human Review Required[/bold red]",
        border_style="red",
    ))

    if auto_approve:
        logger.warning("human_review_auto_approved", run_id=state["run_id"])
    else:
        proceed = typer.confirm("Continue to Moderator anyway?", default=False)
        if not proceed:
            write_escalation_event(
                escalations_path,
                type="human_review_rejected",
                run_id=state["run_id"],
                node="human_review_gate",
            )
            raise HumanReviewRejectedError(
                f"Human review rejected for run {state['run_id']}. "
                "Resume with: cjs resume <run_id>"
            )

    write_escalation_event(
        escalations_path,
        type="human_review_approved",
        run_id=state["run_id"],
        node="human_review_gate",
    )
    return {}
