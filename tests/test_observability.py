import pytest

from src.observability import EventRecorder


def test_event_summary_reports_failures_percentiles_and_routes():
    recorder = EventRecorder(capacity=3)
    recorder.record("query", latency_ms=10, route="STRUCTURED_SQL")
    recorder.record("query", latency_ms=20, success=False, route="HYBRID_RAG")
    recorder.record("query", latency_ms=30, route="STRUCTURED_SQL")

    summary = recorder.summary()["events"]["query"]

    assert summary["count"] == 3
    assert summary["error_count"] == 1
    assert summary["error_rate"] == 0.3333
    assert summary["p50_latency_ms"] == 20
    assert summary["p95_latency_ms"] == 30
    assert summary["routes"] == {"STRUCTURED_SQL": 2, "HYBRID_RAG": 1}


@pytest.mark.parametrize("latency", (-1, float("nan"), float("inf")))
def test_event_recorder_rejects_invalid_latency(latency):
    with pytest.raises(ValueError, match="latency_ms"):
        EventRecorder().record("query", latency_ms=latency)


def test_event_recorder_capacity_discards_oldest_event():
    recorder = EventRecorder(capacity=1)
    recorder.record("old", latency_ms=1)
    recorder.record("new", latency_ms=2)

    assert recorder.summary()["event_count"] == 1
    assert set(recorder.summary()["events"]) == {"new"}
