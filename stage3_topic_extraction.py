"""
Stage 3.2 (Part 1): Topic Extraction
=====================================
Extracts abstract, product-line-agnostic topics from FeedbackUnit objects.

Topic ≠ Taxonomy
-----------------
These are two distinct, deliberately separated concepts in this system:

  Topic     The abstract concept being discussed — the TYPE of issue or problem,
            stripped of all product-line, team, and region specifics.
            e.g. "Duplicate Charge", "App Crash During Checkout"

            Multiple feedback units can and SHOULD share the same topic even
            when they come from different product lines, org units, or regions.
            Topic is a shared cross-product vocabulary.

  Taxonomy  The org-specific hierarchical placement of that feedback.
            e.g. "Product A › Billing › Double Charge"
                 "Product B › Billing › Invoice Error"

            Taxonomy mapping is a separate concern, handled by the Taxonomy
            Engine in Stage 4.  It is NOT performed here.

Example illustrating the separation:
  Unit A: "Product A charged me twice this billing cycle"
  Unit B: "I was double-billed on my Product B plan last month"

  Both units → Topic: "Duplicate Charge"    (same abstract issue)
  Unit A     → Taxonomy: Product A › Billing › Double Charge
  Unit B     → Taxonomy: Product B › Billing › Double Charge
  Same topic, different taxonomy paths — resolved downstream.

Two-step extraction algorithm (mirrors the design doc §3.2):
  Step 1 — Open extraction: the LLM identifies the abstract topic WITHOUT
            seeing the topic store.  This prevents anchoring bias toward
            existing labels and allows genuinely new topics to surface.
  Step 2 — Topic matching: the extracted label is compared against known
            topics via semantic similarity (TopicStore).
            similarity ≥ threshold → matched to existing topic.
            similarity <  threshold → flagged as a new topic candidate.

Dependencies:
    pip install anthropic sentence-transformers numpy
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import anthropic
import numpy as np
from sentence_transformers import SentenceTransformer

from stage2_unitization import FeedbackUnit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOPIC_MATCH_THRESHOLD = 0.82   # Cosine similarity required to match an existing topic.
                                # Lower than the dedup threshold — topics allow more
                                # semantic variance than near-duplicate text.

NEW_TOPIC_CONF_FLOOR  = 0.70   # Extraction confidence below this routes to human review
                                # rather than auto-labelling as a new topic candidate.

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class Topic:
    """
    An abstract, org-agnostic concept extracted from customer feedback.

    A Topic captures the TYPE of issue or problem, deliberately stripped of
    product-line, region, or team specifics.  It is the shared vocabulary
    across organisational boundaries — the same Topic can be referenced by
    feedback units from Product A, Product B, or any future product line.

    Attributes:
        topic_id:       Stable identifier for this topic.
        label:          Short canonical label (3–8 words), e.g. "Billing Error".
        description:    One-sentence definition used for disambiguation and
                        semantic matching.
        aliases:        Surface-form labels that have been matched to this topic
                        (e.g. "double charge", "charged twice").  Used for
                        reporting and taxonomy seeding.
        feedback_count: Running count of FeedbackUnits mapped to this topic
                        (canonical units only; duplicates are not counted here).
        intent_type:    Cached intent classification for this topic.  Set on the
                        first unit processed and reused for all subsequent units —
                        intent is stable per topic (a billing complaint is always
                        a complaint).  None until the first unit is processed.
        intent_urgency: Cached urgency level paired with intent_type.
    """

    topic_id:       str            = field(default_factory=lambda: str(uuid.uuid4()))
    label:          str            = ""
    description:    str            = ""
    aliases:        list[str]      = field(default_factory=list)
    feedback_count: int            = 0
    intent_type:    Optional[str]  = None
    intent_urgency: Optional[str]  = None


@dataclass
class TopicExtractionResult:
    """
    Output of the TopicExtractor for a single FeedbackUnit.

    Attributes:
        unit_id:         ID of the source FeedbackUnit.
        topic_id:        ID of the matched or newly created Topic.  Always set —
                         new topics are assigned a UUID and added to the TopicStore
                         immediately so subsequent similar units can match them.
        topic_label:     The canonical topic label (matched or suggested).
        confidence:      Match confidence (cosine similarity for known topics;
                         LLM-reported confidence for new candidates).
        evidence_spans:  Exact phrases copied from the unit text that ground
                         the topic assignment.
        is_new_topic:    True when no existing topic matched above threshold.
        suggested_label: Candidate label for human/taxonomy review.  Set when
                         is_new_topic=True and confidence ≥ NEW_TOPIC_CONF_FLOOR.
                         None when confidence is too low (routes to review queue).
        raw_extracted:   The raw label returned by the open extraction step,
                         before matching.  Useful for alias accumulation and
                         taxonomy seeding in Stage 4.
    """

    unit_id:         str
    topic_id:        str
    topic_label:     str
    confidence:      float
    evidence_spans:  list[str]      = field(default_factory=list)
    is_new_topic:    bool           = False
    suggested_label: Optional[str] = None
    raw_extracted:   str           = ""


# ---------------------------------------------------------------------------
# Topic Store
# ---------------------------------------------------------------------------


class TopicStoreInterface(ABC):
    """
    Abstract interface for topic persistence and semantic search.

    The TopicStore is a SEPARATE vector store from the deduplication store.
    It indexes Topic embeddings (label + description), not FeedbackUnit
    embeddings.  The two stores must never share an instance.
    """

    @abstractmethod
    def add(self, topic: Topic) -> None:
        """Persist a new Topic and index its label+description embedding."""

    @abstractmethod
    def find_match(
        self, label: str, description: str = ""
    ) -> tuple[Optional[Topic], float]:
        """
        Return (best_matching_topic, cosine_similarity).
        Returns (None, score) when the best match is below TOPIC_MATCH_THRESHOLD.
        """

    @abstractmethod
    def increment_count(self, topic_id: str) -> None:
        """Increment feedback_count for the given topic."""

    @abstractmethod
    def register_alias(self, topic_id: str, alias: str) -> None:
        """Record a surface-form alias that was matched to an existing topic."""

    @abstractmethod
    def get(self, topic_id: str) -> Optional[Topic]:
        """Return a Topic by ID, or None if not found."""

    @abstractmethod
    def all_topics(self) -> list[Topic]:
        """Return all known topics (for reporting and taxonomy seeding)."""


class InMemoryTopicStore(TopicStoreInterface):
    """
    In-memory topic store backed by a dense NumPy matrix.

    Suitable for development and testing.
    Replace with a pgvector-backed implementation in production.

    Topics are indexed by their 'label + description' embedding so that
    semantically similar labels ("Billing Error", "Incorrect Charge",
    "Wrong Amount Charged") resolve to the same Topic.
    """

    def __init__(self, encoder: SentenceTransformer) -> None:
        self._encoder = encoder
        self._topics: dict[str, Topic]     = {}   # topic_id → Topic
        self._ids:    list[str]            = []   # ordered list of topic_ids
        self._vecs:   list[np.ndarray]     = []   # L2-normalised embeddings

    # ------------------------------------------------------------------
    # TopicStoreInterface implementation
    # ------------------------------------------------------------------

    def add(self, topic: Topic) -> None:
        vec = self._embed(f"{topic.label}. {topic.description}")
        self._topics[topic.topic_id] = topic
        self._ids.append(topic.topic_id)
        self._vecs.append(vec)
        logger.debug("TopicStore: added '%s' (%s)", topic.label, topic.topic_id[:8])

    def find_match(
        self, label: str, description: str = ""
    ) -> tuple[Optional[Topic], float]:
        if not self._ids:
            return None, 0.0

        query_text = f"{label}. {description}".strip(". ")
        query_vec  = self._embed(query_text)
        matrix     = np.stack(self._vecs)           # (N, dim)
        sims       = matrix @ query_vec             # (N,)

        best_idx   = int(np.argmax(sims))
        best_score = float(sims[best_idx])

        if best_score >= TOPIC_MATCH_THRESHOLD:
            return self._topics[self._ids[best_idx]], best_score

        return None, best_score

    def increment_count(self, topic_id: str) -> None:
        if topic_id in self._topics:
            self._topics[topic_id].feedback_count += 1

    def register_alias(self, topic_id: str, alias: str) -> None:
        topic = self._topics.get(topic_id)
        if topic and alias not in topic.aliases and alias != topic.label:
            topic.aliases.append(alias)

    def get(self, topic_id: str) -> Optional[Topic]:
        return self._topics.get(topic_id)

    def all_topics(self) -> list[Topic]:
        return list(self._topics.values())

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> np.ndarray:
        vec  = self._encoder.encode(text, normalize_embeddings=False)
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 0 else vec


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior Voice of Customer analyst. Your task is to extract a precise, \
product-neutral topic label from a customer feedback unit.

The topic must be SPECIFIC about the nature of the issue but NEUTRAL about \
which product, product line, team, or region it occurred in.

WHAT TO STRIP — these are ownership/context details handled by taxonomy downstream:
  - Product and product line names  (e.g. "Product A", "Product B", "Pro Plan")
  - Platform or version identifiers (e.g. "iOS app", "v2", "web")
  - Team or org unit names          (e.g. "billing team", "APAC support")
  - Region or market identifiers    (e.g. "US", "EU", "APAC")

WHAT TO KEEP — these make the topic actionable and distinguish it from similar ones:
  - The specific feature or workflow involved (checkout, CSV export, login, subscription)
  - The exact type of failure (crash, timeout, duplicate charge, no response)
  - Contextual detail that scopes the issue  (after cancellation, during upload, at payment step)

CALIBRATION — each row shows the same feedback at three levels of specificity:

  Feedback: "Product A charged me twice after I cancelled my subscription"
  TOO SPECIFIC  (has product name):  "Product A Post-Cancellation Double Charge"
  TOO GENERIC   (loses the detail):  "Billing Problem"
  CORRECT:                           "Duplicate Charge After Cancellation"

  Feedback: "The app crashes every time I try to export a CSV on Product B"
  TOO SPECIFIC  (has product name):  "Product B CSV Export Crash"
  TOO GENERIC   (loses the detail):  "App Crash"
  CORRECT:                           "Crash During CSV Export"

  Feedback: "APAC support took 6 days to respond to my urgent ticket"
  TOO SPECIFIC  (has region name):   "APAC Support Six Day Response Delay"
  TOO GENERIC   (loses the detail):  "Support Issue"
  CORRECT:                           "Support Response Time Delay"

The label must be 3–8 words. The same label should be assignable to feedback \
from any product line experiencing the same type of issue.

Respond in EXACTLY this format (no markdown, no extra text):
LABEL: <3-8 word product-neutral topic label>
DESCRIPTION: <one sentence describing what this topic covers, without product specifics>
EVIDENCE: <comma-separated exact phrases copied verbatim from the feedback>
CONFIDENCE: <float 0.0–1.0>\
"""

