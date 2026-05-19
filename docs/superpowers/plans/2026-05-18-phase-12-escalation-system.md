# Phase 12: Escalation System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two LangGraph gate nodes (human review after deliberation, confidence check after Moderator) and a shared escalation event writer that also standardises the existing ModelRouter fallback events.

**Architecture:** `human_review_gate_node` is inserted between `deliberation_round_node` and `moderator_node`; it raises `HumanReviewRejectedError` (caught by the CLI) when the user declines to continue, allowing `cjs resume` to pick up from the saved checkpoint. `confidence_gate_node` is inserted between `moderator_node` and END; in advisory mode it writes to `metrics.json`; in strict mode it raises `LowConfidenceError`. Both gate nodes and `ModelRouter._write_escalation` share a thin `write_escalation_event()` helper in `cjs/escalation/events.py`.

**Tech Stack:** LangGraph 1.0.7, Typer, Rich, Python stdlib (json, pathlib, datetime).

---

## File map

| Action | File | Responsibility |
|---|---|---|
| Create | `cjs/escalation/__init__.py` | Package marker |
| Create | `cjs/escalation/events.py` | `write_escalation_event(path, **fields)` — shared writer |
| Create | `cjs/escalation/human_review.py` | `HumanReviewRejectedError`, `_compute_max_score_delta`, `_has_unresolved_flags`, `human_review_gate_node` |
| Create | `cjs/escalation/confidence_gate.py` | `LowConfidenceError`, `confidence_gate_node` |
| Modify | `cjs/graph/jury_graph.py` | Add two gate nodes; rewire edges |
| Modify | `cjs/router/model_router.py` | Refactor `_write_escalation` to use shared helper |
| Modify | `cjs/cli.py` | Add `--strict-confidence`; catch `HumanReviewRejectedError` and `LowConfidenceError` |
| Create | `cjs/tests/test_escalation_events.py` | Tests for `write_escalation_event` |
| Create | `cjs/tests/test_human_review_gate.py` | Tests for human review gate node and helpers |
| Create | `cjs/tests/test_confidence_gate.py` | Tests for confidence gate node |
| Modify | `cjs/tests/test_jury_graph.py` | Add two mock gate nodes; update `_build_mock_graph` |

---

### Task 1: Escalation events helper + ModelRouter refactor

**Files:**
- Create: `cjs/escalation/__init__.py`
- Create: `cjs/escalation/events.py`
- Modify: `cjs/router/model_router.py`
- Create: `cjs/tests/test_escalation_events.py`

- [ ] **Step 1: Write failing tests**

```python
# cjs/tests/test_escalation_events.py
import json
import tempfile
from pathlib import Path

from cjs.escalation.events import write_escalation_event


def test_write_creates_file():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "escalations.jsonl"
        write_escalation_event(path, type="test", run_id="r1")
        assert path.exists()


def test_write_appends_multiple_lines():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "escalations.jsonl"
        write_escalation_event(path, type="a", run_id="r1")
        write_escalation_event(path, type="b", run_id="r1")
        lines = path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["type"] == "a"
        assert json.loads(lines[1])["type"] == "b"


def test_write_includes_ts_and_fields():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "escalations.jsonl"
        write_escalation_event(path, type="model_fallback", run_id="r1",
                               node="scoring", from_model="opus", to_model="haiku")
        entry = json.loads(path.read_text())
        assert "ts" in entry
        assert entry["type"] == "model_fallback"
        assert entry["run_id"] == "r1"
        assert entry["node"] == "scoring"
        assert entry["from_model"] == "opus"
        assert entry["to_model"] == "haiku"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest cjs/tests/test_escalation_events.py -v
```
Expected: ImportError or ModuleNotFoundError for `cjs.escalation.events`.

- [ ] **Step 3: Create `cjs/escalation/__init__.py`**

```python
```
(empty file — package marker only)

- [ ] **Step 4: Create `cjs/escalation/events.py`**

```python
import json
from datetime import datetime, timezone
from pathlib import Path


def write_escalation_event(path: Path, **fields: object) -> None:
    entry = {"ts": datetime.now(timezone.utc).isoformat(), **fields}
    with open(path, "a") as fh:
        fh.write(json.dumps(entry) + "\n")
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest cjs/tests/test_escalation_events.py -v
```
Expected: 3 PASSED.

