# Phase 11 — LangGraph Jury Swarm

**Date:** 2026-05-18
**Branch:** `feature/llm-brief-parsing` → merge to `main`, then new branch for Phase 11
**Status:** Design approved, implementation plan pending

---

## Scope

Phase 11 builds the LangGraph jury swarm: `JuryState`, five parallel scoring agents, `ConsistencyChecker`, deliberation round, and `Moderator`. Includes `SqliteSaver` checkpointing and `cjs resume`.

Phases 12–14 (escalation, auction engine, HTML report) are out of scope for this spec.

---

## Architecture decision

**Functional nodes, StateGraph.** Each agent is a plain function, not a class. A shared `_run_scoring_agent()` helper handles the common pattern. This avoids serialization concerns, keeps each agent file thin, and maps cleanly to LangGraph's node model.

**One call per agent, all videos.** Each agent sees all video dossiers in a single LLM call and returns per-video judgements plus a `conviction_allocation` dict (sums to 100 across videos). This enables genuine cross-video comparison and gives the auction engine meaningful conviction weights.

---

## File layout

```
cjs/
  graph/
    __init__.py
    state.py          # JuryState TypedDict + _merge_dicts reducer
    jury_graph.py     # build_jury_graph() → CompiledStateGraph
    nodes/
      __init__.py
      scoring.py      # _run_scoring_agent() + 5 agent node functions + persona constants
      consistency.py  # consistency_checker_node()
      deliberation.py # deliberation_round_node()
      moderator.py    # moderator_node()
  schemas/
    verdict.py        # Verdict Pydantic model (new)
  tests/
    test_jury_graph.py
    test_scoring_node.py
    test_consistency_node.py
    test_deliberation_node.py
    test_moderator_node.py
    test_resume.py
    test_jury_graph_integration.py
```

`cjs/agents/` is not created. The functional approach renders it unnecessary.

---

## JuryState

```python
from typing import Annotated, Any
from typing_extensions import TypedDict

def _merge_dicts(a: dict, b: dict) -> dict:
    return {**a, **b}

class JuryState(TypedDict):
    run_id: str
    brief: dict                                                  # Brief.model_dump()
    rubric: dict                                                 # Rubric.model_dump()
    brand_rules: dict                                            # BrandRules.model_dump()
    video_dossiers: list[dict]                                   # [VideoDossier.model_dump(), ...]
    initial_judgements: Annotated[dict[str, list[dict]], _merge_dicts]
    consistency_report: dict | None
    final_judgements: Annotated[dict[str, list[dict]], _merge_dicts]
    verdict: dict | None
```

All Pydantic models enter state as dicts (`model.model_dump()`) for `SqliteSaver` JSON-serializability. Thread ID for checkpointing = `run_id`.

---

## Router injection

`ModelRouter` is not JSON-serializable and is never stored in state. It is passed at invocation time via `RunnableConfig` configurable:

```python
graph.invoke(
    initial_state,
    config={"configurable": {"router": router}},
    stream_mode="values"
)
```

Every node accesses it as:

```python
from langchain_core.runnables import RunnableConfig

def some_node(state: JuryState, config: RunnableConfig) -> dict:
    router: ModelRouter = config["configurable"]["router"]
```

For `cjs resume <run_id>`, the command re-constructs `ModelRouter` from config and passes it via configurable again. The checkpoint restores state; the router is re-injected at resume time.

---

## Graph structure

```
START
  ├─→ creative_strategist_node ──┐
  ├─→ brand_compliance_node ─────┤
  ├─→ audience_psychology_node ──┼─→ [consistency_checker_node]
  ├─→ performance_marketer_node ─┤         └─→ [deliberation_round_node]
  └─→ storytelling_critic_node ──┘                   └─→ [moderator_node]
                                                               └─→ END
```

The parallel fan-out is wired as a conditional edge from START using the `Send` API:

```python
from langgraph.types import Send

def _fan_out(state: JuryState) -> list[Send]:
    return [
        Send("creative_strategist_node", state),
        Send("brand_compliance_node", state),
        Send("audience_psychology_node", state),
        Send("performance_marketer_node", state),
        Send("storytelling_critic_node", state),
    ]

graph.add_conditional_edges(START, _fan_out)
```

`_fan_out` is a routing function, not a node — it lives in `jury_graph.py`. LangGraph waits for all five `Send` targets to complete before advancing to `consistency_checker_node`. Results merge into `initial_judgements` via `_merge_dicts`.

---

## Scoring agent nodes

All five scoring agents live in `cjs/graph/nodes/scoring.py`. Each is ~8 lines:

```python
_CREATIVE_STRATEGIST_PERSONA = "..."  # verbatim from docs/agent_system_prompts.md

def creative_strategist_node(state: JuryState, config: RunnableConfig) -> dict:
    return _run_scoring_agent(state, config, "creative_strategist", _CREATIVE_STRATEGIST_PERSONA)
```

`_run_scoring_agent(state, config, agent_name, persona)` does:

1. Build system prompt: persona + cross-cutting instructions (token_bid, confidence, evidence guidance) from `docs/agent_system_prompts.md`
2. Build user prompt: rubric dimensions + all video dossiers serialised as JSON blocks
3. Call `router.call_text(...)` — except Brand Compliance which calls `router.call_extended_thinking(...)`
4. Parse response: list of per-video judgements + `conviction_allocation` dict (sums to 100)
5. Populate each `AgentJudgement.token_bid` from `conviction_allocation[video_path]`
6. Return `{"initial_judgements": {agent_name: [j.model_dump() for j in judgements]}}`

