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


def _run_cli(argv):
    import sys

    from src.evaluation.golden import main

    original = sys.argv
    sys.argv = argv
    try:
        return main()
    finally:
        sys.argv = original


def test_cli_writes_evaluation_report(tmp_path, capsys):
    dataset = tmp_path / "golden.jsonl"
    rows = [
        {
            "id": "g1",
            "task": "intent_classification",
            "input": "kaç kampanya var",
            "gold": {"intent": "campaign_count"},
        },
        {
            "id": "g2",
            "task": "field_extraction",
            "input": "%2,50 kâr payı ile 12 ay vadeli finansman",
            "gold": {"profit_rate": "%2,50", "maturity": "12 ay"},
        },
    ]
    dataset.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    output = tmp_path / "out" / "report.json"

    _run_cli(["golden.py", str(dataset), "--output", str(output)])

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["intent"]["exact_match"] == 1.0
    assert report["supported_extraction_fields"]["total"] == 2
    assert json.loads(capsys.readouterr().out) == report


def test_jsonl_loader_rejects_non_object_lines(tmp_path):
    from src.evaluation.golden import load_jsonl

    path = tmp_path / "bad.jsonl"
    path.write_text('"metin"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="nesne olmalıdır"):
        load_jsonl(path)
