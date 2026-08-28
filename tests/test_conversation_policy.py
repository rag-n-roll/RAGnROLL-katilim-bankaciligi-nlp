import pytest

from src.policy import ComparisonCriteria
from src.services.conversation import (
    extract_comparison_criteria,
    extract_contextual_fee_priority,
    extract_contextual_term_months,
    extract_financing_type,
    merge_criteria,
)


def test_follow_up_completes_pending_comparison_criteria():
    current = ComparisonCriteria()
    merged = merge_criteria(
        current,
        {"term_months": 24, "amount": 750_000, "fee_priority": True},
    )
    assert merged.missing() == []
    assert merged.term_months == 24
    assert merged.amount == 750_000
    assert merged.fee_priority is True


def test_extracts_explicit_turkish_comparison_criteria():
    assert extract_comparison_criteria(
        "24 aylık, 750 bin TL; düşük masraf öncelikli"
    ) == {
        "term_months": 24,
        "amount": 750_000,
        "fee_priority": True,
    }


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("1-12 ay vade düşünüyorum", (1, 12)),
        ("1.-12 ay vade düşünüyorum", (1, 12)),
        ("6–8 ay arasında", (6, 8)),
        ("8-6 ay olabilir", (6, 8)),
    ],
)
def test_extracts_inclusive_financing_term_range(message, expected):
    extracted = extract_comparison_criteria(message)

    assert extracted["term_months_min"] == expected[0]
    assert extracted["term_months_max"] == expected[1]
    assert extracted["term_months"] == expected[1]


def test_extracts_fee_priority_in_instrumental_form():
    assert extract_comparison_criteria(
        "50.000 TL tutarda 12 ay vadeli, masraf önceliğiyle karşılaştır"
    ) == {
        "term_months": 12,
        "amount": 50_000,
        "fee_priority": True,
    }


def test_extracts_fee_free_preference_and_supported_financing_type():
    assert extract_comparison_criteria("200.000 TL masrafsız olsun") == {
        "amount": 200_000,
        "fee_priority": True,
    }
    assert extract_financing_type("İhtiyaç finansmanı istiyorum") == "consumer"
    assert extract_financing_type("Ticari/KOBİ finansmanı istiyorum") == "commercial"
    assert extract_financing_type("eğitim kampanyaları") is None
    assert extract_financing_type("eğitim finansmanı") == "consumer"
    assert extract_financing_type("sağlık kampanyaları") is None
    assert extract_financing_type("sağlık finansmanı") == "consumer"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Evlilik ve düğün masrafları için finansman.", "consumer"),
        ("Eğitim ve okul ücreti finansmanı hesapla.", "consumer"),
        ("Sağlık ve tedavi masrafları için finansman.", "consumer"),
        ("Hac ve Umre ibadeti için finansman.", "consumer"),
        ("Tatil ve seyahat için tüketici finansmanı.", "consumer"),
        ("Beyaz eşya ve mobilya alımı için ihtiyaç finansmanı.", "consumer"),
        ("Tadilat ve ev yenileme finansmanı.", "consumer"),
        ("Esnaf için hammadde alım finansmanı.", "commercial"),
        ("Ticari araç ve filo taşıt finansmanı.", "vehicle"),
    ],
)
def test_extracts_financing_type_from_consumer_and_commercial_purposes(
    message, expected
):
    assert extract_financing_type(message) == expected


def test_fee_priority_negation_wins_over_positive_word():
    assert extract_comparison_criteria("Masraf önemli değil") == {
        "fee_priority": False
    }


def test_ambiguous_and_out_of_range_numbers_are_not_extracted():
    assert extract_comparison_criteria("24 ve 750000") == {}
    assert extract_comparison_criteria("1201 ay, 2 milyar TL") == {}


def test_extracts_lira_symbol_amount_and_explicit_non_priority():
    assert extract_comparison_criteria("500.000 ₺, masraf önceliğim değil") == {
        "amount": 500_000,
        "fee_priority": False,
    }


def test_fee_priority_negation_variants_are_false():
    for message in (
        "masraf öncelikli değil",
        "masraf onemli degil",
        "masraf önemli olmasın",
        "düşük masraf istemiyorum",
        "az masraf önceliğim değil",
    ):
        assert extract_comparison_criteria(message) == {"fee_priority": False}


def test_extract_contextual_fee_priority():
    for msg in ("yok", "hayır", "hayir", "istemiyorum", "önemli değil", "onemli degil", "yok."):
        assert extract_contextual_fee_priority(msg) is False

    for msg in ("var", "evet", "olsun", "istiyorum", "önemli", "onemli", "evet!"):
        assert extract_contextual_fee_priority(msg) is True

    for msg in ("24 ay", "500.000 TL", "merhaba", "konut finansmanı"):
        assert extract_contextual_fee_priority(msg) is None


@pytest.mark.parametrize("message", ("12", "18.", "240"))
def test_extract_contextual_term_months_from_bare_bounded_response(message):
    assert extract_contextual_term_months(message) == int(message.rstrip("."))


@pytest.mark.parametrize(
    "message", ("0", "241", "12 ay", "12 gün", "500.000 TL", "12,5")
)
def test_contextual_term_months_rejects_non_bare_or_out_of_range_response(message):
    assert extract_contextual_term_months(message) is None


def test_unrelated_negation_does_not_invert_positive_fee_clause():
    assert extract_comparison_criteria(
        "Uzun vade önemli değil; masraf öncelikli."
    )["fee_priority"] is True
