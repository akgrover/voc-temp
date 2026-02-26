"""
Stage 1.3: PII Redaction
========================
Strips personally identifiable information from customer feedback before
it enters the extraction pipeline. Combines regex patterns for structured
PII with spaCy NER for unstructured PII (names, organizations, etc.).

Dependencies:
    pip install spacy anthropic
    python -m spacy download en_core_web_trf
"""

from __future__ import annotations

import re
import uuid
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

import spacy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class PIIType(str, Enum):
    PERSON_NAME   = "PERSON_NAME"
    EMAIL         = "EMAIL"
    PHONE         = "PHONE"
    ADDRESS       = "ADDRESS"
    ACCOUNT_NUM   = "ACCOUNT_NUM"
    CREDIT_CARD   = "CREDIT_CARD"
    SSN           = "SSN"
    IP_ADDRESS    = "IP_ADDRESS"
    URL           = "URL"
    DATE_OF_BIRTH = "DATE_OF_BIRTH"
    ORG_NAME      = "ORG_NAME"


@dataclass
class PIISpan:
    """A detected PII span with its position in the original text."""
    pii_type:    PIIType
    start:       int          # character offset in original text
    end:         int          # character offset in original text
    original:    str          # the actual PII value (for audit logging only)
    placeholder: str          # replacement token, e.g. "[EMAIL]"
    source:      str          # "regex" | "ner"


