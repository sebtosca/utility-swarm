# Changelog

## 2026-05-15

### Documentation & planning

- Added `docs/production_build_plan.md` — full production build plan covering OTel tracing, structured logging, audit trail, circuit breaker model fallback, human-in-the-loop escalation, confidence gating, LangGraph `SqliteSaver` checkpointing, Docker compose, and GitHub Actions CI.
- Rewrote `BUILD_STEPS.md` — replaced outdated phases 7–14 with production-grade phases 7–16 aligned to the new build plan; preserved completed phases 1–6 and CLI design progress log.
- Copied `BUILD_STEPS.md` into `docs/` for repo discoverability.
- Removed `docs/creative_jury_skeleton.md` — superseded by implemented code and the production build plan.

---

## 2026-03-01

- Implemented major CLI surface updates aligned with the OpenClaw-style plan:
  - Added global `--json` mode.
  - Renamed `setup` to `configure` with non-interactive and override options.
  - Added `config get` / `config set` with dot-path support and validation.
  - Added `models`, `runs`, and `report <run_id>` commands.
  - Upgraded `doctor` with real checks (`python_version`, `ffmpeg`, `whisper`, `config`, `api_key_env`, `runs_dir`), summary status, and `--yes` safe-fix behavior.
  - Added `run` CLI scaffolding with Rich stage output (non-JSON) and machine-readable JSON payload.
- Added broad CLI and helper test coverage.
- Current test status: `50 passed`.

### Known limitations

- Core jury pipeline execution is still not implemented in `cjs run`.
- Current `run` UX is scaffolding only (Rich stages + JSON status payload).
- Doctor `--yes` applies only safe local fixes (config creation and runs-dir recovery), not dependency installation or API key setup.

### Progress snapshot

- Latest local test run: `57 passed`.
