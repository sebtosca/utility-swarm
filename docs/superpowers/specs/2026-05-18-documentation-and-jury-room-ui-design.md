# Design Spec: Documentation Suite + Jury Room UI

**Date:** 2026-05-18  
**Status:** Approved  
**Workstreams:** 2 — Documentation suite (6 files) + Jury Room browser UI (new feature)

---

## Background

Creative Jury Swarm is a CLI-first multi-agent system that evaluates video ads against a creative brief. Phases 1–8 are complete: CLI, config, schemas, PDF extraction, model router, and observability are all done. The pipeline produces a static `report.html`.

Two gaps identified:
1. **Documentation**: No `CLAUDE.md`, `AGENTS.md`, `SOUL.md` — each new AI session lacks context on locked decisions and agent architecture. No contributor docs.
2. **Interface**: The CLI (`--brief`, `--videos` flags) is technical. The target audience — creative and advertising professionals — need a visual interface to upload briefs, upload videos, and watch the jury deliberate live.

---

## Workstream 1 — Documentation Suite (6 files)

### Audience

All three: AI coding sessions, portfolio viewers/recruiters, open-source contributors.

### File inventory

| File | Primary audience | Purpose |
|---|---|---|
| `CLAUDE.md` | AI sessions | Locked decisions, agent roster, module map, code standards |
| `AGENTS.md` | AI sessions + portfolio | Full agent catalog, jury flow, auction mechanics |
| `SOUL.md` | Portfolio / recruiters | Vision, engineering philosophy, the "why" |
| `README.md` | Everyone | Unified narrative hub, three-pillar story, links everything |
| `CONTRIBUTING.md` | Contributors | Short, project-specific — not boilerplate |
| `SECURITY.md` | Contributors + users | API key handling, local-only data policy |

### Cross-linking rules

- `README.md` links to `AGENTS.md`, `SOUL.md`, `CONTRIBUTING.md`, `SECURITY.md`
- `CLAUDE.md` links to `AGENTS.md` (agent detail) and `docs/creative_jury_swarm_full_plan.md` (full spec)
- `AGENTS.md` links to `docs/agent_system_prompts.md` for full prompts
- `SOUL.md` links to `README.md` for "how to run" details

---

### 1.1 `CLAUDE.md`

Focus areas (what AI sessions currently lack): agent architecture, locked tech decisions, code style & standards.

**Sections:**

1. **What this project is** — 2–3 sentences: CLI-first multi-agent creative jury, brief + videos → verdict + HTML report, portfolio artifact demonstrating frontier orchestration.

2. **Locked architecture decisions** — full table from `docs/creative_jury_swarm_full_plan.md`. Prefaced with: *"Do not suggest alternatives to these decisions."*

   | Concern | Decision |
   |---|---|
   | Orchestration | LangGraph |
   | LLM Provider | Anthropic-only (Claude) |
   | UI | `cjs ui` launches FastAPI + WebSocket jury room; `cjs run` headless; static HTML report |
   | Observability | LangSmith (traces) + `metrics.json` per run |
   | Video analysis | Local: ffmpeg + Whisper + Claude Vision; graceful fallback |
   | Agent concurrency | Parallel blind scoring → consistency check → deliberation → final verdict |
   | Storage | SQLite `~/.cjs/runs.db` (metadata) + `runs/<timestamp>/` (artifacts) |
   | Auction engine | Confidence bid × conviction bid hybrid (pure Python, not LLM) |
   | Report format | Static self-contained HTML with Chart.js + D3; also rendered live in jury room |
   | Extended thinking | Moderator + Brand Compliance agents only (claude-opus-4-7) |

3. **Agent roster** — one line per agent: name, persona, scoring domain, extended thinking. Points to `AGENTS.md` for detail.

