# Architecture

A technical reference for how Creative Jury Swarm is built — components, data flow, interfaces, and extension points. Complements [AGENTS.md](AGENTS.md) (agent behavior) and [SOUL.md](SOUL.md) (design philosophy).

---

## System overview

```
cjs run --brief brief.pdf --videos ad1.mp4 ad2.mp4
         │
         ▼
    ┌─────────────┐
    │  CLI (Typer) │  cli.py
    └──────┬──────┘
           │  creates run folder, initialises ModelRouter + AuditLogger + Tracer
           ▼
    ┌─────────────────────────────────────────────────────┐
    │                   LangGraph DAG                     │
    │                                                     │
    │  BriefIngest ──► VideoAnalysis ──► JuryPass ──►    │
    │  ConsistencyCheck ──► Deliberation ──► Moderator   │
    └──────────────────────────┬──────────────────────────┘
                               │
                    writes artifacts to runs/<run_id>/
                    indexes run in SQLite (~/.cjs/runs.db)
                    opens report.html in browser
```

---

## Run lifecycle

1. **CLI entry** (`cli.py`) — Typer parses flags, validates inputs, calls `create_run_folder()` which creates `runs/<run_id>/` with the standard subfolder tree.
2. **Shared services initialised** — `ModelRouter`, `AuditLogger`, and `init_tracer()` are constructed once and injected into every pipeline node.
3. **BriefIngest** — extracts raw text via PyMuPDF, calls Claude to parse into `Brief` + `Rubric` + `BrandRules`, writes JSON to `runs/<run_id>/brief/`.
4. **VideoAnalysis** (parallel) — one task per video: ffmpeg extracts frames + metadata, Whisper transcribes, Claude Vision produces a `VideoDossier`. Writes to `runs/<run_id>/dossiers/`.
5. **Jury blind pass** (parallel) — five scoring agents call Claude independently, producing `AgentJudgement` per video. No agent sees another's scores. Writes to `runs/<run_id>/judgements/`.
6. **ConsistencyChecker** — reads all `AgentJudgement` objects and the `VideoDossier` objects, flags `FACTUAL_CONTRADICTION` and `SCORE_NARRATIVE_MISMATCH`, writes `ConsistencyFlag[]` to `runs/<run_id>/results/consistency_flags.json`.
7. **Deliberation round** — agents receive the group scorecard and any consistency flags; each may revise its scores. Updated judgements overwrite the blind-pass versions.
8. **Moderator** — reads the full jury record, runs the auction formula, produces `Report` with ranked verdict + rationale. Extended thinking enabled.
9. **Report write** — `Report` serialised to `runs/<run_id>/results/report.html` (self-contained). Run indexed in `~/.cjs/runs.db`.

---

## ModelRouter

**File:** `cjs/router/model_router.py`

The single point of contact for all LLM calls. Wraps the Anthropic client with retry, circuit-breaking, and audit logging.

```python
@dataclass
class RouterResult:
    content: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    model: str
    thinking: str | None = None  # populated for extended thinking calls
```

**Call surface:**

| Method | Use case |
|---|---|
| `call_text(system, user, node, agent)` | Standard text completion |
| `call_vision(system, user, images, node, agent)` | Claude Vision (video frames) |
| `call_extended_thinking(system, user, node, agent)` | Moderator + Brand Compliance |
| `call_structured(system, user, node, schema)` | Tool-use extraction (Brief, Rubric, etc.) |

**Resilience:**

- **Retry:** `tenacity` — 3 attempts, exponential backoff (2s → 4s → 8s), retries on `anthropic.APIError`
- **Circuit breaker:** `_failures: dict[str, int]` tracks consecutive failures per model behind `_lock: threading.Lock`. After `CIRCUIT_THRESHOLD = 3` consecutive failures, falls back to `FALLBACK_MODEL = "claude-haiku-4-5-20251001"` and writes a fallback event to `runs/<run_id>/escalations.jsonl`
- **Audit:** every call (success or failure) appended to `audit.jsonl` via the injected `AuditLogger`

---

## Schema layer

All inter-component data contracts are Pydantic models. Nothing passes between pipeline nodes as raw dicts or strings.

| Schema | File | Key fields |
|---|---|---|
| `Brief` | `schemas/brief.py` | `campaign_objective`, `target_audience`, `mandatory_elements`, `forbidden_elements`, `kpis`, `approved_claims`, `prohibited_claims` |
| `Rubric` | `schemas/rubric.py` | `dimensions: list[RubricDimension]` — name, weight, description per scoring axis |
| `BrandRules` | `schemas/brand_rules.py` | Logo timing, mandatory tagline, colour palette, tone constraints |
| `VideoDossier` | `schemas/video_dossier.py` | `transcript`, `scene_metadata`, `logo_first_appearance_sec`, `cta_detected`, `duration_sec`, `frame_paths` |
| `AgentJudgement` | `schemas/judgement.py` | `scores: dict[str, float]`, `confidence: int` (0–100), `token_bid: int`, `evidence: list[str]`, `flags: list[str]`, `notes: str` |
| `ConsistencyFlag` | `schemas/consistency_flag.py` | `flag_type` (FACTUAL_CONTRADICTION \| SCORE_NARRATIVE_MISMATCH), `agent_name`, `video_path`, `claim`, `evidence` |
| `Report` | `schemas/report.py` | `ranking: list[str]`, `winner`, `rationale`, `per_video_summaries`, `unresolved_concerns` |

