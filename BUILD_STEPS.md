# Creative Jury Swarm — Build Checklist

Phases 1–6 are complete. Phases 7 onward follow the production build plan (`docs/production_build_plan.md`).

---

## ✅ Phase 1: Repo & CLI shell — DONE
## ✅ Phase 2: Config — DONE
## ✅ Phase 3: Setup wizard — DONE
## ✅ Phase 4: Run folder & copy inputs — DONE
## ✅ Phase 5: Schemas (data contracts) — DONE
## ✅ Phase 6: PDF extraction (raw text) — DONE

---

## ✅ Phase 7: Model Router — DONE

- [x] **7.1** Create `cjs/router/model_router.py`. Implement `ModelRouter(run_id, config)` with:
  - `call_text(system, user, node) -> RouterResult`
  - `call_vision(system, user, images, node) -> RouterResult`
  - `call_extended_thinking(system, user, node) -> RouterResult`
- [x] **7.2** Each call injects `run_id` via `extra_headers={"X-Run-ID": run_id}` and returns `RouterResult(content, tokens_in, tokens_out, latency_ms, model)`.
- [x] **7.3** Wrap every call with `tenacity` retry: 3 attempts, exponential backoff (2s, 4s, 8s), retry on `anthropic.APIError`.
- [x] **7.4** Add circuit breaker: track consecutive failures per model; after 3, fall back to `claude-haiku-4-5-20251001`; write a fallback event to `runs/<run_id>/escalations.jsonl`.
- [x] **7.5** Write unit tests for retry logic and fallback behaviour (mock the Anthropic client).

---

## ✅ Phase 8: Observability Layer — DONE

- [x] **8.1** Create `cjs/observability/logging.py`. Configure `structlog` with JSON renderer in non-TTY, pretty renderer in TTY. Expose `get_logger()`.
- [x] **8.2** Replace all `typer.echo` / `print` in pipeline code with `structlog` calls carrying `run_id`, `node`, `agent` context vars.
- [x] **8.3** Create `cjs/observability/tracing.py`. Implement `init_tracer(run_id, service_name) -> Tracer` using OTel SDK + OTLP gRPC exporter (target: `OTEL_EXPORTER_OTLP_ENDPOINT` env var, default `localhost:4317`).
- [x] **8.4** Add `trace_node(name)` context manager used in every LangGraph node and every `ModelRouter` call. Span attributes: `run_id`, `model`, `tokens_in`, `tokens_out`, `latency_ms`.
- [x] **8.5** Propagate `trace_id` into every artifact JSON as a top-level field and into the HTML report header.
- [x] **8.6** Create `cjs/observability/audit.py`. Implement `AuditLogger(run_folder)` that appends one JSON line per LLM call to `audit.jsonl`: `{ts, run_id, trace_id, node, agent, model, prompt_hash, tokens_in, tokens_out, latency_ms}`. `prompt_hash` = SHA-256 of the rendered prompt string.
- [x] **8.7** Call `AuditLogger.log(...)` from `ModelRouter` after every successful or failed call.
- [x] **8.8** Add `cjs audit <run_id>` CLI command: load `audit.jsonl`, render as a Rich table.

---

## ✅ Phase 9: Brief Ingestion (LLM) — DONE (uncommitted)

- [x] **9.1** In `cjs/pipelines/brief_ingest.py`, add `parse_brief(raw_text, router) -> BriefJSON` using Claude tool-use structured output.
- [x] **9.2** Add `generate_rubric(brief, router) -> RubricJSON` — LLM generates dimension weights from brief objectives.
- [x] **9.3** Add `extract_brand_rules(brief, router) -> BrandRulesJSON` — fallback when no `--brand` YAML provided.
- [x] **9.4** Wire into `cjs run`: after `extract_brief_raw`, call all three; write `brief/brief.json`, `brief/rubric.json`, `brief/brand_rules.json`.

---

## ✅ Phase 10: Video Analysis Pipeline — DONE (uncommitted)

- [x] **10.1** Create `cjs/utils/ffmpeg.py`: `get_video_duration_sec(path) -> float` (ffprobe JSON), `extract_audio(video_path, out_path) -> None`.
- [x] **10.2** Create `cjs/utils/whisper_stt.py`: `transcribe(audio_path) -> str`. Graceful fallback: return `""` with a warning log if whisper not installed.
- [x] **10.3** Create `cjs/utils/frames.py`: `extract_keyframes(video_path, num_frames, out_dir) -> list[Path]` using OpenCV scene-cut or even sampling.
- [x] **10.4** Create `cjs/pipelines/video_analysis.py`: `analyze_video(video_path, run_folder, router, config) -> VideoDossier`. Flow: validate → audio → transcribe → keyframes → Claude Vision batch → assemble dossier → write `dossiers/<stem>_dossier.json`.
- [x] **10.5** In `cjs run`: for each copied video, call `analyze_video`; collect `list[VideoDossier]`.

---

## Phase 11: LangGraph Jury Swarm

- [x] **11.1** Create `cjs/graph/state.py`: `JuryState` TypedDict with all fields from the architecture plan.
- [x] **11.2** Agent logic lives in `cjs/graph/nodes/` (scoring, consistency, deliberation, moderator nodes).
- [x] **11.3** All five scoring agents, consistency checker, and moderator implemented as LangGraph nodes in `cjs/graph/nodes/`.
- [x] **11.4** Create `cjs/graph/jury_graph.py`: full 9-node LangGraph with `SqliteSaver` checkpointing.
- [x] **11.5** In `cjs run`: compile graph with `SqliteSaver`, invoke with `thread_id=run_id`.
- [x] **11.6** Add `cjs resume <run_id>` CLI command.

