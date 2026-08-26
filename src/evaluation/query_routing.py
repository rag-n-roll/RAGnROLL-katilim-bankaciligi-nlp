from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.knowledge import TerminologyService
from src.query import DomainQueryCompiler


def expected_calibration_error(
    rows: list[tuple[float, bool]], bins: int = 10
) -> float:
    total = len(rows)
    if not total:
        return 0.0
    error = 0.0
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        bucket = [
            (confidence, correct)
            for confidence, correct in rows
            if low <= confidence <= high
        ]
        if not bucket:
            continue
        accuracy = sum(correct for _, correct in bucket) / len(bucket)
        confidence = sum(value for value, _ in bucket) / len(bucket)
        error += len(bucket) / total * abs(accuracy - confidence)
    return round(error, 4)


def evaluate_routing(golden_path: str | Path) -> dict[str, Any]:
    path = Path(golden_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[2] / path
    lines = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    compiler = DomainQueryCompiler(terminology=TerminologyService())

    intent_correct = 0
    route_correct = 0
    sql_tp = 0
    sql_fp = 0
    sql_fn = 0
    calibration_rows: list[tuple[float, bool]] = []

    for item in lines:
        query = item["query"]
        expected_intent = item["expected_intent"]
        expected_route = item["expected_route"]
        sql_eligible = bool(item.get("sql_eligible", False))

        plan = compiler.compile(query)
        pred_intent = plan.intent
        pred_route = plan.route
        pred_confidence = float(plan.confidence)

        is_intent_match = pred_intent == expected_intent
        is_route_match = pred_route == expected_route

        if is_intent_match:
            intent_correct += 1
        if is_route_match:
            route_correct += 1

        is_sql = pred_route == "STRUCTURED_SQL"
        if is_sql and sql_eligible:
            sql_tp += 1
        elif is_sql and not sql_eligible:
            sql_fp += 1
        elif not is_sql and sql_eligible:
            sql_fn += 1

        calibration_rows.append((pred_confidence, is_intent_match))

    total = len(lines)
    sql_precision = (
        round(sql_tp / (sql_tp + sql_fp), 4) if (sql_tp + sql_fp) > 0 else 1.0
    )
    intent_match = round(intent_correct / total, 4) if total else 0.0
    route_acc = round(route_correct / total, 4) if total else 0.0
    ece = expected_calibration_error(calibration_rows)

    return {
        "total": total,
        "intent_exact_match": intent_match,
        "route_accuracy": route_acc,
        "sql_precision": sql_precision,
        "expected_calibration_error": ece,
    }
