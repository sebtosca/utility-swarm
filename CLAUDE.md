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
| UI | `cjs ui` launches FastAPI + WebSocket jury room (planned); `cjs run` headless; static HTML report |
| Observability | LangSmith (traces) + `metrics.json` per run |
| Video analysis | Local: ffmpeg + Whisper + Claude Vision; graceful fallback if deps missing |
| Agent concurrency | Parallel blind scoring → consistency check → deliberation → final verdict |
| Storage | SQLite `~/.cjs/runs.db` (metadata) + `runs/<timestamp>/` (artifacts) |
| Auction engine | Confidence bid × conviction bid hybrid (pure Python, not LLM) |
| Report format | Static self-contained HTML with Chart.js + D3; also rendered live in jury room |
| Extended thinking | Moderator + Brand Compliance agents only (claude-opus-4-7) |

## Agent roster

See [AGENTS.md](AGENTS.md) for the full catalog, jury flow diagram, and auction mechanics.
See [ARCHITECTURE.md](ARCHITECTURE.md) for component interfaces, storage layout, and extension points.

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
    brief.py              # Brief
    judgement.py          # Judgement, Scorecard
    rubric.py             # RubricDimension
    video_dossier.py      # VideoDossier
    brand_rules.py        # BrandRules
    consistency_flag.py   # ConsistencyFlag
    report.py             # Report
  storage/
    runs.py               # SQLite index of all runs (~/.cjs/runs.db)
  observability/
    logging.py            # structlog configuration; get_logger() for structured logging
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

Phases 1–8 complete.
See [BUILD_STEPS.md](BUILD_STEPS.md) for in-flight phases and the production build plan.

## Code standards

- **Linter:** `ruff check .` — line-length 100, rules `E/F/I/UP`
- **Types:** `mypy cjs/` — `check_untyped_defs = true`, `strict = false`
- **Style:** No nested if/else — extract helpers to keep blocks flat and debuggable
- **Comments:** Only when the WHY is non-obvious. Never describe what the code does.
- **Docstrings:** None.

## Testing

```
pytest cjs/ -v                   # unit tests (default)
pytest -m integration            # requires live ANTHROPIC_API_KEY
pytest -m "not integration"      # safe for CI, no API calls
```

Test files live under `cjs/tests/` and `cjs/storage/tests/`.

Mark any test requiring a live API call with `@pytest.mark.integration`.

## Workflow orchestration

### Planning

- Enter plan mode for any non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, stop and re-plan immediately — don't keep pushing
- Write detailed specs upfront to reduce ambiguity
- Use plan mode for verification steps, not just building

### Subagent strategy

- Use subagents liberally to keep the main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One tack per subagent for focused execution

### Self-improvement loop

- After any correction from the user: update `tasks/lessons.md` with the pattern
- Write rules that prevent the same mistake from recurring
- Review `tasks/lessons.md` at session start for relevant patterns

### Verification before done

- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Run tests, check logs, demonstrate correctness
- Ask: "Would a staff engineer approve this?"

### Demand elegance (balanced)

- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: implement the elegant solution from scratch
- Skip this for simple, obvious fixes — don't over-engineer

### Autonomous bug fixing

- When given a bug report: fix it. Don't ask for hand-holding.
- Point at logs, errors, failing tests — then resolve them
- Go fix failing CI tests without being told how

## Task management

- **Plan first:** Write plan to `tasks/todo.md` with checkable items
- **Verify plan:** Check in before starting implementation
- **Track progress:** Mark items complete as you go
- **Explain changes:** High-level summary at each step
- **Capture lessons:** Update `tasks/lessons.md` after any correction

## Core principles

- **Simplicity first:** Make every change as simple as possible. Minimal code impact.
- **No laziness:** Find root causes. No temporary fixes. Senior developer standards.
- **Minimal impact:** Changes should only touch what's necessary. Avoid introducing bugs.