- [ ] **Step 6: Refactor `ModelRouter._write_escalation` to use shared helper**

Open `cjs/router/model_router.py`. Find `_write_escalation` (currently at line ~282). Replace it:

```python
    def _write_escalation(self, *, node: str, from_model: str, to_model: str) -> None:
        from cjs.escalation.events import write_escalation_event
        write_escalation_event(
            self._run_folder / "escalations.jsonl",
            type="model_fallback",
            run_id=self.run_id,
            node=node,
            from_model=from_model,
            to_model=to_model,
            reason="circuit_open",
        )
        logger.warning("model_fallback", from_model=from_model, to_model=to_model, node=node)
```

The local import of `write_escalation_event` avoids a circular-import risk since `model_router.py` is imported before `cjs.escalation` in some code paths.

- [ ] **Step 7: Run full test suite to verify no regressions**

```
pytest cjs/ -v -m "not integration"
```
Expected: all tests pass (127+3 = 130).

- [ ] **Step 8: Tell the user to commit**

> Tests pass. When ready, commit with:
> `git add cjs/escalation/__init__.py cjs/escalation/events.py cjs/router/model_router.py cjs/tests/test_escalation_events.py && git commit -m "feat: add escalation events helper, refactor ModelRouter to use shared writer"`

---

### Task 2: Human review gate node

**Files:**
- Create: `cjs/escalation/human_review.py`
- Create: `cjs/tests/test_human_review_gate.py`

- [ ] **Step 1: Write failing tests**

```python
# cjs/tests/test_human_review_gate.py
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from cjs.escalation.human_review import (
    HumanReviewRejectedError,
    _compute_max_score_delta,
    _has_unresolved_flags,
    human_review_gate_node,
    SCORE_DELTA_THRESHOLD,
)

_BASE_STATE = {
    "run_id": "test_run",
    "brief": {},
    "rubric": {"weights": {"storytelling": 0.5, "message_clarity": 0.5}},
    "brand_rules": {},
    "video_dossiers": [],
    "initial_judgements": {},
    "consistency_report": {"flags": [], "checked_agents": [], "checked_videos": []},
    "final_judgements": {
        "agent_a": [
            {"video_path": "/run/input/ad1.mp4", "scores": {"storytelling": 8.0, "message_clarity": 7.0},
             "agent_name": "agent_a", "confidence": 70, "token_bid": 20, "flags": [],
             "notes": None, "strengths": [], "weaknesses": [], "evidence": [], "metric_comments": {}, "model_info": {}},
        ],
        "agent_b": [
            {"video_path": "/run/input/ad1.mp4", "scores": {"storytelling": 2.0, "message_clarity": 1.0},
             "agent_name": "agent_b", "confidence": 70, "token_bid": 20, "flags": [],
             "notes": None, "strengths": [], "weaknesses": [], "evidence": [], "metric_comments": {}, "model_info": {}},
        ],
    },
    "verdict": None,
}


def _make_config(tmp_path: Path):
    router = mock.MagicMock()
    router._run_folder = tmp_path
    return {"configurable": {"thread_id": "t", "router": router}}


def test_compute_max_score_delta_returns_zero_with_no_scores():
    state = {**_BASE_STATE, "final_judgements": {}}
    assert _compute_max_score_delta(state) == 0.0


def test_compute_max_score_delta_single_agent_returns_zero():
    state = {**_BASE_STATE, "final_judgements": {"agent_a": _BASE_STATE["final_judgements"]["agent_a"]}}
    assert _compute_max_score_delta(state) == 0.0


def test_compute_max_score_delta_two_agents_returns_diff():
    delta = _compute_max_score_delta(_BASE_STATE)
    # weights 0.5/0.5, agent_a scores avg (8+7)/2=7.5 normalised, agent_b (2+1)/2=1.5 normalised
    # weighted/total_weight for agent_a: (8*0.5 + 7*0.5)/1.0 = 7.5, agent_b: (2*0.5+1*0.5)/1.0=1.5
    # delta = 7.5 - 1.5 = 6.0
    assert abs(delta - 6.0) < 0.01


def test_has_unresolved_flags_empty():
    assert not _has_unresolved_flags(_BASE_STATE)


def test_has_unresolved_flags_with_flags():
    state = {**_BASE_STATE, "consistency_report": {
        "flags": [{"agent": "a", "video": "v", "claim": "c",
                   "contradicting_evidence": "e", "classification": "FACTUAL_CONTRADICTION"}],
        "checked_agents": [], "checked_videos": [],
    }}
    assert _has_unresolved_flags(state)


def test_gate_no_escalation_returns_empty(tmp_path):
    # Low delta (agents agree), no flags
    state = {**_BASE_STATE, "final_judgements": {
        "agent_a": [{"video_path": "/r/ad1.mp4", "scores": {"storytelling": 7.0, "message_clarity": 7.0},
                     "agent_name": "agent_a", "confidence": 70, "token_bid": 20, "flags": [],
                     "notes": None, "strengths": [], "weaknesses": [], "evidence": [], "metric_comments": {}, "model_info": {}}],
        "agent_b": [{"video_path": "/r/ad1.mp4", "scores": {"storytelling": 7.5, "message_clarity": 7.0},
                     "agent_name": "agent_b", "confidence": 70, "token_bid": 20, "flags": [],
                     "notes": None, "strengths": [], "weaknesses": [], "evidence": [], "metric_comments": {}, "model_info": {}}],
    }}
    result = human_review_gate_node(state, _make_config(tmp_path))
    assert result == {}


def test_gate_approved_returns_empty(tmp_path):
    with mock.patch("cjs.escalation.human_review.typer.confirm", return_value=True), \
         mock.patch("rich.console.Console"):
        result = human_review_gate_node(_BASE_STATE, _make_config(tmp_path))
    assert result == {}


def test_gate_rejected_raises(tmp_path):
    with mock.patch("cjs.escalation.human_review.typer.confirm", return_value=False), \
         mock.patch("rich.console.Console"):
        with pytest.raises(HumanReviewRejectedError):
            human_review_gate_node(_BASE_STATE, _make_config(tmp_path))
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest cjs/tests/test_human_review_gate.py -v
```
Expected: ImportError for `cjs.escalation.human_review`.

