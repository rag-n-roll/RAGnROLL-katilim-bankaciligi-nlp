"""Deterministik para, oran ve süre normalizasyonu."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import re


_CURRENCIES = {
    "₺": "TRY",
    "tl": "TRY",
    "try": "TRY",
    "$": "USD",
    "usd": "USD",
    "€": "EUR",
    "eur": "EUR",
    "£": "GBP",
    "gbp": "GBP",
}
_NUMBER_RE = re.compile(r"\d[\d.,]*")
_MONEY_RE = re.compile(
    r"(?:"
    r"(?P<leading_currency>₺|\$|€|£|\b(?:TL|TRY|USD|EUR|GBP)\b)\s*"
    r"(?P<leading_number>\d[\d.,]*(?:\s+milyon)?)"
    r"|(?P<trailing_number>\d[\d.,]*(?:\s+milyon)?)\s*"
    r"(?P<trailing_currency>₺|\$|€|£|\b(?:TL|TRY|USD|EUR|GBP)\b)"
    r")",
    re.IGNORECASE,
)
_RATE_RE = re.compile(r"(?:%\s*(\d[\d.,]*)|(\d[\d.,]*)\s*%)")
_DURATION_RE = re.compile(r"(?<!\d)(\d{1,4})\s*(gün|gun|ay|yıl|yil)(?!\w)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    @property
    def minor_units(self) -> int:
        return int((self.amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def to_dict(self) -> dict[str, float | str]:
        return {"amount": float(self.amount), "currency": self.currency}


@dataclass(frozen=True, slots=True)
class Rate:
    fraction: Decimal


@dataclass(frozen=True, slots=True)
class Duration:
    value: int
    unit: str
    approx_days: int

    def to_dict(self) -> dict[str, int | str]:
        return {"value": self.value, "unit": self.unit, "approx_days": self.approx_days}


def parse_number(value: str) -> Decimal | None:
    """Belirlenmiş Türkçe/uluslararası ayırıcı kuralıyla Decimal üretir."""
    match = _NUMBER_RE.search(str(value))
    if not match:
        return None
    raw = match.group(0)
    dots = [index for index, char in enumerate(raw) if char == "."]
    commas = [index for index, char in enumerate(raw) if char == ","]
    if dots and commas:
        decimal_index = max(dots[-1], commas[-1])
        integer = raw[:decimal_index].replace(".", "").replace(",", "")
        normalized = f"{integer}.{raw[decimal_index + 1:]}"
    elif dots or commas:
        separator = "." if dots else ","
        positions = dots or commas
        tail_length = len(raw) - positions[-1] - 1
        if tail_length in (1, 2):
            integer = raw[:positions[-1]].replace(separator, "")
            normalized = f"{integer}.{raw[positions[-1] + 1:]}"
        else:
            normalized = raw.replace(separator, "")
    else:
        normalized = raw
    try:
        return Decimal(normalized)
    except ArithmeticError:
        return None


def normalize_money(value: str) -> Money | None:
    source = str(value or "")
    match = _MONEY_RE.search(source)
    if not match:
        return None
    number_source = match.group("leading_number") or match.group("trailing_number")
    currency_source = match.group("leading_currency") or match.group("trailing_currency")
    number = parse_number(number_source)
    if number is None or currency_source is None:
        return None
    multiplier = (
        Decimal("1000000")
        if re.search(r"\bmilyon\b", number_source, re.IGNORECASE)
        else Decimal("1")
    )
    currency = _CURRENCIES[currency_source.casefold()]
    return Money(amount=number * multiplier, currency=currency)


def normalize_rate(value: str) -> Rate | None:
    match = _RATE_RE.search(str(value or ""))
    if not match:
        return None
    number = parse_number(match.group(1) or match.group(2))
    if number is None:
        return None
    return Rate(fraction=number / Decimal("100"))


def normalize_duration(value: str) -> Duration | None:
    match = _DURATION_RE.search(str(value or ""))
    if not match:
        return None
    amount = int(match.group(1))
    raw_unit = match.group(2).casefold()
    unit = {"gün": "day", "gun": "day", "ay": "month", "yıl": "year", "yil": "year"}[raw_unit]
    days_per_unit = {"day": 1, "month": 30, "year": 365}
    return Duration(value=amount, unit=unit, approx_days=amount * days_per_unit[unit])
