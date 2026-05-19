# Phase 11 — LangGraph Jury Swarm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the LangGraph jury swarm — JuryState, five parallel scoring agents, ConsistencyChecker, deliberation round, Moderator with extended thinking, SqliteSaver checkpointing, and `cjs resume`.

**Architecture:** Functional nodes on a `StateGraph(JuryState)`. Five scoring agents fan out in parallel via `Send` from `START`, converge at `consistency_checker_node`, then run deliberation and Moderator sequentially. `ModelRouter` is passed via `RunnableConfig` configurable (never stored in state). `call_structured` (tool-use) used for scoring/consistency/deliberation; `call_extended_thinking` + JSON parse used for Brand Compliance and Moderator.

**Tech Stack:** `langgraph>=0.2.0`, `langgraph-checkpoint-sqlite`, `langchain-core`, existing `ModelRouter` in `cjs/router/model_router.py`.

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Create | `cjs/graph/__init__.py` | package marker |
| Create | `cjs/graph/state.py` | `JuryState` TypedDict + `_merge_dicts` reducer |
| Create | `cjs/graph/nodes/__init__.py` | package marker |
| Create | `cjs/graph/nodes/scoring.py` | `_run_scoring_agent` helper, persona constants, 5 agent nodes |
| Create | `cjs/graph/nodes/consistency.py` | `consistency_checker_node` |
| Create | `cjs/graph/nodes/deliberation.py` | `deliberation_round_node` |
| Create | `cjs/graph/nodes/moderator.py` | `moderator_node` |
| Create | `cjs/graph/jury_graph.py` | `build_jury_graph()`, `_fan_out` routing function |
| Create | `cjs/schemas/verdict.py` | `Verdict` Pydantic model |
| Modify | `cjs/schemas/__init__.py` | export `Verdict` |
| Modify | `pyproject.toml` | add `langgraph`, `langgraph-checkpoint-sqlite` |
| Modify | `cjs/cli.py` | wire graph into `cjs run`; add `cjs resume` command |
| Create | `cjs/tests/test_scoring_node.py` | unit tests for `_run_scoring_agent` |
| Create | `cjs/tests/test_consistency_node.py` | unit tests for `consistency_checker_node` |
| Create | `cjs/tests/test_deliberation_node.py` | unit tests for `deliberation_round_node` |
| Create | `cjs/tests/test_moderator_node.py` | unit tests for `moderator_node` |
| Create | `cjs/tests/test_jury_graph.py` | end-to-end graph unit test (all nodes mocked) |
| Create | `cjs/tests/test_resume.py` | checkpoint + resume unit test |
| Create | `cjs/tests/test_jury_graph_integration.py` | live API integration test |

---

## Task 1: Add langgraph dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependencies**

In `pyproject.toml`, add to the `dependencies` list:

```toml
dependencies = [
    "typer",
    "pydantic",
    "pymupdf",
    "pyyaml",
    "rich",
    "anthropic>=0.49.0",
    "tenacity>=8.0.0",
    "structlog>=24.0.0",
    "opentelemetry-api>=1.25.0",
    "opentelemetry-sdk>=1.25.0",
    "opentelemetry-exporter-otlp-proto-grpc>=1.25.0",
    "langgraph>=0.2.0",
    "langgraph-checkpoint-sqlite>=2.0.0",
    "langchain-core>=0.2.0",
]
```

- [ ] **Step 2: Install**

```bash
pip install -e .
```

Expected: no errors. Verify:

```bash
python -c "from langgraph.graph import StateGraph; from langgraph.checkpoint.sqlite import SqliteSaver; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add langgraph, langgraph-checkpoint-sqlite, langchain-core"
```

---

## Task 2: Verdict schema

**Files:**
- Create: `cjs/schemas/verdict.py`
- Modify: `cjs/schemas/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `cjs/tests/test_verdict_schema.py`:

```python
import pytest
from pydantic import ValidationError
from cjs.schemas.verdict import Verdict


def test_verdict_valid():
    v = Verdict(
        winner_video="ad1.mp4",
        winner_rationale="Strong hook, clear CTA.",
        ranking=["ad1.mp4", "ad2.mp4"],
        per_video_notes={"ad1.mp4": "Best overall.", "ad2.mp4": "Weak ending."},
        confidence=0.87,
        flags_resolved=["agent claimed no CTA but dossier shows cta_detected=True"],
    )
    assert v.winner_video == "ad1.mp4"
    assert v.confidence == 0.87


def test_verdict_confidence_out_of_range():
    with pytest.raises(ValidationError):
        Verdict(
            winner_video="ad1.mp4",
            winner_rationale="x",
            ranking=["ad1.mp4"],
            per_video_notes={},
            confidence=1.5,
        )


def test_verdict_flags_resolved_defaults_empty():
    v = Verdict(
        winner_video="ad1.mp4",
        winner_rationale="x",
        ranking=["ad1.mp4"],
        per_video_notes={},
        confidence=0.9,
    )
    assert v.flags_resolved == []
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest cjs/tests/test_verdict_schema.py -v
```

Expected: `ImportError` — `cjs.schemas.verdict` does not exist.

- [ ] **Step 3: Create `cjs/schemas/verdict.py`**

```python
from pydantic import BaseModel, Field


class Verdict(BaseModel):
    winner_video: str
    winner_rationale: str
    ranking: list[str]
    per_video_notes: dict[str, str]
    confidence: float = Field(ge=0, le=1)
    flags_resolved: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Export from `cjs/schemas/__init__.py`**

Add to `cjs/schemas/__init__.py`:

```python
from cjs.schemas.verdict import Verdict

__all__ = [
    ...,  # existing exports
    "Verdict",
]
```

- [ ] **Step 5: Run to verify it passes**

```bash
pytest cjs/tests/test_verdict_schema.py -v
```

Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add cjs/schemas/verdict.py cjs/schemas/__init__.py cjs/tests/test_verdict_schema.py
git commit -m "feat: add Verdict schema"
```

---

## Task 3: JuryState

**Files:**
- Create: `cjs/graph/__init__.py`
- Create: `cjs/graph/state.py`
- Create: `cjs/graph/nodes/__init__.py`

- [ ] **Step 1: Write the failing test**

Create `cjs/tests/test_jury_state.py`:

```python
from cjs.graph.state import JuryState, _merge_dicts


def test_merge_dicts_combines_keys():
    a = {"agent_a": [{"video_path": "ad1.mp4"}]}
    b = {"agent_b": [{"video_path": "ad1.mp4"}]}
    result = _merge_dicts(a, b)
    assert "agent_a" in result
    assert "agent_b" in result


def test_merge_dicts_later_wins_on_collision():
    a = {"agent_a": ["old"]}
    b = {"agent_a": ["new"]}
    result = _merge_dicts(a, b)
    assert result["agent_a"] == ["new"]


