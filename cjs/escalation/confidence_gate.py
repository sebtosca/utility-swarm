from __future__ import annotations

import json
from typing import TYPE_CHECKING

from cjs.escalation.events import write_escalation_event
from cjs.observability.logging import get_logger

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig

    from cjs.graph.state import JuryState

logger = get_logger(__name__)

CONFIDENCE_THRESHOLD = 0.70


class LowConfidenceError(Exception):
    pass


def confidence_gate_node(state: JuryState, config: RunnableConfig) -> dict:
    router = config["configurable"]["router"]
    strict_confidence: bool = config["configurable"].get("strict_confidence", False)
    run_folder = router._run_folder
    escalations_path = run_folder / "escalations.jsonl"

    verdict = state.get("verdict") or {}
    confidence = verdict.get("confidence", 1.0)

    if confidence >= CONFIDENCE_THRESHOLD:
        return {}

    metrics_path = run_folder / "metrics.json"
    metrics: dict = {}
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text())
    metrics["verdict_confidence"] = "low"
    metrics["verdict_confidence_value"] = confidence
    metrics_path.write_text(json.dumps(metrics, indent=2))

    write_escalation_event(
        escalations_path,
        type="low_confidence_verdict",
        run_id=state["run_id"],
        node="confidence_gate",
        confidence=confidence,
        threshold=CONFIDENCE_THRESHOLD,
    )
    logger.warning(
        "low_confidence_verdict",
        run_id=state["run_id"],
        confidence=confidence,
        threshold=CONFIDENCE_THRESHOLD,
    )

    if strict_confidence:
        from rich.console import Console
        from rich.panel import Panel
        Console().print(Panel(
            f"[bold yellow]Verdict confidence {confidence:.0%} is below threshold "
            f"{CONFIDENCE_THRESHOLD:.0%}.[/bold yellow]\n"
            "Run without [bold]--strict-confidence[/bold] to accept low-confidence verdicts.",
            title="[bold red]Low Confidence Verdict[/bold red]",
            border_style="red",
        ))
        raise LowConfidenceError(
            f"Verdict confidence {confidence:.0%} below threshold {CONFIDENCE_THRESHOLD:.0%}"
        )

    return {}
