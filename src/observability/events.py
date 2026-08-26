"""Harici servis gerektirmeyen sınırlı boyutlu observability event deposu."""

from __future__ import annotations

from collections import Counter, deque
from datetime import datetime, timezone
from math import ceil, isfinite
from threading import Lock
from typing import Any


class EventRecorder:
    """Gizli içerik tutmadan gecikme, rota ve hata metriklerini toplar."""

    def __init__(self, *, capacity: int = 2000) -> None:
        if capacity < 1:
            raise ValueError("capacity pozitif olmalıdır")
        self._events: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = Lock()

    def record(
        self,
        event: str,
        *,
        latency_ms: float,
        success: bool = True,
        **fields: Any,
    ) -> None:
        if not event.strip():
            raise ValueError("event boş olamaz")
        if not isfinite(latency_ms) or latency_ms < 0:
            raise ValueError("latency_ms negatif veya sonlu olmayan değer olamaz")
        item = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": round(float(latency_ms), 3),
            "success": bool(success),
            **fields,
        }
        with self._lock:
            self._events.append(item)

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        index = max(0, ceil(percentile * len(ordered)) - 1)
        return round(ordered[index], 3)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            events = list(self._events)
        names = sorted({str(item["event"]) for item in events})
        by_event = {}
        for name in names:
            selected = [item for item in events if item["event"] == name]
            latencies = [float(item["latency_ms"]) for item in selected]
            failures = sum(not item["success"] for item in selected)
            routes = Counter(
                str(item["route"])
                for item in selected
                if item.get("route") is not None
            )
            dimensions = {}
            for field in (
                "provider",
                "requested_model",
                "circuit_state",
                "retrieval_backend",
                "generation_mode",
                "fallback_reason",
                "action",
                "reason_code",
                "deduplicated_count",
                "evidence_coverage",
            ):
                counts = Counter(
                    str(item[field])
                    for item in selected
                    if item.get(field) is not None
                )
                if counts:
                    dimensions[field] = dict(counts)
            by_event[name] = {
                "count": len(selected),
                "error_count": failures,
                "error_rate": round(failures / len(selected), 4),
                "p50_latency_ms": self._percentile(latencies, 0.50),
                "p95_latency_ms": self._percentile(latencies, 0.95),
                "routes": dict(routes),
                "dimensions": dimensions,
            }
        return {"event_count": len(events), "events": by_event}