4. **Module map:**
   - `cli.py` — Typer entry point + `cjs ui` command
   - `config.py` — config R/W
   - `router/` — `ModelRouter` (retry, circuit-breaker, fallback to Haiku)
   - `pipelines/` — `brief_ingest.py`, `video_analysis.py`
   - `schemas/` — Pydantic contracts (`Brief`, `Judgement`, `Rubric`, `VideoDossier`, `BrandRules`, `ConsistencyFlag`, `Report`)
   - `storage/` — SQLite runs index
   - `observability/` — OTel tracing, structlog, audit trail
   - `utils/` — `pdf.py`, `ffmpeg.py`, `frames.py`, `whisper_stt.py`
   - `ui/` — FastAPI server, WebSocket event emitter, HTML/CSS/JS jury room (new)

5. **Build phase status** — Phases 1–8 done. Links to `BUILD_STEPS.md` for what's in flight.

6. **Code standards:**
   - Ruff (`ruff check .`), line-length 100, `E/F/I/UP`
   - mypy (`mypy cjs/`)
   - No nested if/else — extract helpers to keep blocks flat
   - No comments unless the WHY is non-obvious
   - No docstrings

7. **Testing:**
   - `pytest cjs/ -v` for unit tests
   - `@pytest.mark.integration` for live API tests
   - `pytest -m "not integration"` by default

---

### 1.2 `AGENTS.md`

**Sections:**

1. **Jury flow diagram** — ASCII pipeline:
```
Brief PDF + Video files
         │
         ▼
  BriefIngest → brief.json + rubric.json + brand_rules.json
         │
         ▼
  VideoAnalysis (parallel, one per video) → video_dossiers/
         │
         ▼
  Jury Agents — parallel blind pass
  ├── Creative Strategist        (conviction only, no rubric dimensions)
  ├── Brand Compliance Agent     (extended thinking, brief_compliance + brand_alignment)
  ├── Audience Psychology Agent  (audience_resonance + emotional_impact)
  ├── Performance Marketer       (message_clarity + performance_potential)
  └── Storytelling Critic        (storytelling)
         │
         ▼
  ConsistencyChecker → consistency_flags.json
         │
         ▼
  Deliberation Round (agents see group scores, may revise)
         │
         ▼
  Moderator (extended thinking) → Auction → Final Verdict
         │
         ▼
  report.html + runs.db + jury room verdict reveal
```

2. **Agent catalog** — one section per agent with consistent template:
   - **Role** (one sentence)
   - **Scoring domains** (which rubric dimensions)
   - **Extended thinking** (yes/no, model)
   - **Token bid logic** (conviction vs confidence)
   - **Flag types** it raises

3. **Scoring dimensions** — 7 rubric dimensions mapped to agent owners:

   | Dimension | Owner |
   |---|---|
   | `brief_compliance` | Brand Compliance |
   | `brand_alignment` | Brand Compliance |
   | `audience_resonance` | Audience Psychology |
   | `emotional_impact` | Audience Psychology |
   | `message_clarity` | Performance Marketer |
   | `performance_potential` | Performance Marketer |
   | `storytelling` | Storytelling Critic |

   Creative Strategist and Moderator are non-scoring — conviction and verdict only.

4. **Auction mechanics** — how confidence bid × conviction bid produces the ranked outcome; why pure LLM verdict was rejected (non-deterministic); how Moderator uses the auction output.

5. **Consistency checking** — two flag types: `FACTUAL_CONTRADICTION` vs `SCORE_NARRATIVE_MISMATCH`; what the Moderator does with unresolved flags.

---

### 1.3 `SOUL.md`

Tone: confident, specific. No buzzwords — every claim grounded in a concrete engineering decision.

**Sections:**

1. **The problem** — Creative review is expensive, inconsistent, and politically loaded. A senior creative director and a performance marketer watching the same ad will disagree — and neither is wrong. The question is whether you can structure that disagreement into a defensible, reproducible decision.

2. **What we built** — one paragraph per pillar:
   - **Orchestration depth**: LangGraph DAG with parallel blind scoring → consistency check → deliberation → extended-thinking verdict. Not a chain of prompts — a system with state, branching, and a deliberation loop.
   - **Multimodal pipeline**: Local ffmpeg + Whisper + Claude Vision per video, producing a structured `VideoDossier` before any agent sees the footage. Agents reason over evidence, not raw video.
   - **Operational maturity**: OTel tracing per node, structlog with run/agent context, per-call audit trail (prompt hash, token cost, latency), LangSmith for trace replay.

