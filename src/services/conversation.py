"""Stateless conversation helpers for comparison clarification."""

from dataclasses import replace
from typing import Any

from src.policy import ComparisonCriteria


def merge_criteria(
    current: ComparisonCriteria, updates: dict[str, Any]
) -> ComparisonCriteria:
    """Merge only supported, non-null comparison criteria."""

    allowed = {"term_months", "amount", "fee_priority"}
    clean = {
        key: value
        for key, value in updates.items()
        if key in allowed and value is not None
    }
    return replace(current, **clean)
