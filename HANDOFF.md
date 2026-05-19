# Project Handoff — Creative Jury Swarm

**Date:** 2026-05-18  
**Branch:** `main`  
**Status:** Phases 1–11 complete. Phase 11 has uncommitted work. Next: Phase 12 (escalation), 13 (auction), 14 (HTML report).

---

## What this is

CLI-first multi-agent system that evaluates video ad creatives against a creative brief. A PDF brief + video files go in; five specialist agents score in parallel, a Consistency Checker audits the record, a Moderator delivers a ranked verdict, and a self-contained HTML report opens in the browser.

Primary goal: portfolio artifact demonstrating frontier orchestration engineering — LangGraph, multimodal pipeline (ffmpeg + Whisper + Claude Vision), and production observability (OTel + LangSmith + audit trail).

---

## What is built (Phases 1–11)

| Phase | What it is | Key files |
|---|---|---|
| 1 | Repo & CLI shell | `cjs/cli.py` |
| 2 | Config system | `cjs/config.py`, `~/.cjs/config.yaml` |
| 3 | Setup wizard | `cjs configure` command |
| 4 | Run folder + input copy | `cjs/storage/runs.py` |
| 5 | Pydantic schemas | `cjs/schemas/` (9 files including `brand_rules.py`, `consistency_flag.py`, `verdict.py`) |
| 6 | PDF extraction | `cjs/utils/pdf.py`, `cjs/pipelines/brief_ingest.py` |
| 7 | ModelRouter | `cjs/router/model_router.py` — retry, circuit-breaker, Haiku fallback |
| 8 | Observability | `cjs/observability/` — OTel tracing, structlog, AuditLogger |
| 9 | Brief ingestion LLM | `cjs/pipelines/brief_ingest.py` — `parse_brief`, `generate_rubric`, `extract_brand_rules`; wired into `cjs run` |
| 10 | Video analysis pipeline | `cjs/utils/{ffmpeg,frames,whisper_stt}.py`, `cjs/pipelines/video_analysis.py` — `analyze_video`; wired into `cjs run` |
| 11 | LangGraph jury swarm | `cjs/graph/` — full 7-node graph, parallel scoring, consistency check, deliberation, Moderator verdict |

---

## What was done this session (Phase 11)

Phase 11 is fully implemented across 11 tasks. All tests pass (127 non-integration tests).

### Phase 11 files created

| File | What it is | Committed? |
|---|---|---|
| `cjs/schemas/verdict.py` | `Verdict` Pydantic schema — Moderator output | ✅ yes |
| `cjs/graph/__init__.py` | Package marker | ✅ yes |
| `cjs/graph/nodes/__init__.py` | Package marker | ✅ yes |
| `cjs/graph/state.py` | `JuryState` TypedDict + `_merge_dicts` reducer | ✅ yes |
| `cjs/graph/nodes/scoring.py` | `_run_scoring_agent`, 5 agent node functions, personas, `AgentScoringResponse` | ✅ yes |
| `cjs/graph/nodes/consistency.py` | `consistency_checker_node` — flags FACTUAL_CONTRADICTION + SCORE_NARRATIVE_MISMATCH | ✅ yes |
| `cjs/graph/nodes/deliberation.py` | `deliberation_round_node` — iterates 5 agents sequentially, passes flags to flagged agents | ⬜ uncommitted |
| `cjs/graph/nodes/moderator.py` | `moderator_node` — extended thinking, parses JSON into `Verdict` | ⬜ uncommitted |
| `cjs/graph/jury_graph.py` | `build_jury_graph()`, `_fan_out` routing function, `Send` API fan-out | ⬜ uncommitted |
| `cjs/tests/test_verdict_schema.py` | 3 tests | ✅ yes |
| `cjs/tests/test_jury_state.py` | 3 tests | ✅ yes |
| `cjs/tests/test_scoring_node.py` | 9 tests | ✅ yes |
| `cjs/tests/test_consistency_node.py` | 3 tests | ✅ yes |
| `cjs/tests/test_deliberation_node.py` | 4 tests | ⬜ uncommitted |
| `cjs/tests/test_moderator_node.py` | 3 tests | ⬜ uncommitted |
| `cjs/tests/test_jury_graph.py` | 3 tests (mock nodes, in-memory SqliteSaver) | ⬜ uncommitted |
| `cjs/tests/test_resume.py` | 1 test (uses `get_state()` — see watch-out below) | ⬜ uncommitted |
| `cjs/tests/test_jury_graph_integration.py` | 1 `@pytest.mark.integration` test — write-only, requires live API | ⬜ uncommitted |

### Modified files

| File | Change | Committed? |
|---|---|---|
| `cjs/cli.py` | Replaced stub with full jury graph invocation; added `cjs resume` command | ⬜ uncommitted |
| `cjs/tests/test_cli_commands.py` | Fixed 2 broken tests (mocked `build_jury_graph`), added 2 resume tests | ⬜ uncommitted |

### Commits to make

```bash
git add cjs/graph/nodes/deliberation.py cjs/tests/test_deliberation_node.py
git commit -m "feat: add deliberation round node"

git add cjs/graph/nodes/moderator.py cjs/tests/test_moderator_node.py
git commit -m "feat: add Moderator node with extended thinking"

git add cjs/graph/jury_graph.py cjs/tests/test_jury_graph.py cjs/tests/test_resume.py
git commit -m "feat: add jury_graph with Send-based fan-out and SqliteSaver checkpointing"

git add cjs/cli.py cjs/tests/test_cli_commands.py
git commit -m "feat: wire jury graph into cjs run and add cjs resume command"

git add cjs/tests/test_jury_graph_integration.py
git commit -m "test: add Phase 11 integration test for full jury swarm"
```

