from collections.abc import Mapping, Sequence
from math import isfinite
from typing import Any

from src.scraper.bddk import BANK_NAME_TO_SLUG


ALLOWED_INTENTS = frozenset(
    {
        "application_requirements",
        "bank_list",
        "campaign_count",
        "campaign_query",
        "complaint_support",
        "definition",
        "maturity_query",
        "product_comparison",
        "product_search",
        "rate_query",
        "relationship_query",
        "trade_finance_query",
        "agriculture_finance_query",
        "investment_query",
        "transaction_howto",
    }
)
ALLOWED_BANKS = frozenset(BANK_NAME_TO_SLUG.values())
ALLOWED_TOOLS = frozenset(
    {"structured_sql", "hybrid_rag", "comparison", "ontology", "financing_quote"}
)
ALLOWED_CRITERIA = frozenset({"term_months", "amount", "fee_priority"})
ALLOWED_METRICS = frozenset({"PROFIT_RATE", "MATURITY", "FEE", "REWARD_AMOUNT"})
ALLOWED_AGGREGATIONS = frozenset({"MIN", "MAX", "COUNT"})
ALLOWED_PRODUCT_TYPES = frozenset(
    {"account", "card", "financing", "investment", "payment", "insurance"}
)
ALLOWED_FINANCING_TYPES = frozenset(
    {"housing", "vehicle", "consumer", "commercial", "agriculture"}
)

INTENT_TOOLS = {
    "application_requirements": frozenset({"hybrid_rag"}),
    "bank_list": frozenset({"structured_sql"}),
    "campaign_count": frozenset({"structured_sql"}),
    "campaign_query": frozenset({"hybrid_rag"}),
    "complaint_support": frozenset(),
    "definition": frozenset({"hybrid_rag", "ontology"}),
    "maturity_query": frozenset({"structured_sql"}),
    "product_comparison": frozenset(
        {"structured_sql", "comparison", "financing_quote"}
    ),
    "product_search": frozenset({"structured_sql", "hybrid_rag"}),
    "rate_query": frozenset({"structured_sql"}),
    "relationship_query": frozenset({"hybrid_rag", "ontology"}),
    "trade_finance_query": frozenset({"hybrid_rag"}),
    "agriculture_finance_query": frozenset({"hybrid_rag"}),
    "investment_query": frozenset({"hybrid_rag"}),
    "transaction_howto": frozenset(),
}

_COMMON_FILTERS = {
    "banks",
    "product_type",
    "financing_type",
}
TOOL_ARGUMENTS = {
    "structured_sql": frozenset(
        {
            *_COMMON_FILTERS,
            "metric",
            "aggregation",
            *ALLOWED_CRITERIA,
        }
    ),
    "hybrid_rag": frozenset(_COMMON_FILTERS),
    "comparison": frozenset({*_COMMON_FILTERS, *ALLOWED_CRITERIA}),
    "financing_quote": frozenset(
        {
            "banks",
            "financing_type",
            "term_months",
            "term_months_min",
            "term_months_max",
            "amount",
            "fee_priority",
        }
    ),
    "ontology": frozenset(),
}


def _valid_arguments(arguments: Mapping[str, Any], *, allowed_banks: set[str]) -> bool:
    banks = arguments.get("banks", ())
    if "banks" in arguments and (
        not isinstance(banks, Sequence)
        or isinstance(banks, (str, bytes))
        or any(not isinstance(bank, str) or bank not in allowed_banks for bank in banks)
    ):
        return False
    enum_fields = {
        "metric": ALLOWED_METRICS,
        "aggregation": ALLOWED_AGGREGATIONS,
        "product_type": ALLOWED_PRODUCT_TYPES,
        "financing_type": ALLOWED_FINANCING_TYPES,
    }
    for key, allowed in enum_fields.items():
        if key in arguments and arguments[key] not in allowed:
            return False
    term_months = arguments.get("term_months")
    if "term_months" in arguments and (
        isinstance(term_months, bool)
        or not isinstance(term_months, int)
        or term_months <= 0
    ):
        return False
    amount = arguments.get("amount")
    if "amount" in arguments and (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not isfinite(float(amount))
        or amount < 0
    ):
        return False
    if "fee_priority" in arguments and not isinstance(arguments["fee_priority"], bool):
        return False
    return True


def valid_tool_call(
    intent: str,
    call: Mapping[str, Any],
    *,
    allowed_banks: set[str] | None = None,
) -> bool:
    if set(call) != {"name", "arguments"}:
        return False
    name = call.get("name")
    arguments = call.get("arguments")
    if not isinstance(name, str) or name not in INTENT_TOOLS.get(intent, ()):
        return False
    if not isinstance(arguments, Mapping):
        return False
    if not set(arguments).issubset(TOOL_ARGUMENTS[name]):
        return False
    if name == "financing_quote":
        required = {"financing_type", "term_months", "amount", "fee_priority"}
        if not required.issubset(arguments):
            return False
        if arguments.get("financing_type") not in {
            "consumer",
            "vehicle",
            "housing",
            "commercial",
        }:
            return False
        term_months = arguments.get("term_months")
        amount = arguments.get("amount")
        term_min = arguments.get("term_months_min")
        term_max = arguments.get("term_months_max")
        if (
            isinstance(term_months, bool)
            or not isinstance(term_months, int)
            or not 1 <= term_months <= 240
            or isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not isfinite(float(amount))
            or not 0 < float(amount) <= 100_000_000
        ):
            return False
        if (term_min is None) != (term_max is None):
            return False
        if term_min is not None and (
            isinstance(term_min, bool)
            or isinstance(term_max, bool)
            or not isinstance(term_min, int)
            or not isinstance(term_max, int)
            or not 1 <= term_min <= term_max <= 240
            or term_max - term_min > 23
            or term_months != term_max
        ):
            return False
    return _valid_arguments(
        arguments,
        allowed_banks=set(ALLOWED_BANKS if allowed_banks is None else allowed_banks),
    )
