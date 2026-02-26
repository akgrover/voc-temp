"""
Feedback Analysis Pipeline
==========================
End-to-end pipeline that reads raw Canonical Feedback Objects (CFOs) from a
Kafka topic, processes them through all analysis stages, and delivers
structured results via a callback.

Stage order and parallelism:
  ┌─────────────────────────────┬────────────┬────────────────────────────────┐
  │ Stage                       │ Execution  │ Reason                         │
  ├─────────────────────────────┼────────────┼────────────────────────────────┤
  │ 1.   PII Redaction          │ Parallel   │ CPU-bound, fully independent   │
  │ 2.1  Unitization            │ Parallel   │ Independent LLM call per CFO   │
  │ 2.2  Deduplication          │ Sequential │ Ordering guarantee (query      │
  │                             │            │ before insert must hold across  │
  │                             │            │ units in the same batch)        │
  │ 3.2  Topic Extraction       │ Sequential │ TopicStore.add() is not safe   │
  │                             │            │ under concurrent writers        │
  │ 3.1/3.3 Sentiment + Intent  │ Parallel   │ Independent LLM calls; intent  │
  │                             │            │ cache writes are near-idempotent│
  └─────────────────────────────┴────────────┴────────────────────────────────┘

Batching:
  The Kafka consumer accumulates messages into a buffer and flushes when either
  (a) the buffer reaches `batch_size` or (b) `batch_timeout_ms` has elapsed,
  whichever comes first.  This bounds latency during quiet periods while still
  amortising per-batch overhead during high-volume periods.

Offset management:
  Kafka offsets are committed manually after each batch completes successfully.
  If the pipeline raises an unhandled exception the offsets are NOT committed,
  so the batch will be reprocessed on consumer restart.

Dependencies:
    pip install confluent-kafka anthropic sentence-transformers numpy spacy
    python -m spacy download en_core_web_sm
"""

from __future__ import annotations

import json
import logging
import signal
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Callable, Iterator, Optional

from confluent_kafka import Consumer, KafkaError, KafkaException, Message

from stage1_pii_redaction import PIIRedactor, redact_cfo
from stage2_unitization import FeedbackUnit, UnitizationAgent, UnitizationResult
from stage2_deduplication import (
    DeduplicationAgent,
    DeduplicationResult,
    InMemoryVectorStore,
    deduplicate_units,
)
from stage3_topic_extraction import (
    InMemoryTopicStore,
    TopicExtractionResult,
    TopicExtractor,
    TopicStoreInterface,
    build_topic_extractor,
)
from stage3_sentiment_extraction import SentimentResult
from stage3_intent_extraction import ExtractionOrchestrator, ExtractionResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class PipelineConfig:
    """
    All tunable parameters for the pipeline in one place.

    Kafka:
        bootstrap_servers:  Comma-separated broker addresses.
        input_topic:        Topic to consume raw CFO JSON messages from.
        group_id:           Consumer group ID (Kafka uses this to track offsets).
        output_topic:       Optional topic to publish BatchAnalysis JSON results
                            to.  If None, results are delivered only via the
                            on_batch_complete callback.

    Batching:
        batch_size:         Flush when this many messages have accumulated.
        batch_timeout_ms:   Flush after this many ms even if batch_size hasn't
                            been reached.  Caps end-to-end latency during quiet
                            periods.

    Concurrency:
        max_workers:        Thread pool size for parallel stages.  LLM calls are
                            I/O-bound so this can safely exceed CPU core count.
                            Start with 8 and tune based on API rate limits.

    Models:
        llm_model_complex:  Claude model for high-judgment tasks: unitization and
                            topic extraction.  Sonnet is the default — these stages
                            require nuanced instruction following and calibrated
                            specificity that smaller models handle less reliably.
        llm_model_simple:   Claude model for structured extraction tasks: sentiment
                            and intent.  Haiku is the default — outputs are well-
                            defined JSON with fixed enums, so the cheaper/faster
                            model handles them well.
        encoder_model:      Sentence-transformer for deduplication and topic
                            matching embeddings.
    """

    # Kafka
    bootstrap_servers: str          = "localhost:9092"
    input_topic:       str          = "raw-feedback"
    group_id:          str          = "voc-pipeline"
    output_topic:      Optional[str] = None

    # Batching
    batch_size:        int          = 50
    batch_timeout_ms:  int          = 5_000

    # Concurrency
    max_workers:       int          = 8

    # Models
    llm_model_complex: str          = "claude-sonnet-4-6"
    llm_model_simple:  str          = "claude-haiku-4-5-20251001"
    encoder_model:     str          = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class UnitAnalysis:
    """
    Complete analysis output for one FeedbackUnit.

    Duplicate units are included (is_duplicate=True) with no theme/sentiment/
    intent fields — those stages were skipped for them.  Duplicates are still
    present in the output so callers have a full audit trail and can count
    raw volume (including duplicates) separately from unique signal.
    """

    unit:               FeedbackUnit
    is_duplicate:       bool
    canonical_id:       Optional[str]              = None   # set when is_duplicate=True

    # Populated only for canonical (non-duplicate) units
    topic:              Optional[TopicExtractionResult] = None
    sentiment:          Optional[SentimentResult]       = None
    intent_type:        Optional[str]                   = None
    urgency:            Optional[str]                   = None
    specific_request:   Optional[str]                   = None
    competitor_mention: Optional[str]                   = None
    churn_indicators:   list                            = field(default_factory=list)


