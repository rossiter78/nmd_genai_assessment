"""Results aggregation task logic."""

import json
import logging

from common.aws import get_s3_client

logger = logging.getLogger(__name__)


def aggregate_results(event: dict) -> dict:
    """Aggregate extraction results and write summary to S3.

    Args:
        event: Full pipeline state with preprocess, classify, and extract results.

    Returns:
        Summary of the pipeline execution.
    """
    logger.info("Aggregating results")

    preprocess = event.get("preprocess_result", {})
    classify = event.get("classify_result", {})
    extract = event.get("extract_result", {})
    document_id = preprocess.get("document_id", "unknown")
    s3_bucket = preprocess.get("s3_bucket", "")

    summary = {
        "document_id": document_id,
        "document_type": classify.get("document_type", "unknown"),
        "classification_confidence": classify.get("confidence", 0.0),
        "extracted_fields": extract.get("extracted_fields", {}),
        "extraction_confidence": extract.get("confidence", 0.0),
        "status": "completed",
    }

    key = f"results/{document_id}.json"
    get_s3_client().put_object(
        Bucket=s3_bucket,
        Key=key,
        Body=json.dumps(summary, indent=2),
        ContentType="application/json",
    )
    logger.info("Wrote results to s3://%s/%s", s3_bucket, key)

    return summary
