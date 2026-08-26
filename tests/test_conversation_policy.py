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
