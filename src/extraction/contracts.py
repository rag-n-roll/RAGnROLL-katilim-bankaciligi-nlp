"""Kanıt, güven ve eksiklik durumunu taşıyan alan sözleşmeleri."""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping


class FieldStatus(str, Enum):
    """Bir alanın kaynak metne göre neden dolu veya boş olduğunu açıklar."""

    EXPLICIT = "EXPLICIT"
    IMPLICIT = "IMPLICIT"
    NOT_STATED = "NOT_STATED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    CONFLICT = "CONFLICT"


FIELD_UNITS = {
    "profit_share_rate": "RATIO",
    "discount_rate": "RATIO",
    "term_months": "MONTH",
    "installment_count": "COUNT",
    "campaign_start_date": "DATE",
    "campaign_end_date": "DATE",
}

FIELD_KEYWORDS = {
    "profit_share_rate": ("kâr payı", "kar payı", "oran"),
    "term_months": ("vade", "vadeli"),
    "installment_count": ("taksit",),
    "reward_amount": ("ödül", "odul", "puan", "bonus", "iade"),
    "discount_rate": ("indirim",),
    "target_audience": ("müşteri", "musteri", "hedef kitle"),
    "fee_information": ("masraf", "ücret", "ucret", "tahsis"),
    "campaign_start_date": ("başlangıç", "baslangic", "tarih"),
    "campaign_end_date": ("bitiş", "bitis", "tarih", "kadar"),
}

CORE_FIELDS = (
    "product_type",
    "financing_type",
    "profit_share_rate",
    "financing_amount",
    "term_months",
    "installment_count",
    "campaign_benefit",
    "reward_amount",
    "discount_rate",
    "target_audience",
    "campaign_start_date",
    "campaign_end_date",
    "fee_information",
    "application_channel",
    "condition",
)


def _evidence_span(source: str, raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    start = source.find(raw)
    if start < 0:
        return {"text": raw, "char_start": None, "char_end": None}
    return {"text": raw, "char_start": start, "char_end": start + len(raw)}


def _not_applicable(field: str, product_type: str | None) -> bool:
    if product_type in {"card", "shopping_points", "new_customer"}:
        return field in {"profit_share_rate", "term_months", "financing_amount"}
    if product_type == "investment":
        return field in {"installment_count", "discount_rate"}
    return False


def _status_for(
    field: str,
    *,
    value: Any,
    raw: str | None,
    source: str,
    product_type: str | None,
    conflicts: Mapping[str, list[Any]],
) -> FieldStatus:
    if conflicts.get(field):
        return FieldStatus.CONFLICT
    if value is not None:
        return FieldStatus.EXPLICIT if raw else FieldStatus.IMPLICIT
    if _not_applicable(field, product_type):
        return FieldStatus.NOT_APPLICABLE
    normalized = source.casefold()
    if field == "profit_share_rate" and any(
        phrase in normalized
        for phrase in ("avantajlı kâr payı", "avantajlı kar payı", "avantajlı oran")
    ):
        return FieldStatus.IMPLICIT
    if any(keyword in normalized for keyword in FIELD_KEYWORDS.get(field, ())):
        return FieldStatus.EXTRACTION_FAILED
    return FieldStatus.NOT_STATED


def build_field_contracts(
    source: str,
    values: Mapping[str, Any],
    evidence: Mapping[str, str],
    *,
    method: str,
    conflicts: Mapping[str, list[Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Geriye uyumlu scalar alanlara denetlenebilir alan nesneleri ekler."""
    conflict_values = conflicts or {}
    product_type = values.get("product_type")
    result: dict[str, dict[str, Any]] = {}
    for field in CORE_FIELDS:
        value = values.get(field)
        raw = evidence.get(field)
        status = _status_for(
            field,
            value=value,
            raw=raw,
            source=source,
            product_type=str(product_type) if product_type else None,
            conflicts=conflict_values,
        )
        confidence = {
            FieldStatus.EXPLICIT: 0.99,
            FieldStatus.IMPLICIT: 0.75,
            FieldStatus.NOT_STATED: 1.0,
            FieldStatus.NOT_APPLICABLE: 1.0,
            FieldStatus.EXTRACTION_FAILED: 0.0,
            FieldStatus.CONFLICT: 0.5,
        }[status]
        result[field] = {
            "raw": raw,
            "value": value,
            "unit": (
                value.get("currency")
                if isinstance(value, dict) and value.get("currency")
                else FIELD_UNITS.get(field)
            ),
            "status": status.value,
            "confidence": confidence,
            "evidence": _evidence_span(source, raw),
            "method": method,
            "conflicting_values": conflict_values.get(field, []),
        }
    return result
