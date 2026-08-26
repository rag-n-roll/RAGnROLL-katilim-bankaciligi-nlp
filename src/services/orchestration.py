"""Validated policy boundary for assistant tool execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypeVar

from src.policy import Action, PolicyDecision
from src.policy.validator import PolicyValidator


T = TypeVar("T")


def _normalized(value):
    if isinstance(value, Mapping):
        return tuple(sorted((key, _normalized(item)) for key, item in value.items()))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(_normalized(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class ValidatedPolicyDecision:
    decision: PolicyDecision


class ToolOrchestrator:
    """Execute an operation only when a validated policy explicitly lists it."""

    def __init__(self, *, allowed_banks: set[str]) -> None:
        self.allowed_banks = set(allowed_banks)
        self.validator = PolicyValidator()

    def validate(self, decision: PolicyDecision) -> ValidatedPolicyDecision:
        return ValidatedPolicyDecision(
            self.validator.validate(decision, allowed_banks=self.allowed_banks)
        )

    def execute(
        self,
        validated_plan: ValidatedPolicyDecision,
        *,
        expected_call: Mapping[str, object],
        operation: Callable[[Mapping[str, object]], T],
    ) -> T | None:
        if not isinstance(validated_plan, ValidatedPolicyDecision):
            return None
        validated = validated_plan.decision
        if validated.action != Action.ANSWER:
            return None
        expected = _normalized(expected_call)
        for call in validated.tool_calls:
            if _normalized(call) == expected:
                return operation(call)
        return None
