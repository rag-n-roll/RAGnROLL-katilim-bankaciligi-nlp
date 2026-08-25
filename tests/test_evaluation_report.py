import json

from src.evaluation.report import build_report


def test_build_report_checks_kpis_and_synthetic_eligibility():
    report = build_report(
        {
            "synthetic_data_warning": True,
            "metrics": {"precision": 0.90, "recall": 0.81, "f1": 0.85},
        },
        {"evaluation": {"accuracy": 0.87}},
    )

    assert report["all_targets_met"] is True
    assert report["competition_metric_eligible"] is False
    assert report["kpis"]["ner_f1"]["target"] == 0.82


def test_build_report_flags_missing_metrics_and_fallback_accuracy_key():
    report = build_report(
        {},
        {"product_accuracy": 0.70},
    )

    assert report["all_targets_met"] is False
    assert report["kpis"]["ner_precision"]["value"] is None
    assert report["kpis"]["ner_precision"]["passed"] is False
    assert report["kpis"]["classification_accuracy"]["value"] == 0.70
    assert report["competition_metric_eligible"] is True
    assert "not marked as synthetic" in report["notes"]


def test_main_writes_report_file_and_prints_json(tmp_path, capsys):
    from src.evaluation.report import main

    ner_path = tmp_path / "ner.json"
    ner_path.write_text(
        json.dumps({"metrics": {"precision": 0.9, "recall": 0.85, "f1": 0.87}}),
        encoding="utf-8",
    )
    classifier_path = tmp_path / "classifier.json"
    classifier_path.write_text(json.dumps({"evaluation": {"accuracy": 0.9}}), encoding="utf-8")
    output = tmp_path / "out" / "report.json"

    import sys

    argv = sys.argv
    sys.argv = [
        "report.py",
        str(ner_path),
        str(classifier_path),
        "--output",
        str(output),
    ]
    try:
        main()
    finally:
        sys.argv = argv

    rendered = json.loads(output.read_text(encoding="utf-8"))
    assert rendered["all_targets_met"] is True
    assert json.loads(capsys.readouterr().out) == rendered