def test_jury_state_is_typeddict():
    # TypedDict instances are plain dicts at runtime
    state: JuryState = {
        "run_id": "test",
        "brief": {},
        "rubric": {},
        "brand_rules": {},
        "video_dossiers": [],
        "initial_judgements": {},
        "consistency_report": None,
        "final_judgements": {},
        "verdict": None,
    }
    assert state["run_id"] == "test"
    assert state["initial_judgements"] == {}
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest cjs/tests/test_jury_state.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create package markers and `state.py`**

```bash
touch cjs/graph/__init__.py cjs/graph/nodes/__init__.py
```

Create `cjs/graph/state.py`:

```python
from typing import Annotated
from typing_extensions import TypedDict


def _merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}


class JuryState(TypedDict):
    run_id: str
    brief: dict
    rubric: dict
    brand_rules: dict
    video_dossiers: list[dict]
    initial_judgements: Annotated[dict[str, list[dict]], _merge_dicts]
    consistency_report: dict | None
    final_judgements: Annotated[dict[str, list[dict]], _merge_dicts]
    verdict: dict | None
```

- [ ] **Step 4: Run to verify it passes**

```bash
pytest cjs/tests/test_jury_state.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add cjs/graph/__init__.py cjs/graph/state.py cjs/graph/nodes/__init__.py cjs/tests/test_jury_state.py
git commit -m "feat: add JuryState TypedDict and _merge_dicts reducer"
```

---

## Task 4: Scoring helper (`_run_scoring_agent`)

**Files:**
- Create: `cjs/graph/nodes/scoring.py`
- Create: `cjs/tests/test_scoring_node.py`

### Shared test fixture

The following `MINIMAL_STATE` dict is used throughout this task's tests. Define it at the top of the test file:

```python
import json
import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock

from cjs.graph.nodes.scoring import _run_scoring_agent, AgentScoringError
from cjs.graph.state import JuryState


MINIMAL_STATE: JuryState = {
    "run_id": "test_run",
    "brief": {
        "brand": "TestBrand", "objective": "Drive awareness", "platform": "YouTube",
        "audience": "18-34 urban", "tone": "energetic", "key_message": "Be bold",
        "primary_kpi": "awareness", "emotional_territory": "excitement",
        "mandatory": ["logo visible by 3s"], "forbidden": ["competitor names"],
        "kpi_priority": {}, "constraints": {},
    },
    "rubric": {
        "name": "test", "description": "test rubric",
        "weights": {"storytelling": 0.5, "message_clarity": 0.5}, "hard_gates": {},
    },
    "brand_rules": {
        "brand_name": "TestBrand", "mandatory_elements": [], "forbidden_elements": [],
        "tone_keywords": [], "approved_claims": [], "prohibited_claims": [],
        "logo_visible_by_sec": 3.0, "disclaimer_required": False, "source": "brief_extracted",
    },
    "video_dossiers": [{
        "video_path": "/runs/test/input/videos/ad1.mp4",
        "duration_sec": 30.0, "transcript": "Buy now and save.", "hook_summary": "Bold open.",
        "scenes": [], "pacing": "fast", "logo_first_appearance_sec": 2.0,
        "cta_detected": True, "cta_text": "Buy now", "frames_analyzed": 6, "metadata": {},
    }],
    "initial_judgements": {},
    "consistency_report": None,
    "final_judgements": {},
    "verdict": None,
}

VALID_SCORING_RESPONSE = {
    "judgements": [{
        "agent_name": "creative_strategist",
        "agent_role": "Creative Director",
        "video_path": "ad1.mp4",
        "scores": {"storytelling": 8.0, "message_clarity": 7.5},
        "strengths": ["Strong hook"],
        "weaknesses": ["Logo late"],
        "evidence": ["0:02 — bold visual open"],
        "metric_comments": {},
        "confidence": 80,
        "token_bid": 0,
        "flags": [],
        "notes": "Solid concept.",
        "model_info": {},
    }],
    "conviction_allocation": {"ad1.mp4": 100},
}


def make_mock_router(response_dict: dict) -> MagicMock:
    from cjs.router.model_router import RouterResult
    router = MagicMock()
    result = RouterResult(
        content=json.dumps(response_dict),
        tokens_in=100, tokens_out=200, latency_ms=500.0, model="claude-sonnet-4-6",
    )
    router.call_structured.return_value = result
    router.call_extended_thinking.return_value = result
    return router
```

- [ ] **Step 1: Write the failing tests**

Append to `cjs/tests/test_scoring_node.py`:

```python
def test_run_scoring_agent_returns_initial_judgements():
    router = make_mock_router(VALID_SCORING_RESPONSE)
    config = {"configurable": {"router": router}}
    result = _run_scoring_agent(MINIMAL_STATE, config, "creative_strategist", "You are a CD.", extended_thinking=False)
    assert "initial_judgements" in result
    assert "creative_strategist" in result["initial_judgements"]
    assert len(result["initial_judgements"]["creative_strategist"]) == 1


def test_run_scoring_agent_populates_token_bid_from_conviction():
    router = make_mock_router(VALID_SCORING_RESPONSE)
    config = {"configurable": {"router": router}}
    result = _run_scoring_agent(MINIMAL_STATE, config, "creative_strategist", "You are a CD.", extended_thinking=False)
    judgement = result["initial_judgements"]["creative_strategist"][0]
    assert judgement["token_bid"] == 100


def test_run_scoring_agent_normalises_conviction_not_summing_to_100():
    bad_response = {
        "judgements": [VALID_SCORING_RESPONSE["judgements"][0].copy()],
        "conviction_allocation": {"ad1.mp4": 50},  # only 50, not 100
    }
    router = make_mock_router(bad_response)
    config = {"configurable": {"router": router}}
    result = _run_scoring_agent(MINIMAL_STATE, config, "creative_strategist", "You are a CD.", extended_thinking=False)
    judgement = result["initial_judgements"]["creative_strategist"][0]
    assert judgement["token_bid"] == 100  # normalised: 50/50 * 100


def test_run_scoring_agent_uses_call_structured_for_regular_agents():
    router = make_mock_router(VALID_SCORING_RESPONSE)
    config = {"configurable": {"router": router}}
    _run_scoring_agent(MINIMAL_STATE, config, "creative_strategist", "You are a CD.", extended_thinking=False)
    router.call_structured.assert_called_once()
    router.call_extended_thinking.assert_not_called()


def test_run_scoring_agent_uses_extended_thinking_for_brand_compliance():
    router = make_mock_router(VALID_SCORING_RESPONSE)
    config = {"configurable": {"router": router}}
    _run_scoring_agent(MINIMAL_STATE, config, "brand_compliance", "You are BC.", extended_thinking=True)
    router.call_extended_thinking.assert_called_once()
    router.call_structured.assert_not_called()


def test_run_scoring_agent_raises_on_invalid_json():
    from cjs.router.model_router import RouterResult
    router = MagicMock()
    router.call_structured.return_value = RouterResult(
        content="not valid json {{{{",
        tokens_in=10, tokens_out=10, latency_ms=0.0, model="claude-sonnet-4-6",
    )
    config = {"configurable": {"router": router}}
    with pytest.raises(AgentScoringError):
        _run_scoring_agent(MINIMAL_STATE, config, "creative_strategist", "You are a CD.", extended_thinking=False)
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest cjs/tests/test_scoring_node.py -v
```