---

## Key architecture decisions locked in Phase 11

| Decision | Detail |
|---|---|
| Functional nodes | Each agent is a plain Python function `(state, config) -> dict`, not class-based |
| One LLM call per agent | Agent sees all videos at once; returns `conviction_allocation` dict summing to 100 |
| `call_structured` | Scoring, consistency, deliberation — tool-use, returns `json.dumps(block.input)` |
| `call_extended_thinking` | Brand Compliance + Moderator only — parses JSON text response |
| `_fan_out` | Routing function (not a node), uses LangGraph `Send` API for parallel scoring fan-out |
| `ModelRouter` in config | Passed via `RunnableConfig` configurable `{"router": router}` — not serialised into state |
| Resume via `get_state()` | LangGraph 1.0.7: second `invoke` on completed thread re-runs full graph; use `get_state()` to read checkpoint |
| SqliteSaver | `SqliteSaver.from_conn_string(str(run_folder / "checkpoints.db"))` per run |

---

## What to build next

### Phase 12 — Escalation system

Human-in-the-loop gate + confidence threshold gate before the Moderator node. If the Moderator's confidence is below a configurable threshold, or if hard flags are unresolved, pause the graph and prompt the user to intervene or override.

See `BUILD_STEPS.md` for the detailed checklist.

### Phase 13 — Auction engine

Pure Python scoring logic: `compute_final_scores`, `select_winner`, `build_verdict`. The auction weights token_bid × confidence_bid to produce final per-video scores. No LLM involved.

### Phase 14 — HTML report

Self-contained static HTML report with Chart.js radar/bar and D3 debate graph. Emitted from `cjs run` as `report.html` in the run folder.

### Jury Room UI (Priority 2)

Full spec written at `docs/superpowers/specs/2026-05-18-documentation-and-jury-room-ui-design.md`. Implementation plan not yet written. Use `superpowers:writing-plans` to create it.

---

## How to pick this up

```bash
# Install
pip install -e .

# Verify environment
cjs doctor

# Run existing tests
pytest cjs/ -v -m "not integration"   # 127 passing

# Check uncommitted work
git status

# Read the Phase 11 plan (for reference)
cat docs/superpowers/plans/2026-05-18-phase-11-langgraph-jury-swarm.md

# Check next phases
cat BUILD_STEPS.md
```

**To resume:** Read HANDOFF.md, commit the pending Phase 11 work (commands above), then start Phase 12 using `superpowers:brainstorming` or `superpowers:writing-plans`.

---

## Key files index

| File | What it is |
|---|---|
| `CLAUDE.md` | Start here for AI sessions |
| `AGENTS.md` | Agent catalog and jury flow |
| `ARCHITECTURE.md` | Component interfaces, data schemas, storage layout |
| `SOUL.md` | Engineering philosophy and portfolio positioning |
| `BUILD_STEPS.md` | Phase-by-phase build checklist |
| `docs/creative_jury_swarm_full_plan.md` | Authoritative architecture decisions (locked) |
| `docs/agent_system_prompts.md` | Full system prompt text for all 7 agents |
| `docs/superpowers/specs/2026-05-18-phase-11-langgraph-jury-swarm.md` | Phase 11 design spec |
| `docs/superpowers/plans/2026-05-18-phase-11-langgraph-jury-swarm.md` | Phase 11 implementation plan (all tasks done) |
| `docs/superpowers/specs/2026-05-18-documentation-and-jury-room-ui-design.md` | Jury Room UI spec |
| `cjs/router/model_router.py` | All LLM calls — `call_text`, `call_structured`, `call_extended_thinking`, `call_vision` |
| `cjs/schemas/judgement.py` | `AgentJudgement` — core agent output schema |
| `cjs/schemas/verdict.py` | `Verdict` — Moderator output schema |
| `cjs/graph/state.py` | `JuryState` TypedDict with `_merge_dicts` reducer |
| `cjs/graph/jury_graph.py` | `build_jury_graph()` — the full 7-node LangGraph |
| `cjs/graph/nodes/scoring.py` | Five parallel scoring agents + `_run_scoring_agent` helper |
| `cjs/graph/nodes/consistency.py` | Consistency Checker node |
| `cjs/graph/nodes/deliberation.py` | Deliberation round node |
| `cjs/graph/nodes/moderator.py` | Moderator node (extended thinking → Verdict) |
| `cjs/observability/` | OTel tracing, structlog, audit trail |

---

## Open items / watch-outs

- **Phase 11 uncommitted:** Deliberation, Moderator, jury_graph, CLI wiring, and integration test are implemented but not committed. Commit commands are in the "What was done" section above.
- **LangGraph resume behaviour:** `invoke` on a completed thread re-runs the full graph (LangGraph 1.0.7). Use `compiled.get_state(thread_config)` to read a completed checkpoint without re-running.
- **No auto-commits:** Claude Code will not auto-commit. After each task completes with passing tests, you (the user) commit manually.
- **Phase 7.5 not done:** ModelRouter unit tests tracked in issue #13.
- **Phase 8.8 not done:** `cjs audit <run_id>` CLI command tracked in issue #14.
- **`cjs ui` planned:** FastAPI + WebSocket jury room tracked in issues #15–17.
- **Branch note:** Development shifted to `main` (the `feature/llm-brief-parsing` branch is stale). All work is on `main`.
