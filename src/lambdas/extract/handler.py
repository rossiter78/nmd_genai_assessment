"""Lambda handler for LLM-based field extraction."""

import logging

from common.settings import get_settings
from tasks.extract import extract_fields

logging.getLogger().setLevel(get_settings().log_level)
logger = logging.getLogger(__name__)


def handler(event: dict, context: object) -> dict:
    """Extract structured fields from a document using Bedrock."""
    logger.info("Extracting fields from document: %s", event.get("document_id"))
    return extract_fields(event)