_USER_PROMPT_TEMPLATE = """\
<feedback_metadata>
  source_channel: {source_channel}
  user_segment:   {user_segment}
</feedback_metadata>

<feedback_unit>
{text}
</feedback_unit>

Extract the topic. The label must be specific about the issue but must not \
include product names, product line identifiers, team names, or region names.\
"""


# ---------------------------------------------------------------------------
# Topic Extractor
# ---------------------------------------------------------------------------


class TopicExtractor:
    """
    LLM-powered agent that extracts abstract, product-line-agnostic topics
    from FeedbackUnit objects.

    Design contract:
      - Output is a Topic (the WHAT) — not a taxonomy placement (the WHERE).
      - Multiple feedback units touching different product lines must resolve
        to the same Topic when the underlying issue is the same type of problem.
      - Taxonomy node mapping is a separate concern owned by Stage 4.

    Two-step algorithm:
      Step 1 (Open extraction)  — LLM identifies the topic without seeing the
                                  TopicStore, preventing anchoring bias toward
                                  existing labels.
      Step 2 (Topic matching)   — The extracted label is compared against known
                                  topics via semantic similarity (TopicStore).
                                  similarity ≥ TOPIC_MATCH_THRESHOLD → matched.
                                  similarity <  TOPIC_MATCH_THRESHOLD → new candidate.

    Args:
        topic_store:  A TopicStoreInterface instance (shared across calls).
        client:       An anthropic.Anthropic client (created from env if None).
        model:        Claude model to use.  Sonnet is preferred — the design doc
                      reserves the more capable model for topic extraction and
                      taxonomy reasoning.
        max_tokens:   Maximum tokens for each LLM response.
        temperature:  Sampling temperature (0 = deterministic).
    """

    def __init__(
        self,
        topic_store:  TopicStoreInterface,
        client:       Optional[anthropic.Anthropic] = None,
        model:        str   = "claude-sonnet-4-6",
        max_tokens:   int   = 256,
        temperature:  float = 0.0,
    ) -> None:
        self._store       = topic_store
        self._client      = client or anthropic.Anthropic()
        self._model       = model
        self._max_tokens  = max_tokens
        self._temperature = temperature

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, unit: FeedbackUnit) -> TopicExtractionResult:
        """
        Extract the abstract topic for a single FeedbackUnit.

        Step 1: Open extraction — LLM identifies a free-form label and
                description without seeing the TopicStore.
        Step 2: Match against known topics via semantic similarity.
                Matched   → link to existing Topic, increment its count.
                Unmatched → create a new Topic with a UUID, add it to the
                            TopicStore immediately so the next similar unit
                            can match it rather than spawning another new Topic.
        """
        # Step 1: open extraction — no topic store context provided to LLM
        raw_label, description, evidence_spans, confidence = self._open_extraction(unit)

        # Step 2: match against known topics
        matched_topic, match_score = self._store.find_match(raw_label, description)

        if matched_topic:
            self._store.increment_count(matched_topic.topic_id)
            self._store.register_alias(matched_topic.topic_id, raw_label)
            logger.debug(
                "Unit %s → topic '%s' (sim=%.3f).",
                unit.unit_id[:8], matched_topic.label, match_score,
            )
            return TopicExtractionResult(
                unit_id         = unit.unit_id,
                topic_id        = matched_topic.topic_id,
                topic_label     = matched_topic.label,
                confidence      = match_score,
                evidence_spans  = evidence_spans,
                is_new_topic    = False,
                suggested_label = None,
                raw_extracted   = raw_label,
            )

        # No match — create a new Topic, assign a UUID, and add it to the store
        # immediately.  This means the next unit with a semantically similar label
        # will find a match rather than spawning yet another new Topic entry.
        new_topic = Topic(
            label          = raw_label,
            description    = description,
            feedback_count = 1,         # counts this unit
        )
        self._store.add(new_topic)
        logger.debug(
            "Unit %s → NEW topic '%s' created (id=%s, conf=%.3f).",
            unit.unit_id[:8], raw_label, new_topic.topic_id[:8], confidence,
        )
        # suggested_label drives the Stage 4 human-review queue.
        # Below NEW_TOPIC_CONF_FLOOR the label itself is unreliable, so we
        # surface it for review rather than auto-promoting it.
        suggested = raw_label if confidence >= NEW_TOPIC_CONF_FLOOR else None
        return TopicExtractionResult(
            unit_id         = unit.unit_id,
            topic_id        = new_topic.topic_id,
            topic_label     = new_topic.label,
            confidence      = confidence,
            evidence_spans  = evidence_spans,
            is_new_topic    = True,
            suggested_label = suggested,
            raw_extracted   = raw_label,
        )

    def extract_batch(
        self,
        units:   list[FeedbackUnit],
        *,
        verbose: bool = False,
    ) -> list[TopicExtractionResult]:
        """
        Extract topics for a list of FeedbackUnits.

        LLM calls are independent per unit; for high-throughput production use,
        replace the sequential loop with asyncio / ThreadPoolExecutor.
        """
        results: list[TopicExtractionResult] = []
        for i, unit in enumerate(units):
            result = self.extract(unit)
            results.append(result)
            if verbose:
                tag = "NEW  " if result.is_new_topic else "KNOWN"
                logger.info(
                    "Unit %d/%d [%s]: %s  '%s'  (conf=%.3f)",
                    i + 1, len(units), unit.unit_id[:8],
                    tag, result.topic_label, result.confidence,
                )
        return results

    # ------------------------------------------------------------------
    # Step 1: Open Extraction (LLM)
    # ------------------------------------------------------------------

    def _open_extraction(
        self, unit: FeedbackUnit
    ) -> tuple[str, str, list[str], float]:
        """
        Ask the LLM to identify the abstract topic without seeing the TopicStore.

        Returns (label, description, evidence_spans, confidence).
        The TopicStore is intentionally withheld here — showing it first biases
        the model toward existing categories and suppresses discovery of new ones.
        """
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            source_channel = unit.metadata.get("source_channel", "unknown"),
            user_segment   = unit.metadata.get("user_segment", "unknown"),
            text           = unit.text,
        )

        response = self._client.messages.create(
            model       = self._model,
            max_tokens  = self._max_tokens,
            temperature = self._temperature,
            system      = _SYSTEM_PROMPT,
            messages    = [{"role": "user", "content": user_prompt}],
        )
        return self._parse_response(response.content[0].text.strip())

    # ------------------------------------------------------------------
    # Response Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(text: str) -> tuple[str, str, list[str], float]:
        """Parse the structured LLM response into typed fields."""
        label: str       = ""
        desc:  str       = ""
        spans: list[str] = []
        conf:  float     = 0.0

        for line in text.splitlines():
            if line.startswith("LABEL:"):
                label = line.removeprefix("LABEL:").strip()
            elif line.startswith("DESCRIPTION:"):
                desc  = line.removeprefix("DESCRIPTION:").strip()
            elif line.startswith("EVIDENCE:"):
                raw   = line.removeprefix("EVIDENCE:").strip()
                spans = [s.strip() for s in raw.split(",") if s.strip()]
            elif line.startswith("CONFIDENCE:"):
                try:
                    conf = float(line.removeprefix("CONFIDENCE:").strip())
                except ValueError:
                    conf = 0.0

        return label, desc, spans, conf


