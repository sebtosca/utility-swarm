# Plan: Creative Jury Swarm — Production AI Engineer Build

## Context

The project is an AI Creative Jury multi-agent system (LangGraph + Claude). A skeleton exists: CLI (Typer), brief extraction (PyMuPDF), run folder storage, and Pydantic schemas. The LangGraph graph, agents, video pipeline, auction engine, and report are all unbuilt.

Goal: Transform this into a portfolio artifact that signals production AI engineering — not just "I used LangGraph", but observability, resilience, traceability, and escalation at the system level.

**Target audience:** Technical HR + senior AI Engineers evaluating for Applied AI Engineer / Agentic Systems Engineer roles.

**Confirmed decisions (from grilling session):**
- Production level: local tool, production-quality code + Docker compose (no hosted deployment)
- OTel experience: yes — use it properly
- Escalation: all 3 types (model fallback circuit breaker + human-in-the-loop on disagreement + confidence gating)
- Wow moments: self-contained HTML report + README architecture diagram
- Resumable runs: LangGraph `SqliteSaver` checkpointing
- CI/CD: GitHub Actions (ruff + mypy + pytest + docker build)
- Timeline: no constraint — build it right

---

## What Exists

| Path | Status |
|---|---|
| `cjs/cli.py` | Done — configure, doctor, run, runs, report |
| `cjs/config.py` | Done |
| `cjs/pipelines/brief_ingest.py` | Partial — PDF text extraction only, no LLM call |
| `cjs/storage/runs.py` | Done — folder creation, file copy |
| `cjs/schemas/` | Done — brief, rubric, video_dossier, judgement, report |
| `cjs/tests/` | Partial — CLI + config tests |

---

## Build Phases

### Phase 1 — Complete the Core Pipeline

**Goal:** Full working run from `cjs run` to `report.html`.

#### 1a. Model Router (`cjs/router/model_router.py`)
- Anthropic client wrapper: `call_text()`, `call_vision()`, `call_extended_thinking()`
- Inject `run_id` into every request via `extra_headers={"X-Run-ID": run_id}`
- Return structured dict: `{content, tokens_in, tokens_out, latency_ms, model}`
- Retry policy via `tenacity`: 3 attempts, exponential backoff (2s, 4s, 8s)
- **Circuit breaker**: track consecutive failures per model; after 3, fall back to cheaper model (`claude-haiku-4-5-20251001`); log escalation event

#### 1b. Brief Ingestion LLM Call (`cjs/pipelines/brief_ingest.py`)
- Add `parse_brief(raw_text, model_router) → BriefJSON` — Claude structured output via tool use
- Add `generate_rubric(brief, model_router) → RubricJSON`
- Add `extract_brand_rules(brief, model_router) → BrandRulesJSON` (fallback if no `--brand`)
- Write `brief/brief.json`, `brief/rubric.json`, `brief/brand_rules.json`

#### 1c. Video Analysis Pipeline (`cjs/pipelines/video_analysis.py`)
- Per-video flow: validate format/duration → ffmpeg audio extract → Whisper transcribe → OpenCV keyframes → Claude Vision batch → assemble dossier
- Graceful fallback: if ffmpeg missing, skip transcript; if Whisper missing, skip transcript with warning
- Write `dossiers/<video_stem>_dossier.json`

#### 1d. LangGraph Graph (`cjs/graph/`)
- `cjs/graph/state.py` — `JuryState` TypedDict (as per plan)
- `cjs/graph/jury_graph.py` — graph definition:
  ```
  BriefNode → VideoAnalysisNode → fan-out → [5 parallel JuryAgentNodes]
                                                    ↓
                                        ConsistencyCheckerNode
                                                    ↓
                                        DeliberationRound
                                                    ↓
                                        ModeratorNode (extended thinking)
                                                    ↓
                                        ReportGeneratorNode
  ```
- **SqliteSaver checkpointing**: `from langgraph.checkpoint.sqlite import SqliteSaver` — stored at `runs/<run_id>/checkpoints.db`
- `cjs run` passes `thread_id=run_id`; `cjs resume <run_id>` resumes from last checkpoint

