"""
Stage 3.3: Intent & Request Detection + Extraction Orchestrator
===============================================================
Two components live in this module:

  IntentAgent
      Classifies the customer's intent (complaint, feature request, bug report,
      etc.) and extracts any specific asks.  Intent is stable per topic —
      "Duplicate Charge After Cancellation" is always a complaint, "Dark Mode
      Request" is always a feature request.  The agent caches the classified
      intent on the Topic object so subsequent units mapped to the same topic
      never need an LLM call for intent.

  ExtractionOrchestrator
      Coordinates the SentimentAgent and IntentAgent and enforces a hard limit
      of ONE LLM call per FeedbackUnit, regardless of whether the topic is new
      or known:

        Known topic (intent already cached on Topic)
          → sentiment-only LLM call
          → intent returned from Topic cache   (0 extra calls)

        New topic (no cached intent yet)
          → single COMBINED LLM call for sentiment + intent together
          → intent result cached on Topic for all future units

      This halves the LLM cost compared to running the agents independently,
      while producing the same output.

Dependencies:
    pip install anthropic
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import anthropic

from stage2_unitization import FeedbackUnit
from stage3_sentiment_extraction import (
    AspectSentiment,
    EmotionTag,
    SentimentAgent,
    SentimentResult,
)
from stage3_topic_extraction import Topic, TopicExtractionResult, TopicStoreInterface

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class ChurnIndicator:
    """A signal that the customer may be at risk of churning."""
    signal:   str    # e.g. "mentioned cancellation", "comparing with competitor"
    severity: float  # 0.0–1.0


@dataclass
class IntentResult:
    """
    Intent classification for a single FeedbackUnit.

    Attributes:
        unit_id:             ID of the source FeedbackUnit.
        intent_type:         The primary intent category.
        urgency:             How urgently this needs attention.
        specific_request:    If the customer asked for something specific, what is it.
        competitor_mention:  Competitor name if mentioned, else None.
        churn_indicators:    Signals that the customer may be about to leave.
        from_cache:          True when intent was inherited from the Topic cache
                             rather than freshly classified by the LLM.  Useful
                             for auditing and for identifying topics where intent
                             has drifted enough to warrant re-classification.
    """

    unit_id:            str
    intent_type:        str                       # see INTENT_TYPES below
    urgency:            str                       # low | medium | high | critical
    specific_request:   Optional[str]             = None
    competitor_mention: Optional[str]             = None
    churn_indicators:   list[ChurnIndicator]      = field(default_factory=list)
    from_cache:         bool                      = False


INTENT_TYPES: tuple[str, ...] = (
    "complaint", "feature_request", "bug_report", "question",
    "praise", "churn_signal", "comparison", "suggestion", "general_comment",
)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

# Used when intent is already cached — only sentiment is needed.
_SENTIMENT_ONLY_SYSTEM = """\
You are a customer feedback sentiment analyst. Analyse the sentiment of the \
given feedback unit and return a single JSON object.

POLARITY SCALE:
  -1.0  very negative (extreme frustration, outrage)
  -0.5  moderately negative (clear dissatisfaction)
   0.0  neutral
  +0.5  moderately positive (satisfied, pleased)
  +1.0  very positive (delighted, highly enthusiastic)

INTENSITY OPTIONS:  mild | moderate | strong | extreme

EMOTION OPTIONS (pick up to 3, highest confidence first):
  frustrated, angry, disappointed, confused, anxious,
  neutral, satisfied, pleased, delighted, grateful,
  surprised_positive, surprised_negative, resigned, hopeful

SARCASM RULE:
  If the customer is sarcastic or ironic, set sarcasm to true and report the
  TRUE underlying polarity (already inverted), not the surface polarity.

ASPECT SENTIMENTS:
  If multiple distinct product areas are mentioned, provide a per-aspect
  breakdown with the exact text span as evidence.

Return ONLY valid JSON:
{
  "polarity": <float -1.0 to 1.0>,
  "intensity": "<mild|moderate|strong|extreme>",
  "emotions": [{"emotion": "<label>", "confidence": <float>}],
  "aspect_sentiments": [{"aspect": "<name>", "polarity": <float>, "evidence": "<exact span>"}],
  "sarcasm": <true|false>,
  "confidence": <float>
}\
"""

# Used when the topic is new — extracts sentiment AND intent in one call.
_COMBINED_SYSTEM = """\
You are a customer feedback analyst. For the given feedback unit, perform two \
analyses in a single pass and return one JSON object with two top-level keys: \
"sentiment" and "intent".