# ---------------------------------------------------------------------------
# Factory Helper
# ---------------------------------------------------------------------------


def build_topic_extractor(
    encoder_model: str                        = "all-MiniLM-L6-v2",
    llm_model:     str                        = "claude-sonnet-4-6",
    client:        Optional[anthropic.Anthropic] = None,
) -> tuple[TopicExtractor, InMemoryTopicStore]:
    """
    Convenience factory that wires up a TopicExtractor with an InMemoryTopicStore.

    In production, replace InMemoryTopicStore with a pgvector-backed
    implementation.  The TopicStore is returned separately so callers can:
      - Seed it with known topics before processing.
      - Inspect all discovered topics after processing (for taxonomy seeding).

    Args:
        encoder_model: Sentence-transformer model name for topic embeddings.
        llm_model:     Claude model for open extraction.
        client:        Anthropic client (reads ANTHROPIC_API_KEY from env if None).
    """
    encoder     = SentenceTransformer(encoder_model)
    topic_store = InMemoryTopicStore(encoder=encoder)
    extractor   = TopicExtractor(
        topic_store = topic_store,
        client      = client or anthropic.Anthropic(),
        model       = llm_model,
    )
    return extractor, topic_store


# ---------------------------------------------------------------------------
# Smoke-test (requires ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    def _make_unit(text: str, channel: str = "app_store_review") -> FeedbackUnit:
        return FeedbackUnit(
            unit_id       = str(uuid.uuid4()),
            parent_cfo_id = "test-cfo",
            text          = text,
            char_start    = 0,
            char_end      = len(text),
            unit_index    = 0,
            metadata      = {
                "source_channel": channel,
                "user_segment":   "enterprise",
            },
        )

    # Units A and B are about the same abstract topic (duplicate charge) but
    # reference different product lines.  They should map to the same Topic.
    # Units C and D are about app crashes during export — same topic, two users.
    # Unit E is unique.
    units = [
        _make_unit("Product A charged me twice this billing cycle, I need a refund."),
        _make_unit("I was double-billed on my Product B subscription last month."),
        _make_unit("The mobile app crashes every time I try to export a report."),
        _make_unit("Exporting data always crashes the app — completely unusable."),
        _make_unit("Support took 6 days to respond to my urgent ticket.", "support_ticket"),
    ]

    extractor, store = build_topic_extractor()
    results          = extractor.extract_batch(units, verbose=True)

    print(f"\n{'='*65}")
    print("EXTRACTION RESULTS")
    print(f"{'='*65}")
    for unit, result in zip(units, results):
        tag = "[NEW]  " if result.is_new_topic else "[KNOWN]"
        print(f"\n  {tag} topic='{result.topic_label}'  conf={result.confidence:.2f}")
        print(f"         unit='{unit.text[:72]}…'")
        print(f"         evidence={result.evidence_spans}")

    print(f"\n{'='*65}")
    print("DISTINCT TOPICS DISCOVERED")
    print(f"{'='*65}")
    for topic in store.all_topics():
        print(
            f"  - '{topic.label}'  count={topic.feedback_count}"
            f"  aliases={topic.aliases}"
        )
    print(
        "\nNote: Units from 'Product A' and 'Product B' billing complaints "
        "should resolve to the same Topic above.  Taxonomy placement "
        "(which product line) is handled separately in Stage 4."
    )
