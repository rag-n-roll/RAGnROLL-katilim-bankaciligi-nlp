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
