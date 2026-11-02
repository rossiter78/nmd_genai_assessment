"""Shared Bedrock request and reply handling for Claude Haiku."""

import json
import logging
import re

logger = logging.getLogger(__name__)

ANTHROPIC_VERSION = "bedrock-2023-05-31"
CODE_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def build_user_message(event: dict) -> str:
    """Wrap the document in tags so the model can tell it apart from the instructions."""
    return (
        f"<title>{event.get('title', '')}</title>\n"
        f"<source>{event.get('source', '')}</source>\n"
        f"<content>{event.get('content', '')}</content>"
    )


def invoke_json(client, model_id: str, system: str, user: str, max_tokens: int, schema: dict) -> dict:
    """Call Haiku and return its reply as a dict.

    Bedrock errors pass through unwrapped so Step Functions can retry them by
    name. A reply we can't use raises ValueError, which isn't retried.
    """
    response = client.invoke_model(
        modelId=model_id,
        body=json.dumps(
            {
                "anthropic_version": ANTHROPIC_VERSION,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            }
        ),
    )
    return parse_reply(json.loads(response["body"].read()))


def parse_reply(reply: dict) -> dict:
    """Return the JSON object in a Messages API reply, skipping any thinking blocks."""
    stop_reason = reply.get("stop_reason")
    if stop_reason in ("max_tokens", "refusal"):
        raise ValueError(f"Model reply is incomplete: stop_reason={stop_reason}")

    text = "".join(block["text"] for block in reply.get("content", []) if block.get("type") == "text").strip()
    fenced = CODE_FENCE.match(text)
    if fenced:
        text = fenced.group(1)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        logger.error("Model reply is not valid JSON: %.200s", text)
        raise ValueError("Model reply is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise ValueError("Model reply is not a JSON object")  # noqa: TRY004 - ValueError is the non-retried failure
    return parsed


def read_confidence(parsed: dict) -> float:
    """Return the reply's confidence, kept between 0.0 and 1.0."""
    try:
        confidence = float(parsed["confidence"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Model reply has no usable confidence") from error
    return max(0.0, min(1.0, confidence))
