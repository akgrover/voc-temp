"""
Configuration loading from environment variables (.env file).
Uses python-dotenv to load settings from .env file.
"""

import logging
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load .env file if it exists
load_dotenv()
logger.debug("Loaded .env file")


def load_pipeline_config():
    """Load PipelineConfig from environment variables."""
    from pipeline import PipelineConfig

    return PipelineConfig(
        bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        input_topic=os.getenv("KAFKA_INPUT_TOPIC", "raw-feedback"),
        group_id=os.getenv("KAFKA_GROUP_ID", "voc-pipeline"),
        output_topic=os.getenv("KAFKA_OUTPUT_TOPIC", None),
        batch_size=int(os.getenv("BATCH_SIZE", "50")),
        batch_timeout_ms=int(os.getenv("BATCH_TIMEOUT_MS", "5000")),
        max_workers=int(os.getenv("MAX_WORKERS", "8")),
        llm_model_complex=os.getenv("LLM_MODEL_COMPLEX", "claude-sonnet-4-6"),
        llm_model_simple=os.getenv("LLM_MODEL_SIMPLE", "claude-haiku-4-5-20251001"),
        encoder_model=os.getenv("ENCODER_MODEL", "all-MiniLM-L6-v2"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        database_url=os.getenv("DATABASE_URL"),
    )