Expected: `ImportError` — `cjs.graph.nodes.scoring` does not exist.

- [ ] **Step 3: Create `cjs/graph/nodes/scoring.py`**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ValidationError

from cjs.observability.logging import get_logger
from cjs.schemas.judgement import AgentJudgement

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from cjs.graph.state import JuryState

logger = get_logger()


class AgentScoringError(Exception):
    pass


class AgentScoringResponse(BaseModel):
    judgements: list[AgentJudgement]
    conviction_allocation: dict[str, int]


# ---------------------------------------------------------------------------
# Cross-cutting instructions injected into every scoring agent prompt.
# Source: docs/agent_system_prompts.md, "Cross-cutting instructions" section.
# ---------------------------------------------------------------------------
_CROSS_CUTTING = """
Your token_bid is your domain conviction. For each ad, bid higher on ads you would stake your
professional reputation on within your area of expertise. A bid of 0 means you have no confidence
this ad should win. A bid of 100 means this is the strongest example of your domain criteria you
have seen. Bid based on genuine assessment, not politeness.

Your confidence (0–100) reflects how clearly the evidence supports your scores — not how good the
ad is, but how certain you are in your assessment. Lower confidence if video quality, ambiguity of
claims, or missing information limits what you can verify. A compliance agent that cannot read a
disclaimer should not give 90 confidence.

In your evidence entries: cite timestamps, specific scenes, dialogue lines, or visual elements —
not impressions. "Logo appears at 0:04, within brief requirement" not "branding was present."
In your notes field: write as your persona would speak. Direct, specific, opinionated prose.
"""

# ---------------------------------------------------------------------------
# Per-agent persona constants.
# Copy each section verbatim from docs/agent_system_prompts.md.
# ---------------------------------------------------------------------------

# Copy "Creative Strategist" section from docs/agent_system_prompts.md
AGENT_PERSONAS: dict[str, str] = {
    "creative_strategist": """<COPY THE CREATIVE STRATEGIST SECTION FROM docs/agent_system_prompts.md>""",
    "brand_compliance": """<COPY THE BRAND COMPLIANCE AGENT SECTION FROM docs/agent_system_prompts.md>""",
    "audience_psychology": """<COPY THE AUDIENCE PSYCHOLOGY AGENT SECTION FROM docs/agent_system_prompts.md>""",
    "performance_marketer": """<COPY THE PERFORMANCE MARKETER AGENT SECTION FROM docs/agent_system_prompts.md>""",
    "storytelling_critic": """<COPY THE STORYTELLING CRITIC SECTION FROM docs/agent_system_prompts.md>""",
}


def _build_scoring_user_prompt(state: JuryState) -> str:
    brief = state["brief"]
    rubric = state["rubric"]

    brief_block = (
        f"Brand: {brief['brand']}\n"
        f"Objective: {brief['objective']}\n"
        f"Audience: {brief['audience']}\n"
        f"Platform: {brief['platform']}\n"
        f"Tone: {brief['tone']}\n"
        f"Key message: {brief['key_message']}\n"
        f"Primary KPI: {brief['primary_kpi']}\n"
    )
    if brief.get("mandatory"):
        brief_block += f"Mandatory elements: {', '.join(brief['mandatory'])}\n"
    if brief.get("forbidden"):
        brief_block += f"Forbidden elements: {', '.join(brief['forbidden'])}\n"

    weights = rubric.get("weights", {})
    rubric_block = "\n".join(f"  - {dim}: weight {w:.2f}" for dim, w in weights.items())

    dossier_blocks = []
    for d in state["video_dossiers"]:
        filename = Path(d["video_path"]).name
        cta_str = "detected" if d.get("cta_detected") else "not detected"
        if d.get("cta_text"):
            cta_str += f" — {d['cta_text']}"
        block = (
            f"### {filename}\n"
            f"Duration: {d['duration_sec']}s | Pacing: {d.get('pacing', 'unknown')}\n"
            f"Transcript: {d.get('transcript') or '(none)'}\n"
            f"Hook: {d.get('hook_summary') or '(none)'}\n"
            f"Logo appears at: {d.get('logo_first_appearance_sec') or 'not detected'}s\n"
            f"CTA: {cta_str}\n"
        )
        if d.get("scenes"):
            scene_lines = [
                f"  [{s['timestamp_sec']:.1f}s] {s['short_text_description']}"
                for s in d["scenes"]
            ]
            block += "Scenes:\n" + "\n".join(scene_lines) + "\n"
        dossier_blocks.append(block)

    filenames = [Path(d["video_path"]).name for d in state["video_dossiers"]]
    conviction_hint = ", ".join(f'"{v}": <integer>' for v in filenames)

    return (
        f"## Brief\n{brief_block}\n"
        f"## Scoring dimensions\n{rubric_block}\n\n"
        f"## Videos to evaluate\n{''.join(dossier_blocks)}\n"
        f"conviction_allocation must sum to 100 across all videos: {{{conviction_hint}}}\n"
        f"Allocate higher conviction to the video you rate highest in your domain."
    )


