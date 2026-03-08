# AI-First Voice of Customer (VoC) System Design

## Extracting Core Feedback Themes, User Sentiment & Taxonomy from Raw Customer Feedback

---

## 1. System Overview & Design Philosophy

The goal of this system is to take raw, unstructured customer feedback — from surveys, support tickets, app store reviews, social media, NPS responses, chat transcripts, and more — and transform it into a structured, queryable knowledge base of themes, sentiments, and a living taxonomy. The system should be **adaptive** (the taxonomy evolves as new feedback arrives), **multi-granular** (operating at the sentence, response, and corpus level), and **explainable** (every theme and sentiment score traces back to source verbatims).

The architecture follows a **pipeline-of-agents** pattern, where each stage is an LLM-powered module with a well-defined contract. This contrasts with traditional NLP pipelines that chain deterministic classifiers; here, each agent reasons over its input with full linguistic context, and downstream agents can challenge or refine upstream outputs.

### Core Design Principles

**Feedback-Native Ingestion:** Treat every feedback source as a first-class citizen with its own schema adapter, rather than flattening everything into plain text prematurely — metadata like channel, timestamp, user segment, and product area are critical context signals that improve extraction quality.

**Hierarchical Theme Modeling:** Themes aren't flat labels. They form a tree (or DAG) where "Checkout Experience" may have children like "Payment Failures," "Slow Loading," and "Coupon Code Issues." The system must discover, maintain, and refine this hierarchy over time.

**Sentiment as a Spectrum, Not a Binary:** Go beyond positive/negative/neutral. Capture intensity (mild frustration vs. outrage), aspect-level sentiment (loves the product but hates support), and emotional tone (confused, delighted, anxious, disappointed).

**Grounded Outputs:** Every extracted theme and sentiment score must point back to the exact span of text (verbatim) that produced it, enabling auditing, QA, and downstream reporting.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     FEEDBACK SOURCES                            │
│  Surveys │ Support Tickets │ Reviews │ Social │ Chat │ Email    │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 1: INGESTION & NORMALIZATION                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐                 │
│  │ Source      │  │ Language   │  │ PII        │                 │
│  │ Adapters    │→ │ Detection  │→ │ Redaction  │                 │
│  └────────────┘  │ & Translate │  └────────────┘                 │
│                  └────────────┘                                   │
└──────┬───────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 2: SEGMENTATION & PREPROCESSING                           │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐               │
│  │ Feedback    │  │ Multi-topic│  │ Deduplication│               │
│  │ Unitization │→ │ Splitting  │→ │ & Near-Dup   │              │
│  └────────────┘  └────────────┘  │ Detection    │               │
│                                  └──────────────┘               │
└──────┬───────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 3: EXTRACTION AGENTS (LLM-Powered)                        │
│  ┌────────────────┐  ┌─────────────────┐  ┌───────────────────┐ │
│  │ Sentiment &    │  │ Theme / Topic   │  │ Intent & Request  │ │
│  │ Emotion Agent  │  │ Extraction Agent│  │ Detection Agent   │ │
│  └───────┬────────┘  └───────┬─────────┘  └───────┬───────────┘ │
│          │                   │                     │             │
│          └───────────┬───────┘─────────────────────┘             │
│                      ▼                                           │
│            ┌──────────────────┐                                  │
│            │ Grounding &      │                                  │
│            │ Evidence Linker  │                                  │
│            └──────────────────┘                                  │
└──────┬───────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 4: TAXONOMY ENGINE                                        │
│  ┌────────────────┐  ┌─────────────────┐  ┌───────────────────┐ │
│  │ Cluster &      │  │ Hierarchy       │  │ Taxonomy          │ │
│  │ Merge Agent    │  │ Construction    │  │ Versioning &      │ │
│  └────────────────┘  └─────────────────┘  │ Drift Detection   │ │
│                                           └───────────────────┘ │
└──────┬───────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 5: AGGREGATION & INSIGHT GENERATION                       │
│  ┌────────────────┐  ┌─────────────────┐  ┌───────────────────┐ │
│  │ Theme Volume & │  │ Trend &         │  │ Executive Summary │ │
│  │ Scoring        │  │ Anomaly Detect  │  │ Generation Agent  │ │
│  └────────────────┘  └─────────────────┘  └───────────────────┘ │
└──────┬───────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────────────┐
│  STAGE 6: SERVING & FEEDBACK LOOP                                │
│  ┌────────────────┐  ┌─────────────────┐  ┌───────────────────┐ │
│  │ API & Dashboard│  │ Human-in-Loop   │  │ Continuous        │ │
│  │ Layer          │  │ Review Queue    │  │ Learning Loop     │ │
│  └────────────────┘  └─────────────────┘  └───────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Stage-by-Stage Algorithm Design

