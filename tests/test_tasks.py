"""Tests for task functions.

Bedrock responses here are written by hand from the expected reply format, so
the prompts still need checking against real Haiku output.
"""

import io
import json
from typing import ClassVar

import pytest

from tasks.aggregate import aggregate_results
from tasks.classify import classify_document
from tasks.extract import extract_fields
from tasks.preprocess import preprocess_document


class ThrottlingException(Exception):
    """Stands in for Bedrock's modeled throttling error, which Step Functions retries by name."""


def bedrock_client(mocker, text, stop_reason="end_turn"):
    """Return a fake Bedrock client whose replies start with a thinking block, as Haiku 5.5's can."""
    client = mocker.MagicMock()
    client.invoke_model.side_effect = lambda **_: {
        "body": io.BytesIO(
            json.dumps(
                {
                    "content": [
                        {"type": "thinking", "thinking": "", "signature": "sig"},
                        {"type": "text", "text": text},
                    ],
                    "stop_reason": stop_reason,
                }
            ).encode()
        )
    }
    client.converse.return_value = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"reasoningContent": {"reasoningText": {"text": "", "signature": "sig"}}}, {"text": text}],
            }
        },
        "stopReason": stop_reason,
    }
    return client


def throttled_client(mocker):
    """Return a fake Bedrock client that is always throttled."""
    client = mocker.MagicMock()
    client.invoke_model.side_effect = ThrottlingException("slow down")
    client.converse.side_effect = ThrottlingException("slow down")
    return client


def patch_bedrock(mocker, module, client):
    """Make a task module use the given Bedrock client."""
    mocker.patch(f"tasks.{module}.get_bedrock_client", return_value=client)
    return client


class TestPreprocess:
    """Tests for the preprocess task."""

    def test_preprocess_returns_document_id(self, mocker):
        """Preprocess should extract document_id from s3_key."""
        s3 = mocker.MagicMock()
        s3.get_object.return_value = {"Body": io.BytesIO(json.dumps({"title": "T", "content": "C"}).encode())}
        mocker.patch("tasks.preprocess.get_s3_client", return_value=s3)

        result = preprocess_document({"s3_bucket": "bucket", "s3_key": "uploads/doc-1.json"})

        assert result["document_id"] == "doc-1"
        assert result["content"] == "C"


class TestClassify:
    """Tests for the classify task."""

    EVENT: ClassVar[dict] = {"document_id": "doc-1", "title": "T", "content": "Some document text."}

    @pytest.mark.parametrize(
        "document_type",
        ["cybersecurity_advisory", "drug_approval", "airworthiness_directive", "financial_filing", "unknown"],
    )
    def test_returns_contract_for_each_type(self, mocker, document_type):
        """The state machine reads document_type and classification_confidence."""
        reply = json.dumps({"document_type": document_type, "confidence": 0.9})
        patch_bedrock(mocker, "classify", bedrock_client(mocker, reply))

        result = classify_document(self.EVENT)

        assert result["document_type"] == document_type
        assert result["classification_confidence"] == 0.9

    def test_type_outside_the_list_becomes_unknown(self, mocker):
        """A type the pipeline doesn't know must not reach Extract."""
        reply = json.dumps({"document_type": "recipe", "confidence": 0.9})
        patch_bedrock(mocker, "classify", bedrock_client(mocker, reply))

        assert classify_document(self.EVENT)["document_type"] == "unknown"

    def test_parses_code_fences(self, mocker):
        """Models often wrap JSON in a Markdown code fence."""
        reply = '```json\n{"document_type": "drug_approval", "confidence": 0.8}\n```'
        patch_bedrock(mocker, "classify", bedrock_client(mocker, reply))

        assert classify_document(self.EVENT)["document_type"] == "drug_approval"

    @pytest.mark.parametrize("reply", ["not json at all", '{"confidence": 0.9}'])
    def test_bad_output_raises_value_error(self, mocker, reply):
        """Invalid JSON and missing keys fail clearly, and ValueError isn't retried."""
        patch_bedrock(mocker, "classify", bedrock_client(mocker, reply))

        with pytest.raises(ValueError):
            classify_document(self.EVENT)

    @pytest.mark.parametrize(("raw", "expected"), [(1.7, 1.0), (-0.2, 0.0)])
    def test_confidence_is_kept_in_range(self, mocker, raw, expected):
        """Confidence stays between 0.0 and 1.0."""
        reply = json.dumps({"document_type": "drug_approval", "confidence": raw})
        patch_bedrock(mocker, "classify", bedrock_client(mocker, reply))

        assert classify_document(self.EVENT)["classification_confidence"] == expected

    @pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
    def test_incomplete_reply_raises_value_error(self, mocker, stop_reason):
        """A cut-off or refused reply can't be trusted, even if its text parses."""
        reply = json.dumps({"document_type": "drug_approval", "confidence": 0.9})
        patch_bedrock(mocker, "classify", bedrock_client(mocker, reply, stop_reason))

        with pytest.raises(ValueError):
            classify_document(self.EVENT)

    def test_bedrock_errors_are_not_wrapped(self, mocker):
        """Step Functions matches retryable errors by name."""
        patch_bedrock(mocker, "classify", throttled_client(mocker))

        with pytest.raises(ThrottlingException):
            classify_document(self.EVENT)


