"""
PostgreSQL Persistence Layer
============================
Stores topics, feedback units, and per-unit sentiment analysis produced by
the VoC pipeline.

Schema overview:
  topics          One row per discovered topic.  Persists the intent cache
                  (intent_type, intent_urgency), the running feedback_count,
                  and all surface-form aliases collected during matching.

  feedback_units  One row per FeedbackUnit — both canonical and duplicate.
                  Canonical units carry their theme assignment and unit-level
                  intent fields (specific_request, competitor_mention,
                  churn_indicators).  Duplicate units carry only a pointer to
                  their canonical entry.

  unit_sentiments One row per canonical FeedbackUnit.  Stores the full
                  sentiment analysis (polarity, intensity, emotions, aspects,
                  sarcasm flag).

Design decisions:

  feedback_count is maintained as a running total on the topics table using
  incremental upserts (ON CONFLICT … feedback_count + delta) rather than a
  derived COUNT(*).  This keeps read queries fast without a GROUP BY join.

  All inserts use ON CONFLICT DO NOTHING so Kafka at-least-once redelivery
  (and pipeline restarts) never produce duplicate rows.

  Topic upserts merge aliases (ARRAY dedup via UNNEST) and use COALESCE for
  intent fields so an established intent is never overwritten by a NULL.

  The entire batch is written in a single transaction.  If anything fails,
  the transaction rolls back and the Kafka offsets remain uncommitted, so the
  batch will be reprocessed on restart.

Typical usage:

    store = PostgresStore.from_url("postgresql://user:pass@host:5432/voc")
    store.apply_schema()          # run once at startup

    pipeline, consumer = build_pipeline(config)

    def on_batch(batch: BatchAnalysis) -> None:
        store.save_batch(batch, pipeline.topic_store)

    consumer = KafkaFeedbackConsumer(config, pipeline, on_batch_complete=on_batch)
    consumer.run()

Dependencies:
    pip install psycopg2-binary
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator, Optional

import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_values, Json
from psycopg2.pool import ThreadedConnectionPool

from pipeline import BatchAnalysis, UnitAnalysis
from stage3_sentiment_extraction import AspectSentiment, EmotionTag
from stage3_intent_extraction import ChurnIndicator
from stage3_topic_extraction import Topic, TopicStoreInterface

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    topic_id        UUID        PRIMARY KEY,
    label           TEXT        NOT NULL,
    description     TEXT        NOT NULL    DEFAULT '',
    aliases         TEXT[]      NOT NULL    DEFAULT '{}',
    feedback_count  INTEGER     NOT NULL    DEFAULT 0,
    intent_type     TEXT,
    intent_urgency  TEXT,
    created_at      TIMESTAMPTZ NOT NULL    DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL    DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback_units (
    unit_id             UUID        PRIMARY KEY,
    parent_cfo_id       TEXT        NOT NULL,
    text                TEXT        NOT NULL,
    char_start          INTEGER     NOT NULL,
    char_end            INTEGER     NOT NULL,
    unit_index          INTEGER     NOT NULL    DEFAULT 0,
    metadata            JSONB       NOT NULL    DEFAULT '{}',

    -- Deduplication
    is_duplicate        BOOLEAN     NOT NULL    DEFAULT FALSE,
    canonical_id        UUID        REFERENCES  feedback_units(unit_id),

    -- Topic assignment (NULL for duplicate units)
    topic_id            UUID        REFERENCES  topics(topic_id),
    topic_label         TEXT,
    topic_confidence    FLOAT,
    topic_is_new        BOOLEAN,
    raw_extracted_label TEXT,
    evidence_spans      TEXT[]      NOT NULL    DEFAULT '{}',

    -- Unit-level intent fields (topic-level intent lives on the topics table)
    specific_request    TEXT,
    competitor_mention  TEXT,
    churn_indicators    JSONB       NOT NULL    DEFAULT '[]',

    created_at          TIMESTAMPTZ NOT NULL    DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS unit_sentiments (
    unit_id             UUID    PRIMARY KEY  REFERENCES feedback_units(unit_id),
    polarity            FLOAT   NOT NULL,
    intensity           TEXT    NOT NULL,
    emotions            JSONB   NOT NULL    DEFAULT '[]',
    aspect_sentiments   JSONB   NOT NULL    DEFAULT '[]',
    sarcasm_flag        BOOLEAN NOT NULL    DEFAULT FALSE,
    confidence          FLOAT   NOT NULL    DEFAULT 0.0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for the most common query patterns
CREATE INDEX IF NOT EXISTS idx_fu_topic_id
    ON feedback_units(topic_id) WHERE NOT is_duplicate;

CREATE INDEX IF NOT EXISTS idx_fu_parent_cfo
    ON feedback_units(parent_cfo_id);

CREATE INDEX IF NOT EXISTS idx_us_polarity
    ON unit_sentiments(polarity);
"""

