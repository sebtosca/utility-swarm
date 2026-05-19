# Documentation Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Write six .MD files that serve AI coding sessions, portfolio viewers, and open-source contributors — all sharing the same engineering narrative (orchestration + multimodal + observability).

**Architecture:** Each file has a single audience and purpose. They cross-link so no reader hits a dead end. Content is derived from the locked architecture in `docs/creative_jury_swarm_full_plan.md` and the agent prompts in `docs/agent_system_prompts.md`.

**Tech Stack:** Markdown only. No tooling required. Review against spec at `docs/superpowers/specs/2026-05-18-documentation-and-jury-room-ui-design.md`.

> **Note:** Workstream 2 (Jury Room UI — FastAPI + WebSocket) is a separate plan to be written after this one is executed.

---

## File map

| File | Action | Purpose |
|---|---|---|
| `CLAUDE.md` | Create | AI session context: locked decisions, module map, agent roster, code standards |
| `AGENTS.md` | Create | Agent catalog, jury flow, scoring domains, auction mechanics |
| `SOUL.md` | Create | Portfolio vision: the three engineering pillars and design philosophy |
| `README.md` | Overwrite | Unified narrative hub linking all three pillars and all docs |
| `CONTRIBUTING.md` | Create | Short, project-specific contributor guide |
| `SECURITY.md` | Create | API key policy, local-only data, audit trail, vulnerability reporting |

---

## Task 1: Write `CLAUDE.md`

**Files:**
- Create: `CLAUDE.md`

- [ ] **Step 1: Write the file**

Write the following content exactly to `CLAUDE.md`:

```markdown
# Creative Jury Swarm — Claude Context

## What this is

CLI-first multi-agent system that evaluates video ad creatives against a brief.
A PDF brief + video files go in; a ranked jury verdict + HTML report come out.
Primary goal: portfolio artifact demonstrating frontier orchestration engineering
(multimodal AI, agentic orchestration, evaluation systems, observability).

## Locked architecture decisions

> Do not suggest alternatives to these decisions. See `docs/creative_jury_swarm_full_plan.md` for full rationale.

| Concern | Decision |
|---|---|
| Orchestration | LangGraph |
| LLM Provider | Anthropic-only (Claude) |
| UI | `cjs ui` launches FastAPI + WebSocket jury room; `cjs run` headless; static HTML report |
| Observability | LangSmith (traces) + `metrics.json` per run |
| Video analysis | Local: ffmpeg + Whisper + Claude Vision; graceful fallback if deps missing |
| Agent concurrency | Parallel blind scoring → consistency check → deliberation → final verdict |
| Storage | SQLite `~/.cjs/runs.db` (metadata) + `runs/<timestamp>/` (artifacts) |
| Auction engine | Confidence bid × conviction bid hybrid (pure Python, not LLM) |
| Report format | Static self-contained HTML with Chart.js + D3; also rendered live in jury room |
| Extended thinking | Moderator + Brand Compliance agents only (claude-opus-4-7) |

## Agent roster

See [AGENTS.md](AGENTS.md) for the full catalog, jury flow diagram, and auction mechanics.

| Agent | Persona | Scoring domains | Extended thinking |
|---|---|---|---|
| Creative Strategist | 15-year creative director | None (conviction only) | No |
| Brand Compliance | Brand and legal specialist | `brief_compliance`, `brand_alignment` | Yes (claude-opus-4-7) |
| Audience Psychology | Behavioral researcher | `audience_resonance`, `emotional_impact` | No |
| Performance Marketer | Growth and conversion specialist | `message_clarity`, `performance_potential` | No |
| Storytelling Critic | Narrative structure analyst | `storytelling` | No |
| Consistency Checker | Factual auditor | None (flags only) | No |
| Moderator | Jury chair and verdict writer | None (verdict only) | Yes (claude-opus-4-7) |

## Module map

```
cjs/
  cli.py                  # Typer entry point; all CLI commands including `cjs ui`
  config.py               # Config R/W (~/.cjs/config.yaml)
  constants.py            # Shared constants
  router/
    model_router.py       # ModelRouter: tenacity retry, circuit-breaker, Haiku fallback
  pipelines/
    brief_ingest.py       # PDF → brief.json + rubric.json + brand_rules.json
    video_analysis.py     # ffmpeg + Whisper + Claude Vision → video_dossier.json
  schemas/
    brief.py              # Brief, Rubric
    judgement.py          # Judgement, Scorecard
    rubric.py             # RubricDimension
    video_dossier.py      # VideoDossier
    brand_rules.py        # BrandRules
    consistency_flag.py   # ConsistencyFlag
    report.py             # Report
  storage/
    runs.py               # SQLite index of all runs (~/.cjs/runs.db)
  observability/
    tracing.py            # OTel SDK + OTLP gRPC exporter; trace_node() context manager
    audit.py              # AuditLogger: one JSON line per LLM call → audit.jsonl
  utils/
    pdf.py                # PyMuPDF text extraction
    ffmpeg.py             # ffmpeg wrapper (duration, frame extraction)
    frames.py             # Frame sampling for Claude Vision
    whisper_stt.py        # Whisper STT wrapper
  ui/                     # (planned) FastAPI + WebSocket jury room