def _run_scoring_agent(
    state: JuryState,
    config: RunnableConfig,
    agent_name: str,
    persona: str,
    *,
    extended_thinking: bool = False,
) -> dict:
    router = config["configurable"]["router"]
    system_prompt = persona + "\n\n" + _CROSS_CUTTING
    user_prompt = _build_scoring_user_prompt(state)
    node = f"scoring_{agent_name}"

    if extended_thinking:
        # Brand Compliance: extended thinking returns JSON in text block
        result = router.call_extended_thinking(system_prompt, user_prompt, node=node, agent=agent_name)
        raw = result.content
    else:
        result = router.call_structured(
            system_prompt,
            user_prompt,
            node=node,
            schema=AgentScoringResponse.model_json_schema(),
            schema_name="agent_scoring_response",
            agent=agent_name,
        )
        raw = result.content

    try:
        data = json.loads(raw)
        response = AgentScoringResponse(**data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise AgentScoringError(
            f"Agent {agent_name} returned unparseable response: {exc}"
        ) from exc

    # Normalise conviction_allocation to sum 100
    total = sum(response.conviction_allocation.values()) or 1
    if total != 100:
        logger.warning(
            "conviction_normalised", agent=agent_name, original_total=total
        )
        normalised = {k: round(v / total * 100) for k, v in response.conviction_allocation.items()}
    else:
        normalised = dict(response.conviction_allocation)

    # Populate token_bid from conviction allocation (match by filename)
    for judgement in response.judgements:
        filename = Path(judgement.video_path).name
        judgement.token_bid = normalised.get(filename, normalised.get(judgement.video_path, 0))

    return {"initial_judgements": {agent_name: [j.model_dump() for j in response.judgements]}}
```

> **Important:** After pasting the code above, replace the `<COPY ... >` placeholders in `AGENT_PERSONAS` with the actual text from each named section in `docs/agent_system_prompts.md`. Each section starts with a `##` header and ends before the next `##`. Copy the triple-quoted text block that follows the `Persona:` line — that is the system prompt text.

- [ ] **Step 4: Run to verify tests pass**

```bash
pytest cjs/tests/test_scoring_node.py -v
```

Expected: 6 PASSED.

- [ ] **Step 5: Commit**

```bash
git add cjs/graph/nodes/scoring.py cjs/tests/test_scoring_node.py
git commit -m "feat: add _run_scoring_agent helper with conviction normalisation"
```

---

## Task 5: Five agent node functions

**Files:**
- Modify: `cjs/graph/nodes/scoring.py` (append node functions)
- Modify: `cjs/tests/test_scoring_node.py` (append tests)

- [ ] **Step 1: Write failing tests**

Append to `cjs/tests/test_scoring_node.py`:

```python
from cjs.graph.nodes.scoring import (
    creative_strategist_node,
    brand_compliance_node,
    audience_psychology_node,
    performance_marketer_node,
    storytelling_critic_node,
)


def test_creative_strategist_node_calls_helper():
    router = make_mock_router(VALID_SCORING_RESPONSE)
    config = {"configurable": {"router": router}}
    result = creative_strategist_node(MINIMAL_STATE, config)
    assert "creative_strategist" in result["initial_judgements"]
    router.call_structured.assert_called_once()


def test_brand_compliance_node_uses_extended_thinking():
    bc_response = {
        "judgements": [{**VALID_SCORING_RESPONSE["judgements"][0], "agent_name": "brand_compliance"}],
        "conviction_allocation": {"ad1.mp4": 100},
    }
    router = make_mock_router(bc_response)
    config = {"configurable": {"router": router}}
    result = brand_compliance_node(MINIMAL_STATE, config)
    assert "brand_compliance" in result["initial_judgements"]
    router.call_extended_thinking.assert_called_once()


def test_all_five_agent_nodes_exist_and_return_correct_key():
    nodes = [
        (creative_strategist_node, "creative_strategist"),
        (audience_psychology_node, "audience_psychology"),
        (performance_marketer_node, "performance_marketer"),
        (storytelling_critic_node, "storytelling_critic"),
    ]
    for node_fn, expected_key in nodes:
        named_response = {
            "judgements": [{**VALID_SCORING_RESPONSE["judgements"][0], "agent_name": expected_key}],
            "conviction_allocation": {"ad1.mp4": 100},
        }
        router = make_mock_router(named_response)
        config = {"configurable": {"router": router}}
        result = node_fn(MINIMAL_STATE, config)
        assert expected_key in result["initial_judgements"], f"Missing key for {expected_key}"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest cjs/tests/test_scoring_node.py::test_creative_strategist_node_calls_helper -v
```

Expected: `ImportError`.

- [ ] **Step 3: Append node functions to `cjs/graph/nodes/scoring.py`**

```python
# ---------------------------------------------------------------------------
# Agent node functions — each is a thin wrapper around _run_scoring_agent
# ---------------------------------------------------------------------------

def creative_strategist_node(state: JuryState, config: RunnableConfig) -> dict:
    return _run_scoring_agent(
        state, config, "creative_strategist",
        AGENT_PERSONAS["creative_strategist"], extended_thinking=False,
    )


def brand_compliance_node(state: JuryState, config: RunnableConfig) -> dict:
    return _run_scoring_agent(
        state, config, "brand_compliance",
        AGENT_PERSONAS["brand_compliance"], extended_thinking=True,
    )


def audience_psychology_node(state: JuryState, config: RunnableConfig) -> dict:
    return _run_scoring_agent(
        state, config, "audience_psychology",
        AGENT_PERSONAS["audience_psychology"], extended_thinking=False,
    )


def performance_marketer_node(state: JuryState, config: RunnableConfig) -> dict:
    return _run_scoring_agent(
        state, config, "performance_marketer",
        AGENT_PERSONAS["performance_marketer"], extended_thinking=False,
    )


def storytelling_critic_node(state: JuryState, config: RunnableConfig) -> dict:
    return _run_scoring_agent(
        state, config, "storytelling_critic",
        AGENT_PERSONAS["storytelling_critic"], extended_thinking=False,
    )
```

- [ ] **Step 4: Run to verify all pass**

```bash
pytest cjs/tests/test_scoring_node.py -v
```

Expected: all PASSED (6 original + 3 new).

- [ ] **Step 5: Commit**

```bash
git add cjs/graph/nodes/scoring.py cjs/tests/test_scoring_node.py
git commit -m "feat: add five jury agent node functions"
```

---

## Task 6: ConsistencyChecker node

**Files:**
- Create: `cjs/graph/nodes/consistency.py`
- Create: `cjs/tests/test_consistency_node.py`

- [ ] **Step 1: Write the failing tests**

Create `cjs/tests/test_consistency_node.py`:

```python
import json
import pytest
from unittest.mock import MagicMock

from cjs.graph.nodes.consistency import consistency_checker_node
from cjs.router.model_router import RouterResult


DOSSIER = {
    "video_path": "/runs/test/input/videos/ad1.mp4",
    "duration_sec": 30.0, "transcript": "Buy now.",
    "hook_summary": "Bold.", "scenes": [], "pacing": "fast",
    "logo_first_appearance_sec": 2.0, "cta_detected": True,
    "cta_text": "Buy now", "frames_analyzed": 6, "metadata": {},
}

JUDGEMENT_WITH_FACTUAL_ERROR = {
    "agent_name": "creative_strategist", "agent_role": None,
    "video_path": "ad1.mp4",
    "scores": {"storytelling": 8.0}, "strengths": [], "weaknesses": [],
    "evidence": [], "metric_comments": {},
    "confidence": 80, "token_bid": 100, "flags": [],
    "notes": "No CTA was detected in this ad.",  # contradicts dossier cta_detected=True
    "model_info": {},
}

STATE = {
    "run_id": "test", "brief": {}, "rubric": {}, "brand_rules": {},
    "video_dossiers": [DOSSIER],
    "initial_judgements": {"creative_strategist": [JUDGEMENT_WITH_FACTUAL_ERROR]},
    "consistency_report": None, "final_judgements": {}, "verdict": None,
}

VALID_REPORT = {
    "flags": [{
        "agent": "creative_strategist",
        "video": "ad1.mp4",
        "claim": "No CTA was detected in this ad.",
        "contradicting_evidence": "dossier.cta_detected=True, cta_text='Buy now'",
        "classification": "FACTUAL_CONTRADICTION",
    }],
    "checked_agents": ["creative_strategist"],
    "checked_videos": ["ad1.mp4"],
}


def make_mock_router(response: dict) -> MagicMock:
    router = MagicMock()
    router.call_structured.return_value = RouterResult(
        content=json.dumps(response),
        tokens_in=50, tokens_out=100, latency_ms=300.0, model="claude-sonnet-4-6",
    )
    return router


def test_consistency_checker_returns_report():
    router = make_mock_router(VALID_REPORT)
    config = {"configurable": {"router": router}}
    result = consistency_checker_node(STATE, config)
    assert "consistency_report" in result
    report = result["consistency_report"]
    assert len(report["flags"]) == 1
    assert report["flags"][0]["classification"] == "FACTUAL_CONTRADICTION"


def test_consistency_checker_uses_call_structured():
    router = make_mock_router(VALID_REPORT)
    config = {"configurable": {"router": router}}
    consistency_checker_node(STATE, config)
    router.call_structured.assert_called_once()


def test_consistency_checker_no_flags_when_clean():
    clean_report = {"flags": [], "checked_agents": ["creative_strategist"], "checked_videos": ["ad1.mp4"]}
    router = make_mock_router(clean_report)
    config = {"configurable": {"router": router}}
    result = consistency_checker_node(STATE, config)
    assert result["consistency_report"]["flags"] == []
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest cjs/tests/test_consistency_node.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `cjs/graph/nodes/consistency.py`**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

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
```

- [ ] **Step 4: Run to verify tests pass**

```bash
pytest cjs/tests/test_consistency_node.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add cjs/graph/nodes/consistency.py cjs/tests/test_consistency_node.py
git commit -m "feat: add ConsistencyChecker node"
```

---

## Task 7: Deliberation round node

**Files:**
- Create: `cjs/graph/nodes/deliberation.py`
- Create: `cjs/tests/test_deliberation_node.py`

- [ ] **Step 1: Write the failing tests**

Create `cjs/tests/test_deliberation_node.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, call

from cjs.graph.nodes.deliberation import deliberation_round_node
from cjs.router.model_router import RouterResult

JUDGEMENT = {
    "agent_name": "creative_strategist", "agent_role": None,
    "video_path": "ad1.mp4", "scores": {"storytelling": 8.0},
    "strengths": [], "weaknesses": [], "evidence": [], "metric_comments": {},
    "confidence": 80, "token_bid": 100, "flags": [], "notes": "Good hook.", "model_info": {},
}

CONSISTENCY_REPORT_WITH_FLAG = {
    "flags": [{
        "agent": "brand_compliance",
        "video": "ad1.mp4",
        "claim": "No CTA detected.",
        "contradicting_evidence": "dossier.cta_detected=True",
        "classification": "FACTUAL_CONTRADICTION",
    }],
    "checked_agents": ["creative_strategist", "brand_compliance"],
    "checked_videos": ["ad1.mp4"],
}

ALL_AGENTS = ["creative_strategist", "brand_compliance", "audience_psychology",
              "performance_marketer", "storytelling_critic"]

STATE = {
    "run_id": "test", "brief": {}, "rubric": {}, "brand_rules": {},
    "video_dossiers": [{"video_path": "/runs/test/input/videos/ad1.mp4", "duration_sec": 30.0,
                        "transcript": "", "hook_summary": "", "scenes": [], "pacing": "fast",
                        "logo_first_appearance_sec": None, "cta_detected": False, "cta_text": None,
                        "frames_analyzed": 0, "metadata": {}}],
    "initial_judgements": {agent: [JUDGEMENT.copy()] for agent in ALL_AGENTS},
    "consistency_report": CONSISTENCY_REPORT_WITH_FLAG,
    "final_judgements": {}, "verdict": None,
}


def make_mock_router(revised_judgement: dict | None = None) -> MagicMock:
    j = revised_judgement or JUDGEMENT
    router = MagicMock()
    router.call_structured.return_value = RouterResult(
        content=json.dumps({"judgements": [j]}),
        tokens_in=50, tokens_out=100, latency_ms=200.0, model="claude-sonnet-4-6",
    )
    return router


def test_deliberation_calls_all_five_agents():
    router = make_mock_router()
    config = {"configurable": {"router": router}}
    deliberation_round_node(STATE, config)
    assert router.call_structured.call_count == 5


def test_deliberation_returns_final_judgements_for_all_agents():
    router = make_mock_router()
    config = {"configurable": {"router": router}}
    result = deliberation_round_node(STATE, config)
    assert set(result["final_judgements"].keys()) == set(ALL_AGENTS)


def test_deliberation_flagged_agent_prompt_contains_flag():
    router = make_mock_router()
    config = {"configurable": {"router": router}}
    deliberation_round_node(STATE, config)
    # brand_compliance was flagged — its call should include flag info
    calls = router.call_structured.call_args_list
    # calls are in order of ALL_AGENTS; brand_compliance is index 1
    bc_call_user_prompt = calls[1].kwargs.get("user") or calls[1].args[1]
    assert "No CTA detected" in bc_call_user_prompt


def test_deliberation_unflagged_agent_prompt_has_no_flags_section():
    router = make_mock_router()
    config = {"configurable": {"router": router}}
    deliberation_round_node(STATE, config)
    calls = router.call_structured.call_args_list
    # creative_strategist is index 0, has no flags
    cs_call_user_prompt = calls[0].kwargs.get("user") or calls[0].args[1]
    assert "Flags directed at you" not in cs_call_user_prompt
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest cjs/tests/test_deliberation_node.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `cjs/graph/nodes/deliberation.py`**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from cjs.schemas.judgement import AgentJudgement
from cjs.graph.nodes.scoring import AGENT_PERSONAS, _CROSS_CUTTING

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
```

- [ ] **Step 4: Run to verify tests pass**

```bash
pytest cjs/tests/test_deliberation_node.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add cjs/graph/nodes/deliberation.py cjs/tests/test_deliberation_node.py
git commit -m "feat: add deliberation round node"
```

---

## Task 8: Moderator node

**Files:**
- Create: `cjs/graph/nodes/moderator.py`
- Create: `cjs/tests/test_moderator_node.py`

- [ ] **Step 1: Write the failing tests**

Create `cjs/tests/test_moderator_node.py`:

```python
import json
import pytest
from unittest.mock import MagicMock

from cjs.graph.nodes.moderator import moderator_node
from cjs.schemas.verdict import Verdict
from cjs.router.model_router import RouterResult

JUDGEMENT = {
    "agent_name": "creative_strategist", "agent_role": None,
    "video_path": "ad1.mp4", "scores": {"storytelling": 8.0},
    "strengths": [], "weaknesses": [], "evidence": [], "metric_comments": {},
    "confidence": 80, "token_bid": 100, "flags": [], "notes": "Strong hook.", "model_info": {},
}

ALL_AGENTS = ["creative_strategist", "brand_compliance", "audience_psychology",
              "performance_marketer", "storytelling_critic"]

STATE = {
    "run_id": "test",
    "brief": {
        "brand": "TestBrand", "objective": "Drive awareness", "platform": "YouTube",
        "audience": "18-34", "tone": "energetic", "key_message": "Be bold",
        "primary_kpi": "awareness", "emotional_territory": None,
        "mandatory": [], "forbidden": [], "kpi_priority": {}, "constraints": {},
    },
    "rubric": {"name": "test", "description": "", "weights": {"storytelling": 1.0}, "hard_gates": {}},
    "brand_rules": {},
    "video_dossiers": [{"video_path": "/runs/test/input/videos/ad1.mp4", "duration_sec": 30.0,
                        "transcript": "", "hook_summary": "", "scenes": [], "pacing": "fast",
                        "logo_first_appearance_sec": None, "cta_detected": False, "cta_text": None,
                        "frames_analyzed": 0, "metadata": {}}],
    "initial_judgements": {},
    "consistency_report": {"flags": [], "checked_agents": [], "checked_videos": []},
    "final_judgements": {agent: [JUDGEMENT.copy()] for agent in ALL_AGENTS},
    "verdict": None,
}

VALID_VERDICT = {
    "winner_video": "ad1.mp4",
    "winner_rationale": "Strongest creative concept with clear CTA.",
    "ranking": ["ad1.mp4"],
    "per_video_notes": {"ad1.mp4": "Best overall."},
    "confidence": 0.87,
    "flags_resolved": [],
}


def make_mock_router(verdict_dict: dict) -> MagicMock:
    router = MagicMock()
    router.call_extended_thinking.return_value = RouterResult(
        content=json.dumps(verdict_dict),
        tokens_in=500, tokens_out=1000, latency_ms=2000.0, model="claude-opus-4-7",
        thinking="<thinking>deliberation...</thinking>",
    )
    return router


def test_moderator_returns_valid_verdict():
    router = make_mock_router(VALID_VERDICT)
    config = {"configurable": {"router": router}}
    result = moderator_node(STATE, config)
    assert "verdict" in result
    verdict = Verdict(**result["verdict"])
    assert verdict.winner_video == "ad1.mp4"
    assert 0 <= verdict.confidence <= 1


def test_moderator_uses_extended_thinking():
    router = make_mock_router(VALID_VERDICT)
    config = {"configurable": {"router": router}}
    moderator_node(STATE, config)
    router.call_extended_thinking.assert_called_once()


def test_moderator_includes_winner_video_in_ranking():
    router = make_mock_router(VALID_VERDICT)
    config = {"configurable": {"router": router}}
    result = moderator_node(STATE, config)
    verdict = Verdict(**result["verdict"])
    assert verdict.winner_video in verdict.ranking
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest cjs/tests/test_moderator_node.py -v
```

Expected: `ImportError`.

- [ ] **Step 3: Create `cjs/graph/nodes/moderator.py`**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from cjs.schemas.verdict import Verdict

if TYPE_CHECKING:
    from langchain_core.runnables import RunnableConfig
    from cjs.graph.state import JuryState

# Copy "Moderator" section verbatim from docs/agent_system_prompts.md
_MODERATOR_PERSONA = """<COPY THE MODERATOR SECTION FROM docs/agent_system_prompts.md>"""

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
    if state.get("consistency_report"):
        flags = state["consistency_report"].get("flags", [])
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
```

> **Important:** Replace the `<COPY ... >` placeholder with the Moderator section from `docs/agent_system_prompts.md`.

- [ ] **Step 4: Run to verify tests pass**

```bash
pytest cjs/tests/test_moderator_node.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add cjs/graph/nodes/moderator.py cjs/tests/test_moderator_node.py
git commit -m "feat: add Moderator node with extended thinking"
```

---

## Task 9: `jury_graph.py` and end-to-end graph unit test

**Files:**
- Create: `cjs/graph/jury_graph.py`
- Create: `cjs/tests/test_jury_graph.py`
- Create: `cjs/tests/test_resume.py`

- [ ] **Step 1: Write the failing graph unit test**

Create `cjs/tests/test_jury_graph.py`:

```python
import pytest
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

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


def _mock_moderator(state, config):
    return {"verdict": FAKE_VERDICT}


def _build_mock_graph():
    """Build a graph wired identically to build_jury_graph() but with mock nodes."""
    from typing import Annotated
    from typing_extensions import TypedDict

    graph = StateGraph(JuryState)
    for name in AGENT_NAMES:
        graph.add_node(f"{name}_node", _make_mock_agent(name))
    graph.add_node("consistency_checker_node", _mock_consistency)
    graph.add_node("deliberation_round_node", _mock_deliberation)
    graph.add_node("moderator_node", _mock_moderator)
    graph.add_conditional_edges(START, _fan_out)
    for name in AGENT_NAMES:
        graph.add_edge(f"{name}_node", "consistency_checker_node")
    graph.add_edge("consistency_checker_node", "deliberation_round_node")
    graph.add_edge("deliberation_round_node", "moderator_node")
    graph.add_edge("moderator_node", END)
    return graph


def test_all_five_agents_run_and_results_merged():
    saver = SqliteSaver.from_conn_string(":memory:")
    compiled = _build_mock_graph().compile(checkpointer=saver)
    result = compiled.invoke(
        MINIMAL_STATE,
        config={"configurable": {"thread_id": "test_thread_1"}},
    )
    assert set(result["initial_judgements"].keys()) == set(AGENT_NAMES)


def test_graph_reaches_moderator_and_produces_verdict():
    saver = SqliteSaver.from_conn_string(":memory:")
    compiled = _build_mock_graph().compile(checkpointer=saver)
    result = compiled.invoke(
        MINIMAL_STATE,
        config={"configurable": {"thread_id": "test_thread_2"}},
    )
    assert result["verdict"] is not None
    assert result["verdict"]["winner_video"] == "ad1.mp4"


def test_build_jury_graph_compiles_without_error():
    graph = build_jury_graph()
    saver = SqliteSaver.from_conn_string(":memory:")
    compiled = graph.compile(checkpointer=saver)
    assert compiled is not None
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest cjs/tests/test_jury_graph.py -v
```

Expected: `ImportError` — `cjs.graph.jury_graph` does not exist.

- [ ] **Step 3: Create `cjs/graph/jury_graph.py`**

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
```

- [ ] **Step 4: Run to verify graph tests pass**

```bash
pytest cjs/tests/test_jury_graph.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Write the resume test**

Create `cjs/tests/test_resume.py`:

```python
import tempfile, os
import pytest
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

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
    """Invoking a completed graph with same thread_id returns the same verdict."""
    call_counts: dict[str, int] = {}

    def make_node(name):
        def node(state, config):
            call_counts[name] = call_counts.get(name, 0) + 1
            return {}
        return node

    graph = StateGraph(JuryState)
    for name in AGENT_NAMES:
        graph.add_node(name, make_node(name))
    graph.add_node("consistency_checker_node", lambda s, c: {"consistency_report": {"flags": [], "checked_agents": [], "checked_videos": []}})
    graph.add_node("deliberation_round_node", lambda s, c: {"final_judgements": {}})
    graph.add_node("moderator_node", lambda s, c: {"verdict": {"winner_video": "ad1.mp4", "winner_rationale": "x", "ranking": [], "per_video_notes": {}, "confidence": 0.9, "flags_resolved": []}})
    graph.add_conditional_edges(START, _fan_out)
    for name in AGENT_NAMES:
        graph.add_edge(name, "consistency_checker_node")
    graph.add_edge("consistency_checker_node", "deliberation_round_node")
    graph.add_edge("deliberation_round_node", "moderator_node")
    graph.add_edge("moderator_node", END)

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "checkpoints.db")
        saver = SqliteSaver.from_conn_string(db_path)
        compiled = graph.compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": "resume_test_thread"}}

        result1 = compiled.invoke(MINIMAL_STATE, config=cfg)
        first_run_counts = dict(call_counts)

        # Second invoke with same thread_id — graph is complete, nodes should NOT re-run
        result2 = compiled.invoke(MINIMAL_STATE, config=cfg)

        assert result1["verdict"] == result2["verdict"]
        # Node call counts should not have increased
        for name in AGENT_NAMES:
            assert call_counts.get(name, 0) == first_run_counts.get(name, 0)
