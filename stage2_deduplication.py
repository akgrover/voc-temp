"""
Stage 2.2: Deduplication & Near-Duplicate Detection
=====================================================
Detects and suppresses near-duplicate feedback units before they reach the
extraction agents.  Only canonical (non-duplicate) units are indexed in the
vector store; duplicates are tracked via a counter on the canonical entry so
that high-frequency issues retain their weight in downstream impact scoring.

Critical ordering contract — must not be violated:
    1. Compute embedding from unit text.
    2. QUERY the index for near-duplicates  ← before any insert.
    3a. Duplicate found  → mark, increment canonical counter, do NOT index.
    3b. No duplicate     → insert as new canonical entry.

Querying before inserting prevents a unit from matching itself and ensures
intra-batch duplicates are also caught when processing in sequence.

Dependencies:
    pip install sentence-transformers numpy
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

from stage2_unitization import FeedbackUnit

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DUPLICATE_THRESHOLD = 0.95  # Cosine similarity above which two units are near-duplicates

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class DeduplicationResult:
    """
    Outcome of the deduplication check for a single FeedbackUnit.

    Attributes:
        unit_id:      ID of the FeedbackUnit that was evaluated.
        is_duplicate: True when this unit is a near-duplicate of an existing entry.
        canonical_id: ID of the canonical entry this duplicates (None if not duplicate).
        similarity:   Highest cosine similarity found against the index (0.0 if empty).
        was_indexed:  True only when this unit was written to the vector store as a
                      new canonical entry.
    """

    unit_id:      str
    is_duplicate: bool
    canonical_id: Optional[str]
    similarity:   float
    was_indexed:  bool


# ---------------------------------------------------------------------------
# Vector Store Abstraction
# ---------------------------------------------------------------------------


class VectorStoreInterface(ABC):
    """
    Abstract interface for vector store backends.

    The deduplication store and the theme store each maintain their own
    independent instance — they index different data for different purposes
    and must never share an instance.

    Concrete implementations: InMemoryVectorStore (dev / test), pgvector,
    Pinecone, or FAISS for production.
    """

    @abstractmethod
    def query(self, embedding: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]:
        """Return [(entry_id, cosine_similarity), ...] for the top_k nearest neighbours."""

    @abstractmethod
    def insert(self, entry_id: str, embedding: np.ndarray) -> None:
        """Persist a new embedding under entry_id."""

    @abstractmethod
    def increment_duplicate_count(self, entry_id: str) -> None:
        """Increment the duplicate counter for a canonical entry."""

    @abstractmethod
    def get_duplicate_count(self, entry_id: str) -> int:
        """Return how many near-duplicates have been suppressed for this entry."""


class InMemoryVectorStore(VectorStoreInterface):
    """
    In-memory vector store backed by a dense NumPy matrix.

    Suitable for local development and unit tests.
    Replace with pgvector (small/medium scale) or Pinecone (large scale)
    in production.

    Embeddings are L2-normalised on insertion so that cosine similarity
    reduces to a dot product at query time, avoiding the per-query division.
    """

    def __init__(self) -> None:
        self._ids:        list[str]            = []
        self._vecs:       list[np.ndarray]     = []   # L2-normalised
        self._dup_counts: dict[str, int]       = {}

    # ------------------------------------------------------------------
    # VectorStoreInterface implementation
    # ------------------------------------------------------------------

    def query(self, embedding: np.ndarray, top_k: int = 5) -> list[tuple[str, float]]:
        if not self._ids:
            return []

        q_norm = self._l2_norm(embedding)
        matrix = np.stack(self._vecs)          # (N, dim)
        sims   = matrix @ q_norm               # (N,) — cosine similarities

        k       = min(top_k, len(self._ids))
        top_idx = np.argpartition(sims, -k)[-k:]
        top_idx = top_idx[np.argsort(sims[top_idx])[::-1]]

        return [(self._ids[i], float(sims[i])) for i in top_idx]

    def insert(self, entry_id: str, embedding: np.ndarray) -> None:
        self._ids.append(entry_id)
        self._vecs.append(self._l2_norm(embedding))
        self._dup_counts[entry_id] = 0

    def increment_duplicate_count(self, entry_id: str) -> None:
        if entry_id in self._dup_counts:
            self._dup_counts[entry_id] += 1

    def get_duplicate_count(self, entry_id: str) -> int:
        return self._dup_counts.get(entry_id, 0)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _l2_norm(v: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v


# ---------------------------------------------------------------------------
# Deduplication Agent
# ---------------------------------------------------------------------------


class DeduplicationAgent:
    """
    Stage 2.2: Deduplication & Near-Duplicate Detection.

    Enforces the query-before-insert contract so that:
      - A unit can never match itself.
      - Intra-batch duplicates are caught when units are processed sequentially.

    Only canonical (non-duplicate) units are written to the vector store.
    Duplicate units are tracked by incrementing the canonical entry's counter
    and are excluded from theme discovery.  Their volume is preserved in the
    duplicate_count so that high-frequency issues retain their weight in the
    impact score formula in Stage 5.

    Args:
        vector_store: A VectorStoreInterface instance (shared across calls for
                      persistence across batches).
        model_name:   Sentence-transformer model for computing embeddings.
        threshold:    Cosine similarity above which two units are near-duplicates.
    """

    def __init__(
        self,
        vector_store: VectorStoreInterface,
        model_name:   str   = "all-MiniLM-L6-v2",
        threshold:    float = DUPLICATE_THRESHOLD,
    ) -> None:
        self._store     = vector_store
        self._encoder   = SentenceTransformer(model_name)
        self._threshold = threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, unit: FeedbackUnit) -> DeduplicationResult:
        """
        Run deduplication for a single FeedbackUnit.

        Ordering (must not be changed):
          1. Compute embedding.
          2. QUERY the index  ← before any insert.
          3a. Duplicate found  → mark, increment canonical count, do NOT index.
          3b. No duplicate     → insert as new canonical entry.
        """
        embedding = self._encode(unit.text)

        # Step 2: query BEFORE insert
        neighbours = self._store.query(embedding, top_k=5)

        # Step 3: check threshold
        for canonical_id, similarity in neighbours:
            if similarity >= self._threshold:
                self._store.increment_duplicate_count(canonical_id)
                logger.debug(
                    "Unit %s is a near-duplicate of %s (sim=%.3f).",
                    unit.unit_id, canonical_id, similarity,
                )
                return DeduplicationResult(
                    unit_id      = unit.unit_id,
                    is_duplicate = True,
                    canonical_id = canonical_id,
                    similarity   = similarity,
                    was_indexed  = False,
                )

        # Step 3b: no duplicate — index as new canonical entry
        self._store.insert(unit.unit_id, embedding)
        top_sim = neighbours[0][1] if neighbours else 0.0
        logger.debug("Unit %s indexed as canonical (nearest_sim=%.3f).", unit.unit_id, top_sim)

        return DeduplicationResult(
            unit_id      = unit.unit_id,
            is_duplicate = False,
            canonical_id = None,
            similarity   = top_sim,
            was_indexed  = True,
        )

    def process_batch(
        self,
        units:   list[FeedbackUnit],
        *,
        verbose: bool = False,
    ) -> list[DeduplicationResult]:
        """
        Process units sequentially so that intra-batch duplicates are caught.

        Each unit is checked — and potentially indexed — before the next is
        evaluated.  Do not parallelise this loop; the ordering guarantee is
        load-bearing.
        """
        results: list[DeduplicationResult] = []
        for i, unit in enumerate(units):
            result = self.process(unit)
            results.append(result)
            if verbose:
                status = "DUPLICATE" if result.is_duplicate else "canonical"
                logger.info(
                    "Unit %d/%d [%s]: %s (sim=%.3f)",
                    i + 1, len(units), unit.unit_id[:8], status, result.similarity,
                )
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _encode(self, text: str) -> np.ndarray:
        return self._encoder.encode(text, normalize_embeddings=False)


# ---------------------------------------------------------------------------
# Pipeline Integration Helper
# ---------------------------------------------------------------------------


def deduplicate_units(
    units:        list[FeedbackUnit],
    agent:        Optional[DeduplicationAgent]   = None,
    vector_store: Optional[VectorStoreInterface] = None,
    *,
    verbose:      bool = False,
) -> tuple[list[FeedbackUnit], list[DeduplicationResult]]:
    """
    Deduplicate a list of FeedbackUnits and return only the canonical ones.

    Args:
        units:        FeedbackUnit objects produced by Stage 2.1.
        agent:        A shared DeduplicationAgent (created if not provided).
        vector_store: A VectorStoreInterface instance.  If both agent and
                      vector_store are None, a fresh InMemoryVectorStore is used
                      (suitable for single-batch runs only).
        verbose:      Log a status line for each unit.

    Returns:
        (canonical_units, all_results)
        canonical_units — units safe to pass to Stage 3 extraction agents.
        all_results     — DeduplicationResult for every input unit (for audit).
    """
    if agent is None:
        store = vector_store or InMemoryVectorStore()
        agent = DeduplicationAgent(vector_store=store)

    all_results = agent.process_batch(units, verbose=verbose)
    canonical   = [u for u, r in zip(units, all_results) if not r.is_duplicate]

    logger.info(
        "Deduplication: %d in → %d canonical, %d duplicates suppressed.",
        len(units), len(canonical), len(units) - len(canonical),
    )
    return canonical, all_results


# ---------------------------------------------------------------------------
# Smoke-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    def _make_unit(text: str) -> FeedbackUnit:
        return FeedbackUnit(
            unit_id       = str(uuid.uuid4()),
            parent_cfo_id = "test-cfo",
            text          = text,
            char_start    = 0,
            char_end      = len(text),
            unit_index    = 0,
        )

    samples = [
        # Cluster 1 — checkout crash (3 near-duplicates)
        "The checkout keeps crashing on my iPhone.",
        "Checkout crashes every time I try to pay on iOS.",
        "I can't complete a purchase — the app crashes at checkout.",
        # Cluster 2 — support latency (2 near-duplicates)
        "Your support team took 5 days to reply to my ticket.",
        "Support response time is way too slow — 5 day wait.",
        # Unique
        "The new dashboard design looks great.",
    ]

    store  = InMemoryVectorStore()
    agent  = DeduplicationAgent(vector_store=store)
    units  = [_make_unit(t) for t in samples]

    canonical, results = deduplicate_units(units, agent=agent, verbose=True)

    print(f"\n{'='*65}")
    print(f"Input units  : {len(units)}")
    print(f"Canonical    : {len(canonical)}")
    print(f"{'='*65}")
    for r in results:
        tag = "DUP  " if r.is_duplicate else "CANON"
        ref = f"→ canonical={r.canonical_id[:8]}…" if r.is_duplicate else ""
        print(f"  [{tag}]  unit={r.unit_id[:8]}…  sim={r.similarity:.3f}  {ref}")

    print(f"\n{'='*65}")
    print("Duplicate counts on canonical entries:")
    for r in results:
        if not r.is_duplicate:
            count = store.get_duplicate_count(r.unit_id)
            print(f"  {r.unit_id[:8]}…  duplicates suppressed: {count}")