── SENTIMENT ────────────────────────────────────────────────────────────────
POLARITY SCALE:
  -1.0  very negative     0.0  neutral     +1.0  very positive
INTENSITY:   mild | moderate | strong | extreme
EMOTIONS (up to 3): frustrated, angry, disappointed, confused, anxious,
  neutral, satisfied, pleased, delighted, grateful,
  surprised_positive, surprised_negative, resigned, hopeful
SARCASM: if detected, set sarcasm=true and report the TRUE (inverted) polarity.
ASPECTS: per-aspect polarity breakdown when multiple product areas are mentioned.

── INTENT ───────────────────────────────────────────────────────────────────
INTENT TYPE (pick one):
  complaint | feature_request | bug_report | question | praise |
  churn_signal | comparison | suggestion | general_comment

URGENCY:  low | medium | high | critical

SPECIFIC REQUEST: if the customer is explicitly asking for something, state it
  precisely.  Null if no specific ask.

COMPETITOR MENTION: name of any competitor mentioned, or null.

CHURN INDICATORS: signals that the customer may be at risk of leaving.
  Can be an empty list.

Return ONLY valid JSON:
{
  "sentiment": {
    "polarity": <float>,
    "intensity": "<mild|moderate|strong|extreme>",
    "emotions": [{"emotion": "<label>", "confidence": <float>}],
    "aspect_sentiments": [{"aspect": "<name>", "polarity": <float>, "evidence": "<span>"}],
    "sarcasm": <true|false>,
    "confidence": <float>
  },
  "intent": {
    "intent_type": "<type>",
    "urgency": "<low|medium|high|critical>",
    "specific_request": "<string or null>",
    "competitor_mention": "<string or null>",
    "churn_indicators": [{"signal": "<description>", "severity": <float>}]
  }
}\
"""

_USER_PROMPT_TEMPLATE = """\
<feedback_metadata>
  source_channel: {source_channel}
  star_rating:    {star_rating}
  user_segment:   {user_segment}
</feedback_metadata>

<feedback_unit>
{text}
</feedback_unit>\
"""


# ---------------------------------------------------------------------------
# Intent Agent
# ---------------------------------------------------------------------------


class IntentAgent:
    """
    Stage 3.3: Intent & Request Detection Agent.

    Classifies intent and caches the result on the Topic object.  All subsequent
    units mapped to the same Topic inherit the cached intent without an LLM call.

    Direct use (without ExtractionOrchestrator):
        If you need standalone intent classification — e.g., for the first unit
        of a new topic when sentiment is not also needed — call classify() directly.
        For coordinated sentiment + intent extraction, use ExtractionOrchestrator.

    Args:
        client:      An anthropic.Anthropic client (created from env if None).
        model:       Claude model to use.
        max_tokens:  Maximum tokens for each LLM response.
        temperature: Sampling temperature.
    """

    def __init__(
        self,
        client:      Optional[anthropic.Anthropic] = None,
        model:       str   = "claude-sonnet-4-6",
        max_tokens:  int   = 256,
        temperature: float = 0.0,
    ) -> None:
        self._client      = client or anthropic.Anthropic()
        self._model       = model
        self._max_tokens  = max_tokens
        self._temperature = temperature

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(
        self,
        unit:         FeedbackUnit,
        topic:        Optional[Topic],
        topic_store:  Optional[TopicStoreInterface] = None,
    ) -> IntentResult:
        """
        Classify the intent for a FeedbackUnit.

        If the associated Topic already has a cached intent_type, returns
        immediately from cache (no LLM call).

        If the intent is not yet cached, runs an LLM call and writes the
        result back to the Topic so future units skip the call.

        Args:
            unit:        The FeedbackUnit to classify.
            topic:       The Topic this unit maps to.  May be None for
                         unmapped units, in which case a fresh LLM call is
                         always made.
            topic_store: Not used here (intent is written directly to the
                         Topic object, which is stored by reference).
                         Accepted for interface consistency.
        """
        if topic is not None and topic.intent_type is not None:
            logger.debug(
                "Unit %s → intent from cache: %s (%s)",
                unit.unit_id[:8], topic.intent_type, topic.intent_urgency,
            )
            return IntentResult(
                unit_id            = unit.unit_id,
                intent_type        = topic.intent_type,
                urgency            = topic.intent_urgency or "medium",
                specific_request   = None,
                competitor_mention = None,
                churn_indicators   = [],
                from_cache         = True,
            )

        # No cache — classify via LLM
        result = self._llm_classify(unit)

        # Cache on topic for future units
        if topic is not None:
            topic.intent_type    = result.intent_type
            topic.intent_urgency = result.urgency
            logger.debug(
                "Unit %s → intent classified and cached on topic %s: %s (%s)",
                unit.unit_id[:8], topic.topic_id[:8],
                result.intent_type, result.urgency,
            )

        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _llm_classify(self, unit: FeedbackUnit) -> IntentResult:
        _intent_only_system = """\