class TestExtract:
    """Tests for the extract task."""

    FIELDS: ClassVar[dict] = {
        "cybersecurity_advisory": ["severity", "cve_ids", "affected_products", "mitigation_steps"],
        "drug_approval": ["drug_name", "indication", "approval_date", "applicant", "dosage"],
        "airworthiness_directive": ["ad_number", "affected_aircraft", "compliance_deadline", "required_action"],
        "financial_filing": ["company_name", "filing_date", "event_type", "revenue", "net_income"],
    }

    @staticmethod
    def event(document_type="drug_approval"):
        return {"document_id": "doc-1", "title": "T", "content": "Some text.", "document_type": document_type}

    def test_returns_contract(self, mocker):
        """The state machine reads extracted_fields and extraction_confidence."""
        reply = json.dumps({"extracted_fields": {"drug_name": "X"}, "confidence": 0.7})
        patch_bedrock(mocker, "extract", bedrock_client(mocker, reply))

        result = extract_fields(self.event())

        assert result["extracted_fields"] == {"drug_name": "X"}
        assert result["extraction_confidence"] == 0.7

    @pytest.mark.parametrize(("document_type", "fields"), FIELDS.items())
    def test_request_names_the_fields_for_the_type(self, mocker, document_type, fields):
        """Each document type asks the model for its own fields."""
        reply = json.dumps({"extracted_fields": {}, "confidence": 0.5})
        client = patch_bedrock(mocker, "extract", bedrock_client(mocker, reply))

        extract_fields(self.event(document_type))

        request = str(client.invoke_model.call_args) + str(client.converse.call_args)
        for field in fields:
            assert field in request

    def test_unknown_type_skips_bedrock(self, mocker):
        """There are no fields to extract from an unknown document."""
        client = patch_bedrock(mocker, "extract", bedrock_client(mocker, "{}"))

        result = extract_fields(self.event("unknown"))

        assert result["extracted_fields"] == {}
        assert result["extraction_confidence"] == 0.0
        client.invoke_model.assert_not_called()
        client.converse.assert_not_called()

    def test_parses_code_fences(self, mocker):
        """Models often wrap JSON in a Markdown code fence."""
        reply = '```json\n{"extracted_fields": {"drug_name": "X"}, "confidence": 0.7}\n```'
        patch_bedrock(mocker, "extract", bedrock_client(mocker, reply))

        assert extract_fields(self.event())["extracted_fields"] == {"drug_name": "X"}

    @pytest.mark.parametrize("reply", ["not json at all", '{"confidence": 0.9}'])
    def test_bad_output_raises_value_error(self, mocker, reply):
        """Invalid JSON and missing keys fail clearly, and ValueError isn't retried."""
        patch_bedrock(mocker, "extract", bedrock_client(mocker, reply))

        with pytest.raises(ValueError):
            extract_fields(self.event())

    def test_confidence_is_kept_in_range(self, mocker):
        """Confidence stays between 0.0 and 1.0."""
        reply = json.dumps({"extracted_fields": {}, "confidence": 1.7})
        patch_bedrock(mocker, "extract", bedrock_client(mocker, reply))

        assert extract_fields(self.event())["extraction_confidence"] == 1.0

    @pytest.mark.parametrize("stop_reason", ["max_tokens", "refusal"])
    def test_incomplete_reply_raises_value_error(self, mocker, stop_reason):
        """A cut-off or refused reply can't be trusted, even if its text parses."""
        reply = json.dumps({"extracted_fields": {"drug_name": "X"}, "confidence": 0.7})
        patch_bedrock(mocker, "extract", bedrock_client(mocker, reply, stop_reason))

        with pytest.raises(ValueError):
            extract_fields(self.event())

    def test_bedrock_errors_are_not_wrapped(self, mocker):
        """Step Functions matches retryable errors by name."""
        patch_bedrock(mocker, "extract", throttled_client(mocker))

        with pytest.raises(ThrottlingException):
            extract_fields(self.event())


class TestAggregate:
    """Tests for the aggregate task."""

    EVENT: ClassVar[dict] = {
        "preprocess_result": {"document_id": "doc-1", "s3_bucket": "bucket"},
        "classify_result": {"document_type": "drug_approval", "confidence": 0.9},
        "extract_result": {"extracted_fields": {"drug_name": "X"}, "confidence": 0.7},
    }

    def test_writes_summary_to_results_prefix(self, mocker):
        """The summary goes to results/{document_id}.json in the document's bucket."""
        s3 = mocker.MagicMock()
        mocker.patch("tasks.aggregate.get_s3_client", return_value=s3)

        aggregate_results(self.EVENT)

        request = s3.put_object.call_args.kwargs
        assert request["Bucket"] == "bucket"
        assert request["Key"] == "results/doc-1.json"
        assert json.loads(request["Body"]) == {
            "document_id": "doc-1",
            "document_type": "drug_approval",
            "classification_confidence": 0.9,
            "extracted_fields": {"drug_name": "X"},
            "extraction_confidence": 0.7,
            "status": "completed",
        }

    def test_returns_contract(self, mocker):
        """The state machine reads document_id, document_type and status."""
        mocker.patch("tasks.aggregate.get_s3_client", return_value=mocker.MagicMock())

        result = aggregate_results(self.EVENT)

        assert result["document_id"] == "doc-1"
        assert result["document_type"] == "drug_approval"
        assert result["status"] == "completed"
