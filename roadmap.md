# VoC Pipeline — Roadmap

Items are loosely ordered by anticipated value. Nothing here is committed or scheduled.

---

## Planned

### Transcript-Aware Unitization
**Status:** Not started

The unitizer currently handles short filler phrases (Rule 7) but is not equipped to deal with extended non-feedback content in call transcripts — pre-meeting chit-chat, technical setup exchanges ("can you hear me?", "let me share my screen"), and meeting logistics issues ("I can't join the Zoom", "my video isn't working").

**Proposed approach:**

Two complementary changes to `stage2_unitization.py`:

1. **Extend Rule 7** — add explicit examples covering multi-turn small talk, technical setup exchanges, and meeting logistics phrases. Catches the unambiguous cases with no added cost.

2. **Add `product_context` to `PipelineConfig`** — a short description of the product (e.g., "B2B analytics dashboard for marketing teams"). Thread it into the unitizer user prompt so Claude can distinguish "can't log into the Zoom" (meeting logistics, discard) from "can't log into your app" (product feedback, keep).

**Open questions:**
- `product_context` should probably live on `PipelineConfig`, but it could also be a per-CFO field to support multi-product deployments.
- If the product itself is auth, video, or communications-related, meeting logistics and product issues will still overlap — those edge cases may warrant a human-review flag on the unit rather than a discard.
- Down the line, if transcript token costs become significant, a cheap heuristic pre-trim (strip leading turns before the first topic-bearing utterance) could be layered in upstream of Stage 1 without touching the unitizer.

---

### Conversation Signal Extraction
**Status:** Not started

Conversations carry signals beyond product feedback. These are orthogonal to `FeedbackUnit` and warrant a parallel extraction track — same input CFO/transcript, separate agents, separate schemas and DB tables.

Signals are grouped below by priority.

#### Tier 1 — Highest value, implement first

**Action Items**
Commitments made by either side during the call, with owner and deadline where stated. Feeds post-call follow-up workflows directly.
- Fields: `text`, `owner` (customer | vendor | unknown), `due_date`, `source_turn`

**Churn & Urgency Risk**
Language indicating a hard deadline, active evaluation of alternatives, contract renewal pressure, or a blocking issue. Feeds account health scoring.
- Fields: `risk_type` (churn | deadline | escalation | blocker), `urgency` (high | medium | low), `verbatim`, `due_date`

#### Tier 2 — High value, implement second

**Competitive Mentions**
Competitor names, feature benchmarks, or active evaluations raised during the call.
- Fields: `competitor_name`, `context` (evaluating | benchmarking | switched_from | mentioned), `verbatim`

**Expansion Signals**
Indicators of potential growth: rollout plans, interest in unpurchased features, budget availability hints.
- Fields: `signal_type` (rollout | feature_interest | budget_available), `verbatim`

#### Tier 3 — Slower-burn, implement later

**Organizational Signals**
Upcoming changes in the customer's org that affect product usage or the relationship — reorgs, migrations, new initiatives, budget cycles.
- Fields: `signal_type` (reorg | migration | new_initiative | budget_cycle), `verbatim`, `timeframe`

**Stakeholder Signals**
New contacts, decision makers, champions, or blockers mentioned but not present on the call.
- Fields: `name` (redacted post-PII), `role`, `influence_type` (champion | blocker | decision_maker | influencer)

**Compliance & Constraints**
Hard technical or regulatory requirements raised (data residency, security certifications, integrations).
- Fields: `constraint_type` (data_residency | security | regulatory | integration), `verbatim`

**Architecture notes:**
- All signal agents run in parallel alongside Stage 3, branching from the same canonical units
- Each signal type has its own DB table; the `BatchAnalysis` object should be extended to carry a `signals` dict keyed by type
- Use Haiku for all extraction — these are structured JSON outputs with fixed enums, same pattern as sentiment/intent
- PII redaction (Stage 1) must run before signal extraction; verbatim fields should reference `clean_text` offsets

**Open questions:**
- Whether signals should be extracted per `FeedbackUnit` or per full transcript turn (turn-level is more natural for action items and stakeholder mentions)
- How to surface signals to consumers — dedicated API endpoints vs. embedding in `BatchAnalysis`
- Deduplication strategy for action items and stakeholder mentions that recur across batches

---

### Product Knowledge Memory
**Status:** Not started

The pipeline currently analyses feedback without any awareness of what the product actually does. This means topic labels can be generic, intent classification lacks grounding, and there is no way to distinguish a known limitation from a regression.

**Proposed approach:**

Introduce a `ProductKnowledgeStore` that builds and maintains a structured understanding of the product from the feedback stream itself — no manual seeding required.

- On each batch, a lightweight summarisation pass extracts product area mentions, feature names, and capability signals from canonical feedback units and merges them into a persistent knowledge graph (product areas → features → known pain points).
- The store is seeded from the first batch and updated incrementally, so it grows richer as more feedback flows through.
- At inference time, the relevant slice of product knowledge is injected into the context window for topic extraction and intent classification, giving Claude a grounded vocabulary to work from.
- Optionally accepts a manually authored product brief (plain text or structured JSON) at initialisation so day-one coverage is not purely feedback-derived.

**Stages that benefit directly:**

| Stage | Benefit |
|---|---|
| `stage3_topic_extraction.py` | Topic labels align to real product areas; fewer generic labels like "performance" when the correct label is "Report Export" |
| `stage3_intent_extraction.py` | Intent classification distinguishes known bugs from new regressions; feature requests are mapped to existing roadmap items where applicable |
| `extract_account.py` | Account context (industry, plan tier) can be cross-referenced against product knowledge to surface account-specific impact |

**Open questions:**
- How to handle product pivots or renames without polluting the store with stale concepts.
- Whether the store should be shared across all accounts (global product model) or maintained per-account (richer per-tenant signal, higher storage cost).
- Persistence backend — the current in-memory pattern works for the dedup and topic stores because they recover quickly; product knowledge is more expensive to rebuild and likely warrants PostgreSQL persistence from the start.
