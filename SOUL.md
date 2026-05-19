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

Phases 1–8 complete: CLI shell, config system, run storage, Pydantic schemas, PDF extraction,
model router (retry + circuit-breaker + Haiku fallback), observability (OTel + structlog + audit
trail), brief ingestion pipeline, and video analysis pipeline (ffmpeg + Whisper + Claude Vision).

v1 target: full LangGraph pipeline — parallel jury scoring, consistency check, deliberation round,
Moderator verdict, and HTML report. See [BUILD_STEPS.md](BUILD_STEPS.md) for in-flight phases.

v2: Improvement Swarm — agents generate specific, actionable improvement recommendations
per video, framed for the production team that made the ad.

→ [Quick start and commands](README.md)
