"""Stateless conversation helpers for comparison clarification."""

from dataclasses import replace
import re
from typing import Any

from src.normalization import normalize_money
from src.normalization.values import parse_number
from src.policy import ComparisonCriteria


_TERM_RE = re.compile(r"(?<!\d)(\d{1,4})\s*ay(?:l[ıi]k)?\b", re.IGNORECASE)
_MONEY_RE = re.compile(
    r"(?<!\d)(\d[\d.,]*)\s*(bin|milyon)?\s*(?:(?:TL|TRY)\b|₺)",
    re.IGNORECASE,
)
_FEE_NEGATIVE_RE = re.compile(
    r"masraf(?:\s+benim)?\s+(?:önemli|onemli|önceliğim|onceligim)\s+değil",
    re.IGNORECASE,
)
_FEE_POSITIVE_RE = re.compile(
    r"(?:masraf\s+(?:öncelikli|oncelikli|önemli|onemli)|"
    r"(?:düşük|dusuk|az)\s+masraf)",
    re.IGNORECASE,
)


def extract_comparison_criteria(message: str) -> dict[str, Any]:
    """Extract only explicit, bounded comparison criteria from Turkish text."""

    updates: dict[str, Any] = {}
    term_match = _TERM_RE.search(message)
    if term_match:
        term_months = int(term_match.group(1))
        if 1 <= term_months <= 1200:
            updates["term_months"] = term_months

    money_match = _MONEY_RE.search(message)
    if money_match:
        token = money_match.group(0)
        multiplier = (money_match.group(2) or "").casefold()
        if multiplier:
            base = parse_number(money_match.group(1))
            factor = 1_000 if multiplier == "bin" else 1_000_000
            amount = float(base) * factor if base is not None else None
        else:
            money = normalize_money(token)
            amount = float(money.amount) if money is not None else None
        if amount is not None and 0 < amount <= 1_000_000_000:
            updates["amount"] = amount

    if _FEE_NEGATIVE_RE.search(message):
        updates["fee_priority"] = False
    elif _FEE_POSITIVE_RE.search(message):
        updates["fee_priority"] = True
    return updates


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
