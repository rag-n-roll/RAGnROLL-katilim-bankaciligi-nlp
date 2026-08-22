"""Structured-first yönlendirme ve kanıt paketli yanıt servisi."""

from __future__ import annotations

from math import isfinite
from time import perf_counter
from typing import Any

from src.observability import EventRecorder
from src.persistence import CampaignStore
from src.preprocessing.clean_text import tokenize_turkish
from src.query import DomainQueryCompiler, QueryPlan
from src.retrieval import HybridRetriever


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


class GroundedAssistant:
    """LLM olmadan da factual ve karşılaştırmalı sorgulara kanıtlı yanıt verir."""

    def __init__(
        self,
        store: CampaignStore,
        *,
        compiler: DomainQueryCompiler | None = None,
        recorder: EventRecorder | None = None,
    ) -> None:
        self.store = store
        self.compiler = compiler or DomainQueryCompiler()
        self.recorder = recorder or EventRecorder()
        self.retriever = HybridRetriever(store, self.compiler.terminology)

    def compile(self, message: str) -> QueryPlan:
        return self.compiler.compile(message, known_banks=self.store.bank_summary())

    @staticmethod
    def _structured(record: dict[str, Any]) -> dict[str, Any]:
        value = record.get("structured")
        return value if isinstance(value, dict) else {}

    @classmethod
    def _metric_value(cls, record: dict[str, Any], metric: str | None) -> Any:
        structured = cls._structured(record)
        mapping = {
            "PROFIT_RATE": "profit_share_rate",
            "MATURITY": "term_months",
            "FEE": "fee_information",
            "REWARD_AMOUNT": "reward_amount",
        }
        return structured.get(mapping.get(metric, ""))

    @classmethod
    def _source(cls, record: dict[str, Any], metric: str | None) -> dict[str, Any]:
        structured = cls._structured(record)
        field_name = {
            "PROFIT_RATE": "profit_share_rate",
            "MATURITY": "term_months",
            "FEE": "fee_information",
            "REWARD_AMOUNT": "reward_amount",
        }.get(metric)
        fields = structured.get("fields") if isinstance(structured.get("fields"), dict) else {}
        field = fields.get(field_name, {}) if field_name else {}
        evidence = field.get("evidence") if isinstance(field, dict) else None
        if evidence is None and field_name:
            raw = structured.get("evidence", {}).get(field_name)
            evidence = {"text": raw, "char_start": None, "char_end": None} if raw else None
        return {
            "campaign_id": str(record.get("id") or ""),
            "bank_name": str(record.get("bank_name") or ""),
            "title": str(record.get("title") or ""),
            "source_url": str(record.get("source_url") or ""),
            "scraped_at": record.get("scraped_at"),
            "evidence": evidence,
        }

    @staticmethod
    def _lexical_score(record: dict[str, Any], query: str) -> int:
        query_tokens = set(tokenize_turkish(query))
        record_tokens = set(
            tokenize_turkish(
                " ".join(
                    (
                        str(record.get("title") or ""),
                        str(record.get("content") or ""),
                    )
                )
            )
        )
        return len(query_tokens & record_tokens)

    def _balanced_candidates(
        self, rows: list[dict[str, Any]], plan: QueryPlan, *, per_bank: int = 2
    ) -> list[dict[str, Any]]:
        banks = list(plan.slots.get("banks") or [])
        ranked = sorted(
            rows,
            key=lambda row: (
                -self._lexical_score(row, plan.canonical_query),
                str(row.get("id") or ""),
            ),
        )
        if not banks:
            return ranked
        result = []
        for bank in banks:
            result.extend(
                row for row in ranked if row.get("bank_slug") == bank
            )
            if sum(row.get("bank_slug") == bank for row in result) > per_bank:
                result = [
                    row
                    for index, row in enumerate(result)
                    if row.get("bank_slug") != bank
                    or sum(
                        previous.get("bank_slug") == bank
                        for previous in result[: index + 1]
                    )
                    <= per_bank
                ]
        return result

    def _structured_answer(self, plan: QueryPlan) -> dict[str, Any]:
        rows, _ = self.store.query_campaigns(
            bank_slugs=plan.slots.get("banks") or None,
            product_type=plan.slots.get("product_type"),
            financing_type=plan.slots.get("financing_type"),
            limit=100,
        )
        candidates = self._balanced_candidates(rows, plan)
        metric = plan.slots.get("metric")
        aggregation = plan.slots.get("aggregation")
        numeric = [
            (row, _finite(self._metric_value(row, metric)))
            for row in candidates
        ]
        numeric = [(row, value) for row, value in numeric if value is not None]
        if numeric and aggregation in {"MIN", "MAX"}:
            reverse = aggregation == "MAX"
            numeric.sort(
                key=lambda item: (item[1], str(item[0].get("id") or "")),
                reverse=reverse,
            )
            candidates = [row for row, _ in numeric]
        if not candidates:
            return {
                "answer": (
                    "Bu sorgu için yapılandırılmış kayıtlarda "
                    "doğrulanabilir bilgi bulunamadı."
                ),
                "facts": [],
                "sources": [],
                "confidence": 0.0,
                "warnings": [*plan.warnings, "Kaynakta doğrulanabilir aday bulunamadı"],
            }
        facts = []
        for row in candidates[:5]:
            value = self._metric_value(row, metric)
            facts.append(
                {
                    "campaign_id": str(row.get("id") or ""),
                    "bank_name": str(row.get("bank_name") or ""),
                    "title": str(row.get("title") or ""),
                    "metric": metric,
                    "value": value,
                }
            )
        lines = []
        for fact in facts:
            value = fact["value"]
            detail = "kaynakta sayısal değer belirtilmemiş"
            if value is not None:
                if metric == "PROFIT_RATE":
                    detail = f"%{float(value) * 100:.2f} kâr payı"
                elif metric == "MATURITY":
                    detail = f"{value} ay vade"
                else:
                    detail = str(value)
            lines.append(f"{fact['bank_name']} - {fact['title']}: {detail}")
        return {
            "answer": "\n".join(lines),
            "facts": facts,
            "sources": [self._source(row, metric) for row in candidates[:5]],
            "confidence": min(0.98, plan.confidence),
            "warnings": plan.warnings,
        }

    def _hybrid_answer(self, plan: QueryPlan, *, limit: int) -> dict[str, Any]:
        filters = dict(plan.filters)
        if plan.intent == "definition" and plan.terminology_rewrites:
            filters["source_types"] = ["terminology"]
        documents = self.retriever.retrieve(
            plan.canonical_query, filters=filters, limit=limit
        )
        if not documents:
            return {
                "answer": "Bu bilgi sağlanan resmî içerik ve terminoloji kayıtlarında bulunamadı.",
                "facts": [],
                "sources": [],
                "confidence": 0.0,
                "warnings": [*plan.warnings, "Retrieval sonucu bulunamadı"],
            }
        excerpts = []
        sources = []
        for document in documents:
            excerpt = " ".join(document["text"].split())[:360]
            metadata = document["metadata"]
            excerpts.append(excerpt)
            sources.append(
                {
                    "campaign_id": metadata.get("campaign_id") or None,
                    "term_id": metadata.get("term_id") or None,
                    "bank_name": metadata.get("bank_name") or None,
                    "title": metadata.get("title") or None,
                    "source_url": metadata.get("source_url") or None,
                    "evidence": {"text": excerpt, "char_start": None, "char_end": None},
                    "retrieval_score": document["score"],
                    "retrieval_method": document["retrieval_method"],
                }
            )
        return {
            "answer": "\n\n".join(excerpts[:3]),
            "facts": [],
            "sources": sources,
            "confidence": min(0.92, plan.confidence),
            "warnings": plan.warnings,
        }

    def answer(self, message: str, *, limit: int = 5) -> dict[str, Any]:
        if not 1 <= limit <= 10:
            raise ValueError("limit 1 ile 10 arasında olmalıdır")
        started = perf_counter()
        success = True
        route = "UNKNOWN"
        try:
            plan = self.compile(message)
            route = plan.route
            if route == "SAFE_REDIRECT":
                result = {
                    "answer": (
                        "Bu sistem müşteri işlemi veya şikâyet kaydı gerçekleştirmez. "
                        "Lütfen ilgili bankanın resmî destek kanalını kullanın."
                    ),
                    "facts": [],
                    "sources": [],
                    "confidence": plan.confidence,
                    "warnings": plan.warnings,
                }
            elif route == "STRUCTURED_SQL":
                result = self._structured_answer(plan)
            else:
                result = self._hybrid_answer(plan, limit=limit)
            return {**result, "plan": plan.to_dict()}
        except Exception:
            success = False
            raise
        finally:
            self.recorder.record(
                "answer_generated",
                latency_ms=(perf_counter() - started) * 1000,
                success=success,
                route=route,
            )