```

## Build phase status

Phases 1–8 complete (CLI, config, schemas, PDF extraction, model router, observability).
See [BUILD_STEPS.md](BUILD_STEPS.md) for in-flight phases and the production build plan.

## Code standards

- **Linter:** `ruff check .` — line-length 100, rules `E/F/I/UP`
- **Types:** `mypy cjs/` — `check_untyped_defs = true`, `strict = false`
- **Style:** No nested if/else — extract helpers to keep blocks flat and debuggable
- **Comments:** Only when the WHY is non-obvious. Never describe what the code does.
- **Docstrings:** None.

## Testing

```bash
pytest cjs/ -v                   # unit tests (default)
pytest -m integration            # requires live ANTHROPIC_API_KEY
pytest -m "not integration"      # safe for CI, no API calls
```

Mark any test requiring a live API call with `@pytest.mark.integration`.
```

- [ ] **Step 2: Review against spec checklist**

Verify the file contains:
- [ ] Project description (2–3 sentences)
- [ ] Full locked architecture table with "Do not suggest alternatives" notice
- [ ] Agent roster table with scoring domains and extended thinking column
- [ ] Module map covering all directories in `cjs/`
- [ ] Build phase status with link to `BUILD_STEPS.md`
- [ ] Code standards: Ruff, mypy, no nested if/else, no comments unless WHY
- [ ] Testing commands with integration marker guidance

- [ ] **Step 3: Suggest commit to user**

> When ready, commit with:
> `git add CLAUDE.md && git commit -m "docs: add CLAUDE.md with locked architecture, agent roster, and module map"`

---

## Task 2: Write `AGENTS.md`

**Files:**
- Create: `AGENTS.md`
- Reference: `docs/agent_system_prompts.md` (for agent persona details)

- [ ] **Step 1: Write the file**

Write the following content exactly to `AGENTS.md`:

