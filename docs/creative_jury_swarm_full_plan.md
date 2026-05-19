
# Creative Jury Swarm — Authoritative Build Plan

## Project Vision

A terminal-first multi-agent system that acts as an AI Creative Jury.
Users provide a PDF creative brief, an optional brand pack, and video ads.
The swarm evaluates the videos using a panel of specialized agents, runs an
auction to select the winner, and produces a full decision report that opens
automatically in the browser.

**Primary goal:** Portfolio artifact demonstrating frontier orchestration
engineering — multimodal AI, agentic orchestration, evaluation systems,
structured reasoning, and observability.

---

## Architecture Decisions (Locked)

| Concern | Decision |
|---|---|
| Orchestration | LangGraph |
| LLM Provider | Anthropic-only (Claude) |
| UI | CLI drives the run; static HTML report auto-opens in browser |
| Observability | LangSmith (traces) + `metrics.json` per run |
| Video analysis | Local: ffmpeg + Whisper + Claude Vision; graceful fallback if deps missing |
| Agent concurrency | Parallel scoring → one deliberation round → final verdict |
| Storage | SQLite `~/.cjs/runs.db` (metadata) + `runs/<timestamp>/` (artifacts) |
| Auction engine | Confidence bid + conviction bid hybrid |
| Report format | Static self-contained HTML with Chart.js (radar/bar) + D3 (debate graph) |
| Consistency tracking | Factual contradiction + score self-consistency → "evaluation consistency" |
| Agent prompting | Fixed persona layer + dynamic scoring instructions from `rubric.json` |
| Brand pack | Full rules-based YAML; auto-extracted from brief if not provided |
| Moderator role | Synthesizer + Judge; ConsistencyChecker is a separate LangGraph node |
| Extended thinking | Moderator + Brand Compliance agents only (Claude Opus 4.7) |
| MVP scope | v1 = full pipeline through report; v2 = Improvement Swarm + polish |

---

## Core Workflow

```
cjs run --brief brief.pdf --videos ad1.mp4 ad2.mp4 ad3.mp4 --brand brand.yaml
```

1. Parse brief PDF → `brief.json` + `rubric.json`
2. Extract brand rules (from `--brand` YAML or auto-extracted from brief)
3. Analyze each video once → `video_dossiers/`
4. Jury agents score in parallel (blind pass)
5. ConsistencyChecker flags contradictions
6. Deliberation round — agents see group scores, may revise
7. Moderator runs auction formula → final ranked scorecard
8. Improvement Swarm generates fix suggestions (v2)
9. Write `report.html`, open in browser; index run in SQLite

---

## Output Structure

```
runs/<timestamp>/
  brief.json
  rubric.json
  brand_rules.json
  video_dossiers/
    ad1_dossier.json
    ad2_dossier.json
  scorecards.json          # initial + final scores per agent per video
  metrics.json             # latency, token cost, consistency flags, disagreement
  config_snapshot.yaml
  report.html              # self-contained, embeds all data as JSON
```

```
~/.cjs/
  config.yaml
  runs.db                  # SQLite index of all runs
```

---

## CLI Commands

### Install
```
pipx install creative-jury-swarm
cjs init
```

### Setup
```
cjs setup
```
Writes `~/.cjs/config.yaml`. Since provider is Anthropic-only, prompts for:
- `ANTHROPIC_API_KEY` env var name
- Text model (default: `claude-sonnet-4-6`)
- Vision model (default: `claude-sonnet-4-6`)
- Extended thinking models (default: `claude-opus-4-7`) — used for Moderator + Brand Compliance
- Safe limits (max videos, max duration, max frames per video)

### Run
```
cjs run --brief brief.pdf --videos *.mp4 [--brand brand.yaml]
```

### List runs
```
cjs runs
```
Renders a table from SQLite: run ID, date, winner, top score, video count.

### Open report
```
cjs report <run_id>
```

### Environment check
```
cjs doctor
```
Checks: ffmpeg, Python version, openai-whisper, ANTHROPIC_API_KEY, brand YAML schema.

---

## Config Schema (`~/.cjs/config.yaml`)

```yaml
provider: anthropic
models:
  text: claude-sonnet-4-6
  vision: claude-sonnet-4-6
  extended_thinking: claude-opus-4-7
limits:
  max_videos: 5
  max_duration_sec: 60
  max_frames: 12
langsmith:
  enabled: true
  project: creative-jury-swarm
```

---

## Brand Pack Schema (`brand.yaml`)