- [ ] **Step 3: Create `cjs/escalation/human_review.py`**

```python
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
    router = config["configurable"]["router"]
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest cjs/tests/test_human_review_gate.py -v
```
Expected: 8 PASSED.

- [ ] **Step 5: Run full test suite**

```
pytest cjs/ -v -m "not integration"
```
Expected: all tests pass.

- [ ] **Step 6: Tell the user to commit**

> Tests pass. When ready, commit with:
> `git add cjs/escalation/human_review.py cjs/tests/test_human_review_gate.py && git commit -m "feat: add human review gate node"`

---

### Task 3: Confidence gate node

**Files:**
- Create: `cjs/escalation/confidence_gate.py`
- Create: `cjs/tests/test_confidence_gate.py`

- [ ] **Step 1: Write failing tests**

```python
# cjs/tests/test_confidence_gate.py
import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from cjs.escalation.confidence_gate import (
    CONFIDENCE_THRESHOLD,
    LowConfidenceError,
    confidence_gate_node,
)

_BASE_STATE = {
    "run_id": "test_run",
    "brief": {}, "rubric": {}, "brand_rules": {},
    "video_dossiers": [], "initial_judgements": {},
    "consistency_report": None, "final_judgements": {},
    "verdict": {"winner_video": "ad1.mp4", "winner_rationale": "Best.",
                "ranking": ["ad1.mp4"], "per_video_notes": {}, "confidence": 0.5,
                "flags_resolved": []},
}


def _make_config(tmp_path: Path, strict: bool = False):
    router = mock.MagicMock()
    router._run_folder = tmp_path
    return {"configurable": {"thread_id": "t", "router": router, "strict_confidence": strict}}


def test_high_confidence_passes_through(tmp_path):
    state = {**_BASE_STATE, "verdict": {**_BASE_STATE["verdict"], "confidence": 0.9}}
    result = confidence_gate_node(state, _make_config(tmp_path))
    assert result == {}
    assert not (tmp_path / "metrics.json").exists()


def test_advisory_writes_metrics(tmp_path):
    result = confidence_gate_node(_BASE_STATE, _make_config(tmp_path, strict=False))
    assert result == {}
    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert metrics["verdict_confidence"] == "low"
    assert abs(metrics["verdict_confidence_value"] - 0.5) < 0.001


def test_advisory_writes_escalation_event(tmp_path):
    confidence_gate_node(_BASE_STATE, _make_config(tmp_path, strict=False))
    line = (tmp_path / "escalations.jsonl").read_text().strip()
    entry = json.loads(line)
    assert entry["type"] == "low_confidence_verdict"
    assert entry["node"] == "confidence_gate"
    assert abs(entry["confidence"] - 0.5) < 0.001


def test_advisory_merges_existing_metrics(tmp_path):
    (tmp_path / "metrics.json").write_text(json.dumps({"previous_key": "value"}))
    confidence_gate_node(_BASE_STATE, _make_config(tmp_path, strict=False))
    metrics = json.loads((tmp_path / "metrics.json").read_text())
    assert metrics["previous_key"] == "value"
    assert metrics["verdict_confidence"] == "low"


def test_strict_raises_low_confidence_error(tmp_path):
    with mock.patch("rich.console.Console"), \
         pytest.raises(LowConfidenceError, match="below threshold"):
        confidence_gate_node(_BASE_STATE, _make_config(tmp_path, strict=True))
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest cjs/tests/test_confidence_gate.py -v
```
Expected: ImportError for `cjs.escalation.confidence_gate`.

