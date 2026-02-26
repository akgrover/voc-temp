"""
Account Name Extractor (Standalone)
=====================================
Identifies the company or organisation that submitted a piece of customer
feedback — making VoC data immediately actionable for customer-facing teams
who need to know *which account* a piece of feedback came from.

Strategy (multi-signal, cheapest signals evaluated first):

  1. Email domain scan (regex) — if the feedback contains an email address,
     the domain is a near-certain signal of the submitter's org.
  2. spaCy NER — fast, API-free extraction of ORG entities from the text.
  3. LLM disambiguation (Claude Haiku) — reasons over all candidates and
     determines which, if any, is the *submitter's* organisation rather than
     a vendor, product, or competitor being mentioned in context.

The key challenge is disambiguation: feedback often mentions multiple org
names (the product vendor, competitors, partners).  Only the LLM step can
reliably distinguish "we at Acme" from "we switched from Salesforce".

Standalone — no pipeline dependencies required beyond `anthropic` and `spacy`.

Dependencies:
    pip install anthropic spacy
    python -m spacy download en_core_web_trf
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

import anthropic
import spacy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class AccountExtractionResult:
    """
    Result of account name extraction for a single piece of feedback.

    Attributes:
        feedback_id:       ID of the source feedback item (or a generated UUID).
        account_name:      Canonical company/org name, or None if not found.
        confidence:        0.0–1.0; see confidence rubric in AccountExtractor.
        evidence:          The text span(s) that support the conclusion.
        extraction_method: How the final answer was reached.
                           "email_domain" — derived from an email address.
                           "llm"          — LLM chose from NER candidates.
                           "none"         — no account identified.
        raw_candidates:    All org names surfaced by NER before disambiguation.
        email_domain:      Raw domain extracted from an email, if any.
    """

    feedback_id:        str
    account_name:       Optional[str]
    confidence:         float
    evidence:           str
    extraction_method:  str                    # "email_domain" | "llm" | "none"
    raw_candidates:     list[str]              = field(default_factory=list)
    email_domain:       Optional[str]          = None


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a B2B customer intelligence analyst. Your job is to identify the \
company or organisation that *submitted* a piece of customer feedback — \
i.e. the customer's own employer or organisation, not the product/service \
being reviewed, not a competitor they mention, and not a vendor they reference.

You will receive:
  - The raw feedback text.
  - A list of organisation name candidates extracted by a Named Entity \
    Recogniser (may be empty or noisy).
  - An email domain extracted from the text, if one was found.

Rules:
1. The submitter's org is usually signalled by possessive language: \
   "we at [Org]", "our team at [Org]", "I'm from [Org]", \
   "[Org] has been a customer", "our [Org] account".
2. An email domain is strong evidence — prefer it when it clearly names a \
   company (ignore gmail, yahoo, outlook, hotmail, icloud, and other \
   consumer domains).
3. Do NOT return the name of the product or service being reviewed.
4. Do NOT return a competitor's name that the customer is merely comparing to.
5. If no submitter org can be identified with reasonable confidence, set \
   "account_name" to null and "confidence" to 0.0.

Confidence rubric:
  0.9–1.0  Multiple corroborating signals (e.g. explicit mention + email domain).
  0.7–0.89 Single strong signal (clear "we at X" or unambiguous email domain).
  0.5–0.69 Weak signal (NER-only, no ownership phrasing, ambiguous context).
  0.0      Cannot determine submitter org.

Return ONLY valid JSON — no markdown fences, no explanation:
{
  "account_name": "<string or null>",
  "confidence": <float 0.0–1.0>,
  "evidence": "<the exact text span(s) that support your answer, or empty string>"
}\
"""

_USER_PROMPT_TEMPLATE = """\
<feedback_text>
{text}
</feedback_text>

<ner_candidates>
{candidates}
</ner_candidates>

<email_domain>
{email_domain}
</email_domain>\
"""

# Consumer email providers that should not be treated as org signals
_CONSUMER_DOMAINS = frozenset({
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com",
    "live.com", "me.com", "aol.com", "protonmail.com", "pm.me",
    "googlemail.com", "msn.com", "ymail.com",
})

_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Account Extractor
# ---------------------------------------------------------------------------


