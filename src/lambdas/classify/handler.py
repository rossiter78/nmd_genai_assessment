"""Lambda handler for document classification."""

import logging

from common.settings import get_settings
from tasks.classify import classify_document

logging.getLogger().setLevel(get_settings().log_level)
logger = logging.getLogger(__name__)


def handler(event: dict, context: object) -> dict:
    """Classify a document using Bedrock LLM."""
    logger.info("Classifying document: %s", event.get("document_id"))
    return classify_document(event)
