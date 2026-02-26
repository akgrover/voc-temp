"""
Stage 3.1: Sentiment & Emotion Extraction
==========================================
Assigns fine-grained sentiment and emotional tone to each FeedbackUnit.

Combines the design doc's three-pass approach (polarity, emotions, sarcasm)
into a single LLM call that returns a structured JSON response.  This is
both cheaper and more coherent — the model can reason about sarcasm and
invert the polarity in the same pass rather than doing it as a correction step.

Sarcasm handling:
    When sarcasm is detected the model is instructed to report the TRUE polarity
    (i.e. already inverted), not the surface polarity.  The sarcasm_flag is set
    so downstream consumers know the inversion occurred.

This module is intentionally standalone.  It does not know about topics or
intent — those concerns live in stage3_topic_extraction.py and
stage3_intent_extraction.py.  The ExtractionOrchestrator in
stage3_intent_extraction.py decides when to call this agent directly versus
when to fold sentiment into a combined call.

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

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class EmotionTag:
    """A single emotional label with an associated confidence score."""
    emotion:    str    # e.g. "frustrated", "delighted" — see EMOTION_LABELS below
    confidence: float  # 0.0–1.0


@dataclass
class AspectSentiment:
    """
    Sentiment toward a specific aspect (feature, workflow, team) mentioned
    in the feedback unit.  Finer-grained than the overall polarity.
    """
    aspect:   str    # e.g. "checkout speed", "customer support"
    polarity: float  # -1.0 to +1.0
    evidence: str    # Exact span from the unit text supporting this score


@dataclass
class SentimentResult:
    """
    Full sentiment analysis for a single FeedbackUnit.

    Attributes:
        unit_id:           ID of the source FeedbackUnit.
        polarity:          Overall sentiment from -1.0 (very negative) to
                           +1.0 (very positive).  Already inverted if sarcasm
                           was detected.
        intensity:         How strongly the sentiment is expressed.
        emotions:          Up to 3 emotional labels, ordered by confidence.
        aspect_sentiments: Per-aspect breakdown when multiple product areas are
                           mentioned in the same unit.
        sarcasm_flag:      True when sarcasm or irony was detected.  Signals
                           that the polarity has been inverted from the literal
                           reading of the text.
        confidence:        Model's confidence in the overall assessment.
    """

    unit_id:           str
    polarity:          float
    intensity:         str                        # mild | moderate | strong | extreme
    emotions:          list[EmotionTag]           = field(default_factory=list)
    aspect_sentiments: list[AspectSentiment]      = field(default_factory=list)
    sarcasm_flag:      bool                       = False
    confidence:        float                      = 0.0


# ---------------------------------------------------------------------------
# Emotion vocabulary — constrained set relevant to customer feedback contexts
# ---------------------------------------------------------------------------

EMOTION_LABELS: tuple[str, ...] = (
    "frustrated", "angry", "disappointed", "confused", "anxious",
    "neutral", "satisfied", "pleased", "delighted", "grateful",
    "surprised_positive", "surprised_negative", "resigned", "hopeful",
)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
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
  If the customer is being sarcastic or ironic (e.g. "Oh great, another crash"),
  set sarcasm to true and report the TRUE underlying polarity (already inverted),
  not the literal surface polarity.

ASPECT SENTIMENTS:
  If the unit mentions more than one distinct product area, feature, or team,
  provide a per-aspect breakdown.  Use the exact text span as evidence.
  If only one aspect is discussed, return a single-item list.

Return ONLY valid JSON — no markdown fences, no explanation:
{
  "polarity": <float -1.0 to 1.0>,
  "intensity": "<mild|moderate|strong|extreme>",
  "emotions": [
    {"emotion": "<label>", "confidence": <float>}
  ],
  "aspect_sentiments": [
    {"aspect": "<name>", "polarity": <float>, "evidence": "<exact span>"}
  ],
  "sarcasm": <true|false>,
  "confidence": <float>
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
# Sentiment Agent
# ---------------------------------------------------------------------------


class SentimentAgent:
    """
    Stage 3.1: Sentiment & Emotion Agent.

    Single LLM call per unit that simultaneously assesses polarity, intensity,
    emotional tone, aspect-level sentiment, and sarcasm.  This collapses the
    design doc's three-pass approach into one call — the model handles all three
    aspects in a single reasoning pass, which is cheaper and produces more
    internally consistent results (sarcasm detection informs the polarity in the
    same step rather than being applied as a post-hoc correction).

    Args:
        client:      An anthropic.Anthropic client (created from env if None).
        model:       Claude model to use.
        max_tokens:  Maximum tokens for each LLM response.
        temperature: Sampling temperature (0 = deterministic).
    """

    def __init__(
        self,
        client:      Optional[anthropic.Anthropic] = None,
        model:       str   = "claude-sonnet-4-6",
        max_tokens:  int   = 512,
        temperature: float = 0.0,
    ) -> None:
        self._client      = client or anthropic.Anthropic()
        self._model       = model
        self._max_tokens  = max_tokens
        self._temperature = temperature

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, unit: FeedbackUnit) -> SentimentResult:
        """Analyse sentiment for a single FeedbackUnit."""
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
            system      = _SYSTEM_PROMPT,
            messages    = [{"role": "user", "content": user_prompt}],
        )
        return self._parse(unit.unit_id, response.content[0].text.strip())

    def extract_batch(
        self,
        units:   list[FeedbackUnit],
        *,
        verbose: bool = False,
    ) -> list[SentimentResult]:
        """
        Extract sentiment for a list of FeedbackUnits.
        LLM calls are independent; replace the loop with asyncio /
        ThreadPoolExecutor for high-throughput production use.
        """
        results: list[SentimentResult] = []
        for i, unit in enumerate(units):
            result = self.extract(unit)
            results.append(result)
            if verbose:
                logger.info(
                    "Unit %d/%d [%s]: polarity=%.2f  intensity=%s  sarcasm=%s",
                    i + 1, len(units), unit.unit_id[:8],
                    result.polarity, result.intensity, result.sarcasm_flag,
                )
        return results

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse(unit_id: str, raw: str) -> SentimentResult:
        """Parse the JSON response from the LLM into a SentimentResult."""
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("SentimentAgent: JSON parse failed for unit %s: %s", unit_id[:8], exc)
            return SentimentResult(unit_id=unit_id, polarity=0.0, intensity="mild", confidence=0.0)

        emotions = [
            EmotionTag(emotion=e.get("emotion", ""), confidence=float(e.get("confidence", 0.0)))
            for e in data.get("emotions", [])
        ]
        aspects = [
            AspectSentiment(
                aspect   = a.get("aspect", ""),
                polarity = float(a.get("polarity", 0.0)),
                evidence = a.get("evidence", ""),
            )
            for a in data.get("aspect_sentiments", [])
        ]

        return SentimentResult(
            unit_id           = unit_id,
            polarity          = float(data.get("polarity", 0.0)),
            intensity         = data.get("intensity", "mild"),
            emotions          = emotions,
            aspect_sentiments = aspects,
            sarcasm_flag      = bool(data.get("sarcasm", False)),
            confidence        = float(data.get("confidence", 0.0)),
        )


# ---------------------------------------------------------------------------
# Smoke-test (requires ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import uuid

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

    units = [
        _make_unit("The checkout keeps crashing — I've lost my cart three times this week."),
        _make_unit("Oh sure, I just LOVE waiting 6 days for support to reply."),   # sarcasm
        _make_unit("The new dashboard redesign is genuinely beautiful. Great work."),
        _make_unit("Billing charged me twice but the product itself works fine."),  # mixed aspects
    ]

    agent   = SentimentAgent()
    results = agent.extract_batch(units, verbose=True)

    print(f"\n{'='*65}")
    for unit, r in zip(units, results):
        print(f"\n  unit    : {unit.text[:72]}…")
        print(f"  polarity: {r.polarity:+.2f}  intensity: {r.intensity}  sarcasm: {r.sarcasm_flag}")
        print(f"  emotions: {[(e.emotion, round(e.confidence, 2)) for e in r.emotions]}")
        for a in r.aspect_sentiments:
            print(f"  aspect  : '{a.aspect}'  polarity={a.polarity:+.2f}  evidence='{a.evidence}'")
