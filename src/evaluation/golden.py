"""Dondurulmuş değerlendirme kayıtları için deterministik kalite ölçümü."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from src.extraction.campaign_fields import extract_prd_fields
from src.normalization import normalize_duration, normalize_money, normalize_rate
from src.query import DomainQueryCompiler


SUPPORTED_EXTRACTION_FIELDS = {
    "profit_rate": "profit_share_rate",
    "financing_amount": "financing_amount",
    "maturity": "term_months",
    "application_channel": "application_channel",
    "condition": "condition",
    "benefit": "campaign_benefit",
}


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("i̇", "i").split())


def _expected_value(field: str, value: Any) -> Any:
    if field == "profit_rate":
        normalized = normalize_rate(str(value))
        return round(float(normalized.fraction), 6) if normalized else None
    if field == "financing_amount":
        normalized = normalize_money(str(value))
        return normalized.to_dict() if normalized else None
    if field == "maturity":
        normalized = normalize_duration(str(value))
        return int(normalized.value) if normalized and normalized.unit == "month" else None
    return _normalized_text(value)


def _actual_value(field: str, extraction: dict[str, Any]) -> Any:
    value = extraction.get(SUPPORTED_EXTRACTION_FIELDS[field])
    if field in {"application_channel", "condition", "benefit"}:
        return _normalized_text(value)
    return value


def evaluate_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Desteklenen alanları ölçer, ölçülmeyen alanları başarıya dahil etmez."""
    compiler = DomainQueryCompiler()
    intent_total = 0
    intent_correct = 0
    extraction_total = 0
    extraction_correct = 0
    unsupported: dict[str, int] = {}
    failures: list[dict[str, Any]] = []

    for record in records:
        identifier = str(record.get("id") or "unknown")
        text = str(record.get("input") or "")
        task = str(record.get("task") or "")
        gold = record.get("gold") if isinstance(record.get("gold"), dict) else {}
        if task == "intent_classification" and gold.get("intent"):
            intent_total += 1
            predicted = compiler.compile(text).intent
            if predicted == gold["intent"]:
                intent_correct += 1
            else:
                failures.append(
                    {
                        "id": identifier,
                        "field": "intent",
                        "expected": gold["intent"],
                        "actual": predicted,
                    }
                )
            continue

        extraction = extract_prd_fields(text)
        for field, expected in gold.items():
            if field not in SUPPORTED_EXTRACTION_FIELDS:
                unsupported[field] = unsupported.get(field, 0) + 1
                continue
            extraction_total += 1
            normalized_expected = _expected_value(field, expected)
            actual = _actual_value(field, extraction)
            matches = actual == normalized_expected
            if field in {"condition", "benefit"}:
                matches = bool(normalized_expected) and normalized_expected in actual
            if matches:
                extraction_correct += 1
            else:
                failures.append(
                    {
                        "id": identifier,
                        "field": field,
                        "expected": normalized_expected,
                        "actual": actual,
                    }
                )

    def ratio(correct: int, total: int) -> float | None:
        return round(correct / total, 4) if total else None

    return {
        "intent": {
            "correct": intent_correct,
            "total": intent_total,
            "exact_match": ratio(intent_correct, intent_total),
        },
        "supported_extraction_fields": {
            "correct": extraction_correct,
            "total": extraction_total,
            "exact_match": ratio(extraction_correct, extraction_total),
        },
        "unsupported_gold_fields": unsupported,
        "failure_count": len(failures),
        "failures": failures[:100],
        "notes": (
            "Yalnız açıkça desteklenen alanlar skora dahil edilir; desteklenmeyen "
            "gold alanları ayrıca raporlanır."
        ),
    }


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Geçersiz JSONL satırı: {line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"JSONL satırı nesne olmalıdır: {line_number}")
        rows.append(value)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(evaluate_records(load_jsonl(args.dataset)), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