# ---------------------------------------------------------------------------
# Row helpers  (dataclass → plain tuple for psycopg2)
# ---------------------------------------------------------------------------


@dataclass
class _TopicRow:
    topic_id:       str
    label:          str
    description:    str
    aliases:        list[str]
    delta:          int         # new canonical units for this topic in this batch
    intent_type:    Optional[str]
    intent_urgency: Optional[str]


@dataclass
class _UnitRow:
    unit_id:             str
    parent_cfo_id:       str
    text:                str
    char_start:          int
    char_end:            int
    unit_index:          int
    metadata:            dict
    is_duplicate:        bool
    canonical_id:        Optional[str]
    topic_id:            Optional[str]
    topic_label:         Optional[str]
    topic_confidence:    Optional[float]
    topic_is_new:        Optional[bool]
    raw_extracted_label: Optional[str]
    evidence_spans:      list[str]
    specific_request:    Optional[str]
    competitor_mention:  Optional[str]
    churn_indicators:    list


@dataclass
class _SentimentRow:
    unit_id:           str
    polarity:          float
    intensity:         str
    emotions:          list
    aspect_sentiments: list
    sarcasm_flag:      bool
    confidence:        float


# ---------------------------------------------------------------------------
# PostgresStore
# ---------------------------------------------------------------------------


