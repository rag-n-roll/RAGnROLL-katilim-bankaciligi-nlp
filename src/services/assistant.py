"""Structured-first yönlendirme ve kanıt paketli yanıt servisi."""

from __future__ import annotations

from dataclasses import replace
from math import isfinite
import re
from time import perf_counter
from typing import Any, Iterator

from src.llm import (
    EvrenDecisionService,
    GroundedPromptBuilder,
    OpenAICompatibleLLM,
    build_llm_from_env,
)
from src.llm.client import LLMUnavailableError
from src.normalization import normalize_duration, normalize_money, normalize_rate
from src.normalization.values import parse_number
from src.observability import EventRecorder
from src.persistence import CampaignStore
from src.preprocessing.clean_text import tokenize_turkish
from src.prompt_optimization import IntentTraceRecorder
from src.query import DomainQueryCompiler, QueryPlan
from src.retrieval import HybridRetriever


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


_CITATION_RE = re.compile(r"\[K(\d+)\]")
_PERCENT_CLAIM_RE = re.compile(r"(?:%\s*\d[\d.,]*|\d[\d.,]*\s*%)")
_MONEY_CLAIM_RE = re.compile(
    r"(?:"
    r"(?:₺|\$|€|£|\b(?:TL|TRY|USD|EUR|GBP)\b)\s*"
    r"\d[\d.,]*(?:\s+milyon)?"
    r"|\d[\d.,]*(?:\s+milyon)?\s*"
    r"(?:₺|\$|€|£|\b(?:TL|TRY|USD|EUR|GBP)\b)"
    r")",
    re.IGNORECASE,
)
_DURATION_CLAIM_RE = re.compile(
    r"(?<!\d)\d{1,4}\s*(?:gün|gun|ay|yıl|yil)(?!\w)", re.IGNORECASE
)
_NUMBER_CLAIM_RE = re.compile(r"(?<!\w)\d[\d.,]*(?!\w)")
_FEE_FREE_CLAIM_RE = re.compile(
    r"\b(?:masrafs[ıi]z(?:d[ıi]r)?|ücretsiz(?:d[ıi]r)?|ucretsiz(?:dir)?|"
    r"ücret\s+yok|ucret\s+yok|masraf\s+yok)\b",
    re.IGNORECASE,
)
_ORDERED_LIST_MARKER_RE = re.compile(r"(?m)^\s*\d{1,2}[.)]\s+")


class _LocalDecisionFallback:
    """Enjekte edilmiş test/yerel LLM'lerde harici karar çağrısını kapatır."""

    @staticmethod
    def is_safe(message: str) -> None:
        del message
        return None

    @staticmethod
    def route(message: str) -> None:
        del message
        return None

    @staticmethod
    def status() -> dict[str, Any]:
        return {"enabled": False, "reason": "local_only"}