---

## Phase 12: Escalation System

- [x] **12.1** Create `cjs/escalation/human_review.py`. Gate node + `--auto-approve` flag.
- [x] **12.2** Create `cjs/escalation/confidence_gate.py`. `--strict-confidence` flag on `cjs run`/`resume`.
- [x] **12.3** Model fallback events write to the same `escalations.jsonl` schema.

---

## Phase 13: Auction Engine

- [x] **13.1** Create `cjs/auction/engine.py`: `compute_final_scores(state) -> dict[video, float]`.
- [x] **13.2** Add `select_winner(scores) -> str` and `build_verdict(scores, state) -> VerdictJSON`.
- [x] **13.3** Write `results/scorecards.json` and `results/verdict.json`.
- [x] **13.4** Unit tests: 13 tests covering all formula cases.

---

## Phase 14: HTML Report

- [x] **14.1** Create `cjs/report/template.html`: self-contained, all JS/CSS inline (no external CDN). Sections: header (run_id, trace_id, winner), radar charts (Chart.js), bar chart, score timeline, D3 debate graph, extended thinking expander, consistency flags panel, escalation events panel, low-confidence banner (conditional).
- [x] **14.2** Create `cjs/report/builder.py`: `build_report(run_folder, state, verdict, metrics) -> Path`. Reads all run artifacts, embeds as `<script>window.CJS_DATA = {...}</script>`, writes `results/report.html`.
- [x] **14.3** In `cjs run`: after auction, call `build_report`; auto-open `report.html` in browser with `webbrowser.open`.
- [x] **14.4** Verify report is fully self-contained (open without internet, no 404s in DevTools).

---

## Phase 15: LangSmith Integration

- [x] **15.1** Set `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_PROJECT=creative-jury-swarm` in `.env.example`.
- [x] **15.2** Add run metadata tags to LangSmith trace: `cjs_run_id`, `video_count`, `creative-jury-swarm` tag.
- [x] **15.3** Capture LangSmith run URL after invocation; write to `metrics.json` as `langsmith_url`.

---

## Phase 16: Packaging & Portfolio

- [x] **16.1** Create `Dockerfile`: multi-stage build, non-root user, `ffmpeg` installed, `pip install -e .`.
- [x] **16.2** Create `docker-compose.yml`: services `jaeger` (all-in-one, ports 16686 + 4317) and `app` (mounts `./runs`, passes `ANTHROPIC_API_KEY` + `OTEL_EXPORTER_OTLP_ENDPOINT`).
- [x] **16.3** Create `.github/workflows/ci.yml`: jobs `lint` (ruff), `typecheck` (mypy), `test` (pytest), `docker-build` — all parallel, triggered on push and PR.
- [x] **16.4** Rewrite `README.md`: Mermaid LangGraph diagram, Production Engineering Features table, Observability Stack diagram, Docker quick-start.
- [x] **16.5** Add `config_snapshot.yaml` written to each run folder at the start of `cjs run`.
- [x] **16.6** `SECURITY.md` and `.env.example` already exist; `langsmith` added to `pyproject.toml` dependencies.

---

## CLI design progress (incremental implementation)

- [x] Root/global `--json` mode and shared output helper in CLI.
- [x] `setup` renamed to `configure`.
- [x] `configure` supports `--non-interactive` and explicit override flags:
  `--provider`, `--text-model`, `--vision-model`, `--api-key-env`,
  `--out-dir`, `--max-videos`, `--max-duration-sec`, `--max-frames`.
- [x] Explicit `configure` options imply non-interactive save behavior.
- [x] Added `config` group with:
  - [x] `config get [key]` (dot-path lookup, full config when key omitted, JSON/non-JSON).
  - [x] `config set key value` (dot-path set, validation, int coercion for `limits.*`, JSON/non-JSON).
- [x] Added `models` command (JSON/non-JSON).
- [x] Added `runs` command (newest-first listing, JSON/non-JSON).
- [x] Added `report <run_id>` command (checks `results/report.html`, JSON/non-JSON).
- [x] Doctor implementation with JSON/non-JSON output and status checks:
  `python_version`, `ffmpeg`, `whisper`, `config`, `api_key_env`, `runs_dir`.
- [x] Doctor now emits an overall summary status in both human and JSON output.
- [x] `doctor --yes` scaffold with safe fixes: create default config when missing; retry runs-dir probe after mkdir attempt.
- [x] Doctor JSON summary includes `fixes_applied` when `--yes` is used.
- [x] `run` command CLI scaffold: Rich pipeline stages line + JSON payload.
- [x] Added comprehensive CLI and helper tests for the implemented surface.

### Remaining CLI items

- [x] `cjs resume <run_id>` — resume from LangGraph checkpoint (Phase 11.6).
- [x] `cjs audit <run_id>` — pretty-print `audit.jsonl` as Rich table (Phase 8.8).
- [x] Run UI: staged Rich progress panels per pipeline node.
- [x] `--strict-confidence` flag on `cjs run` (Phase 12.2).
- [x] `--auto-approve` flag on `cjs run` to skip human-in-the-loop prompt (Phase 12.1).