class PostgresStore:
    """
    Thread-safe PostgreSQL store backed by a psycopg2 ThreadedConnectionPool.

    All public methods acquire a connection from the pool, perform their work
    inside a single transaction, and return the connection to the pool on exit.
    The pool is safe to share across the pipeline's ThreadPoolExecutor threads.

    Args:
        pool: A configured ThreadedConnectionPool instance.
    """

    def __init__(self, pool: ThreadedConnectionPool) -> None:
        self._pool = pool

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_url(
        cls,
        dsn:      str,
        min_conn: int = 2,
        max_conn: int = 10,
    ) -> PostgresStore:
        """
        Create a PostgresStore from a libpq connection string.

        Args:
            dsn:      e.g. "postgresql://user:pass@host:5432/voc"
            min_conn: Minimum connections kept open in the pool.
            max_conn: Maximum connections the pool will open.
        """
        pool = ThreadedConnectionPool(min_conn, max_conn, dsn=dsn)
        logger.info("PostgresStore: connected (pool min=%d max=%d).", min_conn, max_conn)
        return cls(pool)

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    def apply_schema(self) -> None:
        """
        Create tables and indexes if they do not already exist.
        Safe to call on every startup — all DDL statements use IF NOT EXISTS.
        """
        with self._transaction() as cur:
            cur.execute(_SCHEMA)
        logger.info("PostgresStore: schema applied.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_batch(
        self,
        batch:        BatchAnalysis,
        topic_store:  TopicStoreInterface,
    ) -> None:
        """
        Persist all analysis results from one pipeline batch in a single
        transaction.  Rolls back entirely on any failure — Kafka offsets
        should not be committed if this raises.

        Args:
            batch:        The BatchAnalysis produced by FeedbackPipeline.process_batch().
            topic_store:  The pipeline's shared TopicStore, used to look up full
                          Topic objects (description, aliases, intent) by topic_id.
        """
        if not batch.unit_analyses:
            logger.debug("save_batch: nothing to save for batch %s.", batch.batch_id[:8])
            return

        topic_rows, unit_rows, sentiment_rows = self._build_rows(batch, topic_store)

        with self._transaction() as cur:
            self._upsert_topics(cur, topic_rows)
            self._insert_units(cur, unit_rows)
            self._insert_sentiments(cur, sentiment_rows)

        logger.info(
            "Batch %s saved: %d topics, %d units, %d sentiments.",
            batch.batch_id[:8], len(topic_rows), len(unit_rows), len(sentiment_rows),
        )

    def close(self) -> None:
        """Return all connections and close the pool."""
        self._pool.closeall()
        logger.info("PostgresStore: pool closed.")

    # ------------------------------------------------------------------
    # Row construction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_rows(
        batch:        BatchAnalysis,
        topic_store:  TopicStoreInterface,
    ) -> tuple[list[_TopicRow], list[_UnitRow], list[_SentimentRow]]:
        """
        Convert a BatchAnalysis into typed row objects ready for insertion.
        Counts the per-topic delta (canonical units in this batch) for the
        incremental feedback_count upsert.
        """
        # Count canonical units per topic in this batch
        topic_deltas: Counter = Counter(
            ua.topic.topic_id
            for ua in batch.unit_analyses
            if not ua.is_duplicate and ua.topic is not None
        )

        # Build topic rows — one per unique topic_id in this batch
        seen_topic_ids: set[str] = set()
        topic_rows: list[_TopicRow] = []
        for ua in batch.unit_analyses:
            if ua.is_duplicate or ua.topic is None:
                continue
            tid = ua.topic.topic_id
            if tid in seen_topic_ids:
                continue
            seen_topic_ids.add(tid)

            topic = topic_store.get(tid)
            if topic is None:
                # Shouldn't happen, but degrade gracefully
                logger.warning("Topic %s not found in store; skipping.", tid[:8])
                continue

            topic_rows.append(_TopicRow(
                topic_id       = topic.topic_id,
                label          = topic.label,
                description    = topic.description,
                aliases        = topic.aliases,
                delta          = topic_deltas[tid],
                intent_type    = topic.intent_type,
                intent_urgency = topic.intent_urgency,
            ))

        # Build unit and sentiment rows — one per FeedbackUnit
        unit_rows:      list[_UnitRow]      = []
        sentiment_rows: list[_SentimentRow] = []

        for ua in batch.unit_analyses:
            unit_rows.append(_UnitRow(
                unit_id             = ua.unit.unit_id,
                parent_cfo_id       = ua.unit.parent_cfo_id,
                text                = ua.unit.text,
                char_start          = ua.unit.char_start,
                char_end            = ua.unit.char_end,
                unit_index          = ua.unit.unit_index,
                metadata            = ua.unit.metadata or {},
                is_duplicate        = ua.is_duplicate,
                canonical_id        = ua.canonical_id,
                topic_id            = ua.topic.topic_id    if ua.topic else None,
                topic_label         = ua.topic.topic_label if ua.topic else None,
                topic_confidence    = ua.topic.confidence  if ua.topic else None,
                topic_is_new        = ua.topic.is_new_topic if ua.topic else None,
                raw_extracted_label = ua.topic.raw_extracted if ua.topic else None,
                evidence_spans      = ua.topic.evidence_spans if ua.topic else [],
                specific_request    = ua.specific_request,
                competitor_mention  = ua.competitor_mention,
                churn_indicators    = _serialise_churn(ua.churn_indicators),
            ))

            if not ua.is_duplicate and ua.sentiment is not None:
                sentiment_rows.append(_SentimentRow(
                    unit_id           = ua.unit.unit_id,
                    polarity          = ua.sentiment.polarity,
                    intensity         = ua.sentiment.intensity,
                    emotions          = _serialise_emotions(ua.sentiment.emotions),
                    aspect_sentiments = _serialise_aspects(ua.sentiment.aspect_sentiments),
                    sarcasm_flag      = ua.sentiment.sarcasm_flag,
                    confidence        = ua.sentiment.confidence,
                ))

        return topic_rows, unit_rows, sentiment_rows

    # ------------------------------------------------------------------
    # DB writes
    # ------------------------------------------------------------------

    @staticmethod
    def _upsert_topics(cur: psycopg2.extensions.cursor, rows: list[_TopicRow]) -> None:
        """
        Upsert topics one at a time (batches typically contain few unique topics).

        On conflict:
          - feedback_count is incremented by the batch delta (not replaced).
          - aliases are merged and deduplicated via UNNEST.
          - intent fields use COALESCE to never overwrite an established value
            with NULL.
        """
        sql = """
            INSERT INTO topics
                (topic_id, label, description, aliases, feedback_count,
                 intent_type, intent_urgency)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (topic_id) DO UPDATE SET
                label          = EXCLUDED.label,
                description    = EXCLUDED.description,
                aliases        = ARRAY(
                                   SELECT DISTINCT UNNEST(
                                     topics.aliases || EXCLUDED.aliases
                                   )
                                 ),
                feedback_count = topics.feedback_count + EXCLUDED.feedback_count,
                intent_type    = COALESCE(topics.intent_type,    EXCLUDED.intent_type),
                intent_urgency = COALESCE(topics.intent_urgency, EXCLUDED.intent_urgency),
                updated_at     = NOW()
        """
        for row in rows:
            cur.execute(sql, (
                row.topic_id,
                row.label,
                row.description,
                row.aliases,
                row.delta,
                row.intent_type,
                row.intent_urgency,
            ))

    @staticmethod
    def _insert_units(cur: psycopg2.extensions.cursor, rows: list[_UnitRow]) -> None:
        """
        Batch-insert all FeedbackUnits.  ON CONFLICT DO NOTHING makes this
        idempotent — Kafka redelivery on restart won't create duplicates.
        """
        if not rows:
            return

        sql = """
            INSERT INTO feedback_units (
                unit_id, parent_cfo_id, text, char_start, char_end, unit_index,
                metadata, is_duplicate, canonical_id,
                topic_id, topic_label, topic_confidence, topic_is_new,
                raw_extracted_label, evidence_spans,
                specific_request, competitor_mention, churn_indicators
            ) VALUES %s
            ON CONFLICT (unit_id) DO NOTHING
        """
        execute_values(cur, sql, [
            (
                r.unit_id,
                r.parent_cfo_id,
                r.text,
                r.char_start,
                r.char_end,
                r.unit_index,
                Json(r.metadata),
                r.is_duplicate,
                r.canonical_id,
                r.topic_id,
                r.topic_label,
                r.topic_confidence,
                r.topic_is_new,
                r.raw_extracted_label,
                r.evidence_spans,
                r.specific_request,
                r.competitor_mention,
                Json(r.churn_indicators),
            )
            for r in rows
        ])

    @staticmethod
    def _insert_sentiments(
        cur: psycopg2.extensions.cursor, rows: list[_SentimentRow]
    ) -> None:
        """
        Batch-insert sentiment results.  ON CONFLICT DO NOTHING for idempotency.
        """
        if not rows:
            return

        sql = """
            INSERT INTO unit_sentiments (
                unit_id, polarity, intensity, emotions,
                aspect_sentiments, sarcasm_flag, confidence
            ) VALUES %s
            ON CONFLICT (unit_id) DO NOTHING
        """
        execute_values(cur, sql, [
            (
                r.unit_id,
                r.polarity,
                r.intensity,
                Json(r.emotions),
                Json(r.aspect_sentiments),
                r.sarcasm_flag,
                r.confidence,
            )
            for r in rows
        ])

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    @contextmanager
    def _transaction(self) -> Generator[psycopg2.extensions.cursor, None, None]:
        """
        Context manager that acquires a connection, yields a cursor inside a
        transaction, commits on success, rolls back on any exception, and always
        returns the connection to the pool.
        """
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _serialise_emotions(emotions: list) -> list[dict]:
    """Convert EmotionTag objects to plain dicts for JSONB storage."""
    result = []
    for e in emotions:
        if isinstance(e, dict):
            result.append(e)
        else:
            result.append({"emotion": e.emotion, "confidence": e.confidence})
    return result