#### 1e. Jury Agents (`cjs/agents/`)
- `base_agent.py` — `BaseJuryAgent(persona_system_prompt, model_router)`: assembles prompt, calls router, parses `AgentScorecard`
- One file per agent: `creative_strategist.py`, `brand_compliance.py`, `audience_psychology.py`, `performance_marketer.py`, `storytelling_critic.py`
- `moderator.py` — extended thinking; writes `VerdictJSON`
- `consistency_checker.py` — fast call; writes `ConsistencyFlag` list

#### 1f. Auction Engine (`cjs/auction/engine.py`)
- Pure Python — no LLM call
- Formula: `final_score(video) = Σ_agents(rubric_weighted_score × confidence × conviction_weight) − risk_penalty`
- Returns ranked `VerdictJSON`

#### 1g. Report Generator (`cjs/report/`)
- `builder.py` — reads all run artifacts, embeds as JSON into `template.html`
- `template.html` — Chart.js radar + bar + score timeline, D3 debate graph, extended thinking expander, consistency flags panel, escalation events panel
- Self-contained: single `.html` file, no external CDN calls (embed JS inline)

---

### Phase 2 — Observability Layer (the production signal)

#### 2a. Structured Logging (`cjs/observability/logging.py`)
- Use `structlog` — JSON output in production, pretty in terminal
- Every log event carries: `run_id`, `trace_id`, `span_id`, `node`, `agent`, `model`
- Replace all `typer.echo` in pipeline code with `structlog.get_logger()`
- Write `runs/<run_id>/run.log` (newline-delimited JSON)

#### 2b. OpenTelemetry Instrumentation (`cjs/observability/tracing.py`)
- `init_tracer(run_id, service_name="creative-jury-swarm")` — OTLP exporter to Jaeger
- Instrument every LangGraph node with a span: `with tracer.start_as_current_span(node_name):`
- Instrument every LLM call in model router: span attributes = `model`, `tokens_in`, `tokens_out`, `latency_ms`
- Propagate `trace_id` into every artifact file as a top-level field
- `trace_id` appears in the HTML report header and `metrics.json`

#### 2c. Audit Trail (`cjs/observability/audit.py`)
- Every LLM call appended to `runs/<run_id>/audit.jsonl`:
  ```json
  {"ts": "...", "run_id": "...", "trace_id": "...", "node": "...", "agent": "...", "model": "...", "prompt_hash": "...", "tokens_in": 0, "tokens_out": 0, "latency_ms": 0}
  ```
- `prompt_hash` = SHA-256 of the rendered prompt (not the content — for reproducibility without storing PII)
- `cjs audit <run_id>` command: pretty-prints the audit log as a table

#### 2d. LangSmith Integration
- Already in plan: `LANGSMITH_API_KEY` env var, project `creative-jury-swarm`
- Add run metadata tags: `run_id`, `video_count`, `winner`
- Link LangSmith run URL into `metrics.json` as `langsmith_url`

---

### Phase 3 — Escalation System

#### 3a. Model Fallback (Circuit Breaker)
- Already described in Phase 1 model router
- Log escalation event to `runs/<run_id>/escalations.jsonl`:
  ```json
  {"ts": "...", "type": "model_fallback", "from_model": "...", "to_model": "...", "reason": "circuit_open", "node": "..."}
  ```

#### 3b. Human-in-the-Loop Escalation (`cjs/escalation/human_review.py`)
- After `ConsistencyCheckerNode`: if `max_score_delta > 3.0` OR `unresolved_flags > 0` after deliberation:
  - Emit escalation event to `escalations.jsonl`
  - Print a Rich panel to terminal: `[ESCALATION] Jury disagreement exceeds threshold. Review required.`
  - If `--auto-approve` flag not set: prompt user `Continue anyway? [y/N]`
  - If `N`: write partial run state, exit cleanly with `run_id` for later `cjs resume`
- Escalation events rendered in HTML report's "Escalation Events" panel