@dataclass
class RedactionResult:
    original_text:  str
    redacted_text:  str
    pii_spans:      list[PIISpan] = field(default_factory=list)
    pii_detected:   bool = False
    redaction_id:   str  = field(default_factory=lambda: str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Regex Patterns for Structured PII
# ---------------------------------------------------------------------------

_REGEX_PATTERNS: list[tuple[PIIType, re.Pattern]] = [
    # Email — must come before URL to avoid partial matches
    (
        PIIType.EMAIL,
        re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
            re.IGNORECASE,
        ),
    ),
    # US / international phone numbers
    (
        PIIType.PHONE,
        re.compile(
            r"(?:\+?1[\s\-.]?)?"
            r"(?:\(?\d{3}\)?[\s\-.]?)"
            r"\d{3}[\s\-.]?\d{4}"
        ),
    ),
    # Credit card numbers (Luhn-check is skipped for speed; regex is sufficient as a first pass)
    (
        PIIType.CREDIT_CARD,
        re.compile(
            r"\b(?:4[0-9]{12}(?:[0-9]{3})?"          # Visa
            r"|5[1-5][0-9]{14}"                        # MC
            r"|3[47][0-9]{13}"                         # Amex
            r"|6(?:011|5[0-9]{2})[0-9]{12}"            # Discover
            r"|(?:[0-9]{4}[\s\-]?){3}[0-9]{4})\b"     # Generic 16-digit
        ),
    ),
    # SSN
    (
        PIIType.SSN,
        re.compile(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b"),
    ),
    # IPv4
    (
        PIIType.IP_ADDRESS,
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
    ),
    # URLs (http/https/www)
    (
        PIIType.URL,
        re.compile(
            r"https?://[^\s<>\"]+|www\.[^\s<>\"]+",
            re.IGNORECASE,
        ),
    ),
    # Account / order numbers  (heuristic: 6-20 alphanumeric chars following keywords)
    (
        PIIType.ACCOUNT_NUM,
        re.compile(
            r"(?:account|order|ticket|ref|reference|id|#|no\.?)\s*[:\-]?\s*"
            r"([A-Za-z0-9\-]{6,20})",
            re.IGNORECASE,
        ),
    ),
]

# spaCy label → PIIType mapping
_SPACY_LABEL_MAP: dict[str, PIIType] = {
    "PERSON":  PIIType.PERSON_NAME,
    "ORG":     PIIType.ORG_NAME,
    "GPE":     PIIType.ADDRESS,   # Geopolitical entity (city, country)
    "LOC":     PIIType.ADDRESS,
    "FAC":     PIIType.ADDRESS,   # Facility (building, airport)
}


# ---------------------------------------------------------------------------
# PIIRedactor
# ---------------------------------------------------------------------------

class PIIRedactor:
    """
    Detects and replaces PII in text using a two-layer approach:
      1. Regex patterns for structured PII (email, phone, credit card, etc.)
      2. spaCy NER for unstructured PII (names, organizations, locations)

    Spans are merged and sorted before replacement to avoid offset corruption.
    """

    def __init__(self, spacy_model: str = "en_core_web_trf") -> None:
        logger.info("Loading spaCy model '%s'…", spacy_model)
        try:
            self._nlp = spacy.load(spacy_model, disable=["parser", "lemmatizer"])
        except OSError:
            logger.warning(
                "spaCy model '%s' not found. Falling back to 'en_core_web_sm'. "
                "Run: python -m spacy download %s",
                spacy_model, spacy_model,
            )
            self._nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer"])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def redact(self, text: str) -> RedactionResult:
        """
        Redact PII from *text* and return a RedactionResult containing:
          - the redacted text with typed placeholders
          - a list of all detected PIISpan objects (for audit logging)
        """
        if not text or not text.strip():
            return RedactionResult(original_text=text, redacted_text=text)

        spans: list[PIISpan] = []
        spans.extend(self._regex_scan(text))
        spans.extend(self._ner_scan(text))

        merged  = self._merge_spans(spans)
        redacted = self._apply_redactions(text, merged)

        return RedactionResult(
            original_text = text,
            redacted_text = redacted,
            pii_spans     = merged,
            pii_detected  = bool(merged),
        )

    # ------------------------------------------------------------------
    # Layer 1: Regex Scan
    # ------------------------------------------------------------------

    def _regex_scan(self, text: str) -> list[PIISpan]:
        found: list[PIISpan] = []

        for pii_type, pattern in _REGEX_PATTERNS:
            for m in pattern.finditer(text):
                # For ACCOUNT_NUM the PII is in group 1 (after the keyword)
                if pii_type == PIIType.ACCOUNT_NUM and m.lastindex:
                    start, end = m.start(1), m.end(1)
                else:
                    start, end = m.start(), m.end()

                found.append(
                    PIISpan(
                        pii_type    = pii_type,
                        start       = start,
                        end         = end,
                        original    = text[start:end],
                        placeholder = f"[{pii_type.value}]",
                        source      = "regex",
                    )
                )

        return found

    # ------------------------------------------------------------------
    # Layer 2: NER Scan (spaCy)
    # ------------------------------------------------------------------

    def _ner_scan(self, text: str) -> list[PIISpan]:
        found: list[PIISpan] = []
        doc = self._nlp(text)

        for ent in doc.ents:
            pii_type = _SPACY_LABEL_MAP.get(ent.label_)
            if pii_type is None:
                continue

            found.append(
                PIISpan(
                    pii_type    = pii_type,
                    start       = ent.start_char,
                    end         = ent.end_char,
                    original    = ent.text,
                    placeholder = f"[{pii_type.value}]",
                    source      = "ner",
                )
            )

        return found

    # ------------------------------------------------------------------
    # Span Merging & Application
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_spans(spans: list[PIISpan]) -> list[PIISpan]:
        """
        Sort spans by start offset and merge overlapping ones.
        When two spans overlap, the regex span wins (more precise) over the NER span.
        """
        if not spans:
            return []

        # Prefer regex over NER for overlapping spans
        sorted_spans = sorted(spans, key=lambda s: (s.start, s.source != "regex"))
        merged: list[PIISpan] = []

        for span in sorted_spans:
            if merged and span.start < merged[-1].end:
                # Overlapping — extend the last span if needed
                prev = merged[-1]
                if span.end > prev.end:
                    merged[-1] = PIISpan(
                        pii_type    = prev.pii_type,
                        start       = prev.start,
                        end         = span.end,
                        original    = prev.original,
                        placeholder = prev.placeholder,
                        source      = prev.source,
                    )
            else:
                merged.append(span)

        return merged

    @staticmethod
    def _apply_redactions(text: str, spans: list[PIISpan]) -> str:
        """Replace detected spans with placeholders, working right-to-left
        to preserve character offsets."""
        result = text
        for span in reversed(spans):
            result = result[: span.start] + span.placeholder + result[span.end :]
        return result


# ---------------------------------------------------------------------------
# Pipeline Integration Helper
# ---------------------------------------------------------------------------

def redact_cfo(cfo: dict, redactor: Optional[PIIRedactor] = None) -> dict:
    """
    Convenience wrapper that operates on a Canonical Feedback Object (dict).
    Redacts `raw_text`, writes the result to `clean_text`, and sets `pii_redacted`.

    Args:
        cfo:      A CFO dict with at least a `raw_text` key.
        redactor: A shared PIIRedactor instance (created if not provided).

    Returns:
        The mutated CFO dict.
    """
    if redactor is None:
        redactor = PIIRedactor()

    result = redactor.redact(cfo.get("raw_text", ""))
    cfo["clean_text"]   = result.redacted_text
    cfo["pii_redacted"] = result.pii_detected

    # Attach audit metadata (not stored in prod CFO but useful for debugging)
    cfo["_pii_audit"] = {
        "redaction_id": result.redaction_id,
        "pii_type_counts": _count_by_type(result.pii_spans),
    }

    return cfo


def _count_by_type(spans: list[PIISpan]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for span in spans:
        counts[span.pii_type.value] = counts.get(span.pii_type.value, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Quick smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    sample_texts = [
        "Hi, my name is John Smith and my email is john.smith@example.com. "
        "Please call me at (555) 867-5309 or check order #ORD-291847.",

        "I paid with card 4111 1111 1111 1111 and it was charged twice. "
        "My account ID is ACC-0042XZ. SSN: 123-45-6789.",

        "Visit https://evil.example.com/track?user=abc123 for the refund form.",

        "The app keeps crashing — so frustrating! No PII in this one.",
    ]

    redactor = PIIRedactor(spacy_model="en_core_web_sm")  # use sm for local dev

    for i, text in enumerate(sample_texts, 1):
        result = redactor.redact(text)
        print(f"\n{'='*60}")
        print(f"Sample {i}")
        print(f"Original : {result.original_text}")
        print(f"Redacted : {result.redacted_text}")
        print(f"PII found: {[f'{s.pii_type.value}({s.source})' for s in result.pii_spans]}")
