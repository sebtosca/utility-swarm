from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cjs.graph.state import JuryState


def build_report(
    run_folder: Path,
    state: JuryState,
    verdict: dict,
    metrics: dict,
) -> Path:
    template = (Path(__file__).parent / "template.html").read_text()

    data = {
        "run_id": state.get("run_id", ""),
        "rubric": state.get("rubric", {}),
        "brief": state.get("brief", {}),
        "initial_judgements": state.get("initial_judgements", {}),
        "final_judgements": state.get("final_judgements", {}),
        "consistency_report": state.get("consistency_report"),
        "verdict": verdict,
        "metrics": metrics,
        "escalation_events": _load_escalation_events(run_folder),
    }

    html = template.replace(
        "window.CJS_DATA = __CJS_DATA_PLACEHOLDER__",
        f"window.CJS_DATA = {json.dumps(data, indent=2)}",
    )

    results_dir = run_folder / "results"
    results_dir.mkdir(exist_ok=True)
    report_path = results_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return report_path


def _load_escalation_events(run_folder: Path) -> list[dict]:
    path = run_folder / "escalations.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return events
