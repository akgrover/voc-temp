"""
Stage 2.1: Feedback Unitization
================================
Splits a single customer feedback response into atomic "feedback units" —
each expressing exactly one opinion, complaint, request, or observation
about one specific aspect of the product or experience.

Uses an LLM (Claude) as the reasoning core, following the prompt structure
defined in the VoC system design document.

Dependencies:
    pip install anthropic
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class FeedbackUnit:
    """
    An atomic unit of customer feedback covering exactly one topic.

    Attributes:
        unit_id:        Unique identifier for this unit.
        parent_cfo_id:  ID of the originating Canonical Feedback Object.
        text:           The unit's text (verbatim or lightly cleaned).
        char_start:     Character offset (start) in the parent CFO's clean_text.
        char_end:       Character offset (end) in the parent CFO's clean_text.
        unit_index:     Position of this unit among siblings (0-based).
        metadata:       Pass-through metadata from the parent CFO
                        (channel, segment, survey_question, etc.).
    """

    unit_id:       str
    parent_cfo_id: str
    text:          str
    char_start:    int
    char_end:      int
    unit_index:    int
    metadata:      dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.unit_id:
            self.unit_id = str(uuid.uuid4())


@dataclass
class UnitizationResult:
    """Output of the Unitization Agent for one CFO."""

    cfo_id:         str
    original_text:  str
    units:          list[FeedbackUnit]
    raw_llm_output: str   = ""
    error:          str   = ""

    @property
    def is_atomic(self) -> bool:
        return len(self.units) == 1

    @property
    def unit_count(self) -> int:
        return len(self.units)


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a senior Voice of Customer analyst. Your task is to split a single \
piece of raw customer feedback into its atomic "feedback units."

Rules:
1. Each unit must express exactly ONE opinion, complaint, request, or \
   observation about ONE specific aspect of the product or experience.
2. Each unit must be self-contained and fully understandable without reading \
   the others (preserve enough context in each unit's text).
3. Preserve the customer's original wording as closely as possible — do not \
   paraphrase or rephrase.
4. Tag each unit with its character offsets (start, end) in the ORIGINAL text \
   supplied under <feedback_text>. Offsets are 0-based and the end is exclusive.
5. Contextual phrases like "overall" or "in general" must remain attached to \
   the opinion they modify.
6. If the feedback is already atomic (single topic), return it as a single unit.
7. Ignore greetings, sign-offs, and filler phrases (e.g., "Hi there,", \
   "Thanks!") — do NOT create units for them.

Return ONLY a JSON array of objects. Each object must have:
  - "text":       string  (the unit text, preserving original wording)
  - "char_start": integer (start offset in the original feedback text)
  - "char_end":   integer (end offset, exclusive)

Example output:
[
  {"text": "the app redesign looks amazing", "char_start": 10, "char_end": 40},
  {"text": "checkout crashed on me three times", "char_start": 42, "char_end": 76}
]
"""

_USER_PROMPT_TEMPLATE = """\
<feedback_metadata>
  source_channel:   {source_channel}
  survey_question:  {survey_question}
  star_rating:      {star_rating}
  user_segment:     {user_segment}
</feedback_metadata>

<feedback_text>
{clean_text}
</feedback_text>

Split the above feedback into atomic units following the rules. \
Return ONLY the JSON array — no markdown, no explanation.\
"""


# ---------------------------------------------------------------------------
# Unitization Agent
# ---------------------------------------------------------------------------