---

### Stage 1: Ingestion & Normalization

#### 1.1 Source Adapters

Each feedback channel has a dedicated adapter that maps channel-specific data into a **Canonical Feedback Object (CFO)**. This is the universal internal representation that every downstream component consumes.

```
CanonicalFeedbackObject {
  id:               UUID
  raw_text:         string          // Original verbatim
  clean_text:       string          // After normalization
  source_channel:   enum            // survey | ticket | review | social | chat | email
  source_metadata:  {               // Channel-specific fields
    survey_question:    string?     // e.g., "How was your checkout experience?"
    ticket_category:    string?     // e.g., "Billing"
    app_store:          string?     // e.g., "iOS App Store"
    star_rating:        int?        // e.g., 3
    platform:           string?     // e.g., "web", "mobile"
  }
  user_metadata:    {
    segment:            string?     // e.g., "enterprise", "free-tier"
    tenure_days:        int?
    geography:          string?
    anonymized_user_id: string?
  }
  timestamps:       {
    feedback_created:   datetime
    ingested_at:        datetime
  }
  language:         string          // ISO 639-1 code
  pii_redacted:     boolean
}
```

**Why this matters:** Downstream agents use `source_metadata` to calibrate their behavior. For example, a 3-star app review has a very different sentiment baseline than an NPS detractor comment — the agent needs this context to score sentiment accurately. Similarly, knowing the survey question that prompted a response helps the topic extractor disambiguate vague feedback like "it was fine" (fine relative to *what*?).

#### 1.2 Language Detection & Translation

The system uses an LLM call to detect the language and, if non-English (or non-primary language), translate the feedback while preserving the original. Both versions are stored in the CFO so that downstream agents can operate on the translated text but verbatim citations reference the original.

**Algorithm:**

1. Pass `raw_text` through a lightweight language-detection model (e.g., fasttext `lid.176.bin` or an LLM prompt).
2. If the detected language differs from the system's primary analysis language, invoke a translation agent.
3. Store both `raw_text` (original) and `clean_text` (translated + normalized) in the CFO.
4. Flag mixed-language feedback (e.g., Spanglish) for special handling — these should not be naively machine-translated but processed with a bilingual-aware prompt.

#### 1.3 PII Redaction

Before any feedback enters the extraction pipeline, personally identifiable information must be stripped. This is both a compliance requirement (GDPR, CCPA) and a quality measure — PII tokens add noise to theme clustering.

**Approach:** Use a named entity recognition (NER) model fine-tuned for PII (names, emails, phone numbers, addresses, account numbers) combined with regex patterns for structured PII. Replace detected PII with typed placeholders: `[PERSON_NAME]`, `[EMAIL]`, `[PHONE]`, etc. This preserves sentence structure for downstream NLP while removing sensitive data.

---

### Stage 2: Segmentation & Preprocessing

#### 2.1 Feedback Unitization

Raw feedback often contains multiple distinct ideas in a single response. Consider: *"I love the new dashboard redesign, but the export feature is broken and your support team took 3 days to respond."* This is three distinct feedback units — one positive (dashboard), one bug report (export), and one complaint (support response time).

**Algorithm: The Unitization Agent**

This is an LLM-powered agent with the following prompt structure:

```
SYSTEM: You are a feedback analyst. Your job is to split a single piece of
customer feedback into its atomic "feedback units" — each unit should express
exactly one opinion, complaint, request, or observation about one specific
aspect of the product or experience.

Rules:
- Each unit must be self-contained and understandable without the others.
- Preserve the customer's original wording as closely as possible.
- Tag each unit with the character offsets (start, end) in the original text.
- If the feedback is already atomic (single topic), return it as one unit.
- Contextual phrases like "overall" or "in general" should remain attached
  to the opinion they modify.
```

**Input:** The CFO's `clean_text` plus `source_metadata` (the survey question provides disambiguation context).

**Output:** An array of `FeedbackUnit` objects, each with `text`, `char_start`, `char_end`, and a `parent_cfo_id` linking back to the source.