3. **Design philosophy** — 5 principles:
   - Agents have domains, not opinions — each scores only its rubric dimensions
   - Blind first, then deliberate — prevents anchoring
   - Evidence over impression — timestamps and scene citations, not adjectives
   - Hybrid auction, not LLM verdict — final ranking is deterministic; narrative is not
   - Fail gracefully — video analysis degrades to text-only if ffmpeg/Whisper absent

4. **What this is not** — *"This is not a prompt wrapper. Every component has a defined interface, a testable output schema, and a traceable execution path."*

5. **Status** — Phases 1–8 complete. v1 = full pipeline through report. v2 = Improvement Swarm. Links to `BUILD_STEPS.md`.

---

### 1.4 `README.md` overhaul

**New structure:**

1. **Hero** — one punchy sentence + three-pillar subtitle:
   > *Multi-agent AI creative jury: brief + video ads → ranked verdict + HTML report.*
   >
   > Frontier orchestration · Multimodal pipeline · Production observability

2. **How it works** — abbreviated ASCII jury flow (top-level stages only). Links to `AGENTS.md`.

3. **Quick start** — existing block, cleaned up. Includes `cjs ui` for browser experience.

4. **Commands table** — existing table, keep. Add `cjs ui` row.

5. **Architecture** — 3–4 sentence paragraph covering the three pillars. Links to `SOUL.md` and `AGENTS.md`.

6. **Output** — `runs/<timestamp>/` tree as a code block.

7. **Tests** — existing `pytest` block.

8. **Config** — existing block.

9. **Footer links** — `[Agent system →](AGENTS.md)` · `[Engineering philosophy →](SOUL.md)` · `[Contributing →](CONTRIBUTING.md)` · `[Security →](SECURITY.md)`

---

### 1.5 `CONTRIBUTING.md`

Short, project-specific.

1. **Prerequisites** — Python 3.10+, `pip install -e ".[dev]"`, ffmpeg + Whisper optional
2. **Running tests** — `pytest cjs/ -v`; `pytest -m integration` requires live API key
3. **Code standards** — Ruff, mypy, no nested if/else, no comments unless WHY is non-obvious
4. **Adding an agent** — 4-step checklist: persona in `agent_system_prompts.md`, Pydantic schema in `schemas/`, wire into LangGraph, unit test with mocked `ModelRouter`
5. **Branch + PR** — feature branches off `main`, one concern per PR, tests must pass
6. **In scope** — bug fixes, observability improvements, new scoring dimensions, report enhancements, UI improvements
7. **Out of scope** — alternative LLM providers, replacing LangGraph, UI framework rewrites (locked architecture — see `CLAUDE.md`)

---

### 1.6 `SECURITY.md`

Brief, factual.

1. **API keys** — stored only in `~/.cjs/config.yaml`. Never committed. `.gitignore` covers `config.yaml` and `runs/`.
2. **Local-only data** — video files and brief PDFs never uploaded. All processing is local (ffmpeg, Whisper) or sent directly to Anthropic's API under the user's own key.
3. **Audit trail** — every LLM call logged to `audit.jsonl` with prompt hash (SHA-256), not raw prompt text.
4. **Reporting a vulnerability** — open a GitHub issue marked `security`. No public disclosure until patched.

---

## Workstream 2 — Jury Room UI

### Entry point

`cjs ui` launches a local FastAPI server and opens the browser. `cjs run` continues to work headlessly (CI, scripting). The pipeline code is unchanged — only a new interface layer is added.

### Tech stack

| Layer | Choice | Reason |
|---|---|---|
| Server | FastAPI | Lightweight, async, WebSocket support built-in |
| Real-time | WebSocket | Pipeline emits events; server relays to browser |
| Frontend | Vanilla HTML/CSS/JS | No framework dependency; same aesthetic as existing report |
| Served at | `localhost:7842` | Default port; configurable via `--port` flag on `cjs ui` |

