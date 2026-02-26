# VoC UI — User Experience Design

## Design Philosophy

The UI is a **read-and-act layer** on top of the pipeline. Every view traces back to source verbatims (the "grounded outputs" principle from the system design). Users should never see a number they can't click through to the underlying feedback.

Three user modes underpin every interaction:

| Mode | Intent | Primary Entry Point |
|---|---|---|
| **Monitor** | Catch emerging issues, track health | Dashboard |
| **Investigate** | Understand a specific account or topic | Accounts · Taxonomy |
| **Explore** | Discover patterns across the corpus | Feedback Explorer |

---

## Information Architecture

```
VoC App
├── Dashboard (Home)
├── Accounts
│   ├── Account List
│   └── Account Detail
│       ├── Topic Timeline
│       ├── Feedback Units
│       └── Conversation History
├── Taxonomy
│   ├── Topic Tree
│   └── Topic Detail
├── Feedback Explorer
├── Starred
└── Settings
    ├── Taxonomy Management
    └── Alert Rules
```

---

## Global Chrome

Every page shares a persistent shell:

```
┌─────────────────────────────────────────────────────────────────┐
│  [≡] VoC          🔍 Search feedback, topics, accounts…   [🔔] [?] │
│──────────────────────────────────────────────────────────────────│
│  Nav:  Dashboard · Accounts · Taxonomy · Explorer · ★ Starred   │
└─────────────────────────────────────────────────────────────────┘
```

- **Global search** — full-text across verbatims, topic names, and account names. Results grouped by type (Topics / Accounts / Feedback Units).
- **Notification bell** — fires when an alert rule triggers (e.g. a topic spikes >2× its 7-day average, or net sentiment for an account drops sharply).
- **Date range picker** — sticky across all views; defaults to the last 30 days.

---

## 1. Dashboard

The home screen answers: *"What's happening right now, and has anything changed?"*

### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Period: [Last 30 days ▾]                           [Export CSV]    │
├────────────┬────────────┬────────────┬────────────────────────────-─┤
│ 🗂 Topics  │ 😊 Sentiment│ 🏢 Accounts│  ⚡ Signals                  │
│   847      │  +0.12 net │   214 active│  3 new · 1 spike · 0 drops  │
└────────────┴────────────┴────────────┴──────────────────────────────┘

  Top Topics by Type ──────────────────────────── [All types ▾]
  ┌─────────────────────────────────────────────────────────────┐
  │  FEATURE REQUEST              BUG REPORT                    │
  │  ① Report Export      ↑ 34%  ① Login Failures      ↑ 12%  │
  │  ② Dashboard Perf     → 0%   ② CSV Import Errors   ↓  8%  │
  │  ③ Mobile Offline     ↑ 21%  ③ Notification Delay  → 0%   │
  │  ④ Bulk Edit          ↓  6%  ④ Webhook Timeouts    ↑  5%  │
  │  ⑤ SSO Integration    ↑ 18%  ⑤ Sort Order Bug      ↓ 14%  │
  │                                                             │
  │  PRAISE                       CHURN SIGNAL                  │
  │  ① Onboarding Flow    ↑  9%  ① Support Response   ↑ 41%  │
  │  ② API Documentation  → 0%   ② Pricing Concerns    ↑ 17%  │
  │  ③ Search Speed       ↑  4%  ③ Missing Feature X   ↓  3%  │
  └─────────────────────────────────────────────────────────────┘

  Topic Trend (volume over time)
  ┌─────────────────────────────────────────────────────────────┐
  │  [sparkline chart: stacked by type, week-over-week]         │
  └─────────────────────────────────────────────────────────────┘

  ⚡ Signals — Items requiring attention
  ┌─────────────────────────────────────────────────────────────┐
  │  🔴 "Login Failures" up 2.4× this week (41 accounts)  [→]  │
  │  🟡 "Pricing Concerns" new cluster forming (12 accounts)[→]  │
  │  🟢 "Onboarding Flow" sentiment improved significantly  [→]  │
  └─────────────────────────────────────────────────────────────┘
