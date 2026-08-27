import pytest

from src.policy import ComparisonCriteria
from src.services.conversation import extract_comparison_criteria, merge_criteria


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


def test_unrelated_negation_does_not_invert_positive_fee_clause():
    assert extract_comparison_criteria(
        "Uzun vade önemli değil; masraf öncelikli."
    )["fee_priority"] is True
