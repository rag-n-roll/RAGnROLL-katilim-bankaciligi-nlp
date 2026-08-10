from decimal import Decimal

import pytest

from src.normalization import normalize_duration, normalize_money, normalize_rate


@pytest.mark.parametrize(
    ("raw", "amount", "currency"),
    [
        ("10.000 TL", Decimal("10000"), "TRY"),
        ("10,000 TL", Decimal("10000"), "TRY"),
        ("10.000,50 TL", Decimal("10000.50"), "TRY"),
        ("10,000.50 USD", Decimal("10000.50"), "USD"),
        ("₺10.000", Decimal("10000"), "TRY"),
        ("1,5 milyon TL", Decimal("1500000"), "TRY"),
        ("£25.50", Decimal("25.50"), "GBP"),
    ],
)
def test_normalize_money_handles_turkish_and_international_formats(raw, amount, currency):
    result = normalize_money(raw)

    assert result is not None
    assert result.amount == amount
    assert result.currency == currency
    assert result.minor_units == int(amount * 100)


@pytest.mark.parametrize(
    ("raw", "fraction"),
    [("%45", Decimal("0.45")), ("45%", Decimal("0.45")), ("45,5%", Decimal("0.455"))],
)
def test_normalize_rate_requires_explicit_percent_sign(raw, fraction):
    result = normalize_rate(raw)

    assert result is not None
    assert result.fraction == fraction


@pytest.mark.parametrize("raw", ["45", "0.45", "avantajlı oranlar"])
def test_normalize_rate_does_not_guess_unmarked_values(raw):
    assert normalize_rate(raw) is None


@pytest.mark.parametrize(
    ("raw", "value", "unit", "approx_days"),
    [("32 gün", 32, "day", 32), ("3 ay", 3, "month", 90), ("1 yıl", 1, "year", 365)],
)
def test_normalize_duration_preserves_unit_and_adds_comparison_days(raw, value, unit, approx_days):
    result = normalize_duration(raw)

    assert result is not None
    assert (result.value, result.unit, result.approx_days) == (value, unit, approx_days)


def test_normalize_money_binds_currency_to_its_adjacent_amount():
    result = normalize_money("USD hesapta 100 TL kampanyası")

    assert result is not None
    assert result.amount == Decimal("100")
    assert result.currency == "TRY"


@pytest.mark.parametrize(("raw", "currency"), [("USD 100", "USD"), ("TRY 100", "TRY")])
def test_normalize_money_supports_leading_iso_currency_codes(raw, currency):
    result = normalize_money(raw)

    assert result is not None
    assert result.amount == Decimal("100")
    assert result.currency == currency