@dataclass
class BatchAnalysis:
    """Aggregate result for one processed batch."""

    batch_id:        str
    total_cfos:      int            # CFOs received from Kafka
    total_units:     int            # FeedbackUnits after unitization
    canonical_units: int            # Units that survived deduplication
    unit_analyses:   list[UnitAnalysis]
    errors:          list[str]      = field(default_factory=list)
    processing_ms:   float          = 0.0


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class FeedbackPipeline:
    """
    Orchestrates all analysis stages for a batch of Canonical Feedback Objects.

    Stateful components — the TopicStore and the deduplication vector index —
    are shared across batches and persist for the lifetime of the pipeline
    instance.  This means:
      - Topics discovered in batch N are immediately available for matching in
        batch N+1 without re-seeding.
      - Near-duplicate detection improves over time as the index grows.

    Usage:
        pipeline = FeedbackPipeline(config)
        result   = pipeline.process_batch(cfos)   # call repeatedly
        pipeline.shutdown()
    """

    def __init__(self, config: PipelineConfig) -> None:
        self._cfg = config

        # Shared thread pool — all parallel stages use the same pool so the
        # total thread count stays bounded.
        self._executor = ThreadPoolExecutor(max_workers=config.max_workers)

        # Stage 1
        self._pii_redactor = PIIRedactor()

        # Stage 2.1 — complex: judgment-heavy text segmentation
        self._unitizer = UnitizationAgent(model=config.llm_model_complex)

        # Stage 2.2 — dedup index persists across batches
        self._dedup_store = InMemoryVectorStore()
        self._dedup_agent = DeduplicationAgent(
            vector_store = self._dedup_store,
            model_name   = config.encoder_model,
        )

        # Stage 3.2 — complex: nuanced topic label calibration; store persists across batches
        self._topic_extractor, self._topic_store = build_topic_extractor(
            encoder_model = config.encoder_model,
            llm_model     = config.llm_model_complex,
        )

        # Stage 3.1 / 3.3 — simple: structured JSON with fixed enums
        self._orchestrator = ExtractionOrchestrator(model=config.llm_model_simple)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def topic_store(self) -> TopicStoreInterface:
        """
        Expose the shared TopicStore so callers (e.g. the DB persistence layer)
        can look up full Topic objects — including description, aliases, and
        cached intent — by topic_id from a TopicExtractionResult.
        """
        return self._topic_store

    def process_batch(self, cfos: list[dict]) -> BatchAnalysis:
        """
        Run one batch of CFOs through the full pipeline.

        Each CFO must have at minimum an 'id' key and either 'clean_text' or
        'raw_text'.  All other CFO fields (source_metadata, user_metadata, etc.)
        are forwarded to the relevant agents as context.

        Returns a BatchAnalysis with per-unit results and batch-level metrics.
        Failures at the unit level are captured in BatchAnalysis.errors and do
        not abort the rest of the batch.
        """
        if not cfos:
            return BatchAnalysis(
                batch_id        = str(uuid.uuid4()),
                total_cfos      = 0,
                total_units     = 0,
                canonical_units = 0,
                unit_analyses   = [],
            )

        batch_id = str(uuid.uuid4())
        t_start  = time.monotonic()
        errors:  list[str] = []

        logger.info("Batch %s: received %d CFOs.", batch_id[:8], len(cfos))

        # ── Stage 1: PII Redaction  (parallel) ───────────────────────────
        cfos = self._run_parallel(
            fn       = lambda cfo: redact_cfo(cfo, self._pii_redactor),
            items    = cfos,
            stage    = "pii_redaction",
            errors   = errors,
            fallback = lambda cfo: cfo,     # pass through unredacted on failure
        )

        # ── Stage 2.1: Unitization  (parallel) ───────────────────────────
        unit_results: list[Optional[UnitizationResult]] = self._run_parallel(
            fn       = self._unitizer.unitize,
            items    = cfos,
            stage    = "unitization",
            errors   = errors,
            fallback = lambda _: None,
        )
        all_units: list[FeedbackUnit] = [
            unit
            for result in unit_results
            if result is not None
            for unit in result.units
        ]
        logger.info("Batch %s: %d units after unitization.", batch_id[:8], len(all_units))

        # ── Stage 2.2: Deduplication  (sequential — ordering constraint) ─
        canonical_units, dedup_results = deduplicate_units(
            units = all_units,
            agent = self._dedup_agent,
        )
        dedup_map: dict[str, DeduplicationResult] = {
            r.unit_id: r for r in dedup_results
        }
        logger.info(
            "Batch %s: %d canonical, %d duplicates suppressed.",
            batch_id[:8], len(canonical_units), len(all_units) - len(canonical_units),
        )

        # ── Stage 3.2: Topic Extraction  (sequential — TopicStore not thread-safe) ─
        # TopicStore.add() must not be called concurrently: a check-then-act
        # race between find_match() and add() would create duplicate topic nodes
        # for the same concept.  Sequential processing avoids this without
        # needing locks inside the TopicStore itself.
        raw_topic_results: list[Optional[TopicExtractionResult]] = []
        for unit in canonical_units:
            try:
                raw_topic_results.append(self._topic_extractor.extract(unit))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Topic extraction failed for unit %s: %s", unit.unit_id[:8], exc)
                errors.append(f"topic_extraction:{unit.unit_id}:{exc}")
                raw_topic_results.append(None)

        # Drop units whose topic extraction failed so later stages receive
        # clean (unit, topic_result) pairs.
        paired = [
            (u, tr)
            for u, tr in zip(canonical_units, raw_topic_results)
            if tr is not None
        ]
        if paired:
            canonical_units, topic_results = map(list, zip(*paired))
        else:
            logger.warning("Batch %s: no units survived topic extraction.", batch_id[:8])
            canonical_units, topic_results = [], []

        # ── Stage 3.1 / 3.3: Sentiment + Intent  (parallel) ──────────────
        # Intent cache writes (theme.intent_type) are near-idempotent:
        # two threads processing the same new theme both make a combined call
        # and write the same value.  A lock around the orchestrator would
        # prevent the duplicate call but adds coordination overhead.  The
        # trade-off is acceptable for the first occurrence of each theme.
        extraction_results: list[Optional[ExtractionResult]] = self._run_parallel(
            fn    = lambda args: self._orchestrator.extract(
                unit         = args[0],
                topic_result = args[1],
                topic_store  = self._topic_store,
            ),
            items    = list(zip(canonical_units, topic_results)),
            stage    = "sentiment_intent",
            errors   = errors,
            fallback = lambda _: None,
        )

        # ── Assemble output ───────────────────────────────────────────────
        extraction_map: dict[str, ExtractionResult] = {
            unit.unit_id: result
            for unit, result in zip(canonical_units, extraction_results)
            if result is not None
        }
        topic_map: dict[str, TopicExtractionResult] = {
            u.unit_id: tr
            for u, tr in zip(canonical_units, topic_results)
        }

        unit_analyses: list[UnitAnalysis] = []
        for unit in all_units:
            dedup      = dedup_map.get(unit.unit_id)
            is_dup     = dedup.is_duplicate if dedup else False

            if is_dup:
                unit_analyses.append(UnitAnalysis(
                    unit         = unit,
                    is_duplicate = True,
                    canonical_id = dedup.canonical_id if dedup else None,
                ))
                continue

            extraction = extraction_map.get(unit.unit_id)
            unit_analyses.append(UnitAnalysis(
                unit               = unit,
                is_duplicate       = False,
                topic              = topic_map.get(unit.unit_id),
                sentiment          = extraction.sentiment                   if extraction else None,
                intent_type        = extraction.intent.intent_type          if extraction else None,
                urgency            = extraction.intent.urgency              if extraction else None,
                specific_request   = extraction.intent.specific_request     if extraction else None,
                competitor_mention = extraction.intent.competitor_mention   if extraction else None,
                churn_indicators   = extraction.intent.churn_indicators     if extraction else [],
            ))

        processing_ms = (time.monotonic() - t_start) * 1000
        logger.info(
            "Batch %s done: %d unit analyses, %d errors, %.0fms.",
            batch_id[:8], len(unit_analyses), len(errors), processing_ms,
        )

        return BatchAnalysis(
            batch_id        = batch_id,
            total_cfos      = len(cfos),
            total_units     = len(all_units),
            canonical_units = len(canonical_units),
            unit_analyses   = unit_analyses,
            errors          = errors,
            processing_ms   = processing_ms,
        )

    def shutdown(self) -> None:
        """Gracefully drain and shut down the thread pool."""
        self._executor.shutdown(wait=True)
        logger.info("FeedbackPipeline: executor shut down.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_parallel(
        self,
        fn:       Callable,
        items:    list,
        stage:    str,
        errors:   list[str],
        fallback: Callable,
    ) -> list:
        """
        Submit fn(item) for each item via the shared ThreadPoolExecutor.
        Returns results in the same order as items.

        All futures are submitted before any result is collected, so the
        executor runs them concurrently.  as_completed() then yields futures
        as they finish, minimising the time spent waiting on slow stragglers.
        On per-item failure the error is logged, appended to `errors`, and
        fallback(item) is used in place of the result.
        """
        if not items:
            return []

        results = [None] * len(items)
        futures: dict = {
            self._executor.submit(fn, item): (i, item)
            for i, item in enumerate(items)
        }

        for future in as_completed(futures):
            idx, item = futures[future]
            try:
                results[idx] = future.result()
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s failed for item %d: %s", stage, idx, exc)
                errors.append(f"{stage}:{idx}:{exc}")
                results[idx] = fallback(item)

        return results