def _serialise_aspects(aspects: list) -> list[dict]:
    """Convert AspectSentiment objects to plain dicts for JSONB storage."""
    result = []
    for a in aspects:
        if isinstance(a, dict):
            result.append(a)
        else:
            result.append({"aspect": a.aspect, "polarity": a.polarity, "evidence": a.evidence})
    return result


def _serialise_churn(indicators: list) -> list[dict]:
    """Convert ChurnIndicator objects to plain dicts for JSONB storage."""
    result = []
    for c in indicators:
        if isinstance(c, dict):
            result.append(c)
        else:
            result.append({"signal": c.signal, "severity": c.severity})
    return result


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def build_store_callback(
    dsn:                str,
    topic_store_getter,         # callable that returns the TopicStoreInterface
    min_conn:           int = 2,
    max_conn:           int = 10,
) -> tuple[PostgresStore, callable]:
    """
    Create a PostgresStore and a ready-to-use on_batch_complete callback.

    Args:
        dsn:               PostgreSQL connection string.
        topic_store_getter: A zero-argument callable that returns the pipeline's
                           TopicStore.  Pass a lambda so it's evaluated lazily
                           after the pipeline is constructed:
                               build_store_callback(dsn, lambda: pipeline.topic_store)
        min_conn / max_conn: Connection pool bounds.

    Returns:
        (store, callback) — pass callback as on_batch_complete to the consumer.

    Example:
        pipeline, _ = build_pipeline(config)
        store, on_batch = build_store_callback(
            dsn                = "postgresql://user:pass@host/voc",
            topic_store_getter = lambda: pipeline.topic_store,
        )
        store.apply_schema()
        consumer = KafkaFeedbackConsumer(config, pipeline, on_batch_complete=on_batch)
        consumer.run()
    """
    store = PostgresStore.from_url(dsn, min_conn=min_conn, max_conn=max_conn)

    def callback(batch: BatchAnalysis) -> None:
        store.save_batch(batch, topic_store_getter())

    return store, callback


