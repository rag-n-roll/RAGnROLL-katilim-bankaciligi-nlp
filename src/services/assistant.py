"""Structured-first yönlendirme ve kanıt paketli yanıt servisi."""

from __future__ import annotations

from math import isfinite
import re
from time import perf_counter
from typing import Any, Iterator

from src.llm import GroundedPromptBuilder, OpenAICompatibleLLM
from src.llm.client import LLMUnavailableError
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
        llm: OpenAICompatibleLLM | None = None,
        prompt_builder: GroundedPromptBuilder | None = None,
        chroma_enabled: bool | None = None,
    ) -> None:
        self.store = store
        self.compiler = compiler or DomainQueryCompiler()
        self.recorder = recorder or EventRecorder()
        self.llm = llm or OpenAICompatibleLLM()
        self.prompt_builder = prompt_builder or GroundedPromptBuilder()
        self.retriever = HybridRetriever(
            store,
            self.compiler.terminology,
            chroma_enabled=chroma_enabled,
        )

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
        if plan.intent == "definition" and plan.terminology_rewrites:
            exact_term_ids = {
                str(item.get("term_id"))
                for item in plan.terminology_rewrites
                if item.get("term_id")
            }
            exact_documents = [
                document
                for document in documents
                if str(document.get("metadata", {}).get("term_id"))
                in exact_term_ids
            ]
            if exact_documents:
                documents = exact_documents
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
        answer = "\n\n".join(excerpts[:3])
        if plan.intent == "definition" and excerpts:
            answer = excerpts[0].split(" Ana kategori:", 1)[0].strip()
        return {
            "answer": answer,
            "facts": [],
            "sources": sources,
            "confidence": min(0.92, plan.confidence),
            "warnings": plan.warnings,
        }

    def _grounded_result(self, message: str, *, limit: int) -> dict[str, Any]:
        if not 1 <= limit <= 10:
            raise ValueError("limit 1 ile 10 arasında olmalıdır")
        plan = self.compile(message)
        if plan.route == "SAFE_REDIRECT":
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
        elif plan.route == "STRUCTURED_SQL":
            result = self._structured_answer(plan)
        else:
            result = self._hybrid_answer(plan, limit=limit)
        return {**result, "plan": plan.to_dict()}

    @staticmethod
    def _valid_llm_answer(answer: str, *, source_count: int) -> bool:
        normalized = answer.strip()
        if len(normalized) < 12 or "<think>" in normalized.casefold():
            return False
        citations = [int(value) for value in re.findall(r"\[K(\d+)\]", normalized)]
        if source_count and not citations:
            return False
        return all(1 <= citation <= source_count for citation in citations)

    @staticmethod
    def _polish_llm_answer(answer: str) -> str:
        """Küçük modelin sık yaptığı, anlamı değiştirmeyen yazım kusurlarını düzeltir."""

        replacements = {
            "akdıdır": "akdidir",
            "akdı": "akdi",
        }
        polished = answer
        for incorrect, correct in replacements.items():
            polished = re.sub(rf"\b{incorrect}\b", correct, polished, flags=re.IGNORECASE)
        return polished

    def _generation(
        self, *, mode: str, fallback_reason: str | None = None
    ) -> dict[str, Any]:
        return {
            "mode": mode,
            "model": self.llm.model if mode == "llm" else None,
            "fallback_reason": fallback_reason,
            "prompt": self.prompt_builder.metadata(),
            "retrieval_backend": getattr(self.retriever, "last_backend", "bm25"),
        }

    def stream_answer(
        self, message: str, *, limit: int = 5
    ) -> Iterator[dict[str, Any]]:
        """Kanıt paketini önce üretir, LLM yanıtını token parçalarıyla aktarır."""

        started = perf_counter()
        success = True
        route = "UNKNOWN"
        mode = "fallback"
        try:
            grounded = self._grounded_result(message, limit=limit)
            route = str(grounded["plan"]["route"])
            fallback_answer = str(grounded["answer"])
            metadata = {key: value for key, value in grounded.items() if key != "answer"}
            yield {"event": "meta", "data": metadata}

            fallback_reason = None
            if route == "SAFE_REDIRECT":
                fallback_reason = "safe_redirect"
            elif not grounded["sources"]:
                fallback_reason = "evidence_not_found"
            elif not self.llm.enabled:
                fallback_reason = "llm_disabled"

            if fallback_reason:
                yield {"event": "delta", "data": {"text": fallback_answer}}
                yield {
                    "event": "done",
                    "data": self._generation(
                        mode="fallback", fallback_reason=fallback_reason
                    ),
                }
                return

            system_prompt, user_prompt = self.prompt_builder.build(
                question=message,
                fallback_answer=fallback_answer,
                facts=grounded["facts"],
                sources=grounded["sources"],
                plan=grounded["plan"],
            )
            chunks: list[str] = []
            try:
                for chunk in self.llm.stream_chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                ):
                    chunks.append(chunk)
                    yield {"event": "delta", "data": {"text": chunk}}
                generated = "".join(chunks).strip()
                if not self._valid_llm_answer(
                    generated, source_count=len(grounded["sources"])
                ):
                    event = "replace" if chunks else "delta"
                    yield {"event": event, "data": {"text": fallback_answer}}
                    yield {
                        "event": "done",
                        "data": self._generation(
                            mode="fallback", fallback_reason="llm_output_rejected"
                        ),
                    }
                    return
                polished = self._polish_llm_answer(generated)
                if polished != generated:
                    yield {"event": "replace", "data": {"text": polished}}
                mode = "llm"
                yield {"event": "done", "data": self._generation(mode="llm")}
            except LLMUnavailableError:
                event = "replace" if chunks else "delta"
                yield {"event": event, "data": {"text": fallback_answer}}
                yield {
                    "event": "done",
                    "data": self._generation(
                        mode="fallback", fallback_reason="llm_unavailable"
                    ),
                }
        except Exception:
            success = False
            raise
        finally:
            self.recorder.record(
                "answer_generated",
                latency_ms=(perf_counter() - started) * 1000,
                success=success,
                route=route,
                generation_mode=mode,
            )

    def answer(self, message: str, *, limit: int = 5) -> dict[str, Any]:
        """Streaming sözleşmesini tüketerek geriye uyumlu toplu yanıt döndürür."""

        response: dict[str, Any] = {}
        answer_parts: list[str] = []
        generation = self._generation(mode="fallback", fallback_reason="unknown")
        for item in self.stream_answer(message, limit=limit):
            event = item["event"]
            data = item["data"]
            if event == "meta":
                response.update(data)
            elif event == "delta":
                answer_parts.append(str(data.get("text") or ""))
            elif event == "replace":
                answer_parts = [str(data.get("text") or "")]
            elif event == "done":
                generation = data
        if generation.get("mode") == "fallback" and generation.get("fallback_reason") in {
            "llm_unavailable",
            "llm_output_rejected",
        }:
            response.setdefault("warnings", []).append(
                "Dil modeli kullanılamadığı için doğrulanabilir yerel yanıt gösterildi"
            )
        return {
            **response,
            "answer": "".join(answer_parts).strip(),
            "generation": generation,
        }