### New module: `cjs/ui/`

```
cjs/ui/
  server.py          # FastAPI app, WebSocket endpoint, static file serving
  events.py          # Event schema: JuryEvent dataclass (type, agent, payload, ts)
  emitter.py         # EventEmitter injected into pipeline — replaces direct stdout
  static/
    index.html       # Single-page jury room (all CSS + JS inline)
    avatars/         # SVG persona icons (one per agent)
```

### Page layout

```
┌─────────────────────────────────────────────────────┐
│  [Brief Panel — collapsible sidebar]                │
│  Campaign objective · Target audience · KPIs        │
│  Rubric legend: brief_compliance · storytelling...  │
├─────────────────────────────────────────────────────┤
│  UPLOAD ZONE (pre-run only)                         │
│  ┌──────────────────┐  ┌──────────────────────────┐ │
│  │  Brief PDF       │  │  Video Ads (up to 5)     │ │
│  │  drag & drop     │  │  drag & drop multi-file  │ │
│  └──────────────────┘  └──────────────────────────┘ │
│              [ Convene the Jury ]                   │
├─────────────────────────────────────────────────────┤
│  JURY ROOM (visible after run starts)               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ Creative │ │  Brand   │ │ Audience │            │
│  │Strategist│ │Compliance│ │Psychology│            │
│  │  [SVG]   │ │  [SVG]   │ │  [SVG]   │            │
│  │  ● Scoring│ │ ● Thinking│ │ ○ Waiting│           │
│  │ score... │ │ score... │ │          │            │
│  └──────────┘ └──────────┘ └──────────┘            │
│  ┌──────────┐ ┌──────────┐                          │
│  │Performance│ │Storytelling│                       │
│  │ Marketer │ │  Critic  │                          │
│  │  [SVG]   │ │  [SVG]   │                          │
│  └──────────┘ └──────────┘                          │
├─────────────────────────────────────────────────────┤
│  ▸ Consistency check: 2 flags raised [expand]       │
├─────────────────────────────────────────────────────┤
│  MODERATOR — JURY CHAIR                             │
│  [SVG]  ████ Deliberating — Extended thinking...    │
│                                                     │
│  VERDICT (streams in after deliberation)            │
│  🥇 Ad 2 — Campaign Title                          │
│  [rationale text streams in...]                    │
│  [radar chart] [debate graph]                       │
│  [ Download Report ]  [ New Run ]                  │
└─────────────────────────────────────────────────────┘
```

### Agent card states

Each agent card cycles through these states (driven by WebSocket events):

| State | Visual |
|---|---|
| `waiting` | Gray dot, muted card, avatar at 40% opacity |
| `analyzing` | Amber pulsing dot, "Analyzing video..." |
| `scoring` | Amber solid dot, score dimensions appear one by one |
| `deliberating` | Blue pulsing dot, score values may update with highlight |
| `done` | Green dot, full scorecard visible, notes excerpt shown |
| `error` | Red dot, 3-part error message: what / why / what to do |

### Agent SVG avatars

One SVG per agent, inline in HTML, color-coded:

| Agent | Color | Distinguishing motif |
|---|---|---|
| Creative Strategist | `#FF6B35` | Director's clapperboard |
| Brand Compliance | `#4A90D9` | Shield |
| Audience Psychology | `#9B59B6` | Brain / wave |
| Performance Marketer | `#2ECC71` | Upward trend arrow |
| Storytelling Critic | `#E74C3C` | Film reel |
| Consistency Checker | `#95A5A6` | Magnifying glass |
| Moderator | `#F1C40F` | Gavel |

### WebSocket event schema

```python
@dataclass
class JuryEvent:
    type: str          # agent_state | score_update | flag | verdict | error
    agent: str         # agent name or "moderator" or "system"
    payload: dict      # type-specific data
    ts: float          # unix timestamp
```