```

### Interactions

- **Topic card click** → navigates to Topic Detail in Taxonomy view.
- **Trend arrow** → opens inline sparkline for that topic (volume + sentiment over 12 weeks).
- **Type filter** (All types ▾) → shows only the selected intent type (Bug Report, Feature Request, Praise, Churn Signal, Question).
- **Signal row click** → navigates to Feedback Explorer pre-filtered to that topic + date range.
- **Export CSV** → downloads the visible summary table.

### Design Rationale

Intent type as the primary grouping (not just volume) matches how teams actually act on feedback — bugs go to engineering, feature requests go to PM, churn signals go to CS. Trend arrows and the Signals panel surface change, not just absolute volume, so recurring high-volume topics don't crowd out fast-moving emergent ones.

---

## 2. Accounts

### 2a. Account List

Answers: *"Which accounts should I pay attention to today?"*

```
┌──────────────────────────────────────────────────────────────────────┐
│  Search accounts…                [Segment ▾] [Sentiment ▾] [Sort ▾] │
├───────────────────────────┬───────┬────────────┬────────────┬────────┤
│ Account                   │ Units │ Sentiment  │ Top Topic  │ Last   │
├───────────────────────────┼───────┼────────────┼────────────┼────────┤
│ Acme Corp          [STAR] │   87  │ ████░ -0.3 │ Report Export│ 2h  │
│ Globex Industries  [STAR] │   34  │ ██░░░ -0.7 │ Login Fail │ 4h   │
│ Initech LLC               │   21  │ ████░ +0.4 │ API Docs   │ 1d   │
│ Umbrella Co               │   15  │ ██░░░ -0.8 │ Pricing    │ 3d   │
│ …                         │       │            │            │       │
└───────────────────────────┴───────┴────────────┴────────────┴────────┘
```

- **Columns:** Account name · Feedback units (in period) · Net sentiment bar · Top topic · Time since last feedback.
- **Sort options:** Most units · Worst sentiment · Most recent · Alphabetical.
- **Segment filter:** (if account metadata available) plan tier, industry, region.
- **Star** → pins account to Starred for quick access.
- **Row click** → Account Detail.

### 2b. Account Detail

Answers: *"What is this account telling us, and how has it changed over time?"*

```
┌─────────────────────────────────────────────────────────────────────┐
│  ← Accounts    Acme Corp                            [★ Star] [Share]│
│  87 feedback units · Net sentiment: -0.3 · Period: Last 30 days ▾   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  SUMMARY (AI-generated)                                              │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Acme's feedback this period centers on Report Export (38%)   │   │
│  │ and Login Failures (22%). Sentiment has declined since the   │   │
│  │ Jan 14 deploy. Three users mention considering alternatives. │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Topic Breakdown          Sentiment Over Time                        │
│  ┌─────────────────┐      ┌──────────────────────────────────┐       │
│  │ Report Export 38%│      │ [sparkline, last 12 weeks]       │       │
│  │ Login Failures 22%│     └──────────────────────────────────┘       │
│  │ Dashboard Perf 18%│                                                │
│  │ Other        22% │                                                 │
│  └─────────────────┘                                                 │
│                                                                      │
│  Feedback Units                          [Filter: type · sentiment]  │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ ● "The report export hangs on files over 10k rows…"          │   │
│  │   Topic: Report Export · Bug Report · 😠 -0.8 · Jan 22 [★]  │   │
│  │                                                              │   │
│  │ ● "Login is broken after the SSO update, 4 of our users…"   │   │
│  │   Topic: Login Failures · Bug Report · 😠 -0.9 · Jan 19 [★] │   │
│  │                                                              │   │
│  │ ● "Love the new search, much faster than before."            │   │
│  │   Topic: Search Speed · Praise · 😊 +0.8 · Jan 15 [★]       │   │
│  │                                                              │   │
│  │ [Load more…]                                                 │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Conversation History                                                │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ Jan 18  Support ticket #4421 — "SSO Login Issue"    [→ Link] │   │
│  │ Jan 12  NPS response: 4/10 — "Too slow for our volume"       │   │
│  │ Dec 31  Support ticket #4208 — "CSV import failure"          │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### Interactions

- **AI Summary** — generated on page load from this account's feedback units in the selected period. Not cached — always reflects the current filter.
- **Topic slice click** → scrolls Feedback Units list to units for that topic.
- **[★] on each unit** → stars the unit; appears in Starred view.
- **Conversation History row** → external link to the source system (support ticket, survey, etc.) using `source_url` from the CFO.
- **Share** → copies a shareable deep-link to this account + period combination.