You are a customer feedback intent classifier. Identify the customer's intent \
and any specific requests.

INTENT TYPE (pick one):
  complaint | feature_request | bug_report | question | praise |
  churn_signal | comparison | suggestion | general_comment

URGENCY:  low | medium | high | critical

SPECIFIC REQUEST: if the customer is explicitly asking for something, state it
  precisely.  Null if no specific ask.

COMPETITOR MENTION: name of any competitor mentioned, or null.

CHURN INDICATORS: signals the customer may leave (list, can be empty).

Return ONLY valid JSON:
{
  "intent_type": "<type>",
  "urgency": "<low|medium|high|critical>",
  "specific_request": "<string or null>",
  "competitor_mention": "<string or null>",
  "churn_indicators": [{"signal": "<description>", "severity": <float>}]
}\
"""
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            source_channel = unit.metadata.get("source_channel", "unknown"),
            star_rating    = unit.metadata.get("star_rating", "N/A"),
            user_segment   = unit.metadata.get("user_segment", "unknown"),
            text           = unit.text,
        )
        response = self._client.messages.create(
            model       = self._model,
            max_tokens  = self._max_tokens,
            temperature = self._temperature,
            system      = _intent_only_system,
            messages    = [{"role": "user", "content": user_prompt}],
        )
        return self._parse_intent(unit.unit_id, response.content[0].text.strip())

    @staticmethod
    def _parse_intent(unit_id: str, raw: str) -> IntentResult:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("IntentAgent: JSON parse failed for unit %s: %s", unit_id[:8], exc)
            return IntentResult(unit_id=unit_id, intent_type="complaint", urgency="medium")

        churn = [
            ChurnIndicator(signal=c.get("signal", ""), severity=float(c.get("severity", 0.0)))
            for c in data.get("churn_indicators", [])
        ]
        return IntentResult(
            unit_id            = unit_id,
            intent_type        = data.get("intent_type", "complaint"),
            urgency            = data.get("urgency", "medium"),
            specific_request   = data.get("specific_request") or None,
            competitor_mention = data.get("competitor_mention") or None,
            churn_indicators   = churn,
            from_cache         = False,
        )


# ---------------------------------------------------------------------------
# Extraction Orchestrator
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    """Combined output of sentiment + intent for a single FeedbackUnit."""
    sentiment: SentimentResult
    intent:    IntentResult


class ExtractionOrchestrator:
    """
    Coordinates sentiment and intent extraction with a hard cap of ONE LLM
    call per FeedbackUnit.

    Decision logic:
      ┌─────────────────────────────────┬──────────────────────────────────────┐
      │  Topic intent cached?           │  Action                              │
      ├─────────────────────────────────┼──────────────────────────────────────┤
      │  Yes (topic.intent_type set)    │  Sentiment-only call (1 call).       │
      │                                 │  Intent returned from Topic cache.   │
      ├─────────────────────────────────┼──────────────────────────────────────┤
      │  No  (new topic or no cache)    │  Single combined call for sentiment  │
      │                                 │  + intent together (1 call).         │
      │                                 │  Intent result cached on Topic.      │
      └─────────────────────────────────┴──────────────────────────────────────┘

    In both cases: exactly 1 LLM call per unit.

    Args:
        client:      An anthropic.Anthropic client (created from env if None).
        model:       Claude model for all LLM calls.
        max_tokens:  Token budget for each call.
        temperature: Sampling temperature.
    """

    def __init__(
        self,
        client:      Optional[anthropic.Anthropic] = None,
        model:       str   = "claude-sonnet-4-6",
        max_tokens:  int   = 768,
        temperature: float = 0.0,
    ) -> None:
        self._client      = client or anthropic.Anthropic()
        self._model       = model
        self._max_tokens  = max_tokens
        self._temperature = temperature

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        unit:          FeedbackUnit,
        topic_result:  TopicExtractionResult,
        topic_store:   TopicStoreInterface,
    ) -> ExtractionResult:
        """
        Run sentiment + intent extraction for one unit, using exactly one
        LLM call regardless of whether the topic is new or known.
        """
        topic = topic_store.get(topic_result.topic_id)

        if topic is not None and topic.intent_type is not None:
            return self._sentiment_only_path(unit, topic)
        else:
            return self._combined_path(unit, topic)

    def extract_batch(
        self,
        units:          list[FeedbackUnit],
        topic_results:  list[TopicExtractionResult],
        topic_store:    TopicStoreInterface,
        *,
        verbose:        bool = False,
    ) -> list[ExtractionResult]:
        """
        Process a batch of units.  Each unit makes exactly one LLM call.
        LLM calls are independent; replace the loop with asyncio /
        ThreadPoolExecutor for high-throughput use.
        """
        if len(units) != len(topic_results):
            raise ValueError("units and topic_results must be the same length")

        results: list[ExtractionResult] = []
        for i, (unit, topic_result) in enumerate(zip(units, topic_results)):
            result = self.extract(unit, topic_result, topic_store)
            results.append(result)
            if verbose:
                cached = "cache" if result.intent.from_cache else "LLM"
                logger.info(
                    "Unit %d/%d [%s]: polarity=%+.2f  intent=%s(%s)  urgency=%s",
                    i + 1, len(units), unit.unit_id[:8],
                    result.sentiment.polarity,
                    result.intent.intent_type, cached,
                    result.intent.urgency,
                )
        return results

    # ------------------------------------------------------------------
    # Internal paths
    # ------------------------------------------------------------------

    def _sentiment_only_path(
        self, unit: FeedbackUnit, topic: Topic
    ) -> ExtractionResult:
        """
        Known topic: one sentiment-only LLM call, intent from Topic cache.
        """
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            source_channel = unit.metadata.get("source_channel", "unknown"),
            star_rating    = unit.metadata.get("star_rating", "N/A"),
            user_segment   = unit.metadata.get("user_segment", "unknown"),
            text           = unit.text,
        )
        response = self._client.messages.create(
            model       = self._model,
            max_tokens  = self._max_tokens,
            temperature = self._temperature,
            system      = _SENTIMENT_ONLY_SYSTEM,
            messages    = [{"role": "user", "content": user_prompt}],
        )
        sentiment = SentimentAgent._parse(unit.unit_id, response.content[0].text.strip())
        intent    = IntentResult(
            unit_id            = unit.unit_id,
            intent_type        = topic.intent_type,       # type: ignore[arg-type]
            urgency            = topic.intent_urgency or "medium",
            specific_request   = None,
            competitor_mention = None,
            churn_indicators   = [],
            from_cache         = True,
        )
        logger.debug(
            "Unit %s: sentiment-only path (intent='%s' from cache).",
            unit.unit_id[:8], topic.intent_type,
        )
        return ExtractionResult(sentiment=sentiment, intent=intent)

    def _combined_path(
        self, unit: FeedbackUnit, topic: Optional[Topic]
    ) -> ExtractionResult:
        """
        New or uncached topic: one combined LLM call for sentiment + intent.
        Caches intent on the Topic object so the next unit skips the call.
        """
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            source_channel = unit.metadata.get("source_channel", "unknown"),
            star_rating    = unit.metadata.get("star_rating", "N/A"),
            user_segment   = unit.metadata.get("user_segment", "unknown"),
            text           = unit.text,
        )
        response = self._client.messages.create(
            model       = self._model,
            max_tokens  = self._max_tokens,
            temperature = self._temperature,
            system      = _COMBINED_SYSTEM,
            messages    = [{"role": "user", "content": user_prompt}],
        )
        sentiment, intent = self._parse_combined(unit.unit_id, response.content[0].text.strip())

        # Cache intent on topic so future units use the cheap path
        if topic is not None:
            topic.intent_type    = intent.intent_type
            topic.intent_urgency = intent.urgency
            logger.debug(
                "Unit %s: combined path — intent '%s' cached on topic %s.",
                unit.unit_id[:8], intent.intent_type, topic.topic_id[:8],
            )

        return ExtractionResult(sentiment=sentiment, intent=intent)

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_combined(
        unit_id: str, raw: str
    ) -> tuple[SentimentResult, IntentResult]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("ExtractionOrchestrator: JSON parse failed for unit %s: %s", unit_id[:8], exc)
            fallback_sentiment = SentimentResult(unit_id=unit_id, polarity=0.0, intensity="mild")
            fallback_intent    = IntentResult(unit_id=unit_id, intent_type="complaint", urgency="medium")
            return fallback_sentiment, fallback_intent

        sentiment = SentimentAgent._parse(unit_id, json.dumps(data.get("sentiment", {})))
        intent    = IntentAgent._parse_intent(unit_id, json.dumps(data.get("intent", {})))
        return sentiment, intent


# ---------------------------------------------------------------------------
# Smoke-test (requires ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import uuid

    from stage3_topic_extraction import Topic, TopicExtractionResult, InMemoryTopicStore
    from sentence_transformers import SentenceTransformer

    def _make_unit(text: str) -> FeedbackUnit:
        return FeedbackUnit(
            unit_id       = str(uuid.uuid4()),
            parent_cfo_id = "test-cfo",
            text          = text,
            char_start    = 0,
            char_end      = len(text),
            unit_index    = 0,
            metadata      = {"source_channel": "app_store_review", "star_rating": 2},
        )

    # Two units with the same topic: first triggers combined path (LLM),
    # second uses the cached intent path (sentiment-only LLM call).
    billing_topic = Topic(label="Duplicate Charge After Cancellation",
                          description="Customer charged multiple times after cancelling.")
    encoder       = SentenceTransformer("all-MiniLM-L6-v2")
    store         = InMemoryTopicStore(encoder=encoder)
    store.add(billing_topic)

    units = [
        _make_unit("I was charged three times after cancelling my subscription. This is unacceptable."),
        _make_unit("Got billed again even though I cancelled two weeks ago. Please refund."),
        _make_unit("The export feature is completely broken — crashes every single time."),
    ]

    topic_results = [
        TopicExtractionResult(
            unit_id         = units[0].unit_id,
            topic_id        = billing_topic.topic_id,
            topic_label     = billing_topic.label,
            confidence      = 0.91,
            is_new_topic    = True,    # first time → combined path
        ),
        TopicExtractionResult(
            unit_id         = units[1].unit_id,
            topic_id        = billing_topic.topic_id,
            topic_label     = billing_topic.label,
            confidence      = 0.88,
            is_new_topic    = False,   # same topic → cache path after unit[0] runs
        ),
        TopicExtractionResult(
            unit_id         = units[2].unit_id,
            topic_id        = str(uuid.uuid4()),   # different topic
            topic_label     = "Crash During Export",
            confidence      = 0.85,
            is_new_topic    = True,    # new topic → combined path
        ),
    ]

    orchestrator = ExtractionOrchestrator()
    results      = orchestrator.extract_batch(units, topic_results, store, verbose=True)

    print(f"\n{'='*65}")
    print("EXTRACTION RESULTS")
    print(f"{'='*65}")
    for unit, r in zip(units, results):
        cached = "(cache)" if r.intent.from_cache else "(LLM)  "
        print(f"\n  unit    : {unit.text[:70]}…")
        print(f"  polarity: {r.sentiment.polarity:+.2f}  intensity: {r.sentiment.intensity}")
        print(f"  intent  : {r.intent.intent_type} {cached}  urgency: {r.intent.urgency}")
        if r.intent.specific_request:
            print(f"  request : {r.intent.specific_request}")

    print(f"\n{'='*65}")
    print("CACHED INTENT ON TOPIC")
    print(f"  topic   : '{billing_topic.label}'")
    print(f"  intent  : {billing_topic.intent_type}  urgency: {billing_topic.intent_urgency}")