```

- [ ] **Step 6: Run resume test**

```bash
pytest cjs/tests/test_resume.py -v
```

Expected: 1 PASSED.

- [ ] **Step 7: Commit**

```bash
git add cjs/graph/jury_graph.py cjs/tests/test_jury_graph.py cjs/tests/test_resume.py
git commit -m "feat: add jury_graph with Send-based fan-out and SqliteSaver checkpointing"
```

---

## Task 10: Wire graph into `cjs run` + add `cjs resume` command

**Files:**
- Modify: `cjs/cli.py`

- [ ] **Step 1: Write failing CLI tests**

Append to `cjs/tests/test_cli_commands.py` (find the `test_run_*` block and add after it):

```python
def test_resume_missing_run_exits_nonzero(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from cjs.cli import app

    runner = CliRunner()
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(app, ["resume", "nonexistent_run_id"])
    assert result.exit_code != 0


def test_resume_missing_checkpoint_exits_nonzero(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from cjs.cli import app

    runner = CliRunner()
    monkeypatch.setenv("HOME", str(tmp_path))
    # Create a run folder but no checkpoints.db
    run_folder = tmp_path / ".cjs" / "runs" / "20260518_120000_abcd"
    run_folder.mkdir(parents=True)
    result = runner.invoke(app, ["resume", "20260518_120000_abcd"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest cjs/tests/test_cli_commands.py::test_resume_missing_run_exits_nonzero \
       cjs/tests/test_cli_commands.py::test_resume_missing_checkpoint_exits_nonzero -v
```

Expected: FAILED (command does not exist yet).

- [ ] **Step 3: Wire graph into `cjs run`**

In `cjs/cli.py`, locate the block that starts with:
```python
    if json_mode:
        output_result(
            {
                "status": "ok",
                "run_id": run_id,
                ...
                "next_stage": "jury_swarm",
            },
            json_mode=True,
        )
        return
```

Replace that entire block with:

```python
    # --- Phase 11: LangGraph jury swarm ---
    import json as _json
    from langgraph.checkpoint.sqlite import SqliteSaver
    from cjs.graph.jury_graph import build_jury_graph
    from cjs.graph.state import JuryState

    if not json_mode:
        typer.echo("[Jury] Running jury swarm...")

    initial_jury_state: JuryState = {
        "run_id": run_id,
        "brief": parsed_brief.model_dump(),
        "rubric": rubric.model_dump(),
        "brand_rules": brand_rules.model_dump(),
        "video_dossiers": [d.model_dump() for d in dossiers],
        "initial_judgements": {},
        "consistency_report": None,
        "final_judgements": {},
        "verdict": None,
    }

    checkpoints_db = run_folder / "checkpoints.db"
    saver = SqliteSaver.from_conn_string(str(checkpoints_db))
    compiled = build_jury_graph().compile(checkpointer=saver)
    thread_config = {"configurable": {"thread_id": run_id, "router": router}}

    try:
        final_state = compiled.invoke(initial_jury_state, config=thread_config)
    except Exception as exc:
        if json_mode:
            output_result({"status": "error", "run_id": run_id, "error": str(exc)}, json_mode=True)
        else:
            typer.secho(f"Jury swarm failed: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    if final_state.get("verdict"):
        verdict_path = run_folder / "results" / "verdict.json"
        verdict_path.write_text(_json.dumps(final_state["verdict"], indent=2))
        if not json_mode:
            typer.secho(
                f"Winner: {final_state['verdict']['winner_video']}", fg=typer.colors.GREEN
            )

    if not json_mode:
        typer.secho("Run complete.", fg=typer.colors.GREEN)

    if json_mode:
        output_result(
            {
                "status": "ok",
                "run_id": run_id,
                "run_folder": str(run_folder),
                "winner": final_state.get("verdict", {}).get("winner_video"),
                "verdict": str(run_folder / "results" / "verdict.json"),
            },
            json_mode=True,
        )
```

- [ ] **Step 4: Add `cjs resume` command**

In `cjs/cli.py`, before the `if __name__ == "__main__":` line (or at the end of the command group), add:

```python
@app.command()
def resume(
    run_id: str = typer.Argument(..., help="Run ID to resume (the folder name under runs/)."),
    json_output: bool = typer.Option(False, "--json", help="Output result as JSON."),
) -> None:
    """Resume a run from its last LangGraph checkpoint."""
    import json as _json
    from langgraph.checkpoint.sqlite import SqliteSaver
    from cjs.graph.jury_graph import build_jury_graph

    config = load_config()
    run_folder = get_runs_dir(config) / run_id

    if not run_folder.exists() or not run_folder.is_dir():
        message = f"Run not found: {run_id}"
        if json_output:
            output_result({"ok": False, "error": message, "run_id": run_id}, json_mode=True)
        else:
            typer.secho(f"Error: {message}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    checkpoints_db = run_folder / "checkpoints.db"
    if not checkpoints_db.exists():
        message = f"No checkpoint found for run: {run_id}. Was this run started with Phase 11?"
        if json_output:
            output_result({"ok": False, "error": message, "run_id": run_id}, json_mode=True)
        else:
            typer.secho(f"Error: {message}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    router = ModelRouter(run_id=run_id, run_folder=run_folder, config=config)
    saver = SqliteSaver.from_conn_string(str(checkpoints_db))
    compiled = build_jury_graph().compile(checkpointer=saver)
    thread_config = {"configurable": {"thread_id": run_id, "router": router}}

    if not json_output:
        typer.echo(f"Resuming run {run_id}...")

    try:
        final_state = compiled.invoke(None, config=thread_config)
    except Exception as exc:
        if json_output:
            output_result({"ok": False, "error": str(exc), "run_id": run_id}, json_mode=True)
        else:
            typer.secho(f"Resume failed: {exc}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)

    if final_state and final_state.get("verdict"):
        verdict_path = run_folder / "results" / "verdict.json"
        verdict_path.write_text(_json.dumps(final_state["verdict"], indent=2))

    if json_output:
        output_result(
            {
                "ok": True, "run_id": run_id,
                "winner": (final_state or {}).get("verdict", {}).get("winner_video"),
            },
            json_mode=True,
        )
    else:
        winner = (final_state or {}).get("verdict", {}).get("winner_video", "unknown")
        typer.secho(f"Run {run_id} complete. Winner: {winner}", fg=typer.colors.GREEN)
```

- [ ] **Step 5: Run CLI tests**

```bash
pytest cjs/tests/test_cli_commands.py::test_resume_missing_run_exits_nonzero \
       cjs/tests/test_cli_commands.py::test_resume_missing_checkpoint_exits_nonzero -v
```

Expected: 2 PASSED.

- [ ] **Step 6: Run the full test suite to check for regressions**

```bash
pytest cjs/ -v -m "not integration"
```

Expected: all PASSED (no regressions).

- [ ] **Step 7: Commit**

```bash
git add cjs/cli.py cjs/tests/test_cli_commands.py
git commit -m "feat: wire jury graph into cjs run and add cjs resume command"
```

---

## Task 11: Integration test (write only — do not run)

**Files:**
- Create: `cjs/tests/test_jury_graph_integration.py`

- [ ] **Step 1: Write integration test**

Create `cjs/tests/test_jury_graph_integration.py`:

```python
"""
Integration test for the full LangGraph jury swarm.
Requires a live ANTHROPIC_API_KEY. Run with:
    pytest cjs/tests/test_jury_graph_integration.py -v -m integration
"""
import os
import tempfile
import pytest
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from cjs.config import Settings, ModelsConfig, AuthConfig, LimitsConfig, RunConfig
from cjs.graph.jury_graph import build_jury_graph
from cjs.graph.state import JuryState
from cjs.router.model_router import ModelRouter
from cjs.schemas.verdict import Verdict


@pytest.mark.integration
def test_full_jury_swarm_produces_verdict():
    """Full graph with live API — two minimal video dossiers, verify verdict produced."""
    config = Settings(
        models=ModelsConfig(
            text="claude-haiku-4-5-20251001",
            vision="claude-haiku-4-5-20251001",
            extended_thinking="claude-haiku-4-5-20251001",  # use Haiku to keep cost low
        ),
        auth=AuthConfig(api_key_env="ANTHROPIC_API_KEY"),
        limits=LimitsConfig(
            max_videos=2, max_duration_sec=60, max_frames=6,
            max_pdf_pages=10,
        ),
        run=RunConfig(out_dir="~/.cjs/runs"),
        langsmith=None,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        run_folder = Path(tmpdir)
        run_id = "integration_test_run"
        router = ModelRouter(run_id=run_id, run_folder=run_folder, config=config)

        initial_state: JuryState = {
            "run_id": run_id,
            "brief": {
                "brand": "TestBrand", "objective": "Drive brand awareness",
                "platform": "YouTube", "audience": "18-34 urban consumers",
                "tone": "energetic and bold", "key_message": "Choose boldness",
                "primary_kpi": "awareness", "emotional_territory": "excitement",
                "mandatory": ["show logo by 3 seconds"], "forbidden": ["competitor names"],
                "kpi_priority": {}, "constraints": {},
            },
            "rubric": {
                "name": "awareness", "description": "Awareness campaign rubric",
                "weights": {
                    "storytelling": 0.3, "message_clarity": 0.3,
                    "audience_resonance": 0.2, "emotional_impact": 0.2,
                },
                "hard_gates": {},
            },
            "brand_rules": {
                "brand_name": "TestBrand", "mandatory_elements": ["logo visible by 3s"],
                "forbidden_elements": [], "tone_keywords": ["energetic"],
                "approved_claims": [], "prohibited_claims": [],
                "logo_visible_by_sec": 3.0, "disclaimer_required": False,
                "source": "brief_extracted",
            },
            "video_dossiers": [
                {
                    "video_path": "/test/ad1.mp4", "duration_sec": 30.0,
                    "transcript": "Be bold. Choose TestBrand. Shop now.",
                    "hook_summary": "Quick cut to product with energetic music.",
                    "scenes": [
                        {"order": 0, "timestamp_sec": 0.0,
                         "short_text_description": "Product close-up", "frame_image_paths": []},
                        {"order": 1, "timestamp_sec": 15.0,
                         "short_text_description": "Brand logo reveal", "frame_image_paths": []},
                    ],
                    "pacing": "fast", "logo_first_appearance_sec": 2.5,
                    "cta_detected": True, "cta_text": "Shop now",
                    "frames_analyzed": 6, "metadata": {},
                },
                {
                    "video_path": "/test/ad2.mp4", "duration_sec": 25.0,
                    "transcript": "Feel the difference with TestBrand.",
                    "hook_summary": "Slow reveal, emotional music.",
                    "scenes": [
                        {"order": 0, "timestamp_sec": 0.0,
                         "short_text_description": "Lifestyle shot", "frame_image_paths": []},
                    ],
                    "pacing": "slow", "logo_first_appearance_sec": 5.0,
                    "cta_detected": False, "cta_text": None,
                    "frames_analyzed": 4, "metadata": {},
                },
            ],
            "initial_judgements": {},
            "consistency_report": None,
            "final_judgements": {},
            "verdict": None,
        }

        checkpoints_db = run_folder / "checkpoints.db"
        saver = SqliteSaver.from_conn_string(str(checkpoints_db))
        compiled = build_jury_graph().compile(checkpointer=saver)
        thread_config = {"configurable": {"thread_id": run_id, "router": router}}

        final_state = compiled.invoke(initial_state, config=thread_config)

        # All five agents scored
        assert len(final_state["initial_judgements"]) == 5

        # Consistency check ran
        assert final_state["consistency_report"] is not None

        # Deliberation ran
        assert len(final_state["final_judgements"]) == 5

        # Moderator produced verdict
        assert final_state["verdict"] is not None
        verdict = Verdict(**final_state["verdict"])
        assert verdict.winner_video in ["ad1.mp4", "ad2.mp4"]
        assert 0 <= verdict.confidence <= 1
        assert len(verdict.ranking) == 2
```

- [ ] **Step 2: Commit (do not run — requires live API key)**

```bash
git add cjs/tests/test_jury_graph_integration.py
git commit -m "test: add Phase 11 integration test for full jury swarm"
```

---

## Self-review checklist

- [x] Spec coverage: JuryState ✓ · five scoring agents ✓ · ConsistencyChecker ✓ · deliberation ✓ · Moderator ✓ · SqliteSaver checkpointing ✓ · `cjs resume` ✓ · `cjs run` wiring ✓ · Verdict schema ✓
- [x] Placeholder scan: all agent persona strings have concrete copy-from instructions pointing to an exact section of `docs/agent_system_prompts.md`; no TBD or vague steps
- [x] Type consistency: `JuryState`, `AgentJudgement`, `ConsistencyReport`, `Verdict`, `RouterResult` used consistently across all tasks
- [x] `_fan_out` is defined in `jury_graph.py` and imported in `test_jury_graph.py` — both reference the same function
- [x] `AGENT_PERSONAS` defined in `scoring.py` and imported in `deliberation.py`
- [x] `ModelRouter(run_id, run_folder, config)` constructor used correctly in all tasks