# ---------------------------------------------------------------------------
# Kafka Consumer
# ---------------------------------------------------------------------------


class KafkaFeedbackConsumer:
    """
    Consumes raw CFO messages from a Kafka topic and drives the pipeline.

    Messages are expected to be UTF-8 encoded JSON objects conforming to the
    Canonical Feedback Object schema (see Stage 1 design).  Unparseable
    messages are skipped with a warning; the consumer moves on rather than
    blocking the batch.

    Batching:
        The consumer holds an in-memory buffer and flushes it to the pipeline
        when either batch_size messages have accumulated or batch_timeout_ms
        has elapsed — whichever comes first.  During quiet periods the timeout
        ensures results don't stall indefinitely.

    Offset management:
        Offsets are committed only after the pipeline (and the on_batch_complete
        callback) return without raising.  On failure the batch is not committed
        and will be redelivered on the next consumer restart, giving at-least-
        once processing semantics.

    Args:
        config:            Pipeline configuration.
        pipeline:          A FeedbackPipeline instance.
        on_batch_complete: Callback invoked with each BatchAnalysis after
                           successful processing.  Use this to write results to
                           a database, publish to an output Kafka topic, etc.
                           Defaults to a log-only handler.
    """

    def __init__(
        self,
        config:            PipelineConfig,
        pipeline:          FeedbackPipeline,
        on_batch_complete: Optional[Callable[[BatchAnalysis], None]] = None,
    ) -> None:
        self._cfg      = config
        self._pipeline = pipeline
        self._on_batch = on_batch_complete or self._log_handler
        self._stop     = threading.Event()

        self._consumer = Consumer({
            "bootstrap.servers":  config.bootstrap_servers,
            "group.id":           config.group_id,
            "auto.offset.reset":  "earliest",
            "enable.auto.commit": False,    # manual commit after processing
        })

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        """
        Start the consume → batch → process loop.  Blocks until stop() is
        called or a fatal Kafka error is encountered.

        Installs SIGINT and SIGTERM handlers so Ctrl-C triggers a clean
        shutdown after the current batch completes.
        """
        signal.signal(signal.SIGINT,  lambda *_: self.stop())
        signal.signal(signal.SIGTERM, lambda *_: self.stop())

        self._consumer.subscribe([self._cfg.input_topic])
        logger.info(
            "KafkaFeedbackConsumer: listening on '%s' (group=%s).",
            self._cfg.input_topic, self._cfg.group_id,
        )

        try:
            while not self._stop.is_set():
                for batch in self._accumulate():
                    if self._stop.is_set():
                        break
                    self._process_and_commit(batch)
        finally:
            self._consumer.close()
            self._pipeline.shutdown()
            logger.info("KafkaFeedbackConsumer: shut down cleanly.")

    def stop(self) -> None:
        """Signal the run loop to finish after the current batch."""
        logger.info("KafkaFeedbackConsumer: stop requested.")
        self._stop.set()

    # ------------------------------------------------------------------
    # Batch accumulation
    # ------------------------------------------------------------------

    def _accumulate(self) -> Iterator[list[dict]]:
        """
        Yield batches of CFO dicts, flushing when batch_size is reached
        or batch_timeout_ms elapses — whichever comes first.
        """
        timeout_s = self._cfg.batch_timeout_ms / 1_000.0
        batch:    list[dict] = []
        deadline: float      = time.monotonic() + timeout_s

        while not self._stop.is_set():
            remaining = max(0.0, deadline - time.monotonic())
            msg: Optional[Message] = self._consumer.poll(timeout=remaining)

            if msg is None:
                # Timeout elapsed with nothing new — flush whatever we have
                if batch:
                    yield batch
                batch    = []
                deadline = time.monotonic() + timeout_s
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    logger.debug("Partition EOF reached.")
                    continue
                raise KafkaException(msg.error())

            cfo = self._deserialise(msg)
            if cfo is not None:
                batch.append(cfo)

            if len(batch) >= self._cfg.batch_size:
                yield batch
                batch    = []
                deadline = time.monotonic() + timeout_s

        # Flush remaining messages on shutdown
        if batch:
            yield batch

    # ------------------------------------------------------------------
    # Processing and committing
    # ------------------------------------------------------------------

    def _process_and_commit(self, cfos: list[dict]) -> None:
        """
        Hand the batch to the pipeline, invoke the result callback, then
        commit Kafka offsets.  If anything raises, offsets are NOT committed.
        """
        try:
            result = self._pipeline.process_batch(cfos)
            self._on_batch(result)
            self._consumer.commit(asynchronous=False)
        except Exception:
            # Intentionally not committing — reprocessed on restart
            logger.exception(
                "Batch processing failed; Kafka offsets NOT committed."
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _deserialise(msg: Message) -> Optional[dict]:
        """Decode a Kafka message value as a CFO dict, or None on failure."""
        try:
            return json.loads(msg.value().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.warning(
                "Skipping unparseable message at offset %d: %s",
                msg.offset(), exc,
            )
            return None

    @staticmethod
    def _log_handler(result: BatchAnalysis) -> None:
        logger.info(
            "Batch %s | CFOs: %d | units: %d | canonical: %d | "
            "errors: %d | %.0fms",
            result.batch_id[:8],
            result.total_cfos,
            result.total_units,
            result.canonical_units,
            len(result.errors),
            result.processing_ms,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_pipeline(
    config:            PipelineConfig,
    on_batch_complete: Optional[Callable[[BatchAnalysis], None]] = None,
) -> tuple[FeedbackPipeline, KafkaFeedbackConsumer]:
    """
    Wire up and return a (FeedbackPipeline, KafkaFeedbackConsumer) pair.

    Example — minimal setup:
        config   = PipelineConfig(bootstrap_servers="broker:9092")
        pipeline, consumer = build_pipeline(config)
        consumer.run()

    Example — with a result handler:
        def save_to_db(batch: BatchAnalysis) -> None:
            for ua in batch.unit_analyses:
                if not ua.is_duplicate and ua.topic:
                    db.insert(ua)

        _, consumer = build_pipeline(config, on_batch_complete=save_to_db)
        consumer.run()
    """
    pipeline = FeedbackPipeline(config)
    consumer = KafkaFeedbackConsumer(
        config            = config,
        pipeline          = pipeline,
        on_batch_complete = on_batch_complete,
    )
    return pipeline, consumer


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level  = logging.INFO,
        format = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    cfg = PipelineConfig(
        bootstrap_servers = "localhost:9092",
        input_topic       = "raw-feedback",
        group_id          = "voc-pipeline-dev",
        batch_size        = 10,
        batch_timeout_ms  = 3_000,
        max_workers       = 4,
    )

    _, consumer = build_pipeline(cfg)
    consumer.run()   # blocks until Ctrl-C