# ---------------------------------------------------------------------------
# Smoke-test (requires a running PostgreSQL instance)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import uuid
    from pipeline import BatchAnalysis, UnitAnalysis
    from stage2_unitization import FeedbackUnit
    from stage3_topic_extraction import Topic, TopicExtractionResult, InMemoryTopicStore
    from stage3_sentiment_extraction import SentimentResult, EmotionTag, AspectSentiment
    from sentence_transformers import SentenceTransformer

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    DSN = os.environ.get("DATABASE_URL", "postgresql://localhost/voc_test")

    # ── Build minimal test fixtures ───────────────────────────────────────

    encoder     = SentenceTransformer("all-MiniLM-L6-v2")
    topic_store = InMemoryTopicStore(encoder=encoder)

    billing_topic = Topic(
        label          = "Duplicate Charge After Cancellation",
        description    = "Customer charged multiple times after cancelling.",
        aliases        = ["double billed", "charged twice"],
        feedback_count = 2,
        intent_type    = "complaint",
        intent_urgency = "high",
    )
    topic_store.add(billing_topic)

    unit_a = FeedbackUnit(
        unit_id       = str(uuid.uuid4()),
        parent_cfo_id = "cfo-001",
        text          = "I was charged three times after cancelling.",
        char_start    = 0,
        char_end      = 45,
        unit_index    = 0,
        metadata      = {"source_channel": "app_store_review", "user_segment": "enterprise"},
    )
    unit_b = FeedbackUnit(
        unit_id       = str(uuid.uuid4()),
        parent_cfo_id = "cfo-001",
        text          = "Great product overall.",
        char_start    = 46,
        char_end      = 68,
        unit_index    = 1,
        metadata      = {"source_channel": "app_store_review", "user_segment": "enterprise"},
    )

    topic_result = TopicExtractionResult(
        unit_id         = unit_a.unit_id,
        topic_id        = billing_topic.topic_id,
        topic_label     = billing_topic.label,
        confidence      = 0.92,
        evidence_spans  = ["charged three times", "after cancelling"],
        is_new_topic    = False,
        raw_extracted   = "duplicate charge after cancellation",
    )
    sentiment = SentimentResult(
        unit_id      = unit_a.unit_id,
        polarity     = -0.85,
        intensity    = "strong",
        emotions     = [EmotionTag("frustrated", 0.9), EmotionTag("angry", 0.6)],
        aspect_sentiments = [
            AspectSentiment("billing", -0.9, "charged three times after cancelling")
        ],
        sarcasm_flag = False,
        confidence   = 0.93,
    )

    batch = BatchAnalysis(
        batch_id        = str(uuid.uuid4()),
        total_cfos      = 1,
        total_units     = 2,
        canonical_units = 2,
        unit_analyses   = [
            UnitAnalysis(
                unit               = unit_a,
                is_duplicate       = False,
                topic              = topic_result,
                sentiment          = sentiment,
                intent_type        = "complaint",
                urgency            = "high",
                specific_request   = "Request refund for duplicate charges",
                competitor_mention = None,
                churn_indicators   = [],
            ),
            UnitAnalysis(
                unit         = unit_b,
                is_duplicate = False,
                topic        = None,
                sentiment    = SentimentResult(
                    unit_id   = unit_b.unit_id,
                    polarity  = 0.7,
                    intensity = "moderate",
                    emotions  = [EmotionTag("pleased", 0.8)],
                    aspect_sentiments = [],
                    sarcasm_flag = False,
                    confidence   = 0.88,
                ),
            ),
        ],
    )

    store = PostgresStore.from_url(DSN)
    store.apply_schema()
    store.save_batch(batch, topic_store)

    print("\nSmoke-test passed — check your database:")
    print(f"  SELECT * FROM topics WHERE topic_id = '{billing_topic.topic_id}';")
    print(f"  SELECT * FROM feedback_units WHERE parent_cfo_id = 'cfo-001';")
    print(f"  SELECT * FROM unit_sentiments WHERE unit_id = '{unit_a.unit_id}';")

    store.close()