```markdown
# Agent System

## Jury flow

```
Brief PDF + Video files
         │
         ▼
  BriefIngest ──────────────────────────────────────────────────────────
  brief.json + rubric.json + brand_rules.json                          │
         │                                                              │
         ▼                                                              ▼
  VideoAnalysis (parallel, one per video)                     Brief panel
  → video_dossier.json per video                              populates in UI
         │
         ▼
  ┌─────────────────────────────────────────────────────────┐
  │ Jury Agents — parallel blind pass (no agent sees        │
  │ another's scores until deliberation)                    │
  │                                                         │
  │  Creative Strategist        (conviction only)           │
  │  Brand Compliance Agent     (extended thinking)         │
  │  Audience Psychology Agent                              │
  │  Performance Marketer                                   │
  │  Storytelling Critic                                    │
  └─────────────────────────────────────────────────────────┘
         │
         ▼
  ConsistencyChecker
  → consistency_flags.json (FACTUAL_CONTRADICTION | SCORE_NARRATIVE_MISMATCH)
         │
         ▼
  Deliberation Round
  Agents see group scores and consistency flags; may revise their scores
         │
         ▼
  Moderator (extended thinking)
  Reads full jury record + auction outcome → Final ranked verdict
         │
         ▼
  report.html + runs/<timestamp>/ artifacts + SQLite index
```

Full system prompt text for each agent: [`docs/agent_system_prompts.md`](docs/agent_system_prompts.md)

---

## Agent catalog

### Creative Strategist
**Role:** Evaluates the creative idea itself — concept, craft, and execution. The only question: is this a great ad?  
**Scoring domains:** None. Provides overall creative conviction only.  
**Extended thinking:** No.  
**Token bid logic:** Bids highest on the ad with the strongest creative work, regardless of brief compliance or media performance. A bid of 0 = no creative conviction. A bid of 100 = strongest work seen.  
**Flags:** None. This agent delivers conviction and narrative, not compliance findings.

---

### Brand Compliance Agent
**Role:** Final line of defence between the brand and reputational or legal risk. Audits mandatory elements, forbidden elements, approved claims, and logo timing.  
**Scoring domains:** `brief_compliance`, `brand_alignment`.  
**Extended thinking:** Yes — claude-opus-4-7. Used to work through edge cases where a claim appears compliant on the surface but carries legal risk in context.  
**Token bid logic:** Domain conviction on compliance rigour.  
**Flags:** Hard flags only — factual findings the client must act on before the ad can run:
- Missing mandatory element
- Forbidden element present
- Prohibited claim made
- Logo timing violation

Each flag format: *what was expected · what was found · where in the ad (timestamp or scene).*

---

### Audience Psychology Agent
**Role:** Evaluates whether the ad will actually land with the target audience — not strategic correctness on paper, but real-moment resonance.  
**Scoring domains:** `audience_resonance`, `emotional_impact`.  
**Extended thinking:** No.  
**Token bid logic:** Domain conviction on audience resonance.  
**Flags:** Factual findings (not subjective preferences):
- Cultural insensitivity
- Demographic alienation signal
- Psychographic mismatch causing significant audience disengagement

---

### Performance Marketer Agent
**Role:** Evaluates whether the ad will perform — hook speed, CTA clarity, value proposition delivery, platform-specific optimisation.  
**Scoring domains:** `message_clarity`, `performance_potential`.  
**Extended thinking:** No.  
**Token bid logic:** Domain conviction on media performance likelihood.  
**Flags:** Compliance findings (not performance opinions):
- Platform policy violation (Meta, TikTok, YouTube ad review failure)
- Implied claim not supported by the brief
- CTA mechanics rejected by ad auction

---

### Storytelling Critic Agent
**Role:** Evaluates the structural integrity and emotional logic of the story — arc, pacing, payoff, narrative coherence.  
**Scoring domains:** `storytelling`.  
**Extended thinking:** No.  
**Token bid logic:** Domain conviction on narrative quality.  
**Flags:** Structural findings only:
- Misleading narrative structure (arc implies a claim the brand cannot support)
- Structural deception (emotional payoff built on an unearned premise)

---

### Consistency Checker
**Role:** Factual auditor. Detects contradictions between agent claims and the video dossier, and between agents' written narratives and their own scores. Runs after the blind pass, before deliberation.  
**Scoring domains:** None.  
**Extended thinking:** No (fast call).  
**Output schema:** `ConsistencyFlag[]`

Two flag types:
- `FACTUAL_CONTRADICTION` — agent claim contradicts the video dossier (e.g. agent writes "no CTA present" but dossier records `cta_detected: true`)
- `SCORE_NARRATIVE_MISMATCH` — agent's narrative contradicts their own scores (e.g. writes "exceptional emotional territory" but scores `emotional_impact: 2.1`)

Each flag: agent name · video · quoted claim · contradicting evidence · flag type.

---

### Moderator
**Role:** Jury chair. Reads the full jury record, identifies agreement and divergence, applies the auction outcome, and delivers the final ranked verdict the client acts on.  
**Scoring domains:** None.  
**Extended thinking:** Yes — claude-opus-4-7.  
**Responsibilities:**
1. Review all agent scorecards and consistency flags
2. Identify significant agreement and disagreement points
3. Apply auction formula outcome as primary quantitative signal
4. Produce a ranked list (best to worst) across all ads
5. Write winner verdict: why this ad wins for this brief
6. Write per-video bullet summaries: strengths, weaknesses, one improvement
7. Populate `unresolved_concerns`: hard flags, split decisions, low-confidence scores

---

## Scoring dimensions

| Dimension | Owner agent | What it measures |
|---|---|---|
| `brief_compliance` | Brand Compliance | Mandatory elements present, forbidden elements absent |
| `brand_alignment` | Brand Compliance | Adherence to brand guidelines and approved claims |
| `audience_resonance` | Audience Psychology | Whether the ad speaks to the audience's identity and values |
| `emotional_impact` | Audience Psychology | Emotional triggers activated and their appropriateness |
| `message_clarity` | Performance Marketer | Hook speed, value proposition delivery, CTA clarity |
| `performance_potential` | Performance Marketer | Likelihood of driving the primary KPI on the target platform |
| `storytelling` | Storytelling Critic | Narrative arc integrity, pacing, emotional logic |

Creative Strategist and Moderator do not score rubric dimensions.

---

## Auction mechanics

After the deliberation round, the Moderator runs a hybrid auction to produce a quantitative ranking before writing the verdict narrative.

**Formula:** `auction_score = confidence_bid × conviction_bid / 100`

- **Conviction bid (token_bid):** Each scoring agent bids 0–100 per video, representing domain conviction — how strongly they'd stake their professional reputation on this ad winning within their domain.
- **Confidence bid:** Each agent reports 0–100 confidence per video — how clearly the evidence supports their scores (not how good the ad is, but how certain they are). Low video quality, ambiguous claims, or missing information drive confidence down.

**Why hybrid, not pure LLM verdict:** A pure LLM ranking is non-deterministic and not auditable. The auction produces a deterministic quantitative ranking. The Moderator uses this as the primary signal, then writes a qualitative verdict that explains and contextualises it.

**Weights:** The auction treats all scoring agents equally. The Moderator's extended thinking resolves cases where the auction outcome conflicts with a hard compliance flag (e.g. the highest-scoring ad has a missing mandatory element).
```

- [ ] **Step 2: Review against spec checklist**

Verify the file contains:
- [ ] ASCII jury flow diagram (all 7 stages)
- [ ] All 7 agents with role, scoring domains, extended thinking, token bid logic, and flag types
- [ ] Scoring dimension table mapping dimensions to owner agents
- [ ] Auction mechanics: formula, conviction vs confidence distinction, why hybrid not LLM
- [ ] Consistency Checker: both flag types with examples
- [ ] Link to `docs/agent_system_prompts.md`

- [ ] **Step 3: Suggest commit to user**

> When ready, commit with:
> `git add AGENTS.md && git commit -m "docs: add AGENTS.md with full jury flow, agent catalog, and auction mechanics"`

---

## Task 3: Write `SOUL.md`

**Files:**
- Create: `SOUL.md`

- [ ] **Step 1: Write the file**

```markdown
# Soul

## The problem

Creative review is expensive, inconsistent, and politically loaded. A senior creative director and
a performance marketer watching the same ad will disagree — and neither is wrong. Their disagreement
is valid domain expertise in tension. The question is whether you can structure that tension into a
defensible, reproducible decision: one that shows its work, names its uncertainty, and doesn't paper
over a hard call.

## What we built

**Orchestration depth.** A LangGraph DAG that runs five specialist agents in parallel — blind, so no
agent can anchor on another's score — then runs a consistency check, opens a deliberation round where
agents can revise in light of the group, and finally routes to a Moderator running extended thinking
to synthesise the record and deliver a ranked verdict. Not a chain of prompts. A system with state,
branching, contradiction detection, and a deliberation loop that converges on a decision.

**Multimodal pipeline.** Before any agent scores a video, a local analysis pipeline runs: ffmpeg
extracts frames and metadata, Whisper transcribes the audio, and Claude Vision analyses the visual
content. The output is a structured `VideoDossier` — transcript, scene metadata, logo timing, CTA
detection — that agents receive as structured evidence, not raw footage. Agents cite timestamps and
scene descriptions. They reason over evidence, not impressions.

**Operational maturity.** Every LangGraph node is wrapped in an OTel trace span carrying `run_id`,
`model`, `tokens_in`, `tokens_out`, and `latency_ms`. Every LLM call appends a line to `audit.jsonl`
with a SHA-256 prompt hash, token cost, and latency. LangSmith receives the full trace for replay and
inspection. A `metrics.json` is written per run. Every run is inspectable, reproducible, and auditable
without touching the raw LLM calls.

## Design philosophy

**Agents have domains, not opinions.** Each scoring agent evaluates only its rubric dimensions.
The Brand Compliance agent does not opine on storytelling. The Storytelling Critic does not audit
legal claims. Domain separation makes disagreements legible and verdicts defensible.

**Blind first, then deliberate.** Agents score without seeing each other's work. Deliberation happens
in a second pass, after the Consistency Checker has flagged contradictions. This prevents anchoring
— the most confident voice in the room setting the floor for everyone else.

**Evidence over impression.** Agents are instructed to cite timestamps, scene descriptions, and
specific dialogue lines — not adjectives. "Logo appears at 0:04, within brief requirement" not
"branding was present." The Consistency Checker enforces this: an agent who writes glowing copy
but scores a dimension at 2.1 gets flagged before the Moderator sees the record.

**Hybrid auction, not LLM verdict.** The final ranking is produced by a deterministic formula
(confidence bid × conviction bid). The Moderator's narrative explains and contextualises the
quantitative outcome — it does not replace it. Rankings are auditable; narratives are not.

**Fail gracefully.** If ffmpeg or Whisper are not installed, video analysis falls back to
text-only mode. The pipeline runs. The report notes what was unavailable. No crash, no silent
omission — a documented degradation.

## What this is not

This is not a prompt wrapper. Every component has a defined interface, a testable output schema,
and a traceable execution path. You can replay any run from its `audit.jsonl`. You can inspect
any LLM call from LangSmith. You can read any agent's scorecard, their consistency flags, and
the Moderator's unresolved concerns. The system shows its work.

## Status

Phases 1–8 complete: CLI, config, schemas, PDF extraction, model router, observability.
v1 target: full pipeline through report — brief ingestion, video analysis, parallel jury,
deliberation, verdict, HTML report. See [BUILD_STEPS.md](BUILD_STEPS.md) for in-flight phases.

v2: Improvement Swarm — agents generate specific, actionable improvement recommendations
per video, framed for the production team that made the ad.

→ [Quick start and commands](README.md)
```

- [ ] **Step 2: Review against spec checklist**

Verify:
- [ ] "The problem" — creative review is expensive/inconsistent, structures disagreement into defensible decision
- [ ] Three pillars: orchestration depth, multimodal pipeline, operational maturity — each grounded in specific engineering decisions (not buzzwords)
- [ ] Five design philosophy principles (agents have domains, blind first, evidence over impression, hybrid auction, fail gracefully)
- [ ] "What this is not" — explicitly not a prompt wrapper
- [ ] Status with v1/v2 scope and link to BUILD_STEPS.md

- [ ] **Step 3: Suggest commit to user**

> When ready, commit with:
> `git add SOUL.md && git commit -m "docs: add SOUL.md with engineering vision and design philosophy"`

---

## Task 4: Overhaul `README.md`

**Files:**
- Modify: `README.md` (full overwrite)

- [ ] **Step 1: Read current `README.md`**

Read the current file to confirm no content is lost (the commands table and quick-start block are kept).

- [ ] **Step 2: Write the new file**

```markdown
# Creative Jury Swarm

Multi-agent AI creative jury: brief + video ads → ranked verdict + HTML report.

*Frontier orchestration · Multimodal pipeline · Production observability*

---

## How it works

```
Brief PDF + Videos
       │
       ▼
BriefIngest → VideoAnalysis (parallel) → Jury Agents (parallel, blind)
       │
       ▼
ConsistencyChecker → Deliberation → Moderator (extended thinking) → Verdict
       │
       ▼
report.html  ·  runs/<timestamp>/  ·  SQLite index
```

Five specialist agents score in parallel — blind, so no agent anchors on another's score.
A Consistency Checker flags contradictions. A deliberation round lets agents revise.
The Moderator synthesises the record and delivers a ranked verdict.

→ [Full agent catalog and jury flow](AGENTS.md)

---

## Quick start

```bash
pip install -e .
cjs configure
```

**Browser interface (recommended for creative teams):**
```bash
cjs ui
```
Opens a live jury room at `localhost:7842`. Drag-and-drop your brief and videos, then watch the jury deliberate in real time.

**Headless (CI / scripting):**
```bash
cjs run --brief path/to/brief.pdf --videos ad1.mp4 ad2.mp4
```

---

## Commands

| Command | Description |
|---|---|
| `cjs ui` | Launch browser jury room (drag-and-drop brief + videos, live scoring) |
| `cjs configure` | One-time config (provider, models, limits) |
| `cjs config get` | Read config values |
| `cjs config set <key> <value>` | Update config |
| `cjs run` | Headless run: `--brief`, `--videos`, optional `--brand`, `--out` |
| `cjs doctor` | Environment checks |
| `cjs models` | Show configured text/vision models |
| `cjs runs` | List run folders (newest first) |
| `cjs report <run_id>` | Check report path/status for a run |
| `cjs audit <run_id>` | Show LLM call audit trail as a Rich table |

---

## Architecture

Creative Jury Swarm is built around three engineering pillars. A LangGraph DAG orchestrates
five specialist agents running in parallel, each scoring only their domain dimensions — a
deliberate structure that makes disagreements legible and verdicts defensible. Before any agent
scores, a local multimodal pipeline (ffmpeg + Whisper + Claude Vision) builds a structured
`VideoDossier` per video, so agents reason over evidence rather than impressions. Every run
is fully observable: OTel traces per node, structlog with run and agent context, a per-call
audit trail, and LangSmith for trace replay.

→ [Engineering philosophy and design decisions](SOUL.md)  
→ [Agent catalog, scoring domains, and auction mechanics](AGENTS.md)

---

## Output

```
runs/<timestamp>/
  brief.json              # parsed brief
  rubric.json             # scoring dimensions and weights
  brand_rules.json        # mandatory/forbidden elements
  video_dossiers/
    ad1_dossier.json      # transcript, scene metadata, logo timing, CTA
    ad2_dossier.json
  scorecards.json         # initial + final scores per agent per video
  consistency_flags.json  # factual and score/narrative contradictions
  metrics.json            # latency, token cost, consistency flags, disagreement
  audit.jsonl             # one line per LLM call: model, tokens, latency, prompt hash
  config_snapshot.yaml    # config at time of run
  report.html             # self-contained; embeds all data as inline JSON
```

```
~/.cjs/
  config.yaml             # provider, models, limits
  runs.db                 # SQLite index of all runs
```

---

## Tests

```bash
pytest cjs/ -v                   # unit tests
pytest -m integration            # requires ANTHROPIC_API_KEY
```

---

## Config

After `cjs configure`, config lives at `~/.cjs/config.yaml`. Safe defaults (max videos, duration, frames) are enforced.

---

[Agent system →](AGENTS.md) · [Engineering philosophy →](SOUL.md) · [Contributing →](CONTRIBUTING.md) · [Security →](SECURITY.md)
```

- [ ] **Step 3: Review against spec checklist**

Verify:
- [ ] Hero: one punchy sentence + three-pillar subtitle
- [ ] ASCII jury flow (abbreviated, top-level only)
- [ ] Quick start includes `cjs ui` as the recommended entry point for creative teams
- [ ] Commands table includes `cjs ui` and `cjs audit`
- [ ] Architecture paragraph covers all three pillars and links to SOUL.md and AGENTS.md
- [ ] Output tree includes `consistency_flags.json` and `audit.jsonl`
- [ ] Footer links to AGENTS.md, SOUL.md, CONTRIBUTING.md, SECURITY.md

- [ ] **Step 4: Suggest commit to user**

> When ready, commit with:
> `git add README.md && git commit -m "docs: overhaul README with unified narrative hub and three-pillar architecture"`

---

## Task 5: Write `CONTRIBUTING.md`

**Files:**
- Create: `CONTRIBUTING.md`

- [ ] **Step 1: Write the file**

```markdown
# Contributing

## Prerequisites

- Python 3.10+
- `pip install -e ".[dev]"`
- ffmpeg and Whisper are optional — the pipeline degrades gracefully without them

## Running tests

```bash
pytest cjs/ -v                   # unit tests, no API calls
pytest -m integration            # requires ANTHROPIC_API_KEY in environment
```

## Code standards

- `ruff check .` must pass (line-length 100, rules `E/F/I/UP`)
- `mypy cjs/` must pass
- No nested if/else — extract helpers to keep blocks flat
- No comments unless the WHY is non-obvious
- No docstrings

## Adding a scoring agent

1. Add the agent persona to `docs/agent_system_prompts.md` — fixed persona layer and scoring domain instructions
2. Add a Pydantic output schema to `cjs/schemas/` — one class, one file
3. Wire the agent as a LangGraph node in the pipeline — call via `ModelRouter`, emit a `score_update` event
4. Add a unit test in `cjs/tests/` that mocks `ModelRouter` and asserts the output schema is valid

## Branches and pull requests

- Branch off `main`: `git checkout -b feature/<short-description>`
- One concern per PR — don't combine a feature with a refactor
- Tests must pass: `pytest cjs/ -v` and `ruff check .`

## In scope

- Bug fixes
- Observability improvements (new span attributes, richer audit fields)
- New scoring dimensions (new rubric entries + corresponding agent logic)
- Report enhancements (new charts, improved layout)
- UI improvements (jury room layout, new agent states, accessibility)

## Out of scope

The following are **locked architecture decisions** (see [CLAUDE.md](CLAUDE.md)):
- Alternative LLM providers (OpenAI, Gemini, etc.)
- Replacing LangGraph with another orchestration framework
- Replacing FastAPI + vanilla HTML/JS with a JS framework (React, Vue, etc.)
- Changing the auction formula from the confidence × conviction hybrid

If you believe a locked decision is wrong, open an issue to discuss before implementing.
```

- [ ] **Step 2: Review against spec checklist**

Verify:
- [ ] Prerequisites with ffmpeg/Whisper as optional
- [ ] Test commands for both unit and integration
- [ ] Code standards: Ruff, mypy, no nested if/else, no comments
- [ ] Adding an agent: 4-step checklist (prompt, schema, LangGraph node, test)
- [ ] Branch + PR rules
- [ ] In scope list includes UI improvements
- [ ] Out of scope references CLAUDE.md and names the four locked decisions

- [ ] **Step 3: Suggest commit to user**

> When ready, commit with:
> `git add CONTRIBUTING.md && git commit -m "docs: add CONTRIBUTING.md with project-specific contributor guide"`

---

## Task 6: Write `SECURITY.md`

**Files:**
- Create: `SECURITY.md`

- [ ] **Step 1: Write the file**

```markdown
# Security

## API keys

Your Anthropic API key is stored only in `~/.cjs/config.yaml` — your user home directory,
never inside the repository. The `.gitignore` covers `config.yaml`, `runs/`, and `my_runs/`.
Do not commit these files.

## Local-only data

Video files and brief PDFs are never uploaded to any third-party service. All processing
is local: ffmpeg and Whisper run on your machine. Frames and transcripts are sent directly
to Anthropic's API under your own API key, subject to Anthropic's data handling policies.
No data passes through any CJS-operated server.

## Audit trail

Every LLM call is logged to `runs/<run_id>/audit.jsonl`. Each entry contains the model,
node name, token counts, latency, and a SHA-256 hash of the rendered prompt — not the raw
prompt text. This provides a verifiable record of what was called and when, without storing
sensitive brief or video content in plaintext logs.

## Reporting a vulnerability

Open a GitHub issue labelled `security`. Describe the vulnerability without including
exploit details in the public issue. We will acknowledge within 48 hours and coordinate
a fix before any public disclosure.
```

- [ ] **Step 2: Review against spec checklist**

Verify:
- [ ] API keys: location (`~/.cjs/config.yaml`), gitignore coverage
- [ ] Local-only data: explicit that no data passes through a CJS server
- [ ] Audit trail: SHA-256 hash, not raw prompt text
- [ ] Vulnerability reporting: GitHub issue, 48-hour acknowledgement, no public disclosure before fix

- [ ] **Step 3: Suggest commit to user**

> When ready, commit with:
> `git add SECURITY.md && git commit -m "docs: add SECURITY.md with API key policy, local-only data, and audit trail"`

---

## Self-review checklist

- [ ] All 6 files exist at the repo root
- [ ] Cross-links resolve: README → AGENTS, SOUL, CONTRIBUTING, SECURITY; CLAUDE → AGENTS, BUILD_STEPS; SOUL → README, BUILD_STEPS; CONTRIBUTING → CLAUDE; AGENTS → docs/agent_system_prompts.md
- [ ] `cjs ui` appears in README quick start, commands table, and CLAUDE.md locked decisions table
- [ ] No file contains "TBD", "TODO", or placeholder text
- [ ] Agent roster in CLAUDE.md matches agent catalog in AGENTS.md (same 7 agents, same domains)
- [ ] CONTRIBUTING.md out-of-scope list matches locked decisions in CLAUDE.md
