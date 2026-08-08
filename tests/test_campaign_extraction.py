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
