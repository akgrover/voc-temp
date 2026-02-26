"""
REST API Ingestion for VoC
Usage:
    uvicorn api:app --reload --port 8000       # development
    uvicorn api:app --port 8000 --workers 1    # production (must be workers=1;
                                               #  TopicStore and dedup index are in-memory)
"""
from __future__ import annotations

import dataclasses
import logging
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from pipeline import BatchAnalysis, FeedbackPipeline, PipelineConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton pipeline (shared across all requests)
# ---------------------------------------------------------------------------
_pipeline: Optional[FeedbackPipeline] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline
    if _pipeline is None:           # skip if pre-injected by start_api.py
        cfg = PipelineConfig()
        _pipeline = FeedbackPipeline(cfg)
        logger.info("REST: pipeline initialised (max_workers=%d).", cfg.max_workers)
    yield
    _pipeline.shutdown()


app = FastAPI(
    title="VoC Feedback Analysis API",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class CFORequest(BaseModel):
    id: str
    raw_text: Optional[str] = None
    clean_text: Optional[str] = None
    source_channel: Optional[str] = None
    user_segment: Optional[str] = None
    survey_question: Optional[str] = None
    model_config = {"extra": "allow"}   # arbitrary metadata passes through to pipeline

    @model_validator(mode="after")
    def require_text(self) -> "CFORequest":
        if not self.raw_text and not self.clean_text:
            raise ValueError("Provide at least one of 'raw_text' or 'clean_text'.")
        return self


class AnalyzeRequest(BaseModel):
    cfos: list[CFORequest] = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def _to_dict(obj: Any) -> Any:
    """Recursively convert dataclass graph → plain dict/list for JSON response."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/analyze")
def analyze(request: AnalyzeRequest) -> dict:
    """Submit CFOs for synchronous analysis. Blocks until all pipeline stages complete."""
    cfos = [cfo.model_dump(exclude_none=True) for cfo in request.cfos]
    try:
        result: BatchAnalysis = _pipeline.process_batch(cfos)
    except Exception as exc:
        logger.exception("Pipeline error.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _to_dict(result)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "pipeline_ready": _pipeline is not None}