---

## 3. Taxonomy

The taxonomy is the living topic tree maintained by the pipeline. This view is for PM / CS leads who want to understand and curate the topic space.

### 3a. Topic Tree

```
┌────────────────────────────────────────────────────────────────────┐
│  Taxonomy                  [Search topics…]   [+ Add topic]  [⚙]  │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ▼ Performance                          312 units · ↑ 18%          │
│      ▶ Report Export                    143 units · ↑ 34%          │
│      ▶ Dashboard Loading                 89 units · →  0%          │
│      ▶ Search Speed                      80 units · ↑  4%          │
│                                                                     │
│  ▼ Authentication                       201 units · ↑ 12%          │
│      ▶ Login Failures                    95 units · ↑ 12%          │
│      ▶ SSO Integration                   67 units · ↑ 18%          │
│      ▶ Session Timeouts                  39 units · →  0%          │
│                                                                     │
│  ▼ Data Management                      178 units · ↓  6%          │
│      ▶ CSV Import Errors                 98 units · ↓  8%          │
│      ▶ Bulk Edit                         80 units · ↓  6%          │
│                                                                     │
│  ▶ Unclassified                          24 units · [Review ↗]     │
└────────────────────────────────────────────────────────────────────┘
```

- **Unclassified row** — surfaces units where the pipeline's confidence fell below `NEW_TOPIC_CONF_FLOOR (0.70)`. These are the human-in-the-loop review queue.
- **Trend indicator** — percentage change vs the previous period.
- **[+ Add topic]** — manually create a topic node; the pipeline will match future units against it using `TOPIC_MATCH_THRESHOLD (0.82)`.
- **[⚙] Taxonomy Settings** — merge topics, rename, adjust thresholds (admin only).

### 3b. Topic Detail

```
┌────────────────────────────────────────────────────────────────────┐
│  ← Taxonomy    Report Export                         [★ Track] [⚙]│
│  143 units · ↑ 34% vs last period · Confidence avg: 0.91          │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  SUMMARY                                                           │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ "Report Export" has surged this period, driven primarily    │  │
│  │ by enterprise accounts. 78% of mentions are bug reports     │  │
│  │ (file size limits, timeout errors). 12% are feature         │  │
│  │ requests for PDF/Excel format support.                      │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Sentiment Distribution          Intent Breakdown                  │
│  [bar chart: -1 to +1]           [pie: Bug 78% · FR 12% · Q 10%]  │
│                                                                     │
│  Accounts mentioning this topic          [Sort: most units ▾]      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Acme Corp        34 units  😠 -0.7   [→ Account Detail]     │  │
│  │ Globex           18 units  😐 -0.3   [→ Account Detail]     │  │
│  │ Initech           9 units  😠 -0.8   [→ Account Detail]     │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Verbatims (sample)                [Show all 143 →]                │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ "The report export hangs on files over 10k rows…"   [★] [→] │  │
│  │ "We need Excel export, PDF doesn't work for our workflow…"  │  │
│  │ "Export finally worked after the workaround — thanks!"      │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Trend (weekly volume + sentiment)                                  │
│  [dual-axis chart: bars = volume, line = net sentiment]             │
└────────────────────────────────────────────────────────────────────┘
```

- **[★ Track]** → pins this topic to the Dashboard Signals panel and enables alert rules for it.
- **"Show all 143 →"** → opens Feedback Explorer pre-filtered to this topic.
- **Account row click** → Account Detail scoped to this topic.

---

## 4. Feedback Explorer

Answers: *"Give me every piece of feedback that matches these criteria."*

This is the power-user view — a filterable, sortable, exportable table of all feedback units.

### Layout