```yaml
brand:
  name: "Nike"
  mandatory:
    logo_visible_by_seconds: 3
    tagline: "Just Do It"
    disclaimer_required: false
  forbidden:
    competitor_names: ["Adidas", "Puma"]
    colors: []
  tone:
    - energetic
    - aspirational
```

If `--brand` is not provided, the brief parser extracts brand rules from the
PDF and writes them to `brand_rules.json`. The Brand Compliance agent receives
whichever source is available.

---

## Pipeline 1 — Brief Ingestion

1. Extract text from PDF (PyMuPDF)
2. LLM converts to structured JSON:
   - `objective`, `audience`, `tone`, `platform`, `mandatory_rules`, `KPIs`
3. Auto-generate scoring rubric with dimension weights
4. Attempt brand rule extraction if no `--brand` flag

Outputs: `brief.json`, `rubric.json`, `brand_rules.json`

---

## Pipeline 2 — Video Analysis (single pass per video)

For each video:
1. Validate format + duration against config limits
2. Extract audio → `ffmpeg` (graceful fallback: skip transcript if ffmpeg missing)
3. Transcribe → Whisper local (graceful fallback: empty transcript with warning)
4. Extract keyframes → OpenCV scene-cut detection
5. Claude Vision analyzes frames in batches
6. Assemble `video_dossier.json`

```json
{
  "filename": "ad1.mp4",
  "duration_sec": 28,
  "transcript": "...",
  "hook_summary": "...",
  "scenes": [...],
  "pacing": "fast",
  "logo_first_appearance_sec": 2.4,
  "cta_detected": true,
  "cta_text": "Shop now",
  "frames_analyzed": 12
}
```

---

## Pipeline 3 — Jury Swarm (LangGraph)

### LangGraph State Schema

```python
class JuryState(TypedDict):
    brief: BriefJSON
    rubric: RubricJSON
    brand_rules: BrandRulesJSON
    video_dossiers: list[DossierJSON]
    initial_scores: dict[str, AgentScorecard]   # agent_name → scorecard
    consistency_flags: list[ConsistencyFlag]
    final_scores: dict[str, AgentScorecard]
    verdict: VerdictJSON
    metrics: MetricsJSON
```

### Graph Structure

```
[BriefNode] → [VideoAnalysisNode] → fan-out → [5 parallel JuryAgentNodes]
                                                      ↓
                                          [ConsistencyCheckerNode]
                                                      ↓
                                          [DeliberationRound]  ← agents see group scores
                                                      ↓
                                          [ModeratorNode]  ← extended thinking
                                                      ↓
                                          [ReportGeneratorNode]
```

### Jury Agents

Each agent has:
- **Fixed persona** — hardcoded system prompt with role, expertise, and voice
- **Dynamic scoring instructions** — injected from `rubric.json` at runtime

| Agent | Persona | Extended Thinking |
|---|---|---|
| Creative Strategist | 15yr creative director | No |
| Brand Compliance | Brand + legal specialist | **Yes** |
| Audience Psychology | Behavioral researcher | No |
| Performance Marketer | Growth/conversion expert | No |
| Storytelling Critic | Narrative structure analyst | No |
| Moderator | Jury chair + verdict writer | **Yes** |

### Agent Output Schema

```json
{
  "agent": "CreativeStrategist",
  "video": "ad1.mp4",
  "scores": {
    "visual_impact": 8.2,
    "message_clarity": 7.5,
    "brand_alignment": 6.8,
    "audience_fit": 9.0,
    "pacing": 7.0
  },
  "strengths": ["Strong hook in first 3 seconds", "Clear CTA"],
  "weaknesses": ["Logo appears too late"],
  "confidence": 0.87,
  "conviction_allocation": {"ad1.mp4": 45, "ad2.mp4": 35, "ad3.mp4": 20},
  "narrative": "..."
}
```

`conviction_allocation` sums to 100 across all videos — forces genuine ranking.

---

## Pipeline 4 — Auction Engine

```
final_score(video) =
    Σ_agents(
        rubric_weighted_score(agent, video)
        × confidence(agent, video)
        × conviction_weight(agent, video)
    )
    − risk_penalty(video)
```

Where:
- `rubric_weighted_score` = dot product of agent dimension scores × rubric weights
- `conviction_weight` = `conviction_allocation / 100` (sums to 1 across videos per agent)
- `risk_penalty` = derived from Brand Compliance flags (0–10 point deduction)

Winner = highest `final_score`. Implemented in pure Python, not an LLM call.

---