**Why unitize before extracting themes?** If you run theme extraction on the whole feedback verbatim, you get muddied results — a response that's both positive about UX and negative about performance might get classified as "mixed" or assigned to only the dominant theme. Unitizing first gives each downstream agent a clean, single-topic input to reason about, dramatically improving precision.

#### 2.2 Deduplication & Near-Duplicate Detection

In high-volume environments (100k+ feedback items per month), you'll encounter verbatim duplicates (same user submitting the same feedback twice) and near-duplicates (templated responses, copied complaint scripts, or bot-generated reviews).

**Algorithm:**

1. Compute a semantic embedding for each feedback unit using a sentence-transformer model (e.g., `all-MiniLM-L6-v2` or a similar efficient model).
2. Index embeddings in a vector store (e.g., pgvector, Pinecone, or FAISS).
3. For each new feedback unit, query the index for nearest neighbors with cosine similarity > 0.95.
4. If a near-duplicate cluster is found, mark subsequent entries as `is_duplicate = true` with a pointer to the canonical entry, and increment the canonical entry's `duplicate_count`.
5. Duplicates are excluded from theme discovery but included in volume counting (a theme mentioned 500 times is more important than one mentioned 5 times, even if 400 of the 500 are near-duplicates of 50 originals).

---

### Stage 3: Extraction Agents

This is the heart of the system. Three specialized LLM agents run in parallel on each feedback unit, then a grounding agent links their outputs back to source text.

#### 3.1 Sentiment & Emotion Agent

**Purpose:** Assign fine-grained sentiment and emotional tone to each feedback unit.

**Output Schema:**

```
SentimentResult {
  unit_id:            UUID
  polarity:           float         // -1.0 (very negative) to +1.0 (very positive)
  intensity:          enum          // mild | moderate | strong | extreme
  emotions:           [{            // Multi-label emotional tags
    emotion:          string        // e.g., "frustrated", "delighted", "confused"
    confidence:       float         // 0.0 to 1.0
  }]
  aspect_sentiments:  [{            // Aspect-level sentiment
    aspect:           string        // e.g., "checkout speed", "customer support"
    polarity:         float
    evidence_span:    string        // Exact text span supporting this
  }]
  sarcasm_flag:       boolean       // Did the model detect sarcasm or irony?
  confidence:         float
}
```

**Algorithm — Multi-Pass Sentiment Extraction:**

**Pass 1: Context-Aware Polarity Scoring.** The agent receives the feedback unit text *plus* the source metadata (channel, star rating if available, survey question). This context is essential because the same words carry different weight in different channels. "It's okay I guess" in a 2-star review is negative; in a post-resolution survey, it might be neutral-to-positive.

The LLM prompt instructs the model to first identify the aspect being discussed, then assess the customer's stance toward that aspect, and finally map it to the polarity/intensity scale. The prompt includes calibration examples spanning the full range (mild positive to extreme negative) to anchor the model's internal scale.

**Pass 2: Emotion Classification.** Using the same text, a second prompt (or a second section of the same structured prompt) asks the model to identify the emotional state of the customer. The emotion taxonomy is based on a curated set of 12–16 emotions relevant to customer feedback contexts: frustrated, angry, disappointed, confused, anxious, neutral, satisfied, pleased, delighted, grateful, surprised (positive), surprised (negative), resigned, and hopeful.

**Pass 3: Sarcasm & Irony Detection.** This is a critical quality gate. Sarcastic feedback like *"Oh sure, I just LOVE waiting 45 minutes for support"* will fool naive sentiment classifiers into returning a positive score. The agent is prompted to flag sarcasm and, when detected, to invert the polarity score accordingly.