```
┌────────────────────────────────────────────────────────────────────────┐
│  Feedback Explorer                                      [Export CSV]   │
├──────────────────────────────────────────────────────────────────────── │
│                                                                         │
│  FILTERS                                                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Date range:  [Feb 1 — Feb 25, 2026 ▾]                           │   │
│  │ Type:        [All ▾]  Bug · Feature Request · Praise · Churn    │   │
│  │ Sentiment:   [All ▾]  😠 Negative · 😐 Neutral · 😊 Positive    │   │
│  │ Topic:       [All topics ▾]                                      │   │
│  │ Account:     [All accounts ▾]                                    │   │
│  │ Min accounts: [───○───────]  1+  (slider)                        │   │
│  │ Starred only: [ ]                                                │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  847 units  [Sort: Most recent ▾]                                       │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ ★  "The report export hangs on files over 10k rows and times…"   │  │
│  │    Topic: Report Export · Bug Report · 😠 -0.8 · Acme Corp      │  │
│  │    Jan 22, 2026  [→ Account]  [→ Topic]  [★ Star]                │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │    "SSO login is broken after the Jan 14 deploy. 4 of our…"      │  │
│  │    Topic: Login Failures · Bug Report · 😠 -0.9 · Globex        │  │
│  │    Jan 19, 2026  [→ Account]  [→ Topic]  [★ Star]                │  │
│  ├──────────────────────────────────────────────────────────────────┤  │
│  │    "Love the new search speed — much faster than before."        │  │
│  │    Topic: Search Speed · Praise · 😊 +0.8 · Initech             │  │
│  │    Jan 15, 2026  [→ Account]  [→ Topic]  [★ Star]                │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│  [Load more…]                                                           │
│                                                                         │
│  SUMMARY BAR (live, updates with filters)                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  847 units · 214 accounts · Net sentiment: -0.14                │   │
│  │  Top type: Bug Report (52%) · Top topic: Report Export (17%)    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### Filter Interactions

- **Date range** — calendar picker; presets: Today, 7d, 30d, 90d, Custom.
- **Type** — multi-select chips (mirrors intent classification output).
- **Sentiment** — radio (All / Negative / Neutral / Positive) or threshold slider (-1 to +1).
- **Min accounts** — slider to find topics mentioned by many accounts (breadth signal vs. one-off noise).
- **Starred only** — toggle to review your saved items.
- **Filters are URL-encoded** — sharing the URL recreates the exact view.

### Sort Options

Most recent · Oldest · Worst sentiment · Best sentiment · Most accounts · Most duplicate matches (find the single unit that best represents a cluster of near-duplicates).

### Feedback Unit Expansion

Clicking a unit expands it inline:

```
  ▼  "The report export hangs on files over 10k rows and times out after 30s.
      We've tried 3 times. This is blocking our end-of-month process."

     Source: Support ticket #4421 · Acme Corp · Jan 22, 2026
     Original (pre-PII): [Show ▾]
     Duplicate cluster: 12 near-identical units (0.96 similarity) [View all]

     Topic:       Report Export (conf: 0.94)
     Intent:      Bug Report (conf: 0.97)
     Sentiment:   -0.8 · Intense frustration · Urgency signal
     Emotions:    Frustrated, Anxious

     [→ Account Detail]  [→ Topic Detail]  [★ Star]  [Flag for review]
```

- **Duplicate cluster** → opens Feedback Explorer filtered to that cluster's canonical unit ID.
- **Flag for review** → sends this unit to the Taxonomy Unclassified queue with a note.

---

## 5. Starred

A personal curation space for units and accounts worth tracking.

```
┌────────────────────────────────────────────────────────────────────┐
│  Starred                         [+ New collection]  [Export]      │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Collections                                                        │
│  [All ▾]  · Q1 Review (12)  · Churn Risk (8)  · Share with PM (5) │
│                                                                     │
│  Starred Feedback Units (34)                                        │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ ★  "Report export hangs on files over 10k rows…"            │  │
│  │    Acme Corp · Jan 22  [+ Collection ▾]  [✕ Unstar]         │  │
│  │                                                             │  │
│  │ ★  "SSO login broken after Jan 14 deploy…"                  │  │
│  │    Globex · Jan 19  [+ Collection ▾]  [✕ Unstar]            │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Starred Accounts (6)                                               │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ ★  Acme Corp     87 units  😠 -0.3  [→]                     │  │
│  │ ★  Globex        34 units  😠 -0.7  [→]                     │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Tracked Topics (3)                                                 │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ ★  Report Export    143 units  ↑ 34%  [→]                   │  │
│  │ ★  Login Failures    95 units  ↑ 12%  [→]                   │  │
│  │ ★  Pricing Concerns  28 units  ↑ 17%  [→]                   │  │
│  └─────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