The LLM response is requested as structured JSON matching:

```python
class AgentScoringResponse(BaseModel):
    judgements: list[AgentJudgement]           # one per video
    conviction_allocation: dict[str, int]      # video filename → points, must sum to 100
```

`AgentScoringResponse` is a local schema used only for parsing — not persisted.

---

## ConsistencyChecker node

`cjs/graph/nodes/consistency.py`

- Fast Claude call (`router.call_text(...)`, Sonnet, no extended thinking)
- Receives: all `initial_judgements` + `video_dossiers`
- Detects two flag types (from `ConsistencyFlag.classification`):
  - `FACTUAL_CONTRADICTION` — agent claim contradicts dossier data (e.g. "no CTA detected" when `cta_detected: true`)
  - `SCORE_NARRATIVE_MISMATCH` — agent writes "excellent logo timing" but scores `brand_alignment < 5`
- Returns `{"consistency_report": ConsistencyReport(...).model_dump()}`

---

## Deliberation round node

`cjs/graph/nodes/deliberation.py`

Single node (not a fan-out). Iterates over all five agents sequentially. Each agent receives:
- Their own initial judgements
- A named summary of all agents' initial scores (agent names always included)
- Any `ConsistencyFlag` entries directed at them specifically

The prompt makes it explicit: if confidence is high and no flags apply, returning the same scores is the correct response. Only genuinely flagged agents are expected to revise.

Returns `{"final_judgements": {agent_name: [revised.model_dump() for revised in ...]}}` for all five agents.

---

## Moderator node

`cjs/graph/nodes/moderator.py`

- `router.call_extended_thinking(...)` with `claude-opus-4-7`
- Receives: brief + rubric + all `final_judgements` + `consistency_report`
- Produces qualitative synthesis — does NOT compute auction scores (that is Phase 13)
- Returns `{"verdict": Verdict(...).model_dump()}`

### Verdict schema (`cjs/schemas/verdict.py`)

```python
class Verdict(BaseModel):
    winner_video: str                    # filename of recommended winner
    winner_rationale: str                # narrative explanation
    ranking: list[str]                   # all videos ranked best → worst
    per_video_notes: dict[str, str]      # video filename → moderator note
    confidence: float = Field(ge=0, le=1)  # used by Phase 12 confidence gate
    flags_resolved: list[str]            # consistency flag claims addressed
```

---

## Error handling

| Failure | Behaviour |
|---|---|
| LLM call fails (after router retry + fallback) | Node raises; graph halts; checkpoint is intact for `cjs resume` |
| Agent returns malformed JSON | `_run_scoring_agent` retries once with a correction prompt; second failure raises `AgentScoringError` |
| `conviction_allocation` doesn't sum to 100 | Normalise proportionally with a warning log; do not fail the run |
| Graph interrupted mid-run | `SqliteSaver` checkpoint allows `cjs resume` to restart from last completed node |

---

## Checkpointing and `cjs resume`

`SqliteSaver` stored at `runs/<run_id>/checkpoints.db`. `thread_id = run_id`.

```python
from langgraph.checkpoint.sqlite import SqliteSaver

checkpoints_db = run_folder / "checkpoints.db"
with SqliteSaver.from_conn_string(str(checkpoints_db)) as saver:
    compiled = build_jury_graph().compile(checkpointer=saver)
    result = compiled.invoke(initial_state, config={...})
```

`cjs resume <run_id>` command:
1. Resolves `run_folder` from `~/.cjs/runs.db`
2. Re-constructs `ModelRouter` from config
3. Re-opens `SqliteSaver` at `runs/<run_id>/checkpoints.db`
4. Re-compiles graph with same saver
5. Re-invokes with `thread_id=run_id` — LangGraph resumes from last checkpoint

---

## Wiring into `cjs run`

After Phase 9 (brief ingestion) and Phase 10 (video analysis), `cjs run` invokes the graph:

```python
initial_state: JuryState = {
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
```

The graph output (final `JuryState`) is passed to Phase 13 (auction engine) and Phase 14 (report builder) after graph completion.

---

## Testing

| File | Covers | Type |
|---|---|---|
| `test_scoring_node.py` | `_run_scoring_agent`: prompt shape, judgement parsing, conviction allocation, `token_bid` population | unit |
| `test_consistency_node.py` | Both flag types detected against fixture dossiers + judgements | unit |
| `test_deliberation_node.py` | Flagged agents receive flag context; unflagged agents do not | unit |
| `test_moderator_node.py` | Valid `Verdict` schema produced | unit |
| `test_jury_graph.py` | Full graph with all nodes mocked — correct state transitions end-to-end | unit |
| `test_resume.py` | Graph interrupted after scoring; resumed; completes without re-running completed nodes | unit |
| `test_jury_graph_integration.py` | Full live graph — one brief, two videos, verdict produced | integration |

All unit tests mock `ModelRouter`. Integration test marked `@pytest.mark.integration`.

---

## Dependencies to add before implementation

- `langgraph` — not yet in `pyproject.toml`
- `langgraph-checkpoint-sqlite` — for `SqliteSaver`
