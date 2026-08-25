from dataclasses import dataclass, field
from enum import StrEnum
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


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: Action
    in_domain: bool
    intent: str
    confidence: float
    reason_code: str
    concepts: tuple[str, ...] = ()
    missing_criteria: tuple[str, ...] = ()
    tool_calls: tuple[dict[str, Any], ...] = ()
    safe_message: str = ""
    criteria: ComparisonCriteria = field(default_factory=ComparisonCriteria)
