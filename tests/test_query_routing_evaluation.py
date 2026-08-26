from src.evaluation.query_routing import evaluate_routing, expected_calibration_error


def test_expected_calibration_error_empty():
    assert expected_calibration_error([]) == 0.0


def test_expected_calibration_error_perfect():
    # Confidence matches empirical accuracy perfectly
    rows = [(0.95, True)] * 10 + [(0.05, False)] * 10
    # In bin [0.9, 1.0], avg conf is 0.95, acc is 1.0 (diff 0.05)
    # In bin [0.0, 0.1], avg conf is 0.05, acc is 0.0 (diff 0.05)
    ece = expected_calibration_error(rows)
    assert ece <= 0.06


def test_query_routing_reference_set_meets_quality_thresholds():
    report = evaluate_routing("tests/fixtures/query_routing_golden.jsonl")
    assert report["total"] >= 40
    assert report["intent_exact_match"] >= 0.85
    assert report["route_accuracy"] >= 0.85
    assert report["sql_precision"] >= 0.85
    assert report["expected_calibration_error"] <= 0.15
