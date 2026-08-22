from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.extraction.campaign_nlp_pipeline import normalize_entity
from src.extraction.date_range import extract_date_range


def test_normalizes_turkish_rate_and_money() -> None:
    assert normalize_entity("INDIRIM_ORANI", "%2,87") == {
        "type": "rate",
        "fraction": pytest.approx(0.0287),
        "percent": pytest.approx(2.87),
    }
    assert normalize_entity("KAMPANYA_KOSULU", "750 TL") == {
        "type": "money",
        "amount": 750.0,
        "currency": "TRY",
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("36 ay", {"type": "duration", "value": 36, "unit": "month", "approx_days": 1080}),
        ("7 gün", {"type": "duration", "value": 7, "unit": "day", "approx_days": 7}),
        ("2 yıl", {"type": "duration", "value": 2, "unit": "year", "approx_days": 730}),
    ],
)
def test_normalizes_duration(value: str, expected: dict[str, object]) -> None:
    assert normalize_entity("VADE", value) == expected


def test_normalizes_installments_and_promotion_code() -> None:
    assert normalize_entity("TAKSIT_SAYISI", "vade farksız 6 taksit") == {
        "type": "installment",
        "count": 6,
    }
    assert normalize_entity("PROMOSYON_KODU", " KUVEYT360 ") == {
        "type": "code",
        "value": "KUVEYT360",
    }


def test_extracts_numeric_and_turkish_textual_ranges() -> None:
    assert tuple(value.isoformat() for value in extract_date_range("01-04-2025 - 31-12-2026")) == (
        "2025-04-01",
        "2026-12-31",
    )
    values = extract_date_range("1 Kasım 2025 – 31 Ekim 2026")
    assert tuple(value.isoformat() for value in values) == (
        "2025-11-01",
        "2026-10-31",
    )


def test_output_schema_is_valid_json() -> None:
    schema = Path("data/model_training_data/campaign_nlp_output_schema.json")
    payload = json.loads(schema.read_text(encoding="utf-8"))
    assert payload["properties"]["schema_version"]["const"] == "campaign-nlp-v1"
