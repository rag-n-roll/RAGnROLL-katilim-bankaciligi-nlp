import pytest

from src.extraction.campaign_fields import extract_prd_fields


def test_extracts_financing_fields_with_evidence():
    result = extract_prd_fields(
        "Yeni müşterilere özel %2,05 kâr payı oranı, 36 ay vade ve "
        "masrafsız ihtiyaç finansmanı."
    )

    assert result["product_type"] == "financing"
    assert result["financing_type"] == "consumer"
    assert result["profit_share_rate"] == 0.0205
    assert result["term_months"] == 36
    assert result["target_audience"] == "new_customer"
    assert result["fee_information"] == "masrafsız"
    assert result["evidence"]["profit_share_rate"] == "%2,05 kâr payı oranı"


def test_extracts_reward_discount_and_installments():
    result = extract_prd_fields(
        "Kartınızla 4 taksit ve %10 indirim; en fazla 500 TL nakit ödül."
    )

    assert result["product_type"] == "card"
    assert result["installment_count"] == 4
    assert result["discount_rate"] == 0.10
    assert result["reward_amount"] == {"amount": 500.0, "currency": "TRY"}


def test_missing_values_are_null_not_guessed():
    result = extract_prd_fields("Avantajlı ürünümüzü keşfedin.")

    assert result["profit_share_rate"] is None
    assert result["term_months"] is None
    assert result["extraction_method"] == "rules-v1"


def test_extracts_normalized_amount_and_duration_with_evidence():
    result = extract_prd_fields(
        "Yeni müşterilere 100.000 TL'ye kadar, 3 ay vadeli finansman fırsatı."
    )

    assert result["max_amount"] == {"amount": 100000.0, "currency": "TRY"}
    assert result["duration"] == {"value": 3, "unit": "month", "approx_days": 90}
    assert result["target_audience"] == "new_customer"
    assert result["evidence"]["max_amount"] == "100.000 TL'ye kadar"


def test_extracts_min_amount_day_duration_and_evidence_for_inferred_fields():
    result = extract_prd_fields(
        "Yeni müşterilere en az 1.000 TL ile 32 gün vadeli ihtiyaç finansmanı ve 45% indirim."
    )

    assert result["min_amount"] == {"amount": 1000.0, "currency": "TRY"}
    assert result["duration"] == {"value": 32, "unit": "day", "approx_days": 32}
    assert result["discount_rate"] == 0.45
    assert result["evidence"]["product_type"] == "ihtiyaç finansmanı"
    assert result["evidence"]["financing_type"] == "ihtiyaç"
    assert result["evidence"]["target_audience"] == "Yeni müşterilere"


@pytest.mark.parametrize(
    ("text", "field", "expected"),
    [
        ("Altın yatırımı ile getiri", "product_type", "Altın"),
        ("Alışveriş puanı kazanın", "product_type", "Alışveriş puanı"),
        ("Worldpuan kazanın", "product_type", "Worldpuan"),
        ("Parafpara kazanın", "product_type", "Parafpara"),
        ("alisveris puan kazanın", "product_type", "alisveris puan"),
        ("İlk kez müşteri kampanyası", "product_type", "İlk kez müşteri"),
        ("Yeni musteri kampanyası", "target_audience", "Yeni musteri"),
    ],
)
def test_every_classified_field_has_source_evidence(text, field, expected):
    result = extract_prd_fields(text)

    assert result["evidence"][field] == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Konut finansmanı", "financing"),
        ("Kart harcamanıza bonus", "card"),
        ("Altın katılma hesabı yatırım ürünü", "investment"),
        ("Alışveriş puanı kazanın", "shopping_points"),
        ("İlk kez müşteri olanlara özel", "new_customer"),
    ],
)
def test_classifies_prd_product_types(text: str, expected: str):
    assert extract_prd_fields(text)["product_type"] == expected
