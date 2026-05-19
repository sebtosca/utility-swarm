# Agent System

## Jury flow

```
Brief PDF + Video files
         │
         ▼
  BriefIngest
  brief.json + rubric.json + brand_rules.json
         │
         ▼
  VideoAnalysis (parallel, one per video)
  → video_dossier.json per video
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
**Token bid logic:** Bids 0–100 per video on compliance rigour. A bid of 100 means this ad is fully compliant and clean; a bid of 0 means the agent would not stake its professional reputation on approving it.  
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
**Token bid logic:** Bids 0–100 per video on audience resonance conviction. A bid of 100 means this ad will genuinely land with the target audience; a bid of 0 means it will alienate or miss them.  
**Flags:** Factual findings (not subjective preferences):
- Cultural insensitivity
- Demographic alienation signal
- Psychographic mismatch causing significant audience disengagement

---

### Performance Marketer Agent
**Role:** Evaluates whether the ad will perform — hook speed, CTA clarity, value proposition delivery, platform-specific optimisation.  
**Scoring domains:** `message_clarity`, `performance_potential`.  
**Extended thinking:** No.  
**Token bid logic:** Bids 0–100 per video on performance conviction. A bid of 100 means this ad will drive the primary KPI; a bid of 0 means it will be paused by the algorithm or ignored by the audience.  
**Flags:** Compliance findings (not performance opinions):
- Platform policy violation (Meta, TikTok, YouTube ad review failure)
- Implied claim not supported by the brief
- CTA mechanics rejected by ad auction

---

### Storytelling Critic Agent
**Role:** Evaluates the structural integrity and emotional logic of the story — arc, pacing, payoff, narrative coherence.  
**Scoring domains:** `storytelling`.  
**Extended thinking:** No.  
**Token bid logic:** Bids 0–100 per video on narrative quality conviction. A bid of 100 means the story is structurally excellent; a bid of 0 means the narrative fails to earn its emotional payoff.  
**Flags:** Structural findings only:
- Misleading narrative structure (arc implies a claim the brand cannot support)
- Structural deception (emotional payoff built on an unearned premise)

---

### Consistency Checker
**Role:** Factual auditor. Detects contradictions between agent claims and the video dossier, and between agents' written narratives and their own scores. Runs after the blind pass, before deliberation.  
**Scoring domains:** None.  
**Extended thinking:** No (fast call).  
**Token bid logic:** N/A — does not participate in the auction.
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
**Token bid logic:** N/A — does not participate in the auction.
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

Creative Strategist, Consistency Checker, and Moderator do not score rubric dimensions.

---

## Auction mechanics

After the deliberation round, the Moderator runs a hybrid auction to produce a quantitative ranking before writing the verdict narrative.

**Formula:** `auction_score = confidence_bid × conviction_bid / 100`

- **Conviction bid (token_bid):** Each scoring agent bids 0–100 per video, representing domain conviction — how strongly they'd stake their professional reputation on this ad winning within their domain.
- **Confidence bid:** Each agent reports 0–100 confidence per video — how clearly the evidence supports their scores (not how good the ad is, but how certain they are). Low video quality, ambiguous claims, or missing information drive confidence down.

**Why hybrid, not pure LLM verdict:** A pure LLM ranking is non-deterministic and not auditable. The auction produces a deterministic quantitative ranking. The Moderator uses this as the primary signal, then writes a qualitative verdict that explains and contextualises it.

**Weights:** The auction treats all five scoring agents equally. The Moderator's extended thinking resolves cases where the auction outcome conflicts with a hard compliance flag (e.g. the highest-scoring ad has a missing mandatory element).