class GroundedAssistant:
    """LLM olmadan da factual ve karşılaştırmalı sorgulara kanıtlı yanıt verir."""

    def __init__(
        self,
        store: CampaignStore,
        *,
        compiler: DomainQueryCompiler | None = None,
        recorder: EventRecorder | None = None,
        llm: OpenAICompatibleLLM | None = None,
        decisions: EvrenDecisionService | None = None,
        prompt_builder: GroundedPromptBuilder | None = None,
        intent_trace: IntentTraceRecorder | None = None,
        chroma_enabled: bool | None = None,
    ) -> None:
        self.store = store
        self.compiler = compiler or DomainQueryCompiler()
        self.recorder = recorder or EventRecorder()
        self.llm = llm or build_llm_from_env()
        self.decisions = decisions or (
            _LocalDecisionFallback()
            if llm is not None
            else EvrenDecisionService(planner=self.llm)
        )
        self.prompt_builder = prompt_builder or GroundedPromptBuilder()
        self.intent_trace = intent_trace or IntentTraceRecorder()
        self.retriever = HybridRetriever(
            store,
            self.compiler.terminology,
            chroma_enabled=chroma_enabled,
        )

    def compile(self, message: str) -> QueryPlan:
        known_banks = self.store.bank_summary()
        plan = self.compiler.compile(message, known_banks=known_banks)
        if plan.route == "SAFE_REDIRECT":
            return plan
        analyzer = getattr(self.decisions, "analyze", None)
        decision = (
            analyzer(
                message,
                canonical_query=plan.canonical_query,
                deterministic_plan=plan.to_dict(),
                known_banks=known_banks,
            )
            if callable(analyzer)
            else None
        )
        if callable(analyzer):
            if decision:
                selected = self._merge_llm_plan(plan, decision)
                try:
                    self.intent_trace.record(
                        raw_input=message,
                        bank_catalog=known_banks,
                        deterministic_plan=plan.to_dict(),
                        llm_decision=(
                            decision.to_dict()
                            if callable(getattr(decision, "to_dict", None))
                            else decision
                        ),
                        selected_plan=selected.to_dict(),
                    )
                except OSError:
                    # Eğitim izi yanıt yolunu kesemez; metrikler ana akışta tutulur.
                    pass
                return selected
            return plan

        # Enjekte edilmiş eski karar servisleri için geriye uyumlu yol.
        safe = self.decisions.is_safe(message)
        advised_route = self.decisions.route(message)
        warnings = list(plan.warnings)
        if safe is False or advised_route == "SAFE_REDIRECT":
            warnings.append("EVREN güvenlik sinyali güvenli yönlendirme önerdi")
            return replace(plan, route="SAFE_REDIRECT", warnings=warnings)
        if advised_route == "STRUCTURED_SQL":
            trusted_domain = bool(
                plan.confidence_components.get("trusted_domain", False)
            )
            eligible_route = self.compiler.route_for(
                plan.intent, plan.slots, trusted_domain=trusted_domain
            )
            if eligible_route == "STRUCTURED_SQL":
                return replace(plan, route="STRUCTURED_SQL")
            warnings.append(
                "EVREN structured route önerisi ölçülebilir sorgu koşullarını karşılamadı"
            )
            return replace(plan, route=eligible_route, warnings=warnings)
        if advised_route not in {None, plan.route, "HYBRID_RAG"}:
            warnings.append("EVREN route önerisi yerel sözleşmeyle uyuşmadığı için yok sayıldı")
            return replace(plan, warnings=warnings)
        return plan

    def _merge_llm_plan(
        self, plan: QueryPlan, decision: dict[str, Any]
    ) -> QueryPlan:
        """Model planını yalnız yerel sözleşmenin izin verdiği ölçüde uygular."""

        if decision.get("safe") is False or decision.get("route") == "SAFE_REDIRECT":
            return replace(
                plan,
                intent=str(decision["intent"]),
                route="SAFE_REDIRECT",
                confidence=float(decision["confidence"]),
                warnings=[*plan.warnings, "LLM güvenlik planı güvenli yönlendirme önerdi"],
            )

        intent = str(decision["intent"])
        advised_route = str(decision["route"])
        decision_slots = decision.get("slots") or {}
        slots = dict(plan.slots)
        for key in (
            "banks",
            "metric",
            "aggregation",
            "product_type",
            "financing_type",
        ):
            value = decision_slots.get(key)
            if value not in (None, [], ""):
                slots[key] = value
            elif key in {"metric", "aggregation", "product_type", "financing_type"}:
                slots[key] = None
        filters = {
            key: value
            for key, value in {
                "bank_slugs": slots.get("banks"),
                "product_type": slots.get("product_type"),
                "financing_type": slots.get("financing_type"),
                "active_only": True,
            }.items()
            if value not in (None, [], "")
        }
        trusted_sources = list(
            plan.confidence_components.get("trusted_domain_sources") or ()
        )
        trusted_domain = bool(trusted_sources)
        eligible_route = self.compiler.route_for(
            intent, slots, trusted_domain=trusted_domain
        )
        if not trusted_domain and plan.route == "SAFE_REDIRECT":
            eligible_route = "SAFE_REDIRECT"
        route = (
            "STRUCTURED_SQL"
            if advised_route == "STRUCTURED_SQL" and eligible_route == "STRUCTURED_SQL"
            else eligible_route
        )
        confidence_components = self.compiler.confidence_evidence(
            slots,
            filters,
            (),
            source="llm_plan",
            trusted_domain_sources=trusted_sources,
        )
        return replace(
            plan,
            canonical_query=str(decision["normalized_query"]),
            intent=intent,
            route=route,
            slots=slots,
            filters=filters,
            terminology_rewrites=[],
            confidence=float(decision["confidence"]),
            confidence_components=confidence_components,
        )

    @staticmethod
    def _relation_sentence(relation: dict[str, Any]) -> str | None:
        subject = str(relation.get("source_term") or "").strip()
        target = str(relation.get("target_term") or "").strip()
        if not subject or not target:
            return None
        predicate = str(relation.get("relation") or "")
        type_sentences = {
            "IS_A_DOCUMENT": f"{subject} bir belgedir.",
            "IS_A_PRODUCT": f"{subject} bir üründür.",
            "IS_AN_ORGANIZATION": f"{subject} bir kuruluştur.",
        }
        if predicate in type_sentences:
            return type_sentences[predicate]
        predicates = {
            "RELATED_TO": "ile ilişkilidir",
            "USES": "kullanır",
            "DISTRIBUTES": "dağıtır",
            "MAY_REQUIRE": "gerektirebilir",
            "GOVERNED_BY": "tarafından düzenlenir",
            "FINANCES": "finanse eder",
            "PAYS": "ödeme yapar",
            "COLLECTS_FROM": "tahsilat yapar",
            "TARGETS": "hedefler",
            "USES_PLATFORM": "platformunu kullanır",
        }
        label = predicates.get(predicate)
        return f"{subject}, {target} {label}." if label else None

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
    def _comparison_value(
        cls, record: dict[str, Any], metric: str | None
    ) -> tuple[float, str | None] | None:
        """Karşılaştırılabilir değeri ve birimini açıkça üretir."""

        value = cls._metric_value(record, metric)
        if metric in {"PROFIT_RATE", "MATURITY"}:
            number = _finite(value)
            return (number, None) if number is not None else None
        if metric == "REWARD_AMOUNT":
            if not isinstance(value, dict):
                return None
            amount = _finite(value.get("amount"))
            currency = str(value.get("currency") or "").strip().upper()
            if amount is None or not currency:
                return None
            return amount, currency
        if metric != "FEE":
            return None
        normalized = str(value or "").casefold().replace("i̇", "i")
        if _FEE_FREE_CLAIM_RE.search(normalized):
            return 0.0, "FEE_FREE"
        money = normalize_money(str(value or ""))
        if money is None:
            return None
        return float(money.amount), money.currency

    @classmethod
    def _extrema_candidates(
        cls,
        rows: list[dict[str, Any]],
        metric: str | None,
        aggregation: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """Aynı birimdeki gerçek extrema ve eşit liderleri döndürür."""

        comparable: list[tuple[dict[str, Any], float, str | None]] = []
        rejected_explicit = 0
        for row in rows:
            comparison = cls._comparison_value(row, metric)
            if comparison is None:
                if cls._metric_value(row, metric) not in (None, "", {}):
                    rejected_explicit += 1
                continue
            comparable.append((row, comparison[0], comparison[1]))
        warnings: list[str] = []
        if rejected_explicit:
            warnings.append(
                "Birimi veya biçimi doğrulanamayan değerler karşılaştırmaya alınmadı"
            )
        if not comparable:
            return [], warnings

        if metric == "FEE" and aggregation == "MIN":
            fee_free = [item for item in comparable if item[2] == "FEE_FREE"]
            if fee_free:
                return (
                    [
                        item[0]
                        for item in sorted(
                            fee_free, key=lambda item: str(item[0].get("id") or "")
                        )
                    ],
                    warnings,
                )

        groups: dict[str | None, list[tuple[dict[str, Any], float]]] = {}
        for row, number, unit in comparable:
            groups.setdefault(unit, []).append((row, number))
        if metric in {"REWARD_AMOUNT", "FEE"} and len(groups) > 1:
            warnings.append(
                "Farklı para birimleri kur dönüşümü yapılmadan ayrı karşılaştırıldı"
            )

        winners: list[dict[str, Any]] = []
        for unit in sorted(groups, key=lambda value: str(value or "")):
            group = groups[unit]
            extreme = (
                min(item[1] for item in group)
                if aggregation == "MIN"
                else max(item[1] for item in group)
            )
            winners.extend(
                item[0]
                for item in sorted(
                    (item for item in group if item[1] == extreme),
                    key=lambda item: str(item[0].get("id") or ""),
                )
            )
        return winners, warnings

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
        metric = plan.slots.get("metric")
        aggregation = plan.slots.get("aggregation")
        if plan.intent == "bank_list":
            banks = self.store.bank_summary()
            names = [str(bank.get("name") or bank.get("slug") or "") for bank in banks]
            answer = f"Kayıtlarda {len(names)} katılım bankası bulunuyor:"
            if names:
                answer += "\n" + "\n".join(f"- {name}" for name in names)
            return {
                "answer": answer,
                "facts": [
                    {
                        "metric": "BANK_COUNT",
                        "value": len(names),
                        "banks": names,
                    }
                ],
                "sources": [],
                "confidence": 0.99,
                "warnings": plan.warnings,
            }
        query_filters = {
            "bank_slugs": plan.slots.get("banks") or None,
            "product_type": plan.slots.get("product_type"),
            "financing_type": plan.slots.get("financing_type"),
        }
        rows, total = self.store.query_campaigns(
            **query_filters,
            limit=100,
        )
        if plan.intent == "campaign_count":
            bank_names = list(
                dict.fromkeys(
                    str(row.get("bank_name") or "").strip()
                    for row in rows
                    if str(row.get("bank_name") or "").strip()
                )
            )
            if len(bank_names) == 1:
                subject = f"{bank_names[0]} için"
            elif plan.slots.get("banks"):
                subject = "Seçili bankalar için"
            else:
                subject = "Kayıtlarda"
            return {
                "answer": f"{subject} doğrulanmış {total} kampanya bulundu.",
                "facts": [
                    {
                        "metric": "CAMPAIGN_COUNT",
                        "value": total,
                        "bank_slugs": plan.slots.get("banks") or [],
                    }
                ],
                # Sayım SQL'de yapılıyor; bu örnekler sonucu denetlemeyi kolaylaştırır.
                "sources": [self._source(row, None) for row in rows[:5]],
                "confidence": 0.99,
                "warnings": plan.warnings,
            }
        if aggregation in {"MIN", "MAX"} and total > len(rows):
            rows, _ = self.store.query_campaigns(
                **query_filters,
                limit=total,
            )
        comparison_warnings: list[str] = []
        if aggregation in {"MIN", "MAX"}:
            candidates, comparison_warnings = self._extrema_candidates(
                rows, metric, aggregation
            )
        else:
            candidates = self._balanced_candidates(rows, plan)
        if not candidates:
            return {
                "answer": (
                    "Bu sorgu için yapılandırılmış kayıtlarda "
                    "doğrulanabilir bilgi bulunamadı."
                ),
                "facts": [],
                "sources": [],
                "confidence": 0.0,
                "warnings": [
                    *plan.warnings,
                    *comparison_warnings,
                    "Kaynakta doğrulanabilir aday bulunamadı",
                ],
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
                elif metric == "REWARD_AMOUNT" and isinstance(value, dict):
                    detail = (
                        f"{value.get('amount')} {value.get('currency') or ''} ödül"
                    ).strip()
                else:
                    detail = str(value)
            lines.append(f"{fact['bank_name']} - {fact['title']}: {detail}")
        return {
            "answer": "\n".join(lines),
            "facts": facts,
            "sources": [self._source(row, metric) for row in candidates[:5]],
            "confidence": min(0.98, plan.confidence),
            "warnings": [*plan.warnings, *comparison_warnings],
        }

    def _hybrid_answer(self, plan: QueryPlan, *, limit: int) -> dict[str, Any]:
        filters = dict(plan.filters)
        filters["intent"] = plan.intent
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
        relation_sentences: list[str] = []
        for document in documents:
            excerpt = " ".join(document["text"].split())[:360]
            metadata = document["metadata"]
            evidence_text = excerpt
            char_start = metadata.get("char_start")
            char_end = metadata.get("char_end")
            section = str(metadata.get("section") or "")
            if section == "content" and "İçerik: " in document["text"]:
                evidence_text = document["text"].split("İçerik: ", 1)[1][:360]
                char_end = min(int(char_end), int(char_start) + len(evidence_text))
            elif section == "overview":
                lines = document["text"].splitlines()
                while lines and lines[0].startswith(("Başlık: ", "Banka: ")):
                    lines.pop(0)
                evidence_text = "\n".join(lines).split(
                    "\nYapılandırılmış alanlar:", 1
                )[0][:360]
                char_end = min(int(char_end), len(evidence_text))
            elif section == "structured_fields":
                char_start = None
                char_end = None
            excerpts.append(excerpt)
            for relation in metadata.get("graph_relations") or []:
                sentence = self._relation_sentence(relation)
                if sentence and sentence not in relation_sentences:
                    relation_sentences.append(sentence)
            sources.append(
                {
                    "campaign_id": metadata.get("campaign_id") or None,
                    "term_id": metadata.get("term_id") or None,
                    "bank_name": metadata.get("bank_name") or None,
                    "title": metadata.get("title") or None,
                    "source_url": metadata.get("source_url") or None,
                    "relations": metadata.get("graph_relations") or [],
                    "evidence": {
                        "text": evidence_text,
                        "char_start": char_start,
                        "char_end": char_end,
                    },
                    "retrieval_score": document["score"],
                    "retrieval_method": document["retrieval_method"],
                }
            )
        campaign_lines = []
        for index, source in enumerate(sources, start=1):
            if not source.get("campaign_id"):
                continue
            bank = str(source.get("bank_name") or "").strip()
            title = str(source.get("title") or "Kampanya").strip()
            label = f"{bank} — {title}" if bank else title
            line = f"- {label} [K{index}]"
            if line not in campaign_lines:
                campaign_lines.append(line)
        if campaign_lines:
            answer = "İlgili doğrulanmış kampanya kayıtları:\n" + "\n".join(
                campaign_lines[:5]
            )
        else:
            answer = "\n\n".join(excerpts[:3])
        if relation_sentences:
            answer = "\n".join(relation_sentences[:5]) + "\n\n" + answer
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
    def _claim_signatures(text: str) -> set[tuple[str, str, str]]:
        """Metindeki sayısal/finansal iddiaları karşılaştırılabilir biçime getirir."""

        normalized = _CITATION_RE.sub("", str(text or ""))
        normalized = _ORDERED_LIST_MARKER_RE.sub("", normalized)
        signatures: set[tuple[str, str, str]] = set()
        occupied: list[tuple[int, int]] = []

        for pattern, kind in (
            (_PERCENT_CLAIM_RE, "rate"),
            (_MONEY_CLAIM_RE, "money"),
            (_DURATION_CLAIM_RE, "duration"),
        ):
            for match in pattern.finditer(normalized):
                value = None
                unit = ""
                if kind == "rate":
                    rate = normalize_rate(match.group(0))
                    value = rate.fraction if rate else None
                elif kind == "money":
                    money = normalize_money(match.group(0))
                    value = money.amount if money else None
                    unit = money.currency if money else ""
                else:
                    duration = normalize_duration(match.group(0))
                    value = duration.value if duration else None
                    unit = duration.unit if duration else ""
                if value is not None:
                    signatures.add((kind, format(value, "f"), unit))
                    occupied.append(match.span())

        for match in _NUMBER_CLAIM_RE.finditer(normalized):
            if any(start <= match.start() and match.end() <= end for start, end in occupied):
                continue
            number = parse_number(match.group(0))
            if number is not None:
                signatures.add(("number", format(number, "f"), ""))
        if _FEE_FREE_CLAIM_RE.search(normalized):
            signatures.add(("fee", "0", "fee_free"))
        return signatures

    @classmethod
    def _valid_llm_answer(
        cls, answer: str, *, sources: list[dict[str, Any]]
    ) -> bool:
        normalized = answer.strip()
        if len(normalized) < 12 or "<think>" in normalized.casefold():
            return False
        citations = [int(value) for value in _CITATION_RE.findall(normalized)]
        if sources and not citations:
            return False
        if not all(1 <= citation <= len(sources) for citation in citations):
            return False

        source_signatures = []
        for source in sources:
            evidence = source.get("evidence")
            evidence_text = (
                evidence.get("text") if isinstance(evidence, dict) else evidence
            )
            supported_text = "\n".join(
                (
                    str(source.get("title") or ""),
                    str(evidence_text or ""),
                )
            )
            source_signatures.append(cls._claim_signatures(supported_text))

        claim_text = _ORDERED_LIST_MARKER_RE.sub("", normalized)
        segments = []
        for line in claim_text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("- ", "* ", "• ")):
                segments.append(stripped)
            else:
                segments.extend(re.split(r"(?<=[.!?])\s+", stripped))
        for segment in segments:
            claims = cls._claim_signatures(segment)
            if not claims:
                continue
            segment_citations = {
                int(value) for value in _CITATION_RE.findall(segment)
            }
            if not segment_citations:
                return False
            supported: set[tuple[str, str, str]] = set()
            for citation in segment_citations:
                supported.update(source_signatures[citation - 1])
            if not claims.issubset(supported):
                return False
        return True

    @classmethod
    def _sanitize_llm_answer(
        cls, answer: str, *, sources: list[dict[str, Any]]
    ) -> str | None:
        """Yalnız kanıtlanmayan sayısal iddia taşıyan liste satırlarını çıkarır."""

        source_signatures = []
        for source in sources:
            evidence = source.get("evidence")
            evidence_text = (
                evidence.get("text") if isinstance(evidence, dict) else evidence
            )
            source_signatures.append(
                cls._claim_signatures(
                    f"{source.get('title') or ''}\n{evidence_text or ''}"
                )
            )
        kept = []
        removed = False
        for line in str(answer or "").splitlines():
            stripped = line.strip()
            if not stripped.startswith(("- ", "* ", "• ")):
                kept.append(line)
                continue
            claims = cls._claim_signatures(stripped)
            citations = {int(value) for value in _CITATION_RE.findall(stripped)}
            supported: set[tuple[str, str, str]] = set()
            for citation in citations:
                if 1 <= citation <= len(source_signatures):
                    supported.update(source_signatures[citation - 1])
            if claims and (not citations or not claims.issubset(supported)):
                removed = True
                continue
            kept.append(line)
        sanitized = "\n".join(kept).strip()
        if not removed or not cls._valid_llm_answer(sanitized, sources=sources):
            return None
        return sanitized

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
        polished = re.sub(r"(?m)^\s*\*\s+", "• ", polished)
        polished = polished.replace("**", "")
        polished = re.sub(r"\*([^*\n]+)\*", r"\1", polished)
        return polished

    def _generation(
        self, *, mode: str, fallback_reason: str | None = None
    ) -> dict[str, Any]:
        metadata_factory = getattr(self.llm, "generation_metadata", None)
        provider_metadata = metadata_factory() if callable(metadata_factory) else {}
        return {
            "mode": mode,
            "model": self.llm.model if mode == "llm" else None,
            "fallback_reason": fallback_reason,
            "prompt": self.prompt_builder.metadata(),
            "retrieval_backend": getattr(self.retriever, "last_backend", "bm25"),
            **provider_metadata,
        }

    def stream_answer(
        self, message: str, *, limit: int = 5
    ) -> Iterator[dict[str, Any]]:
        """Kanıt paketini ve yalnız doğrulanmış nihai yanıtı aktarır."""

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
            elif grounded["plan"]["intent"] == "bank_list":
                fallback_reason = "deterministic_bank_list"
            elif grounded["plan"]["intent"] == "campaign_count":
                # SQL toplamı kesin yanıttır; modele yeniden yazdırmak gerekmez.
                fallback_reason = "deterministic_count"
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
            candidate_factory = getattr(self.llm, "stream_chat_candidates", None)
            if callable(candidate_factory):
                rejected = False
                for chunks, candidate_metadata in candidate_factory(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                ):
                    generated = "".join(chunks).strip()
                    sanitized = None
                    valid = (
                        candidate_metadata.get("finish_reason") != "length"
                        and self._valid_llm_answer(
                            generated, sources=grounded["sources"]
                        )
                    )
                    if not valid and candidate_metadata.get("finish_reason") != "length":
                        sanitized = self._sanitize_llm_answer(
                            generated, sources=grounded["sources"]
                        )
                        valid = sanitized is not None
                    if not valid:
                        rejected = True
                        self.llm.reject_candidate(candidate_metadata)
                        continue
                    if sanitized is not None:
                        candidate_metadata["validation"] = "unsupported_lines_removed"
                    self.llm.accept_candidate(candidate_metadata)
                    polished = self._polish_llm_answer(sanitized or generated)
                    yield {"event": "delta", "data": {"text": polished}}
                    mode = "llm"
                    yield {"event": "done", "data": self._generation(mode="llm")}
                    return
                fallback_reason = (
                    "llm_output_rejected" if rejected else "llm_unavailable"
                )
                yield {"event": "delta", "data": {"text": fallback_answer}}
                yield {
                    "event": "done",
                    "data": self._generation(
                        mode="fallback", fallback_reason=fallback_reason
                    ),
                }
                return

            chunks: list[str] = []
            try:
                for chunk in self.llm.stream_chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                ):
                    chunks.append(chunk)
                generated = "".join(chunks).strip()
                if not self._valid_llm_answer(
                    generated, sources=grounded["sources"]
                ):
                    yield {"event": "delta", "data": {"text": fallback_answer}}
                    yield {
                        "event": "done",
                        "data": self._generation(
                            mode="fallback", fallback_reason="llm_output_rejected"
                        ),
                    }
                    return
                polished = self._polish_llm_answer(generated)
                yield {"event": "delta", "data": {"text": polished}}
                mode = "llm"
                yield {"event": "done", "data": self._generation(mode="llm")}
            except LLMUnavailableError:
                yield {"event": "delta", "data": {"text": fallback_answer}}
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
            metadata_factory = getattr(self.llm, "generation_metadata", None)
            provider_metadata = metadata_factory() if callable(metadata_factory) else {}
            self.recorder.record(
                "answer_generated",
                latency_ms=(perf_counter() - started) * 1000,
                success=success,
                route=route,
                generation_mode=mode,
                provider=provider_metadata.get("provider"),
                requested_model=provider_metadata.get("requested_model"),
                circuit_state=provider_metadata.get("circuit_state"),
                retrieval_backend=getattr(self.retriever, "last_backend", "bm25"),
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