Event types:
- `brief_ready` — `BriefIngest` done; payload contains brief summary fields for the brief panel
- `video_dossier_ready` — one video's dossier complete; payload contains video filename + thumbnail path
- `agent_state` — state transition for an agent card
- `score_update` — a dimension score appears or updates (with `initial` vs `revised` flag)
- `flag` — a consistency or compliance flag raised
- `consistency_complete` — ConsistencyChecker done, N flags total
- `deliberation_start` — deliberation round begins
- `verdict` — Moderator final output streams in chunks
- `run_complete` — pipeline done, report written

### Brief panel

Collapsible sidebar (collapsed by default, toggle with one click). Shows:
- Campaign objective
- Target audience
- Mandatory elements
- KPIs
- Rubric dimension legend (7 dimensions with one-line descriptions)

Populated from `brief.json` via a `brief_ready` WebSocket event emitted after `BriefIngest` completes. The brief panel populates asynchronously — the panel container is visible immediately after "Convene the Jury" with a loading state, then fills in once parsing finishes. Jury agent cards only activate after both `brief_ready` and all `video_dossier_ready` events are received.

### Post-verdict state

After `run_complete` event:
- All agent cards freeze in `done` state
- Radar charts and debate graph render in Moderator area (using Chart.js + D3, same as current `report.html`)
- "Download Report" button triggers download of the self-contained `report.html`
- "New Run" button resets the upload zone and clears the jury room

### Aesthetic

- Background: `#0D0D0D`
- Card background: `#1A1A1A` with `1px` border in agent persona color at 30% opacity
- Active agent card: ambient glow in persona color (`box-shadow`)
- Score numbers: `#F5F5F5`, monospace font
- State dots: CSS-only animations (pulse keyframe for thinking/scoring states)
- Typography: system sans-serif stack (no web font dependency)
- Winner card highlight: `#F1C40F` border + subtle background tint

### File uploads (pre-run)

- Two drag-and-drop zones rendered on page load
- Brief zone: accepts `.pdf` only, shows filename + PDF icon on drop
- Video zone: accepts `.mp4`, `.mov`, `.webm`, multi-file, shows thumbnail per video (native browser `<video>` preview) + filename
- "Convene the Jury" button activates once at least one brief and one video are staged
- On click: files POST to `/api/run/start`, server writes to a temp staging dir (`/tmp/cjs-staging/<uuid>/`), pipeline moves them into `runs/<timestamp>/` at run start, upload zone collapses, jury room reveals. Staging dir is deleted after move.

---

## Implementation notes

### What changes in the pipeline

The pipeline (LangGraph nodes) emits events via an `EventEmitter` injected at run time. In headless mode (`cjs run`), the emitter is a no-op logger. In UI mode (`cjs ui`), the emitter sends `JuryEvent` objects over the active WebSocket connection.

No pipeline logic changes. Only the output channel changes.

### What is new

- `cjs/ui/` module (server, events, emitter, static assets)
- `cjs ui` CLI command (starts FastAPI, opens browser)
- SVG avatar assets (7 files)
- `EventEmitter` interface + two implementations (noop + WebSocket)
- `cjs ui` added to `README.md`, `CLAUDE.md`, `CONTRIBUTING.md`

### What does not change

- All pipeline nodes (LangGraph)
- All schemas (Pydantic)
- `ModelRouter`, `ModelRouter` retry/fallback logic
- Observability (OTel, structlog, audit trail)
- `cjs run` headless behaviour
- `report.html` generation
- SQLite storage

---

## Estimated file sizes

| File | ~length |
|---|---|
| `CLAUDE.md` | 120 lines |
| `AGENTS.md` | 180 lines |
| `SOUL.md` | 80 lines |
| `README.md` | 100 lines |
| `CONTRIBUTING.md` | 60 lines |
| `SECURITY.md` | 40 lines |
| `cjs/ui/server.py` | 120 lines |
| `cjs/ui/events.py` | 40 lines |
| `cjs/ui/emitter.py` | 60 lines |
| `cjs/ui/static/index.html` | 600–800 lines |
| SVG avatars (7×) | 30–50 lines each |
