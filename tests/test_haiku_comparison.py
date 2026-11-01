"""Compare real Haiku results with the expected results in tests/expected/.

Calling Haiku needs AWS access and costs money, so it only runs through
`make test-haiku`. The other tests here check the expected files and the
comparison itself, and run offline with `make test`.
"""

import json
import os
from pathlib import Path

import pytest

from tasks.classify import classify_document
from tasks.extract import extract_fields

ROOT = Path(__file__).parent.parent
EXPECTED_FILES = sorted((ROOT / "tests" / "expected").glob("*.json"))
DOCUMENT_NAMES = [path.stem for path in EXPECTED_FILES]


def load_case(name):
    """Return the source document and its expected result."""
    document = json.loads((ROOT / "data" / f"{name}.json").read_text())
    expected = json.loads((ROOT / "tests" / "expected" / f"{name}.json").read_text())
    return document, expected


def as_text(value):
    """Flatten a field value to lowercase text for phrase checks."""
    return json.dumps(value, ensure_ascii=False).lower()


def compare_field(expected, actual, checks):
    """Return a list of problems with one extracted field. Empty means it matches."""
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return [f"expected a list, got {type(actual).__name__}"]
        if len(actual) != len(expected):
            return [f"expected {len(expected)} items, got {len(actual)}"]
    elif not isinstance(actual, str):
        return [f"expected text, got {type(actual).__name__}"]

    text = as_text(actual)
    problems = [f"missing {phrase!r}" for phrase in checks["must_contain"] if as_text(phrase)[1:-1] not in text]
    problems += [
        f"should not include {phrase!r}" for phrase in checks["must_not_contain"] if as_text(phrase)[1:-1] in text
    ]
    return problems


def compare_result(expected, actual_type, actual_fields):
    """Return {name: problems} for the document type and every extracted field."""
    problems = {}
    if actual_type != expected["document_type"]:
        problems["document_type"] = [f"expected {expected['document_type']!r}, got {actual_type!r}"]

    for field, expected_value in expected["extracted_fields"].items():
        if field not in actual_fields:
            problems[field] = ["field is missing"]
            continue
        field_problems = compare_field(expected_value, actual_fields[field], expected["checks"][field])
        if field_problems:
            problems[field] = field_problems

    for field in actual_fields.keys() - expected["extracted_fields"].keys():
        problems[field] = ["field was not requested"]
    return problems


def format_report(name, expected, actual_type, actual_fields, problems, confidences):
    """Show the expected and actual value of every field, side by side."""
    lines = [f"\n=== {name}", f"confidence: classify {confidences[0]}, extract {confidences[1]}"]
    rows = [("document_type", expected["document_type"], actual_type)]
    rows += [(field, value, actual_fields.get(field)) for field, value in expected["extracted_fields"].items()]
    rows += [
        (field, None, actual_fields[field]) for field in actual_fields.keys() - expected["extracted_fields"].keys()
    ]
    for field, expected_value, actual_value in rows:
        lines.append(f"[{'DIFF' if field in problems else 'OK'}] {field}")
        lines.append(f"  expected: {json.dumps(expected_value, ensure_ascii=False)}")
        lines.append(f"  actual:   {json.dumps(actual_value, ensure_ascii=False)}")
        lines += [f"  problem:  {problem}" for problem in problems.get(field, [])]
    return "\n".join(lines)


@pytest.mark.parametrize("name", DOCUMENT_NAMES)
class TestExpectedFiles:
    """Catch mistakes in the expected files before comparing Haiku against them."""

    def test_covers_the_fields_for_the_type(self, name):
        """Each expected value has its checks, and every field has a check to apply."""
        _, expected = load_case(name)

        assert expected["extracted_fields"].keys() == expected["checks"].keys()
        assert all(checks["must_contain"] for checks in expected["checks"].values())

    def test_expected_values_pass_their_own_checks(self, name):
        """The planned answer has to pass the comparison."""
        _, expected = load_case(name)

        assert compare_result(expected, expected["document_type"], expected["extracted_fields"]) == {}

    def test_check_phrases_come_from_the_document(self, name):
        """A phrase the document doesn't contain would be a typo in the checks."""
        document, expected = load_case(name)
        source = as_text(f"{document['title']} {document['content']}")

        for checks in expected["checks"].values():
            for phrase in checks["must_contain"] + checks["must_not_contain"]:
                assert as_text(phrase)[1:-1] in source, phrase


class TestComparison:
    """The comparison has to catch the mistakes the expected files are there to catch."""

    @pytest.mark.parametrize(
        ("name", "field", "wrong_value", "problem"),
        [
            ("financial-filing", "revenue", "$78 million", "should not include '$78 million'"),
            ("airworthiness-directive", "compliance_deadline", "Within 18 months", "missing 'May 22, 2024'"),
            ("drug-approval", "dosage", "Oral tablet, 6 mg and 12 mg", "missing '6 mg once daily'"),
            ("cybersecurity-advisory", "cve_ids", "CVE-2023-27997", "expected a list, got str"),
            ("cybersecurity-advisory", "mitigation_steps", ["Apply patches."], "expected 6 items, got 1"),
            ("financial-filing", "net_income", None, "expected text, got NoneType"),
        ],
    )
    def test_wrong_value_is_reported(self, name, field, wrong_value, problem):
        _, expected = load_case(name)
        actual = {**expected["extracted_fields"], field: wrong_value}

        assert problem in compare_result(expected, expected["document_type"], actual)[field]

    def test_wrong_type_is_reported(self):
        _, expected = load_case("drug-approval")

        assert "document_type" in compare_result(expected, "unknown", expected["extracted_fields"])

    def test_missing_and_extra_fields_are_reported(self):
        _, expected = load_case("drug-approval")
        actual = {**expected["extracted_fields"], "patent_expiry": "2038"}
        del actual["applicant"]

        problems = compare_result(expected, expected["document_type"], actual)

        assert problems == {"applicant": ["field is missing"], "patent_expiry": ["field was not requested"]}

    def test_differences_in_case_are_accepted(self):
        _, expected = load_case("financial-filing")
        actual = {**expected["extracted_fields"], "company_name": "MERIDIAN TECHNOLOGIES INC."}

        assert compare_result(expected, expected["document_type"], actual) == {}


@pytest.mark.skipif(not os.environ.get("RUN_HAIKU_TESTS"), reason="calls real Haiku; run with make test-haiku")
@pytest.mark.parametrize("name", DOCUMENT_NAMES)
def test_haiku_matches_expected(name):
    """Run each sample document through the real functions, in the pipeline's order."""
    document, expected = load_case(name)
    event = {
        "document_id": name,
        "title": document["title"],
        "content": document["content"],
        "source": document["source"],
    }

    classified = classify_document(event)
    extracted = extract_fields({**event, "document_type": classified["document_type"]})

    actual_type = classified["document_type"]
    actual_fields = extracted["extracted_fields"]
    problems = compare_result(expected, actual_type, actual_fields)
    confidences = (classified["classification_confidence"], extracted["extraction_confidence"])
    report = format_report(name, expected, actual_type, actual_fields, problems, confidences)
    print(report)
    assert not problems, report