---

## Auction engine

Pure Python — no LLM involved in ranking.

```
auction_score(agent, video) = confidence_bid × token_bid / 100
```

- **`token_bid`** (`AgentJudgement.token_bid`) — domain conviction (0–100). Set by the agent in its prompt.
- **`confidence`** (`AgentJudgement.confidence`) — evidence clarity (0–100). Set by the agent in its prompt.
- Scores are summed across all five scoring agents per video to produce the final ranking input.
- The Moderator receives this ranking as structured input before writing its narrative verdict.

The formula is deterministic. Two runs with identical inputs produce identical rankings (modulo LLM non-determinism in the agents themselves, which affects `token_bid` and `confidence` values).

---

## Storage layout

### Run folder

Created by `create_run_folder()` at `runs/<YYYYMMDD_HHMMSS_<4hex>>/`:

```
runs/<run_id>/
  input/
    brief.pdf               # original brief (copied)
    videos/
      ad1.mp4               # original videos (copied)
  brief/
    brief_raw.txt           # raw PDF text
    brief.json              # Brief schema
    rubric.json             # Rubric schema
    brand_rules.json        # BrandRules schema
  dossiers/
    ad1_dossier.json        # VideoDossier per video
  judgements/
    ad1_creative_strategist.json   # AgentJudgement (blind pass)
    ad1_brand_compliance.json
    ...                     # deliberation pass overwrites these
  results/
    consistency_flags.json  # ConsistencyFlag[]
    scorecards.json         # all AgentJudgements, initial + final
    metrics.json            # latency, token cost, disagreement, consistency flag count
    report.html             # self-contained HTML report
  audit.jsonl               # one line per LLM call
  escalations.jsonl         # circuit-breaker fallback events
  config_snapshot.yaml      # config at time of run
```

### Global index

`~/.cjs/runs.db` — SQLite database. One row per run, indexed for `cjs runs` and `cjs report <run_id>`.

---

## Observability stack

Three independent layers — each captures different granularity.

### OTel tracing (`cjs/observability/tracing.py`)

```python
tracer = init_tracer(run_id, service_name="creative-jury-swarm")

with trace_node(tracer, "brief_ingest", run_id=run_id, node="brief_ingest"):
    ...
```

- `init_tracer()` creates a `TracerProvider` with `cjs.run_id` as a resource attribute
- If `OTEL_EXPORTER_OTLP_ENDPOINT` is set, exports via OTLP gRPC to that endpoint (LangSmith, Jaeger, etc.)
- Falls back to `ConsoleSpanExporter` if env var is absent
- Every `trace_node` span carries: `run_id`, `model`, `tokens_in`, `tokens_out`, `latency_ms`

### Structured logging (`cjs/observability/logging.py`)

- `get_logger(__name__)` returns a `structlog` logger
- JSON renderer in non-TTY environments; pretty renderer in TTY
- All log calls carry `run_id`, `node`, `agent` as context vars

### Audit trail (`cjs/observability/audit.py`)

`AuditLogger` appends one JSON line per LLM call to `runs/<run_id>/audit.jsonl`:

```json
{
  "ts": 1747612800.123,
  "run_id": "20260518_120000_ab12",
  "trace_id": "abc123...",
  "node": "brief_parse",
  "agent": null,
  "model": "claude-sonnet-4-6",
  "prompt_hash": "sha256:...",
  "tokens_in": 1200,
  "tokens_out": 340,
  "latency_ms": 1823.4
}
```

`prompt_hash` is SHA-256 of the rendered prompt string — not the raw text. Enables audit without storing sensitive content.

---

## Extension points

### Adding a scoring agent

1. Add persona and scoring instructions to `docs/agent_system_prompts.md`
2. Create a Pydantic schema in `cjs/schemas/` if the agent produces a new output type
3. Add a LangGraph node that calls `ModelRouter.call_text()` (or `call_extended_thinking()` if needed)
4. Wire the node into the DAG between `VideoAnalysis` and `ConsistencyChecker`
5. Add the new scoring dimensions to `cjs/constants.py` (`JURY_DIMENSIONS`)
6. Add a unit test in `cjs/tests/` that mocks `ModelRouter` and asserts `AgentJudgement` schema validity

### Adding a new scoring dimension

1. Add the dimension name to `JURY_DIMENSIONS` in `cjs/constants.py`
2. Update `KPI_DIMENSION_MAP` if it maps to a KPI
3. Assign it to an agent (or create a new agent to own it)
4. The `Rubric` schema picks it up automatically from the brief parsing step

### Extending the report

`Report` is serialised to self-contained HTML. Chart.js (radar/bar charts) and D3 (debate graph) are embedded inline. To add a new visualisation: add the data field to `Report`, update the HTML template in the report writer, and add Chart.js/D3 code inline.

---

## Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API authentication (or set via `cjs configure`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | None | OTel gRPC endpoint (e.g. `localhost:4317`). Falls back to console. |
| `LANGCHAIN_API_KEY` | No | None | LangSmith tracing. Set alongside `LANGCHAIN_TRACING_V2=true`. |
| `LANGCHAIN_TRACING_V2` | No | `false` | Enable LangSmith trace export |
