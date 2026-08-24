"""İnceleme sonrası DSPy verisine çevrilebilen opt-in intent plan izleri."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any


class IntentTraceRecorder:
    """Ham kullanıcı metnini yalnız açıkça etkinleştirilmiş dosyaya kaydeder."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.getenv("RAGNROLL_INTENT_TRACE_PATH")
        self.path = Path(configured) if configured else None
        self._lock = Lock()

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def record(
        self,
        *,
        raw_input: str,
        bank_catalog: list[dict[str, Any]],
        deterministic_plan: dict[str, Any],
        llm_decision: dict[str, Any],
        selected_plan: dict[str, Any],
    ) -> None:
        if self.path is None:
            return
        item = {
            "schema_version": "2026.08",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "raw_input": str(raw_input)[:4000],
            "bank_catalog": bank_catalog,
            "deterministic_plan": deterministic_plan,
            "llm_decision": llm_decision,
            "selected_plan": selected_plan,
            "review_status": "pending",
            "reviewed_plan": None,
        }
        line = json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(line)


def load_reviewed_intent_examples(path: str | Path) -> list[dict[str, str]]:
    """Yalnız insan onaylı izleri DSPy IntentPlanner girdilerine dönüştürür."""

    examples = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Geçersiz intent izi: satır {line_number}") from exc
        if item.get("review_status") != "approved":
            continue
        reviewed = item.get("reviewed_plan")
        deterministic = item.get("deterministic_plan")
        if not isinstance(reviewed, dict) or not isinstance(deterministic, dict):
            raise ValueError(f"Onaylı intent izi eksik: satır {line_number}")
        examples.append(
            {
                "raw_input": str(item.get("raw_input") or ""),
                "canonical_query": str(deterministic.get("canonical_query") or ""),
                "deterministic_hint": json.dumps(
                    deterministic, ensure_ascii=False, sort_keys=True
                ),
                "bank_catalog": json.dumps(
                    item.get("bank_catalog") or [], ensure_ascii=False, sort_keys=True
                ),
                "intent_plan": json.dumps(reviewed, ensure_ascii=False, sort_keys=True),
            }
        )
    return examples