- [ ] **Step 3: Create `cjs/escalation/confidence_gate.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest cjs/tests/test_confidence_gate.py -v
```
Expected: 5 PASSED.

- [ ] **Step 5: Run full test suite**

```
pytest cjs/ -v -m "not integration"
```
Expected: all tests pass.

- [ ] **Step 6: Tell the user to commit**

> Tests pass. When ready, commit with:
> `git add cjs/escalation/confidence_gate.py cjs/tests/test_confidence_gate.py && git commit -m "feat: add confidence gate node"`

---

### Task 4: Wire gate nodes into graph and CLI

**Files:**
- Modify: `cjs/graph/jury_graph.py`
- Modify: `cjs/cli.py`
- Modify: `cjs/tests/test_jury_graph.py`

**Context:** `jury_graph.py` currently edges: `deliberation_round_node → moderator_node → END`. After this task: `deliberation_round_node → human_review_gate_node → moderator_node → confidence_gate_node → END`. The CLI `run` command needs `--strict-confidence` flag; both `run` and `resume` need to catch `HumanReviewRejectedError` and `LowConfidenceError`.

- [ ] **Step 1: Update `cjs/tests/test_jury_graph.py`**

Add two mock gate functions and update `_build_mock_graph`. Replace the file with:

```python
import pytest
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from cjs.graph.state import JuryState, _merge_dicts
from cjs.graph.jury_graph import build_jury_graph, _fan_out

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

FAKE_JUDGEMENT = {
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
```

- [ ] **Step 2: Run graph tests to verify they fail**

```
pytest cjs/tests/test_jury_graph.py -v
```
Expected: tests may pass (mock graph is self-contained) or fail with import errors if `build_jury_graph` now tries to import new modules. Either way, proceed to update the graph.

- [ ] **Step 3: Update `cjs/graph/jury_graph.py`**

Replace the entire file with:

```python
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
from cjs.escalation.human_review import human_review_gate_node
from cjs.escalation.confidence_gate import confidence_gate_node

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
    graph.add_node("human_review_gate_node", human_review_gate_node)
    graph.add_node("moderator_node", moderator_node)
    graph.add_node("confidence_gate_node", confidence_gate_node)

    graph.add_conditional_edges(START, _fan_out)
    for name in _AGENT_NODES:
        graph.add_edge(name, "consistency_checker_node")
    graph.add_edge("consistency_checker_node", "deliberation_round_node")
    graph.add_edge("deliberation_round_node", "human_review_gate_node")
    graph.add_edge("human_review_gate_node", "moderator_node")
    graph.add_edge("moderator_node", "confidence_gate_node")
    graph.add_edge("confidence_gate_node", END)

    return graph
```

- [ ] **Step 4: Run graph tests to verify they pass**

```
pytest cjs/tests/test_jury_graph.py -v
```
Expected: 3 PASSED.

