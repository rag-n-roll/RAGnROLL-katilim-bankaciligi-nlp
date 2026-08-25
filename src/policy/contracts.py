from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class Action(StrEnum):
    ANSWER = "ANSWER"
    CLARIFY = "CLARIFY"
    REFUSE = "REFUSE"
    REDIRECT = "REDIRECT"


@dataclass(frozen=True, slots=True)
class ComparisonCriteria:
    term_months: int | None = None
    amount: float | None = None
    fee_priority: bool | None = None

    def missing(self) -> list[str]:
        values = {
            "term_months": self.term_months,
            "amount": self.amount,
            "fee_priority": self.fee_priority,
        }
        return [name for name, value in values.items() if value is None]


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: Action
    in_domain: bool
    intent: str
    confidence: float
    reason_code: str
    concepts: tuple[str, ...] = ()
    missing_criteria: tuple[str, ...] = ()
    tool_calls: tuple[Mapping[str, Any], ...] = ()
    safe_message: str = ""
    criteria: ComparisonCriteria = field(default_factory=ComparisonCriteria)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_calls", tuple(_freeze(call) for call in self.tool_calls))