class UnitizationAgent:
    """
    LLM-powered agent that splits feedback into atomic FeedbackUnit objects.

    Args:
        client:          An `anthropic.Anthropic` client instance.
        model:           Claude model to use (default: claude-sonnet-4-6).
        max_tokens:      Maximum tokens for the LLM response.
        temperature:     Sampling temperature (0 = deterministic).
        fallback_on_err: If True, return the full text as one unit on error.
    """

    def __init__(
        self,
        client:          Optional[anthropic.Anthropic] = None,
        model:           str   = "claude-sonnet-4-6",
        max_tokens:      int   = 1024,
        temperature:     float = 0.0,
        fallback_on_err: bool  = True,
    ) -> None:
        self._client          = client or anthropic.Anthropic()
        self._model           = model
        self._max_tokens      = max_tokens
        self._temperature     = temperature
        self._fallback_on_err = fallback_on_err

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def unitize(self, cfo: dict) -> UnitizationResult:
        """
        Split a Canonical Feedback Object into atomic FeedbackUnit objects.

        Args:
            cfo: A CFO dict. Expected keys:
                 - id (str)
                 - clean_text (str)
                 - source_channel (str, optional)
                 - source_metadata.survey_question (str, optional)
                 - source_metadata.star_rating (int, optional)
                 - user_metadata.segment (str, optional)

        Returns:
            UnitizationResult with a list of FeedbackUnit objects.
        """
        cfo_id     = cfo.get("id", str(uuid.uuid4()))
        clean_text = cfo.get("clean_text") or cfo.get("raw_text", "")

        if not clean_text.strip():
            logger.warning("CFO %s has empty text; returning empty result.", cfo_id)
            return UnitizationResult(
                cfo_id=cfo_id, original_text=clean_text, units=[]
            )

        user_prompt = self._build_user_prompt(cfo, clean_text)

        try:
            raw_output = self._call_llm(user_prompt)
            units      = self._parse_response(raw_output, cfo_id, clean_text, cfo)
            return UnitizationResult(
                cfo_id=cfo_id,
                original_text=clean_text,
                units=units,
                raw_llm_output=raw_output,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unitization failed for CFO %s: %s", cfo_id, exc)

            if self._fallback_on_err:
                fallback_unit = self._make_fallback_unit(cfo_id, clean_text, cfo)
                return UnitizationResult(
                    cfo_id=cfo_id,
                    original_text=clean_text,
                    units=[fallback_unit],
                    error=str(exc),
                )
            raise

    # ------------------------------------------------------------------
    # Prompt Construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_user_prompt(cfo: dict, clean_text: str) -> str:
        source_meta = cfo.get("source_metadata") or {}
        user_meta   = cfo.get("user_metadata") or {}

        return _USER_PROMPT_TEMPLATE.format(
            source_channel  = cfo.get("source_channel", "unknown"),
            survey_question = source_meta.get("survey_question") or "N/A",
            star_rating     = source_meta.get("star_rating") or "N/A",
            user_segment    = user_meta.get("segment") or "N/A",
            clean_text      = clean_text,
        )

    # ------------------------------------------------------------------
    # LLM Call
    # ------------------------------------------------------------------

    def _call_llm(self, user_prompt: str) -> str:
        response = self._client.messages.create(
            model      = self._model,
            max_tokens = self._max_tokens,
            temperature= self._temperature,
            system     = _SYSTEM_PROMPT,
            messages   = [{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text.strip()

    # ------------------------------------------------------------------
    # Response Parsing
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        raw: str,
        cfo_id: str,
        original_text: str,
        cfo: dict,
    ) -> list[FeedbackUnit]:
        """
        Parse the LLM JSON response into FeedbackUnit objects.
        Validates offsets and text alignment against the original.
        """
        cleaned = self._strip_markdown_fences(raw)

        try:
            items: list[dict] = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"LLM returned invalid JSON for CFO {cfo_id}: {exc}\nRaw: {raw[:300]}"
            ) from exc

        if not isinstance(items, list):
            raise ValueError(
                f"Expected a JSON array, got {type(items).__name__} for CFO {cfo_id}"
            )

        units: list[FeedbackUnit] = []
        shared_metadata = self._extract_metadata(cfo)

        for idx, item in enumerate(items):
            text       = item.get("text", "").strip()
            char_start = item.get("char_start", 0)
            char_end   = item.get("char_end", len(original_text))

            if not text:
                logger.debug("Skipping empty unit at index %d for CFO %s", idx, cfo_id)
                continue

            # Validate & repair offsets
            char_start, char_end = self._validate_offsets(
                text, char_start, char_end, original_text, cfo_id, idx
            )

            units.append(
                FeedbackUnit(
                    unit_id       = str(uuid.uuid4()),
                    parent_cfo_id = cfo_id,
                    text          = text,
                    char_start    = char_start,
                    char_end      = char_end,
                    unit_index    = idx,
                    metadata      = shared_metadata,
                )
            )

        if not units:
            logger.warning(
                "LLM returned 0 valid units for CFO %s; using full text as fallback.",
                cfo_id,
            )
            units = [self._make_fallback_unit(cfo_id, original_text, cfo)]

        return units

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Remove ```json ... ``` or ``` ... ``` wrappers if present."""
        return re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()

    @staticmethod
    def _validate_offsets(
        unit_text:     str,
        char_start:    int,
        char_end:      int,
        original_text: str,
        cfo_id:        str,
        idx:           int,
    ) -> tuple[int, int]:
        """
        Verify that the offsets point to text that matches (or approximately
        matches) the unit text. If they don't, perform a substring search
        to find the correct offsets.
        """
        n = len(original_text)
        char_start = max(0, min(char_start, n))
        char_end   = max(char_start, min(char_end, n))

        extracted = original_text[char_start:char_end].strip()

        # Accept if extracted text starts with the unit text's first 15 chars
        prefix = unit_text[:15].lower()
        if not extracted.lower().startswith(prefix):
            # Try substring search
            pos = original_text.lower().find(unit_text[:20].lower())
            if pos != -1:
                char_start = pos
                char_end   = pos + len(unit_text)
                logger.debug(
                    "Offset mismatch for unit %d in CFO %s; repaired via search.",
                    idx, cfo_id,
                )
            else:
                logger.warning(
                    "Could not repair offsets for unit %d in CFO %s. Using raw offsets.",
                    idx, cfo_id,
                )

        return char_start, char_end

    @staticmethod
    def _extract_metadata(cfo: dict) -> dict:
        """Pull forward relevant CFO metadata to each child unit."""
        source_meta = cfo.get("source_metadata") or {}
        user_meta   = cfo.get("user_metadata") or {}
        return {
            "source_channel":   cfo.get("source_channel"),
            "survey_question":  source_meta.get("survey_question"),
            "star_rating":      source_meta.get("star_rating"),
            "platform":         source_meta.get("platform"),
            "user_segment":     user_meta.get("segment"),
            "geography":        user_meta.get("geography"),
            "anonymized_uid":   user_meta.get("anonymized_user_id"),
            "feedback_created": (cfo.get("timestamps") or {}).get("feedback_created"),
        }

    @staticmethod
    def _make_fallback_unit(cfo_id: str, text: str, cfo: dict) -> FeedbackUnit:
        """Return the entire text as a single FeedbackUnit (fallback path)."""
        return FeedbackUnit(
            unit_id       = str(uuid.uuid4()),
            parent_cfo_id = cfo_id,
            text          = text,
            char_start    = 0,
            char_end      = len(text),
            unit_index    = 0,
            metadata      = UnitizationAgent._extract_metadata(cfo),
        )


# ---------------------------------------------------------------------------
# Batch Helper
# ---------------------------------------------------------------------------


def unitize_batch(
    cfos:    list[dict],
    agent:   Optional[UnitizationAgent] = None,
    *,
    verbose: bool = False,
) -> list[UnitizationResult]:
    """
    Unitize a list of CFOs sequentially.
    For high-throughput use cases, replace with asyncio / ThreadPoolExecutor.

    Args:
        cfos:    List of Canonical Feedback Object dicts.
        agent:   A shared UnitizationAgent (created if not provided).
        verbose: If True, log a summary for each CFO processed.

    Returns:
        List of UnitizationResult objects (same order as input).
    """
    if agent is None:
        agent = UnitizationAgent()

    results: list[UnitizationResult] = []
    for i, cfo in enumerate(cfos):
        result = agent.unitize(cfo)
        results.append(result)
        if verbose:
            logger.info(
                "CFO %d/%d (id=%s): split into %d unit(s).",
                i + 1, len(cfos), cfo.get("id", "?"), result.unit_count,
            )
    return results


# ---------------------------------------------------------------------------
# Smoke-test (requires ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    # Example CFO matching the one in the design doc
    sample_cfo = {
        "id":             str(uuid.uuid4()),
        "raw_text":       (
            "Honestly, the app redesign looks amazing, but I've had the checkout "
            "crash on me three times this week. Also, when I contacted support, "
            "they took 4 days to get back to me which is ridiculous. Please add "
            "Apple Pay — I shouldn't have to type my card number in 2025."
        ),
        "clean_text":     (
            "Honestly, the app redesign looks amazing, but I've had the checkout "
            "crash on me three times this week. Also, when I contacted support, "
            "they took 4 days to get back to me which is ridiculous. Please add "
            "Apple Pay — I shouldn't have to type my card number in 2025."
        ),
        "source_channel":  "app_store_review",
        "source_metadata": {
            "star_rating": 2,
            "app_store":   "iOS App Store",
        },
        "user_metadata":   {
            "segment": "free-tier",
        },
        "timestamps": {
            "feedback_created": "2025-01-15T10:30:00Z",
        },
        "language":     "en",
        "pii_redacted": False,
    }

    agent  = UnitizationAgent()  # Uses ANTHROPIC_API_KEY from env
    result = agent.unitize(sample_cfo)

    print(f"\n{'='*65}")
    print(f"CFO ID   : {result.cfo_id}")
    print(f"Units    : {result.unit_count}")
    print(f"{'='*65}")
    for unit in result.units:
        print(f"\n  [{unit.unit_index}] id={unit.unit_id[:8]}…")
        print(f"       text  : {unit.text!r}")
        print(f"       offsets: {unit.char_start}–{unit.char_end}")