class AccountExtractor:
    """
    Extracts the submitter's company/account name from raw customer feedback.

    Uses a three-layer approach:
      1. Email domain scan — cheap, high-precision when a work email is present.
      2. spaCy NER — identifies all ORG entities without an LLM call.
      3. Claude Haiku LLM call — disambiguates candidates and identifies the
         submitter's organisation from context.

    The LLM call is always made when step 1 or 2 surfaces any candidate, so
    that the model can apply ownership-signal reasoning.  When neither step
    surfaces anything, the LLM is skipped (returns `account_name=None`).

    Args:
        client:       An `anthropic.Anthropic` client (created from env if None).
        model:        Claude model for the disambiguation step.
                      Defaults to Haiku — the output is well-defined JSON with
                      no free-form judgment beyond candidate selection.
        max_tokens:   Maximum tokens for each LLM response.
        temperature:  Sampling temperature (0 = deterministic).
        spacy_model:  spaCy model name. Must be installed before use.
    """

    def __init__(
        self,
        client:      Optional[anthropic.Anthropic] = None,
        model:       str   = "claude-haiku-4-5-20251001",
        max_tokens:  int   = 256,
        temperature: float = 0.0,
        spacy_model: str   = "en_core_web_trf",
    ) -> None:
        self._client      = client or anthropic.Anthropic()
        self._model       = model
        self._max_tokens  = max_tokens
        self._temperature = temperature
        self._nlp         = self._load_spacy(spacy_model)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, feedback: str | dict, feedback_id: Optional[str] = None) -> AccountExtractionResult:
        """
        Extract the submitter's account/company name from a piece of feedback.

        Args:
            feedback:    Either a raw text string or a CFO dict (must have
                         `raw_text` or `clean_text`).
            feedback_id: Optional identifier for the feedback item.  A UUID is
                         generated if not provided.

        Returns:
            AccountExtractionResult with the identified account name (or None)
            and supporting evidence.
        """
        text, fid = self._resolve_input(feedback, feedback_id)

        if not text.strip():
            return self._empty_result(fid)

        email_domain = self._extract_email_domain(text)
        ner_candidates = self._ner_scan(text)

        # Skip LLM entirely when there is nothing to disambiguate
        if not email_domain and not ner_candidates:
            logger.debug("feedback %s: no candidates found; skipping LLM.", fid[:8])
            return AccountExtractionResult(
                feedback_id       = fid,
                account_name      = None,
                confidence        = 0.0,
                evidence          = "",
                extraction_method = "none",
                raw_candidates    = [],
                email_domain      = None,
            )

        return self._llm_disambiguate(fid, text, ner_candidates, email_domain)

    def extract_batch(
        self,
        feedbacks: list[str | dict],
        *,
        verbose: bool = False,
    ) -> list[AccountExtractionResult]:
        """
        Extract account names for a list of feedback items.

        LLM calls are independent; replace the loop with asyncio /
        ThreadPoolExecutor for high-throughput production use.

        Args:
            feedbacks: List of raw text strings or CFO dicts.
            verbose:   If True, log a one-line summary per item.

        Returns:
            List of AccountExtractionResult objects (same order as input).
        """
        results: list[AccountExtractionResult] = []
        for i, feedback in enumerate(feedbacks):
            result = self.extract(feedback)
            results.append(result)
            if verbose:
                logger.info(
                    "Item %d/%d [%s]: account=%r  confidence=%.2f  method=%s",
                    i + 1, len(feedbacks), result.feedback_id[:8],
                    result.account_name, result.confidence, result.extraction_method,
                )
        return results

    # ------------------------------------------------------------------
    # Signal extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_email_domain(text: str) -> Optional[str]:
        """
        Return the first non-consumer email domain found in the text, or None.
        Consumer domains (gmail, yahoo, etc.) are filtered out — they carry no
        account signal.
        """
        for m in _EMAIL_PATTERN.finditer(text):
            domain = m.group(1).lower()
            if domain not in _CONSUMER_DOMAINS:
                return domain
        return None

    def _ner_scan(self, text: str) -> list[str]:
        """
        Run spaCy NER and return unique ORG entity strings.
        Short fragments (≤ 2 chars) are filtered out as noise.
        """
        doc = self._nlp(text)
        seen: set[str] = set()
        orgs: list[str] = []
        for ent in doc.ents:
            if ent.label_ == "ORG" and len(ent.text.strip()) > 2:
                normalised = ent.text.strip()
                if normalised not in seen:
                    seen.add(normalised)
                    orgs.append(normalised)
        return orgs

    # ------------------------------------------------------------------
    # LLM disambiguation
    # ------------------------------------------------------------------

    def _llm_disambiguate(
        self,
        fid:           str,
        text:          str,
        ner_candidates: list[str],
        email_domain:  Optional[str],
    ) -> AccountExtractionResult:
        """Call Claude Haiku to pick the submitter's org from the candidates."""
        user_prompt = _USER_PROMPT_TEMPLATE.format(
            text         = text,
            candidates   = ", ".join(ner_candidates) if ner_candidates else "(none detected)",
            email_domain = email_domain or "(none detected)",
        )

        try:
            response = self._client.messages.create(
                model       = self._model,
                max_tokens  = self._max_tokens,
                temperature = self._temperature,
                system      = _SYSTEM_PROMPT,
                messages    = [{"role": "user", "content": user_prompt}],
            )
            raw = response.content[0].text.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM call failed for feedback %s: %s", fid[:8], exc)
            return self._empty_result(fid)

        return self._parse_llm_response(fid, raw, ner_candidates, email_domain)

    @staticmethod
    def _parse_llm_response(
        fid:            str,
        raw:            str,
        ner_candidates: list[str],
        email_domain:   Optional[str],
    ) -> AccountExtractionResult:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("AccountExtractor: JSON parse failed for %s: %s", fid[:8], exc)
            return AccountExtractionResult(
                feedback_id       = fid,
                account_name      = None,
                confidence        = 0.0,
                evidence          = "",
                extraction_method = "none",
                raw_candidates    = ner_candidates,
                email_domain      = email_domain,
            )

        account_name = data.get("account_name") or None
        confidence   = float(data.get("confidence", 0.0))
        evidence     = data.get("evidence", "")

        # Determine the method so callers know how to weight the result
        if account_name and email_domain and account_name.lower() in email_domain.lower():
            method = "email_domain"
        elif account_name:
            method = "llm"
        else:
            method = "none"

        return AccountExtractionResult(
            feedback_id       = fid,
            account_name      = account_name,
            confidence        = confidence,
            evidence          = evidence,
            extraction_method = method,
            raw_candidates    = ner_candidates,
            email_domain      = email_domain,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_input(
        feedback: str | dict,
        feedback_id: Optional[str],
    ) -> tuple[str, str]:
        """Normalise the input to (text, id)."""
        if isinstance(feedback, dict):
            text = feedback.get("clean_text") or feedback.get("raw_text", "")
            fid  = feedback_id or feedback.get("id") or str(uuid.uuid4())
        else:
            text = feedback
            fid  = feedback_id or str(uuid.uuid4())
        return text, fid

    @staticmethod
    def _empty_result(fid: str) -> AccountExtractionResult:
        return AccountExtractionResult(
            feedback_id       = fid,
            account_name      = None,
            confidence        = 0.0,
            evidence          = "",
            extraction_method = "none",
        )

    @staticmethod
    def _load_spacy(model_name: str):
        logger.info("Loading spaCy model '%s'…", model_name)
        try:
            return spacy.load(model_name, disable=["parser", "lemmatizer"])
        except OSError:
            logger.warning(
                "spaCy model '%s' not found. Falling back to 'en_core_web_sm'. "
                "Run: python -m spacy download %s",
                model_name, model_name,
            )
            return spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])


