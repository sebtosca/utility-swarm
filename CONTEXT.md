# Creative Jury Swarm

A multi-agent evaluation system that ingests a creative brief and video ads, runs a structured specialist jury, and produces a ranked verdict with a full audit trail.

## Language

### Evaluation pipeline

**Jury Run**:
A single end-to-end evaluation: one brief, one or more videos, one verdict. Produces a timestamped run folder and a SQLite index entry.
_Avoid_: job, task, session, evaluation

**Brief**:
The client's creative specification, parsed from PDF into structured JSON (`Brief`, `Rubric`, `BrandRules`).
_Avoid_: spec, requirements, creative brief (redundant)

**Video Dossier**:
The structured analysis of a single video: transcript, scene metadata, frame paths, logo timing, CTA detection, duration.
_Avoid_: video analysis, video data, video record

**Rubric**:
The weighted scoring dimensions extracted from the brief. Owns the per-dimension weights and descriptions used by scoring agents.
_Avoid_: scorecard, criteria, dimensions

### Jury process

**Blind Pass**:
The first jury scoring round. Each scoring agent evaluates videos independently; no agent sees another's scores or narrative until deliberation.
_Avoid_: first pass, initial scoring, independent scoring

**Deliberation Round**:
The second scoring pass. Agents receive the group scorecard and any consistency flags; each may revise its scores. Overwrites blind pass judgements.
_Avoid_: second pass, revision round, adjustment round

**AgentJudgement**:
The output of one scoring agent for one video: dimension scores, conviction bid, confidence bid, evidence citations, flags, and notes.
_Avoid_: scorecard (ambiguous — refers to the collection), judgement, score

**Consistency Flag**:
A factual finding raised by the Consistency Checker: either a `FACTUAL_CONTRADICTION` (agent claim contradicts the dossier) or a `SCORE_NARRATIVE_MISMATCH` (agent's text contradicts its own scores).
_Avoid_: flag, warning, inconsistency

### Auction

**Conviction Bid** (`token_bid`):
An agent's 0–100 stake on a video winning within its domain. Represents professional conviction, not evidence quality.
_Avoid_: token bid (implementation name), domain score, weight

**Confidence Bid** (`confidence`):
An agent's 0–100 rating of how clearly the evidence supports its scores. Low video quality or ambiguous claims drive this down.
_Avoid_: certainty, evidence score, confidence score

**Auction Score**:
`conviction_bid × confidence_bid / 100` — the deterministic per-video ranking signal. Summed across all five scoring agents per video.
_Avoid_: weighted score, final score, ranking score

**Verdict**:
The Moderator's final output: ranked video list, winner rationale, per-video summaries, unresolved concerns.
_Avoid_: result, report, ranking (refers only to the ordered list)

### UI

**Jury Room**:
The live web UI for observing a jury run in progress. Distinct from the static `report.html` which is the post-run artefact.
_Avoid_: UI, dashboard, frontend

**Heartbeat Event**:
A WebSocket event emitted at the start and end of every LLM call (`llm_call_start`, `llm_call_complete`). Carries model, node, agent, tokens, latency, and thinking (if extended thinking).
_Avoid_: streaming event, status update, progress event

**Observability Panel**:
The right-side panel in the Jury Room that shows the real-time trace: heartbeat events, handoff rows, and expandable thinking blocks.
_Avoid_: trace panel, log panel, debug panel

---

## Relationships

- A **Jury Run** evaluates one **Brief** against one or more **Video Dossiers**
- The **Blind Pass** produces one **AgentJudgement** per scoring agent per video
- The **Deliberation Round** may revise those **AgentJudgements** in place
- The **Auction** uses all post-deliberation **AgentJudgements** to compute an **Auction Score** per video
- The **Moderator** reads the **Auction Score** ranking and writes the final **Verdict**
- The **Consistency Checker** reads **Blind Pass** judgements (not deliberation) and emits **Consistency Flags**
- A **Heartbeat Event** is emitted once per LLM call, regardless of which agent or pipeline stage

---

## Example dialogue

> **Dev:** "When the Consistency Checker fires, does it see the deliberation scores or the blind pass scores?"
> **Domain expert:** "Blind pass only — it runs before deliberation. That's the point: it catches contradictions before agents can revise to hide them."

> **Dev:** "Why do we show both the conviction bid and the confidence bid on the agent card? Isn't one enough?"
> **Domain expert:** "The auction multiplies them. An agent can be highly confident but have low conviction — or the reverse. Showing only one misrepresents why a video ranked where it did."

---

## Flagged ambiguities

- "scorecard" appears in code as both the collection of all `AgentJudgements` and sometimes as a synonym for a single `AgentJudgement` — resolved: **scorecard** refers to the full collection; individual outputs are **AgentJudgements**.
- "confidence" was used in the Anthropic API context (LLM confidence) and in the jury context (evidence clarity bid) — resolved: in this system **confidence** always means the **Confidence Bid** (0–100 evidence clarity score set by the agent), never model-level uncertainty.