#### 3c. Confidence Gating (`cjs/escalation/confidence_gate.py`)
- After `ModeratorNode`: if `verdict.confidence < 0.70`:
  - Flag run as `"verdict_confidence": "low"` in `metrics.json`
  - Emit escalation event: `{"type": "low_confidence_verdict", "confidence": 0.62, ...}`
  - HTML report shows a yellow banner: "Low-confidence verdict — human review recommended"
  - Run still completes; the gate is advisory, not blocking (configurable via `--strict-confidence` flag to make it blocking)

---

### Phase 4 — Packaging & Portfolio

#### 4a. Docker Compose (`docker-compose.yml`)
Services:
- `app` — the CJS tool, mounts `./runs` and env vars
- `jaeger` — `jaegertracing/all-in-one:latest`, ports 16686 (UI) + 4317 (OTLP gRPC)

```yaml
services:
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports: ["16686:16686", "4317:4317"]
  app:
    build: .
    environment:
      - ANTHROPIC_API_KEY
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
    volumes:
      - ./runs:/app/runs
```

`Dockerfile`: multi-stage build, non-root user, `ffmpeg` installed in image

#### 4b. GitHub Actions (`.github/workflows/ci.yml`)
Jobs (run in parallel):
- `lint`: `ruff check .`
- `typecheck`: `mypy cjs/`
- `test`: `pytest cjs/ --tb=short`
- `docker-build`: `docker build .` (smoke test only, no push)

All triggered on `push` and `pull_request`.

#### 4c. README Architecture
- Mermaid diagram of the full LangGraph graph (auto-renders on GitHub)
- Section: "Production Engineering Features" — bullet list of OTel, circuit breaker, human-in-the-loop, checkpointing, audit trail
- Section: "Observability Stack" — diagram showing LangSmith + Jaeger + structlog layers
- GIF/screenshot of the HTML report and terminal output
- `cjs doctor` output screenshot

---

## Critical Files to Create / Modify

| File | Action |
|---|---|
| `cjs/router/model_router.py` | Create — circuit breaker, retry, per-call audit |
| `cjs/pipelines/brief_ingest.py` | Extend — add LLM parse/rubric/brand calls |
| `cjs/pipelines/video_analysis.py` | Create |
| `cjs/graph/state.py` | Create |
| `cjs/graph/jury_graph.py` | Create — SqliteSaver checkpointing |
| `cjs/agents/base_agent.py` | Create |
| `cjs/agents/{5 agents + moderator + checker}.py` | Create |
| `cjs/auction/engine.py` | Create |
| `cjs/report/builder.py` | Create |
| `cjs/report/template.html` | Create |
| `cjs/observability/logging.py` | Create — structlog |
| `cjs/observability/tracing.py` | Create — OTel |
| `cjs/observability/audit.py` | Create |
| `cjs/escalation/human_review.py` | Create |
| `cjs/escalation/confidence_gate.py` | Create |
| `cjs/cli.py` | Extend — `resume`, `audit` commands |
| `docker-compose.yml` | Create |
| `Dockerfile` | Create |
| `.github/workflows/ci.yml` | Create |
| `README.md` | Rewrite — architecture diagram, feature list |

---

## New Dependencies to Add (`pyproject.toml`)

```
langgraph
langgraph-checkpoint-sqlite
langsmith
opentelemetry-api
opentelemetry-sdk
opentelemetry-exporter-otlp-proto-grpc
structlog
tenacity
anthropic
pymupdf
openai-whisper
opencv-python-headless
```

---

## Verification Plan

1. `cjs doctor` — all checks green
2. `cjs run --brief sample.pdf --videos a.mp4 b.mp4` — full pipeline runs, `report.html` opens in browser
3. `docker compose up` — Jaeger UI at `localhost:16686` shows spans for the run
4. Kill mid-run, `cjs resume <run_id>` — resumes from last completed node
5. Feed deliberately disagreeing agent outputs — escalation panel fires in terminal + report
6. `pytest cjs/` — all tests pass
7. GitHub Actions — all 4 jobs green on push