# ---------------------------------------------------------------------------
# Smoke-test (requires ANTHROPIC_API_KEY)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    samples = [
        # Explicit org mention
        {
            "id":       str(uuid.uuid4()),
            "raw_text": (
                "Hi, I'm reaching out on behalf of Meridian Health Systems. We've "
                "been using your platform for about six months now and the reporting "
                "module keeps timing out on large exports. Our data team is blocked."
            ),
        },

        # Email domain as primary signal
        {
            "id":       str(uuid.uuid4()),
            "raw_text": (
                "The onboarding flow is really confusing — half my team gave up. "
                "Please fix the invite emails. — sarah.k@luminarylogistics.com"
            ),
        },

        # Competitor mention should NOT be returned
        {
            "id":       str(uuid.uuid4()),
            "raw_text": (
                "We moved to your product after years of frustration with Salesforce. "
                "So far Nova Dynamics loves it, but the API rate limits are too low."
            ),
        },

        # Consumer email — should not count as org signal
        {
            "id":       str(uuid.uuid4()),
            "raw_text": (
                "Love the new design update! The dark mode is perfect. "
                "Keep it up — tom.baker@gmail.com"
            ),
        },

        # Multiple org mentions, possessive phrasing identifies submitter
        {
            "id":       str(uuid.uuid4()),
            "raw_text": (
                "Our team at Crestline Partners has integrated your API with Stripe "
                "and HubSpot. The Stripe webhook delays are a problem for us."
            ),
        },

        # No org signal at all
        {
            "id":       str(uuid.uuid4()),
            "raw_text": "The checkout page is slow. Please fix it.",
        },
    ]

    extractor = AccountExtractor(spacy_model="en_core_web_sm")  # sm for local dev
    results   = extractor.extract_batch(samples, verbose=True)

    print(f"\n{'='*70}")
    for sample, r in zip(samples, results):
        text_preview = (sample.get("raw_text") or "")[:72]
        print(f"\n  feedback : {text_preview!r}…")
        print(f"  account  : {r.account_name!r}")
        print(f"  confidence: {r.confidence:.2f}  method: {r.extraction_method}")
        if r.evidence:
            print(f"  evidence : {r.evidence!r}")
        if r.email_domain:
            print(f"  email dom: {r.email_domain}")
        if r.raw_candidates:
            print(f"  ner found: {r.raw_candidates}")
