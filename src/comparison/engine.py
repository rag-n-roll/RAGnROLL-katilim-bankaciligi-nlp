"""Yapılandırılmış alanlarla deterministic ürün karşılaştırması."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any, Iterable

from src.preprocessing.clean_text import tokenize_turkish


@dataclass(frozen=True, slots=True)
class ComparisonConfig:
    matching_weights: dict[str, float] | None = None
    financing_weights: dict[str, float] | None = None
    investment_weights: dict[str, float] | None = None
    campaign_weights: dict[str, float] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "matching_weights",
            self.matching_weights
            or {
                "product_type": 0.35,
                "subcategory": 0.20,
                "duration": 0.15,
                "amount": 0.10,
                "eligibility": 0.10,
                "title": 0.10,
            },
        )
        object.__setattr__(
            self,
            "financing_weights",
            self.financing_weights
            or {
                "rate": 0.45,
                "amount": 0.30,
                "fee": 0.15,
                "eligibility": 0.10,
            },
        )
        object.__setattr__(
            self,
            "investment_weights",
            self.investment_weights
            or {
                "rate": 0.60,
                "amount": 0.20,
                "duration": 0.10,
                "eligibility": 0.10,
            },
        )
        object.__setattr__(
            self,
            "campaign_weights",
            self.campaign_weights
            or {
                "discount": 0.35,
                "reward": 0.35,
                "installment": 0.20,
                "eligibility": 0.10,
            },
        )


@dataclass(frozen=True, slots=True)
class ComparisonQuery:
    product_type: str
    currency: str
    duration_days: int | None = None
    eligibility: str | None = None
    financing_type: str | None = None
    amount: float | None = None
    title: str | None = None


@dataclass(slots=True)
class ComparisonResult:
    included: list[dict[str, Any]]
    excluded: list[dict[str, str]]
    pair_cache_keys: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "included": self.included,
            "excluded": self.excluded,
            "pair_cache_keys": self.pair_cache_keys,
        }

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]


def _structured(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("structured")
    return value if isinstance(value, dict) else {}


def _currency(record: dict[str, Any]) -> str | None:
    structured = _structured(record)
    for field in ("max_amount", "reward_amount", "min_amount"):
        money = structured.get(field)
        if isinstance(money, dict) and money.get("currency"):
            return str(money["currency"])
    value = record.get("currency")
    return str(value) if value else None


def _amount(record: dict[str, Any], field: str) -> float | None:
    value = _structured(record).get(field)
    if not isinstance(value, dict):
        return None
    try:
        return float(value["amount"])
    except (KeyError, TypeError, ValueError):
        return None


def _normalized_scores(
    rows: list[dict[str, Any]], field: str, *, lower_is_better: bool
) -> dict[str, float]:
    values = {str(row["id"]): row["_values"].get(field) for row in rows}
    known = [float(value) for value in values.values() if value is not None]
    if len(known) == 1:
        return {
            identifier: 0.5 for identifier, value in values.items() if value is not None
        }
    if not known:
        return {}
    low, high = min(known), max(known)
    if low == high:
        return {
            identifier: 0.5 for identifier, value in values.items() if value is not None
        }
    return {
        identifier: ((high - float(value)) if lower_is_better else (float(value) - low))
        / (high - low)
        for identifier, value in values.items()
        if value is not None
    }


def _matching_score(
    record: dict[str, Any], query: ComparisonQuery, config: ComparisonConfig
) -> float:
    structured = _structured(record)
    known: list[tuple[float, float]] = []
    if structured.get("product_type"):
        known.append(
            (
                config.matching_weights["product_type"],
                float(structured["product_type"] == query.product_type),
            )
        )
    if query.financing_type and structured.get("financing_type"):
        known.append(
            (
                config.matching_weights["subcategory"],
                float(structured["financing_type"] == query.financing_type),
            )
        )
    if query.eligibility and structured.get("target_audience"):
        known.append(
            (
                config.matching_weights["eligibility"],
                float(structured["target_audience"] == query.eligibility),
            )
        )
    if query.duration_days and isinstance(structured.get("duration"), dict):
        distance = abs(
            int(structured["duration"].get("approx_days", 0)) - query.duration_days
        )
        known.append(
            (
                config.matching_weights["duration"],
                max(0.0, 1 - distance / max(query.duration_days, 1)),
            )
        )
    if query.amount is not None:
        amount = _amount(record, "max_amount")
        if amount is not None:
            known.append(
                (
                    config.matching_weights["amount"],
                    max(0.0, 1 - abs(amount - query.amount) / max(query.amount, 1)),
                )
            )
    if query.title and record.get("title"):
        known.append(
            (
                config.matching_weights["title"],
                _title_similarity(str(record["title"]), query.title),
            )
        )
    if not known:
        return 0.0
    return round(
        sum(weight * score for weight, score in known)
        / sum(weight for weight, _ in known),
        4,
    )


@lru_cache(maxsize=2048)
def _normalized_title(value: str) -> str:
    return " ".join(tokenize_turkish(value))


def _title_similarity(left: str, right: str) -> float:
    left_tokens = _normalized_title(left)
    right_tokens = _normalized_title(right)
    return SequenceMatcher(a=left_tokens, b=right_tokens).ratio()


def _weights_for(
    product_type: str, config: ComparisonConfig, duration_requested: bool
) -> dict[str, float]:
    if product_type == "financing":
        return dict(config.financing_weights)
    if product_type == "investment":
        weights = dict(config.investment_weights)
        if not duration_requested:
            weights.pop("duration")
        return weights
    return dict(config.campaign_weights)


def compare_records(
    records: Iterable[dict[str, Any]],
    query: ComparisonQuery,
    config: ComparisonConfig | None = None,
) -> dict[str, Any]:
    """Query ile uyumlu kayıtları sıralar; eksik alanları cezalandırmaz."""
    config = config or ComparisonConfig()
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for record in records:
        identifier = str(record.get("id") or "")
        structured = _structured(record)
        if structured.get("product_type") not in (None, query.product_type):
            excluded.append({"id": identifier, "reason": "product_type_mismatch"})
            continue
        currency = _currency(record)
        if currency is not None and currency != query.currency:
            excluded.append({"id": identifier, "reason": "currency_mismatch"})
            continue
        if query.eligibility and structured.get("target_audience") not in (
            None,
            query.eligibility,
        ):
            excluded.append({"id": identifier, "reason": "eligibility_mismatch"})
            continue
        included.append(
            {
                "id": identifier,
                "title": str(record.get("title") or ""),
                "record": record,
                "match_score": _matching_score(record, query, config),
                "_values": {
                    "rate": structured.get("profit_share_rate"),
                    "amount": _amount(record, "max_amount"),
                    "discount": structured.get("discount_rate"),
                    "reward": _amount(record, "reward_amount"),
                    "installment": structured.get("installment_count"),
                    "fee": (
                        1.0
                        if structured.get("fee_information") == "masrafsız"
                        else None
                    ),
                    "eligibility": 1.0 if structured.get("target_audience") else None,
                    "duration": (
                        structured.get("duration", {}).get("approx_days")
                        if isinstance(structured.get("duration"), dict)
                        and query.duration_days
                        else None
                    ),
                },
            }
        )
    weights = _weights_for(query.product_type, config, query.duration_days is not None)
    numeric_scores: dict[str, dict[str, float]] = {}
    for criterion in weights:
        numeric_scores[criterion] = _normalized_scores(
            included,
            criterion,
            lower_is_better=(query.product_type == "financing" and criterion == "rate"),
        )
    for row in included:
        criteria: dict[str, dict[str, float]] = {}
        total_weight = 0.0
        total_score = 0.0
        for criterion, weight in weights.items():
            score = numeric_scores[criterion].get(row["id"])
            if score is None:
                continue
            criteria[criterion] = {
                "value": float(row["_values"][criterion]),
                "score": round(score, 4),
                "weight": weight,
            }
            total_weight += weight
            total_score += score * weight
        row["criteria"] = criteria
        row["missing_fields"] = [
            criterion for criterion in weights if criterion not in criteria
        ]
        if total_weight:
            for criterion in criteria.values():
                criterion["contribution"] = round(
                    criterion["score"] * criterion["weight"] / total_weight, 4
                )
        row["advantage_score"] = (
            round(total_score / total_weight, 4) if total_weight else None
        )
        reasons = []
        if "rate" in criteria:
            reasons.append(
                "düşük kâr payı oranı"
                if query.product_type == "financing"
                else "yüksek kâr payı oranı"
            )
        if "amount" in criteria:
            reasons.append("açık tutar")
        if "reward" in criteria:
            reasons.append("ödül tutarı")
        row["ranking_reason"] = (
            ", ".join(reasons) if reasons else "Yeterli karşılaştırılabilir alan yok"
        )
        row.pop("record")
        row.pop("_values")
    included.sort(
        key=lambda row: (
            row["advantage_score"] is not None,
            row["advantage_score"] or -1,
            row["match_score"],
        ),
        reverse=True,
    )
    pair_cache_keys = [
        ":".join(sorted((left["id"], right["id"])))
        for index, left in enumerate(included)
        for right in included[index + 1 :]
    ]
    return ComparisonResult(
        included=included,
        excluded=excluded,
        pair_cache_keys=pair_cache_keys,
    )
