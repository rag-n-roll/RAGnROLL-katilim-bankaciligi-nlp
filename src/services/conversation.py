"""Stateless conversation helpers for comparison clarification."""

from dataclasses import replace
import re
from typing import Any
import unicodedata

from src.normalization import normalize_money
from src.normalization.values import parse_number
from src.policy import ComparisonCriteria


_TERM_RE = re.compile(r"(?<!\d)(\d{1,4})\s*ay(?:l[ıi]k)?\b", re.IGNORECASE)
_TERM_RANGE_RE = re.compile(
    r"(?<!\d)(\d{1,3})\s*\.?\s*[-–—]\s*(\d{1,3})\s*ay(?:l[ıi]k)?\b",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(
    r"(?<!\d)(\d[\d.,]*)\s*(bin|milyon)?\s*(?:(?:TL|TRY)\b|₺)",
    re.IGNORECASE,
)
_FEE_POSITIVE_RE = re.compile(
    r"(?:"
    r"masraf\s+(?:oncelikli|onemli|oncelig(?:iyle|im(?:\s+var)?|ine\s+gore))"
    r"|(?:dusuk|az)\s+masraf"
    r"|masrafsiz|masraf\s+yok"
    r")",
    re.IGNORECASE,
)
_FEE_NEGATION_RE = re.compile(
    r"(?:"
    r"masraf\s+(?:oncelikli|onemli)(?:\s+olmasin)?\s+(?:degil|olmasin)"
    r"|masraf\s+onceligim\s+(?:degil|yok)"
    r"|masraf\s+onemli\s+degil"
    r"|(?:dusuk|az)\s+masraf\s+(?:istemiyorum|onceligim\s+degil)"
    r"|az\s+masraf\s+onceligim\s+degil"
    r")",
    re.IGNORECASE,
)

_BARE_NEGATIVE_FEE_RE = re.compile(
    r"^\s*(?:yok|hay[ıi]r|istemiyorum|[öo]nemli\s+de[gğ]il|fark\s+etmez)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_BARE_POSITIVE_FEE_RE = re.compile(
    r"^\s*(?:var|evet|olsun|istiyorum|[öo]nemli)\s*[.!]?\s*$",
    re.IGNORECASE,
)
_BARE_TERM_RESPONSE_RE = re.compile(r"^\s*(\d{1,3})\s*[.!]?\s*$")

FINANCING_TYPE_LABELS = {
    "consumer": "İhtiyaç finansmanı",
    "vehicle": "Taşıt finansmanı",
    "housing": "Konut finansmanı",
    "commercial": "Ticari/KOBİ finansmanı",
}
_FINANCING_TYPE_PATTERNS = {
    "consumer": re.compile(
        r"\b(?:ihtiyac|tuketici|borc\s+(?:transfer|kapatma))\s*(?:finansman\w*)?\b|"
        r"\b(?:evlilik|dugun|egitim|okul|saglik|tedavi|hac|umre|"
        r"tatil|seyahat|beyaz\s+esya|mobilya|tadilat|yenileme)\b"
        r"[^\n.!?]{0,80}?\s*finansman\w*\b"
    ),
    "vehicle": re.compile(
        r"\b(?:tasit|arac|otomobil|araba|togg|motosiklet)\s*(?:finansman\w*)?\b"
    ),
    "housing": re.compile(
        r"\b(?:konut|kentsel\s+donusum|gunes\s+enerji\w*)\s*(?:finansman\w*)?\b|"
        r"\b(?:ev|bina)\b[^\n.!?]{0,30}?\s*finansman\w*\b"
    ),
    "commercial": re.compile(
        r"\b(?:ticari|isletme|kobi|esnaf|hammadde|filo)\s*(?:finansman\w*)?\b"
    ),
}


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
    range_match = _TERM_RANGE_RE.search(message)
    if range_match:
        first, last = sorted((int(range_match.group(1)), int(range_match.group(2))))
        if 1 <= first <= last <= 240 and last - first <= 23:
            updates["term_months"] = last
            updates["term_months_min"] = first
            updates["term_months_max"] = last
    term_match = _TERM_RE.search(message)
    if term_match and "term_months" not in updates:
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


def extract_financing_type(message: str) -> str | None:
    """Extract one explicitly named, supported financing type."""

    normalized = _ascii_turkish(message)
    matches = [
        financing_type
        for financing_type, pattern in _FINANCING_TYPE_PATTERNS.items()
        if pattern.search(normalized)
    ]
    if not matches:
        return None
    # Explicit vehicle language wins over a commercial qualifier such as
    # "ticari" or "filo" (e.g. ticari taşıt finansmanı).
    if "vehicle" in matches:
        return "vehicle"
    # Commercial purpose cues are more specific than generic consumer
    # language (e.g. esnaf için ihtiyaç finansmanı).
    if "commercial" in matches:
        return "commercial"
    if "consumer" in matches:
        return "consumer"
    if len(matches) == 1:
        return matches[0]
    return None


def extract_contextual_fee_priority(message: str) -> bool | None:
    """Extract contextual boolean fee_priority from a short yes/no response."""

    normalized = _ascii_turkish(message.strip())
    if _BARE_NEGATIVE_FEE_RE.match(normalized):
        return False
    if _BARE_POSITIVE_FEE_RE.match(normalized):
        return True
    return None


def extract_contextual_term_months(message: str) -> int | None:
    """Extract a bare, bounded month count only for a pending term prompt."""

    match = _BARE_TERM_RESPONSE_RE.match(message)
    if match is None:
        return None
    term_months = int(match.group(1))
    return term_months if 1 <= term_months <= 240 else None


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