## ConsistencyChecker Node

Runs after initial parallel scoring. Uses a fast Claude call (no extended thinking) to detect:

1. **Factual contradiction** — agent claim contradicts the video dossier (e.g., "no CTA detected" when dossier has `cta_detected: true`)
2. **Score/narrative inconsistency** — agent writes "excellent logo timing" but scores brand_alignment < 5

Outputs `consistency_flags` into state. Flagged agents are prompted to
reconsider during the deliberation round.

---

## Pipeline 5 — Improvement Swarm (v2)

After winner is selected:
- Improvement suggestions for the winning ad
- Fix recommendations for each losing ad
- Alternative hook variations
- Editing cut suggestions

---

## Observability

### LangSmith
- Auto-captures every LangGraph node execution
- Trace waterfall per run (latency, token cost per node)
- Accessible at `smith.langchain.com` with project `creative-jury-swarm`

### metrics.json (per run)
```json
{
  "run_id": "20260508_143022",
  "total_duration_sec": 87.4,
  "total_tokens": 42300,
  "total_cost_usd": 0.34,
  "per_node_latency": {...},
  "inter_agent_disagreement": {
    "max_score_delta": 2.4,
    "most_contested_video": "ad2.mp4",
    "most_contested_dimension": "pacing"
  },
  "evaluation_consistency": {
    "flags_raised": 2,
    "flags_resolved_in_deliberation": 1
  },
  "tool_failures": []
}
```

---

## Report (report.html)

Self-contained static HTML. All data embedded as JSON at build time.

### Visualizations
- **Radar charts** (Chart.js) — per-agent scores per video across rubric dimensions
- **Bar chart** — final auction scores ranked
- **Agent debate graph** (D3 force-directed) — nodes = agents, edges = disagreements weighted by delta
- **Score timeline** — initial vs. final scores after deliberation (shows how deliberation moved scores)
- **Extended thinking expander** — Moderator and Brand Compliance reasoning chains rendered as collapsible blocks
- **Consistency flags panel** — flagged contradictions with resolution status

---

## Security

- File size + duration limits enforced at pipeline entry
- Video format allowlist (mp4, mov, avi)
- No arbitrary URL fetching
- Brand YAML schema validated at startup (`cjs doctor`)
- Prompt injection hardening in brief extraction (structured JSON output only)
- Docker sandbox recommended for media processing in production

---

## Repo Structure

```
creative-jury-swarm/
  cjs/
    cli.py                  # Typer CLI entry point
    config.py               # Config loader + validator
    router/
      model_router.py       # Anthropic client wrapper (text + vision + extended thinking)
    pipelines/
      brief_ingestion.py
      video_analysis.py
      report_generator.py
    agents/
      base_agent.py         # Fixed persona + dynamic prompt assembly
      creative_strategist.py
      brand_compliance.py
      audience_psychology.py
      performance_marketer.py
      storytelling_critic.py
      moderator.py
      consistency_checker.py
    graph/
      jury_graph.py         # LangGraph state machine definition
      state.py              # JuryState TypedDict
    auction/
      engine.py             # Deterministic Python auction formula
    storage/
      sqlite_store.py       # Run indexing
      artifacts.py          # File I/O for run folder
    report/
      builder.py            # Assembles report.html from template + data
      template.html         # Chart.js + D3 template
  install.sh
  pyproject.toml
  README.md
  docs/
    creative_jury_swarm_full_plan.md
```

---

## Build Roadmap

### v1 — MVP (portfolio-ready)

**Week 1**
- CLI skeleton (Typer): `setup`, `doctor`, `run`, `runs`, `report`
- Config loader + model router (Anthropic client wrapper)
- Brief ingestion pipeline (PyMuPDF + Claude structured output)
- Brand pack YAML schema + auto-extraction fallback

**Week 2**
- Video analysis pipeline (ffmpeg + Whisper + Claude Vision)
- LangGraph state schema + graph skeleton
- 5 jury agents (parallel scoring, structured JSON output)
- ConsistencyChecker node

**Week 3**
- Deliberation round
- Moderator node with extended thinking
- Auction engine (Python)
- SQLite run storage
- Static HTML report with Chart.js + D3

**Week 4**
- LangSmith integration + `metrics.json`
- Polish: Rich terminal output, `cjs doctor` full checks, README

### v2 — Post-portfolio

- Improvement Swarm (Pipeline 5)
- `cjs runs` filtering + search
- Reputation scoring across runs
- Docker sandbox for media processing
- Extended brand pack validation
