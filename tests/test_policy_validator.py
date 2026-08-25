import math

import pytest

from src.policy import Action, ComparisonCriteria, PolicyDecision
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


def test_declared_clarification_gets_deterministic_missing_comparison_criteria():
    decision = PolicyDecision(
        action=Action.CLARIFY,
        in_domain=True,
        intent="product_comparison",
        confidence=0.7,
        reason_code="model_clarify",
        tool_calls=({"name": "comparison", "arguments": {}},),
    )
    validated = PolicyValidator().validate(decision)
    assert validated.action == Action.CLARIFY
    assert validated.missing_criteria == ("term_months", "amount", "fee_priority")
    assert validated.tool_calls == ()
    assert validated.reason_code == "missing_comparison_criteria"


@pytest.mark.parametrize("action", [Action.REFUSE, Action.REDIRECT])
def test_missing_comparison_criteria_overrides_declared_terminal_action(action):
    decision = PolicyDecision(
        action=action,
        in_domain=True,
        intent="product_comparison",
        confidence=0.7,
        reason_code="model_terminal",
        tool_calls=({"name": "comparison", "arguments": {}},),
    )
    validated = PolicyValidator().validate(decision)
    assert validated.action == Action.CLARIFY
    assert validated.missing_criteria == ("term_months", "amount", "fee_priority")
    assert validated.tool_calls == ()
    assert validated.reason_code == "missing_comparison_criteria"


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


@pytest.mark.parametrize("action", [Action.REFUSE, Action.REDIRECT, Action.CLARIFY])
def test_non_answer_actions_never_retain_tools(action):
    decision = PolicyDecision(
        action=action,
        in_domain=True,
        intent="product_search",
        confidence=0.8,
        reason_code="model_choice",
        tool_calls=({"name": "hybrid_rag", "arguments": {}},),
    )
    validated = PolicyValidator().validate(decision)
    assert validated.action == action
    assert validated.tool_calls == ()


@pytest.mark.parametrize("action", [Action.REDIRECT, Action.CLARIFY])
def test_invalid_tool_plan_overrides_non_answer_action(action):
    decision = PolicyDecision(
        action=action,
        in_domain=True,
        intent="product_search",
        confidence=0.8,
        reason_code="model_choice",
        tool_calls=({"name": "shell", "arguments": {}},),
    )
    validated = PolicyValidator().validate(decision)
    assert validated.action == Action.REFUSE
    assert validated.tool_calls == ()
    assert validated.reason_code == "invalid_tool_plan"


@pytest.mark.parametrize(
    ("intent", "tool_call"),
    [
        ("definition", {"name": "structured_sql", "arguments": {}}),
        ("definition", {"name": "comparison", "arguments": {}}),
        (
            "product_search",
            {"name": "hybrid_rag", "arguments": {"banks": ["unknown-bank"]}},
        ),
        (
            "product_search",
            {"name": "hybrid_rag", "arguments": {"query": {"$ne": None}}},
        ),
        (
            "product_search",
            {"name": "hybrid_rag", "arguments": {"term_months": True}},
        ),
        (
            "product_comparison",
            {"name": "comparison", "arguments": {"amount": "lots"}},
        ),
    ],
)
def test_validator_rejects_invalid_intent_tool_and_arguments(intent, tool_call):
    criteria = (
        ComparisonCriteria(term_months=12, amount=1000, fee_priority=False)
        if intent == "product_comparison"
        else ComparisonCriteria()
    )
    decision = PolicyDecision(
        action=Action.ANSWER,
        in_domain=True,
        intent=intent,
        confidence=0.8,
        reason_code="model_answer",
        tool_calls=(tool_call,),
        criteria=criteria,
    )
    validated = PolicyValidator().validate(decision)
    assert validated.action == Action.REFUSE
    assert validated.tool_calls == ()
    assert validated.reason_code == "invalid_tool_plan"


def test_non_finite_tool_argument_fails_closed_at_decision_contract():
    with pytest.raises(TypeError, match="finite"):
        PolicyDecision(
            action=Action.ANSWER,
            in_domain=True,
            intent="product_comparison",
            confidence=0.8,
            reason_code="model_answer",
            tool_calls=({"name": "comparison", "arguments": {"amount": math.inf}},),
        )


def test_validator_independently_rejects_forged_non_finite_argument():
    decision = object.__new__(PolicyDecision)
    values = {
        "action": Action.ANSWER,
        "in_domain": True,
        "intent": "product_comparison",
        "confidence": 0.8,
        "reason_code": "model_answer",
        "concepts": (),
        "missing_criteria": (),
        "tool_calls": ({"name": "comparison", "arguments": {"amount": math.inf}},),
        "safe_message": "",
        "criteria": ComparisonCriteria(term_months=12, amount=1000, fee_priority=False),
    }
    for name, value in values.items():
        object.__setattr__(decision, name, value)

    validated = PolicyValidator().validate(decision)
    assert validated.action == Action.REFUSE
    assert validated.tool_calls == ()
    assert validated.reason_code == "invalid_tool_plan"
