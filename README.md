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

[Agent system →](AGENTS.md) · [Architecture →](ARCHITECTURE.md) · [Engineering philosophy →](SOUL.md) · [Contributing →](CONTRIBUTING.md) · [Security →](SECURITY.md)