- [ ] **Step 5: Update `cjs/cli.py` — `run` command**

Find the `run` function signature (line ~581). Add `strict_confidence` parameter after the `out` parameter:

```python
    strict_confidence: bool = typer.Option(
        False,
        "--strict-confidence",
        help="Exit with error if verdict confidence is below 70%.",
    ),
```

Find the `thread_config` line in `run` (line ~737):
```python
    thread_config = {"configurable": {"thread_id": run_id, "router": router}}
```
Replace with:
```python
    thread_config = {"configurable": {"thread_id": run_id, "router": router, "strict_confidence": strict_confidence}}
```

Find the try/except block wrapping `compiled.invoke` in `run` (lines ~739–746):
```python
    try:
        final_state = compiled.invoke(initial_jury_state, config=thread_config)
    except Exception as exc:
        if json_mode:
            output_result({"status": "error", "run_id": run_id, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(f"Jury swarm failed: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
```
Replace with:
```python
    from cjs.escalation.human_review import HumanReviewRejectedError
    from cjs.escalation.confidence_gate import LowConfidenceError
    try:
        final_state = compiled.invoke(initial_jury_state, config=thread_config)
    except HumanReviewRejectedError:
        if json_mode:
            output_result({"status": "paused", "run_id": run_id,
                           "reason": "human_review_rejected"}, json_mode=True)
        else:
            typer.secho(
                f"Run paused at human review gate. Resume with: cjs resume {run_id}",
                fg=typer.colors.YELLOW,
            )
        raise typer.Exit(0)
    except LowConfidenceError as exc:
        if json_mode:
            output_result({"status": "error", "run_id": run_id, "error": str(exc)},
                          json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as exc:
        if json_mode:
            output_result({"status": "error", "run_id": run_id, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(f"Jury swarm failed: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
```

- [ ] **Step 6: Update `cjs/cli.py` — `resume` command**

Find the `resume` function signature (line ~912). Add `strict_confidence` parameter:
```python
    strict_confidence: bool = typer.Option(
        False,
        "--strict-confidence",
        help="Exit with error if verdict confidence is below 70%.",
    ),
```

Find the `thread_config` line in `resume` (line ~944):
```python
    thread_config = {"configurable": {"thread_id": run_id, "router": router}}
```
Replace with:
```python
    thread_config = {"configurable": {"thread_id": run_id, "router": router, "strict_confidence": strict_confidence}}
```

Find the try/except block wrapping `compiled.invoke` in `resume` (lines ~949–956):
```python
    try:
        final_state = compiled.invoke(None, config=thread_config)
    except Exception as exc:
        if json_output:
            output_result({"ok": False, "error": str(exc), "run_id": run_id}, json_mode=True)
        else:
            typer.secho(f"Resume failed: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
```
Replace with:
```python
    from cjs.escalation.human_review import HumanReviewRejectedError
    from cjs.escalation.confidence_gate import LowConfidenceError
    try:
        final_state = compiled.invoke(None, config=thread_config)
    except HumanReviewRejectedError:
        if json_output:
            output_result({"ok": False, "status": "paused", "run_id": run_id,
                           "reason": "human_review_rejected"}, json_mode=True)
        else:
            typer.secho(
                f"Run paused at human review gate. Resume again with: cjs resume {run_id}",
                fg=typer.colors.YELLOW,
            )
        raise typer.Exit(0)
    except LowConfidenceError as exc:
        if json_output:
            output_result({"ok": False, "error": str(exc), "run_id": run_id}, json_mode=True)
        else:
            typer.secho(str(exc), err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    except Exception as exc:
        if json_output:
            output_result({"ok": False, "error": str(exc), "run_id": run_id}, json_mode=True)
        else:
            typer.secho(f"Resume failed: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
```

- [ ] **Step 7: Run full test suite**

```
pytest cjs/ -v -m "not integration"
```
Expected: all tests pass (check that existing CLI tests in `test_cli_commands.py` still pass — they mock `build_jury_graph` so gate nodes don't run).

- [ ] **Step 8: Tell the user to commit**

> Tests pass. When ready, commit with:
> `git add cjs/graph/jury_graph.py cjs/cli.py cjs/tests/test_jury_graph.py && git commit -m "feat: wire human review and confidence gate nodes into jury graph and CLI"`
