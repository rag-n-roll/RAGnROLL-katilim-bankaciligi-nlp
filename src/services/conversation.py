"""Stateless conversation helpers for comparison clarification."""

from dataclasses import replace
import re
from typing import Any
import unicodedata

from src.normalization import normalize_money
from src.normalization.values import parse_number
from src.policy import ComparisonCriteria


_TERM_RE = re.compile(r"(?<!\d)(\d{1,4})\s*ay(?:l[ıi]k)?\b", re.IGNORECASE)
_MONEY_RE = re.compile(
    r"(?<!\d)(\d[\d.,]*)\s*(bin|milyon)?\s*(?:(?:TL|TRY)\b|₺)",
    re.IGNORECASE,
)
_FEE_POSITIVE_RE = re.compile(
    r"(?:masraf\s+(?:oncelikli|onemli)|(?:dusuk|az)\s+masraf)",
    re.IGNORECASE,
)
_FEE_NEGATION_RE = re.compile(
    r"(?:"
    r"masraf\s+(?:oncelikli|onemli)(?:\s+olmasin)?\s+(?:degil|olmasin)"
    r"|masraf\s+onceligim\s+degil"
    r"|(?:dusuk|az)\s+masraf\s+(?:istemiyorum|onceligim\s+degil)"
    r"|az\s+masraf\s+onceligim\s+degil"
    r")",
    re.IGNORECASE,
)


def _ascii_turkish(value: str) -> str:
    translated = value.casefold().translate(str.maketrans({"ı": "i"}))
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", translated)
        if not unicodedata.combining(character)
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

    normalized = _ascii_turkish(message)
    fee_clauses = re.split(r"[;,.!?]+", normalized)
    for clause in fee_clauses:
        if _FEE_NEGATION_RE.search(clause):
            updates["fee_priority"] = False
            break
        if _FEE_POSITIVE_RE.search(clause):
            updates["fee_priority"] = True
            break
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
