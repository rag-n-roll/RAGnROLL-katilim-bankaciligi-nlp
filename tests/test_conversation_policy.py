from src.policy import ComparisonCriteria
from src.services.conversation import merge_criteria


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
