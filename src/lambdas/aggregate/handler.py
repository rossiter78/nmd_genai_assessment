"""Lambda handler for aggregating extraction results."""

import logging

from common.settings import get_settings
from tasks.aggregate import aggregate_results

logging.getLogger().setLevel(get_settings().log_level)
logger = logging.getLogger(__name__)


def handler(event: dict, context: object) -> dict:
    """Aggregate extraction results and write final output to S3."""
    logger.info("Aggregating results")
    return aggregate_results(event)
