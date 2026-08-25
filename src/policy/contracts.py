from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TypeAlias

JsonScalar: TypeAlias = type(None) | bool | int | float | str
JsonValue: TypeAlias = (
    JsonScalar
    | Mapping[str, "JsonValue"]
    | list["JsonValue"]
    | tuple["JsonValue", ...]
)


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


def _freeze(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Tool-call mapping keys must be strings")
            frozen[key] = _freeze(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    raise TypeError(
        f"Tool-call values must be JSON-compatible; got {type(value).__name__}"
    )


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: Action
    in_domain: bool
    intent: str
    confidence: float
    reason_code: str
    concepts: tuple[str, ...] = ()
    missing_criteria: tuple[str, ...] = ()
    tool_calls: tuple[Mapping[str, JsonValue], ...] = ()
    safe_message: str = ""
    criteria: ComparisonCriteria = field(default_factory=ComparisonCriteria)

    def __post_init__(self) -> None:
        frozen_tool_calls: list[Mapping[str, JsonValue]] = []
        for tool_call in self.tool_calls:
            if not isinstance(tool_call, Mapping):
                raise TypeError("Tool calls must be mappings")
            frozen_tool_call = _freeze(tool_call)
            assert isinstance(frozen_tool_call, Mapping)
            frozen_tool_calls.append(frozen_tool_call)
        object.__setattr__(self, "tool_calls", tuple(frozen_tool_calls))