**Calibration Strategy:** To prevent model drift and ensure consistency across runs, maintain a calibration dataset of 200–500 expert-labeled feedback units spanning all channels, emotions, and polarity levels. Periodically run the agent over this dataset and compute agreement metrics (Cohen's kappa, mean absolute error on polarity). If agreement drops below threshold, update the prompt with additional examples from the failure cases.

#### 3.2 Theme & Topic Extraction Agent

**Purpose:** Identify the core product/experience topic(s) that each feedback unit is about, expressed as a short, canonical theme label.

**This is the most complex agent in the system.** The challenge is twofold: the agent must (a) extract the specific topic from the text, and (b) map it to the correct node in an evolving taxonomy — or flag it as a new topic if it doesn't match anything.

**Output Schema:**

```
ThemeResult {
  unit_id:            UUID
  primary_theme:      {
    label:            string        // e.g., "Payment Processing Failure"
    taxonomy_node_id: UUID?         // Link to existing taxonomy, null if new
    confidence:       float
  }
  secondary_themes:   [...]         // Same structure, for multi-theme units
  extracted_features: [{            // Specific product features mentioned
    feature:          string        // e.g., "Apple Pay", "CSV export"
    sentiment_toward: float         // Sentiment specifically about this feature
  }]
  is_new_topic:       boolean       // True if no good taxonomy match exists
  suggested_label:    string?       // Suggested label if is_new_topic = true
  evidence_spans:     [string]      // Text spans grounding the theme assignment
}
```

**Algorithm — Taxonomy-Guided Theme Extraction:**

**Step 1: Open Extraction.** First, the agent extracts the topic *without* seeing the existing taxonomy. This is deliberate — showing the taxonomy first biases the model toward existing categories and makes it less likely to discover genuinely new themes.

Prompt structure: *"Read this customer feedback and identify the specific product area, feature, or experience being discussed. Be as precise as possible — 'billing' is too vague; 'unexpected charge after free trial cancellation' is much better. Return a short label (3–8 words) and the exact text spans that support your choice."*

**Step 2: Taxonomy Matching.** Next, the agent receives the extracted label from Step 1 alongside the current taxonomy (or the relevant subtree, if the taxonomy is large). It's asked to find the best-matching taxonomy node.

Prompt structure: *"You extracted the theme '[open_label]' from this feedback. Here is the current taxonomy of known themes: [taxonomy_subtree]. Does the extracted theme match any existing node? If yes, return the node ID and explain why. If no existing node is a good match, return 'NEW_THEME' and suggest where in the hierarchy it should be placed."*

**Step 3: Confidence Gating.** If the agent's match confidence is below 0.7, the unit is routed to a human review queue (discussed in Stage 6) rather than being auto-classified. This prevents taxonomy pollution from low-confidence assignments.

**Step 4: Feature Extraction.** As a sub-task, the agent identifies specific product features, API endpoints, UI elements, or workflows mentioned in the feedback. These are finer-grained than themes and are critical for product teams who need to know *exactly* which button or flow is causing issues.

#### 3.3 Intent & Request Detection Agent

**Purpose:** Classify the type of feedback (complaint, feature request, question, praise, churn signal, etc.) and extract any specific asks from the customer.

**Output Schema:**

```
IntentResult {
  unit_id:            UUID
  intent_type:        enum          // complaint | feature_request | bug_report |
                                    // question | praise | churn_signal |
                                    // comparison | suggestion | general_comment
  urgency:            enum          // low | medium | high | critical
  specific_request:   string?       // e.g., "Add dark mode to the mobile app"
  competitor_mention:  string?       // e.g., "Competitor X has this feature"
  churn_indicators:   [{            // Signals that the customer may leave
    signal:           string        // e.g., "mentioned cancellation"
    severity:         float
  }]
}
```

**Why separate intent from theme?** Theme answers *"what is this about?"* while intent answers *"what does the customer want to happen?"* A feedback unit about "checkout speed" (theme) could be a complaint (intent: it's too slow), a feature request (intent: add one-click checkout), or praise (intent: none, just expressing satisfaction). Separating these dimensions enables richer analysis downstream — for example, a PM can filter for all *feature requests* about *checkout*, specifically from *enterprise* users.

#### 3.4 Grounding & Evidence Linker

After all three agents have produced their outputs, the **Evidence Linker** performs a critical quality assurance step: it verifies that every claim (theme assignment, sentiment score, intent classification) is grounded in the actual text.

**Algorithm:**

1. For each extraction result, collect the `evidence_spans` cited by the agent.
2. Verify that each span actually exists in the original text (character offset matching).
3. For sentiment, verify that the cited span plausibly supports the assigned polarity (a simple entailment check — does "I love this feature" support a positive polarity?).
4. For themes, verify that the cited span actually discusses the assigned theme (a relevance check).
5. Flag any "ungrounded" claims — these are sent to the review queue and excluded from aggregation until resolved.

This step catches hallucinations. LLMs occasionally generate evidence spans that don't exist in the source text or assign themes based on inferential leaps rather than explicit mentions. The Grounding Agent acts as a quality firewall.

---

### Stage 4: Taxonomy Engine

The taxonomy is the backbone of the entire system. It defines the shared vocabulary that product teams, support leaders, and executives use to discuss customer feedback. A poorly maintained taxonomy renders everything downstream useless.

#### 4.1 Taxonomy Structure

```
TaxonomyNode {
  id:                 UUID
  label:              string        // Human-readable label
  description:        string        // Definition to disambiguate
  parent_id:          UUID?         // Null for root nodes
  aliases:            [string]      // Alternative labels that map to this node
  embedding:          vector        // Semantic embedding of label + description
  created_at:         datetime
  last_updated:       datetime
  feedback_count:     int           // How many units are tagged with this node
  status:             enum          // active | deprecated | candidate | merged
  merge_target:       UUID?         // If merged, points to the surviving node
}
```

**The taxonomy has 3–4 levels of depth:**

- **Level 0 (Pillars):** Broad product areas. Examples: "Product Experience," "Customer Support," "Pricing & Billing," "Onboarding," "Reliability."
- **Level 1 (Categories):** Major topic areas within pillars. Under "Product Experience": "Navigation & UX," "Performance," "Feature Gaps," "Mobile Experience."
- **Level 2 (Themes):** Specific issues or topics. Under "Performance": "Page Load Speed," "Search Latency," "Export Timeout," "Mobile App Crashes."
- **Level 3 (Sub-themes, optional):** Ultra-specific variants. Under "Mobile App Crashes": "Crash on iOS 17 During Checkout," "Crash After Photo Upload."

#### 4.2 Taxonomy Bootstrap Algorithm

For a new deployment with no existing taxonomy, the system must bootstrap one from scratch using the first batch of feedback.

**Algorithm:**

1. **Batch Extraction:** Run the Theme Extraction Agent (Stage 3.2, Step 1 only — open extraction, no taxonomy matching) on the first N feedback units (N = 1,000–5,000 is typically sufficient for a reasonable initial taxonomy).

2. **Semantic Clustering:** Embed all extracted theme labels using a sentence-transformer. Apply hierarchical agglomerative clustering with a distance threshold tuned to produce 30–80 clusters at the leaf level. The intuition is that labels like "slow page load," "pages take forever," and "loading speed is terrible" should cluster together.

3. **Cluster Labeling:** For each cluster, pass the member labels and a sample of the underlying feedback text to an LLM agent and ask it to generate a canonical label and a short description. Prompt: *"These feedback items all discuss similar topics: [sample]. Generate a clear, specific theme label (3-8 words) and a one-sentence description that would help a product manager understand exactly what this theme covers."*

4. **Hierarchy Construction:** Pass the full set of cluster labels to an LLM agent and ask it to organize them into a tree. Prompt: *"Here are [N] customer feedback themes extracted from our product. Organize them into a hierarchy of 3–4 levels, from broad product areas down to specific issues. Group related themes under common parents. Return the tree structure with labels and parent-child relationships."*

5. **Human Review:** Present the draft taxonomy to the product team for validation. They may rename nodes, merge clusters, or add missing categories from their domain knowledge. This human review step is essential for the initial taxonomy — it ensures alignment with how the organization already thinks about their product.

#### 4.3 Continuous Taxonomy Evolution

The taxonomy must evolve as the product and customer base evolve. New features launch, old issues get fixed, and entirely new categories of feedback emerge.

**Algorithm: The Taxonomy Evolution Loop (runs weekly or at configurable intervals)**

**Step 1: Collect New Topic Candidates.** Gather all feedback units from the period where `is_new_topic = true` (units that the Topic Extraction Agent couldn't match to existing taxonomy nodes).

**Step 2: Cluster Candidates.** Embed and cluster the new theme labels, same as the bootstrap algorithm. If a cluster has >= K members (K = 5–10, configurable), it's a strong candidate for a new taxonomy node.

**Step 3: Evaluate Against Existing Taxonomy.** For each candidate cluster, the system checks whether it should become a new node or be merged into an existing node that was simply too narrowly defined. The LLM agent receives the candidate cluster's labels, sample feedback, and the most semantically similar existing taxonomy nodes. It decides: (a) create new node (and suggest where in the hierarchy), (b) merge into existing node (and update the node's description/aliases), or (c) discard (noise, not a real theme).

**Step 4: Detect Deprecated Themes.** If an existing taxonomy node's feedback volume drops to near-zero for 3+ consecutive periods, flag it as a deprecation candidate. Deprecated themes remain in the taxonomy (for historical reporting) but are de-prioritized in the matching step.

**Step 5: Drift Detection.** Compare the embedding of each taxonomy node's label/description against the centroid of the feedback units assigned to it. If these diverge significantly over time (cosine similarity drops below 0.8), it means the theme's *meaning* is shifting — customers are using the same label to discuss different things. Flag for human review and potential node splitting.

**Step 6: Version the Taxonomy.** Every change produces a new taxonomy version. Historical feedback retains its original taxonomy version annotation, and dashboards allow users to view data under any taxonomy version. This is critical for trend analysis — you need to know whether a spike in "Payment Issues" is real growth or an artifact of a taxonomy restructure.

---

### Stage 5: Aggregation & Insight Generation

Raw extractions are useful for individual ticket triage, but the real value of a VoC system comes from aggregation — understanding themes at scale.

#### 5.1 Theme Volume & Impact Scoring

For each taxonomy node, compute:

**Volume Metrics:**
- `absolute_count`: Total feedback units in the period.
- `relative_share`: Percentage of all feedback assigned to this theme.
- `unique_users`: Distinct users mentioning this theme (to avoid one loud user skewing numbers).
- `channel_distribution`: Breakdown by source channel (is this theme concentrated in support tickets, or spread across all channels?).

**Sentiment Metrics:**
- `mean_polarity`: Average sentiment polarity for units in this theme.
- `polarity_distribution`: Histogram of polarity scores (a bimodal distribution — some people love it, some hate it — is very different from a unimodal negative distribution).
- `dominant_emotion`: Most common emotional tag within this theme.
- `nps_correlation`: If NPS data is available, the correlation between this theme's presence and the user's NPS score.

**Impact Score:** A composite metric that combines volume, sentiment severity, user segment importance, and trend direction into a single priority score. The formula is configurable per organization, but a reasonable default is:

```
impact_score = (
    w1 * normalized_volume +
    w2 * abs(mean_polarity) * (1 if mean_polarity < 0 else 0.5) +
    w3 * segment_weight +
    w4 * trend_acceleration
)
```

Where `segment_weight` upweights feedback from high-value segments (enterprise customers, high-LTV users) and `trend_acceleration` captures whether this theme is growing faster than baseline.

#### 5.2 Trend & Anomaly Detection

**Time Series Construction:** For each taxonomy node, construct a time series of daily/weekly feedback volume and mean sentiment. Apply Seasonal-Trend decomposition using LOESS (STL) or a similar method to separate the trend, seasonal, and residual components.

**Anomaly Detection Algorithm:**

1. Compute the expected value for the current period based on the trend + seasonal components.
2. Calculate the residual (actual - expected).
3. If the residual exceeds 2.5 standard deviations from the historical residual distribution, flag as an anomaly.
4. For flagged anomalies, run an LLM agent over the recent feedback units in that theme to generate a natural-language explanation: *"The spike in 'Payment Processing Failure' appears to be driven by a Stripe API outage reported by 47 users in the last 24 hours, primarily affecting credit card transactions on the web checkout flow."*

**Emerging Topic Detection:** Beyond anomalies in existing topics, detect when a *new cluster* of feedback is forming that doesn't match any existing taxonomy node. This is done by monitoring the `is_new_topic` rate — if > 15% of recent feedback units are unmatched, run an ad-hoc clustering pass (same as taxonomy evolution Step 2) to surface the emerging topic.

#### 5.3 Executive Summary Generation

**Algorithm:** An LLM agent receives the top-K themes by impact score, their volume/sentiment metrics, notable anomalies, and emerging themes. It generates a structured executive summary.

Prompt: *"You are the Voice of Customer analyst for [Company]. Based on this week's data, write a concise executive brief covering: (1) the top 3 themes by impact score with one-sentence summaries, (2) any significant trend changes or anomalies, (3) emerging themes that warrant attention, and (4) one recommended action. Write for a VP of Product audience — be specific and data-driven."*

The output is a structured document with sections, embedded metrics, and links to drill-down dashboards. Crucially, every claim in the summary includes a citation to the underlying theme data and sample verbatims.

---

### Stage 6: Serving & Feedback Loop

#### 6.1 API & Dashboard Layer

The system exposes a REST/GraphQL API for downstream consumers:

- `GET /themes` — List all taxonomy nodes with volume/sentiment metrics for a given time range.
- `GET /themes/{id}/verbatims` — Retrieve the actual feedback units tagged with a theme, with pagination and filtering by segment, channel, sentiment.
- `GET /themes/{id}/trend` — Time series data for a theme.
- `GET /anomalies` — Current anomalies with explanations.
- `GET /summary` — Latest executive summary.
- `POST /feedback/{id}/reclassify` — Human override to re-tag a feedback unit (feeds back into the learning loop).

The dashboard provides visual exploration: a treemap of themes by volume (sized by count, colored by sentiment), time series charts, and a verbatim browser with sentiment highlights.

#### 6.2 Human-in-the-Loop Review Queue

Not all extractions are high-confidence. The review queue surfaces items that need human judgment:

- **Low-confidence theme assignments** (confidence < 0.7).
- **New theme candidates** awaiting taxonomy placement.
- **Grounding failures** (evidence linker flagged ungrounded claims).
- **Sarcasm-flagged units** (sarcasm detection is imperfect; humans verify).
- **Ambiguous feedback units** where the unitization agent wasn't sure how to split.

**Algorithm for Review Prioritization:** Items are prioritized by `expected_information_gain` — how much would resolving this item improve the system's overall accuracy? New theme candidates with high volume potential are prioritized over isolated low-confidence classifications. A simple proxy: `priority = uncertainty * volume_of_similar_items`.

Each human review decision is logged as a labeled example. Over time, this builds a gold-standard dataset for evaluation and prompt refinement.

#### 6.3 Continuous Learning Loop

The system improves itself over three feedback mechanisms:

**Prompt Refinement:** Weekly, run the extraction agents over the gold-standard dataset (built from human reviews). Compute accuracy metrics (F1 for themes, MAE for sentiment, precision/recall for intent). If performance degrades, analyze the failure modes and update the agent prompts with additional examples or refined instructions targeting the specific failure patterns.

**Embedding Model Tuning:** If the organization accumulates enough labeled data (5,000+ human-reviewed theme assignments), fine-tune the sentence-transformer model used for clustering and taxonomy matching on this domain-specific data. This improves clustering quality significantly for specialized vocabularies (e.g., fintech vs. healthcare).

**Taxonomy Feedback Loop:** When product teams fix an issue and the corresponding theme's volume drops, automatically update the theme's status and surface this as a "resolved theme" in dashboards. Conversely, when a new feature launches, watch for new feedback clusters related to it and proactively create taxonomy nodes.

---

## 4. Data Flow Summary for a Single Feedback Item

To make the full pipeline concrete, here is the end-to-end journey of a single customer review:

**Input:** *"Honestly, the app redesign looks amazing, but I've had the checkout crash on me three times this week. Also, when I contacted support, they took 4 days to get back to me which is ridiculous. Please add Apple Pay — I shouldn't have to type my card number in 2025."*

**Stage 1 (Ingestion):** Source adapter creates a CFO with `source_channel = "app_store_review"`, `star_rating = 2`, language detected as English, PII check passes (no PII present).

**Stage 2 (Segmentation):** The Unitization Agent splits this into 4 feedback units: (1) "the app redesign looks amazing" → praise about UI design, (2) "checkout crash on me three times this week" → bug report about checkout, (3) "support took 4 days to get back to me which is ridiculous" → complaint about support response time, (4) "Please add Apple Pay — I shouldn't have to type my card number in 2025" → feature request for Apple Pay.

**Stage 3 (Extraction):** Each unit is processed in parallel by three agents.

For Unit 2 ("checkout crash"): Sentiment Agent returns `polarity = -0.8, intensity = strong, emotion = [frustrated: 0.9]`. Theme Agent returns `label = "Checkout App Crashes", taxonomy_node_id = <existing node>`. Intent Agent returns `intent_type = bug_report, urgency = high`.

For Unit 4 ("Add Apple Pay"): Sentiment Agent returns `polarity = -0.4, intensity = moderate, emotion = [frustrated: 0.6]`. Topic Agent returns `label = "Apple Pay Support", is_new_topic = true`. Intent Agent returns `intent_type = feature_request, specific_request = "Add Apple Pay as a payment method", competitor_mention = null`.

**Stage 4 (Taxonomy):** Unit 2 matches an existing node. Unit 4's new theme candidate joins a growing cluster of Apple Pay requests — if the cluster hits threshold, a new taxonomy node is created under "Payment Methods."

**Stage 5 (Aggregation):** These units contribute to the aggregate metrics for their respective themes. If checkout crashes are spiking, the anomaly detector fires.

**Stage 6 (Serving):** The dashboard shows "Checkout App Crashes" trending up with high urgency. The executive summary highlights it. The PM drills down to see verbatims and files a bug ticket.

---

## 5. Key Engineering Considerations

### Latency vs. Throughput

The system operates in two modes. **Real-time mode** processes individual feedback units as they arrive (target: < 5 seconds per unit) for use cases like support ticket tagging and alert triggering. **Batch mode** processes large volumes (10k–100k units) on a schedule for trend analysis and taxonomy evolution. In batch mode, parallelize LLM calls aggressively — each feedback unit's three extraction agents are independent and can run concurrently.

### Cost Optimization

LLM calls are the primary cost driver. Strategies to manage cost without sacrificing quality include using a smaller, cheaper model (e.g., Claude Haiku) for straightforward tasks like language detection and deduplication, while reserving the more capable model (e.g., Claude Sonnet) for theme extraction and taxonomy reasoning. Additionally, implementing aggressive caching helps — if two feedback units are near-duplicates, reuse the extraction results from the first and skip the LLM calls for the second.

### Evaluation Framework

Establish a rigorous evaluation framework from day one. Maintain a gold-standard dataset of 500+ human-labeled feedback units covering all channels, themes, and sentiment levels. Define metrics for each agent: theme extraction should target F1 > 0.85, sentiment polarity should target MAE < 0.15, and intent classification should target accuracy > 0.90. Run evals on every prompt change and track performance over time.

### Multi-Tenant Considerations

If building this as a SaaS VoC product, each customer gets their own taxonomy (a fintech company's themes are completely different from a gaming company's). The extraction agents' prompts should be parameterized with the tenant's taxonomy and product context. Consider using tenant-specific few-shot examples to improve accuracy for each customer's domain.

---

## 6. Technology Stack Recommendations

| Component | Recommended Technology | Rationale |
|---|---|---|
| LLM (Extraction Agents) | Claude Sonnet for extraction, Claude Haiku for preprocessing | Best cost/quality tradeoff for structured extraction tasks |
| Embeddings | Voyage AI or Cohere Embed v3 | High-quality sentence embeddings for clustering |
| Vector Store | pgvector (small scale) or Pinecone (large scale) | For deduplication and taxonomy matching |
| Orchestration | Temporal or Prefect | For managing the multi-stage pipeline with retries and parallelism |
| Data Store | PostgreSQL + TimescaleDB | Relational data with time-series support for trend analysis |
| Dashboard | Metabase, Superset, or custom React app | For visualization and exploration |
| Queue | Redis Streams or Kafka | For real-time feedback ingestion |

---

## 7. Failure Modes & Mitigations

**Theme Drift:** Over time, the same theme label starts covering increasingly different sub-topics, making it meaninglessly broad. Mitigation: the drift detection algorithm in Stage 4.3 catches this by monitoring embedding divergence.

**Taxonomy Explosion:** Without governance, the taxonomy grows to hundreds of nodes that overwhelm users. Mitigation: enforce a maximum node count per level, require minimum volume thresholds for new nodes, and run periodic taxonomy consolidation reviews.

**Sentiment Calibration Drift:** The LLM's sentiment scores shift subtly across model versions or prompt changes, making historical comparisons invalid. Mitigation: always run the calibration dataset after any change and apply a normalization function to map raw scores to the calibrated scale.

**Echo Chamber Effect:** If the system only surfaces high-volume themes, it systematically ignores important but rare feedback (e.g., security vulnerabilities, accessibility issues). Mitigation: the Impact Score formula includes a `segment_weight` term that can upweight critical segments, and the anomaly detector catches sudden spikes regardless of baseline volume.

**Adversarial / Spam Feedback:** Competitors or bad actors may flood feedback channels with fake reviews. Mitigation: the deduplication layer catches bulk duplicates, and an optional spam-classification agent can flag suspicious patterns (identical phrasing from different accounts, sudden volume spikes from new accounts).

---

*This document is a living reference intended to evolve as the system is implemented and refined. Each stage should be built incrementally, starting with Stages 1–3 for core extraction, then adding the Taxonomy Engine and Aggregation layers as data accumulates.*