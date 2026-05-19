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
- `cjs ui` improvements (jury room layout, new agent states, real-time updates, accessibility)

## Out of scope

The following are **locked architecture decisions** (see [CLAUDE.md](CLAUDE.md)):
- Alternative LLM providers (OpenAI, Gemini, etc.)
- Replacing LangGraph with another orchestration framework
- Replacing FastAPI + vanilla HTML/JS with a JS framework (React, Vue, etc.)
- Changing the auction formula from the confidence × conviction hybrid

If you believe a locked decision is wrong, open an issue to discuss before implementing.
