from src.policy import Action, PolicyDecision
from src.policy.validator import PolicyValidator


def test_out_of_domain_decision_cannot_call_tools():
    decision = PolicyDecision(
        action=Action.ANSWER,
        in_domain=False,
        intent="product_search",
        confidence=0.92,
        reason_code="model_answer",
        tool_calls=({"name": "structured_sql", "arguments": {}},),
    )
    validated = PolicyValidator().validate(decision)
    assert validated.action == Action.REFUSE
    assert validated.tool_calls == ()


def test_subjective_comparison_requires_all_criteria():
    decision = PolicyDecision(
        action=Action.ANSWER,
        in_domain=True,
        intent="product_comparison",
        confidence=0.91,
        reason_code="comparison",
    )
    validated = PolicyValidator().validate(decision)
    assert validated.action == Action.CLARIFY
    assert validated.missing_criteria == ("term_months", "amount", "fee_priority")


def test_unknown_tool_is_removed_and_refused():
    decision = PolicyDecision(
        action=Action.ANSWER,
        in_domain=True,
        intent="product_search",
        confidence=0.8,
        reason_code="model_answer",
        tool_calls=({"name": "shell", "arguments": {}},),
    )
    validated = PolicyValidator().validate(decision)
    assert validated.action == Action.REFUSE
    assert validated.tool_calls == ()
    assert validated.reason_code == "invalid_tool_plan"