- **Collections** — lightweight folders (local to user, not shared unless exported).
- **[+ Collection ▾]** — assign a starred item to one or more collections.
- **Export** — exports all starred items + collections as a structured report (markdown or CSV).

---

## 6. Settings — Taxonomy Management

Accessible to admins. Supports the human-in-the-loop review queue that the pipeline design calls for.

```
┌────────────────────────────────────────────────────────────────────┐
│  Settings / Taxonomy                                                │
├────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Review Queue (24 units pending)                                    │
│  These units scored below the confidence floor (0.70).             │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ "Our compliance team needs field-level audit logs…"          │  │
│  │ Suggested: Audit Logging (conf 0.61)  [Accept] [Reassign ▾] │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Topic Management                                                   │
│  [Search topics…]                                                   │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Report Export  [Rename] [Merge into ▾] [Move under ▾]       │  │
│  │ Login Failures [Rename] [Merge into ▾] [Move under ▾]       │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  Thresholds (advanced)                                              │
│  Duplicate threshold:       [0.95 ────○──────────] (0.80–1.00)     │
│  Topic match threshold:     [0.82 ──────○────────] (0.70–1.00)     │
│  New topic confidence floor:[0.70 ───○──────────] (0.50–0.90)      │
│                                                                     │
│  Alert Rules                                                        │
│  [+ Add rule]                                                       │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ "Login Failures" volume > 2× 7-day avg  → Notify [slack #voc]│ │
│  │ Any account net sentiment < -0.8         → Notify [email]    │  │
│  └─────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

---

## User Flow Summary

### Flow 1: Morning review

1. **Dashboard** — scan Signals panel for overnight spikes. Note "Login Failures" is up 2.4×.
2. Click Signal → **Feedback Explorer** pre-filtered to Login Failures, last 7 days.
3. Expand a unit → confirm it's a real regression pattern, not noise.
4. **[★ Star]** three representative verbatims → assign to "Share with Eng" collection.
5. Export collection as markdown → paste into Slack.

### Flow 2: Account check-in (CS team)

1. **Accounts** → sort by worst sentiment → open Globex Industries.
2. Review AI Summary → confirm churn signal is new vs. ongoing.
3. Scroll Feedback Units → star the most articulate verbatims.
4. Review Conversation History → see when the last support ticket was.
5. Share Account Detail link with the account owner.

### Flow 3: Taxonomy curation (PM, weekly)

1. **Taxonomy** → open Unclassified queue (24 pending).
2. For each unclassified unit, accept the suggestion or reassign to an existing topic.
3. Scan the Topic Tree for topics with high volume and low confidence avg → investigate.
4. Merge two topics that have drifted together ("Slow Reports" + "Report Export").
5. Track two fast-rising topics by starring them; alert rule fires if either doubles.

### Flow 4: Deep exploration

1. **Feedback Explorer** → set Date: last 90 days · Type: Churn Signal · Min accounts: 5.
2. Sort by Worst sentiment → identify the 3 issues that are widespread and deeply negative.
3. Click "→ Topic" on each → Topic Detail shows breadth (accounts) + trend.
4. Export filtered results to CSV for stakeholder presentation.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Intent type as primary grouping on Dashboard | Matches how teams act: bugs → eng, FRs → PM, churn → CS. Volume-only grouping buries actionable signals. |
| AI Summary is per-page, not global | Summaries scoped to the visible filter state are more useful than static blurbs. Generated on load; not pre-cached. |
| "Min accounts" slider in Explorer | Distinguishes signal from noise. A single-account complaint about a niche workflow is different from 40 accounts hitting the same wall. |
| Duplicate cluster surfaced inline | The pipeline deduplicates to a canonical unit, but users need to see that 12 accounts hit the same issue — not just 1. |
| Stars are personal, collections are shareable via export | Avoids permissions complexity while still enabling async handoffs (PM → Eng, CS → PM). |
| Taxonomy thresholds exposed in Settings | The pipeline's `DUPLICATE_THRESHOLD`, `TOPIC_MATCH_THRESHOLD`, and `NEW_TOPIC_CONF_FLOOR` directly affect taxonomy quality. Admins need visibility and control without editing code. |
| Review Queue = human-in-the-loop surface | Low-confidence units (below 0.70) aren't silently dropped — they surface here for expert judgment, closing the feedback loop. |
