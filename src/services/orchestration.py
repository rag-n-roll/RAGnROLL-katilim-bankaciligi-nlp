"""Validated policy boundary for assistant tool execution."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from src.policy import Action, PolicyDecision
from src.policy.validator import PolicyValidator


T = TypeVar("T")


class ToolOrchestrator:
    """Execute an operation only when a validated policy explicitly lists it."""

    def __init__(self, *, allowed_banks: set[str]) -> None:
        self.allowed_banks = set(allowed_banks)
        self.validator = PolicyValidator()

    def execute(
        self,
        decision: PolicyDecision,
        *,
        tool_name: str,
        operation: Callable[[], T],
    ) -> T | None:
        if not isinstance(decision, PolicyDecision):
            return None
        validated = self.validator.validate(
            decision, allowed_banks=self.allowed_banks
        )
        if validated.action != Action.ANSWER:
            return None
        listed = {str(call.get("name") or "") for call in validated.tool_calls}
        return operation() if tool_name in listed else None
