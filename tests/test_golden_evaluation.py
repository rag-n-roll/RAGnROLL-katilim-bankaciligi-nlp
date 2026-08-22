import json

import pytest

from src.evaluation.golden import evaluate_records, load_jsonl


def test_golden_evaluator_separates_supported_and_unsupported_fields():
    report = evaluate_records(
        [
            {
                "id": "intent",
                "task": "intent_classification",
                "input": "Murabaha nedir?",
                "gold": {"intent": "definition"},
            },
            {
                "id": "extract",
                "task": "product_extraction",
                "input": "%2,25 kâr payı ile 48 ay vadeli finansman.",
                "gold": {
                    "profit_rate": "%2,25",
                    "maturity": "48 ay",
                    "product": "Örnek ürün",
                },
            },
        ]
    )

    assert report["intent"]["exact_match"] == 1.0
    assert report["supported_extraction_fields"]["exact_match"] == 1.0
    assert report["unsupported_gold_fields"] == {"product": 1}
    assert report["failure_count"] == 0


def test_golden_evaluator_reports_mismatch_without_masking_it():
    report = evaluate_records(
        [
            {
                "id": "bad-rate",
                "task": "product_extraction",
                "input": "%2,25 kâr payı ile finansman.",
                "gold": {"profit_rate": "%1,99"},
            }
        ]
    )

    assert report["supported_extraction_fields"]["exact_match"] == 0.0
    assert report["failures"][0]["id"] == "bad-rate"


def test_jsonl_loader_reports_line_number_for_invalid_input(tmp_path):
    path = tmp_path / "golden.jsonl"
    path.write_text(json.dumps({"id": "ok"}) + "\n{broken}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="satırı: 2"):
        load_jsonl(path)
