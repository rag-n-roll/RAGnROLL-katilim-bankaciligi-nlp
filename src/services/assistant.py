"""Structured-first yönlendirme ve kanıt paketli yanıt servisi."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from time import perf_counter, sleep
import re
from typing import Any, Iterator

from src.llm import (
    EvrenDecisionService,
    GroundedPromptBuilder,
    OpenAICompatibleLLM,
    build_llm_from_env,
)
from src.llm.client import LLMUnavailableError
from src.llm.judging import SemanticJudge
from src.financing import build_financing_quotes, fetch_official_quotes
from src.normalization import normalize_duration, normalize_money, normalize_rate
from src.normalization.values import parse_number
from src.observability import EventRecorder
from src.persistence import CampaignStore
from src.policy import (
    Action,
    ComparisonCriteria,
    InputGuard,
    OutputGate,
    PolicyDecision,
    present_answer,
)
from src.policy.tool_policy import ALLOWED_BANKS
from src.preprocessing.clean_text import tokenize_turkish
from src.prompt_optimization import IntentTraceRecorder
from src.query import DomainQueryCompiler, QueryPlan
from src.query.compiler import _answer_confidence
from src.retrieval import HybridRetriever
from src.services.conversation import (
    FINANCING_TYPE_LABELS,
    extract_comparison_criteria,
    extract_contextual_fee_priority,
    extract_financing_type,
    merge_criteria,
)
from src.services.orchestration import ToolOrchestrator


def _safe_stream_chunks(text: str, *, words_per_chunk: int = 3) -> Iterator[str]:
    """Doğrulanmış metni küçük parçalar halinde aktarır; ham düşünceyi hiç açmaz."""
    clean = str(text or "")
    words = re.findall(r"\S+\s*", clean)
    for start in range(0, len(words), words_per_chunk):
        yield "".join(words[start : start + words_per_chunk])
        sleep(0.035)


def _complete_excerpt(text: str, *, limit: int = 360) -> str:
    """Kanıt özetini son tamamlanmış cümlede kes; yarım hüküm üretme."""

    clean = " ".join(str(text or "").split()).strip()
    if len(clean) <= limit:
        return clean
    bounded = clean[:limit].rstrip()
    sentence_ends = [match.end() for match in re.finditer(r"[.!?](?=\s|$)", bounded)]
    if sentence_ends:
        return bounded[: sentence_ends[-1]].rstrip()
    return bounded.rstrip(" ,;:-") + "…"


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _source_value(source: dict[str, Any], key: str) -> Any:
    value = source.get(key)
    if value is not None and (not isinstance(value, str) or value.strip()):
        return value
    metadata = source.get("metadata")
    return metadata.get(key) if isinstance(metadata, dict) else None


def stable_source_key(source: dict[str, Any]) -> str:
    """Return a stable evidence identity across raw and normalized source shapes."""

    for key in ("campaign_id", "term_id", "document_id"):
        value = str(_source_value(source, key) or "").strip()
        if value:
            return f"{key}:{value}"
    source_url = str(_source_value(source, "source_url") or "").strip()
    if source_url:
        return f"source_url:{source_url}"
    evidence = source.get("evidence")
    evidence_text = evidence.get("text") if isinstance(evidence, dict) else evidence
    if evidence_text in (None, ""):
        evidence_text = source.get("text")
    material = f"{_source_value(source, 'title') or ''}\n{evidence_text or ''}"
    return f"content:{sha256(material.encode('utf-8')).hexdigest()}"


def deduplicate_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the greatest-scoring source per stable identity in input-key order."""

    winners: dict[
        str, tuple[int, tuple[int, float], dict[str, Any]]
    ] = {}
    for index, source in enumerate(sources):
        key = stable_source_key(source)
        score = _finite(source.get("retrieval_score"))
        if score is None:
            score = _finite(source.get("score"))
        rank = (1, score) if score is not None else (0, 0.0)
        current = winners.get(key)
        if current is None or rank > current[1]:
            winners[key] = (current[0] if current else index, rank, source)
    deduplicated = []
    for _, rank, source in sorted(winners.values(), key=lambda item: item[0]):
        normalized = dict(source)
        normalized["retrieval_score"] = rank[1] if rank[0] else 0.0
        deduplicated.append(normalized)

    # Aynı kampanya scraper/ingest turlarında farklı teknik kimliklerle gelebilir.
    # Kullanıcı açısından banka + normalize başlık aynı kaynak rozetidir.
    semantic_winners: dict[str, tuple[int, dict[str, Any]]] = {}
    for index, source in enumerate(deduplicated):
        campaign_id = str(_source_value(source, "campaign_id") or "").strip()
        bank = " ".join(str(_source_value(source, "bank_name") or "").split())
        title = " ".join(str(_source_value(source, "title") or "").split())
        semantic_key = (
            f"campaign:{bank.casefold()}:{title.casefold()}"
            if campaign_id and bank and title
            else stable_source_key(source)
        )
        current = semantic_winners.get(semantic_key)
        if current is None:
            semantic_winners[semantic_key] = (index, source)
        elif source["retrieval_score"] > current[1]["retrieval_score"]:
            semantic_winners[semantic_key] = (current[0], source)
    return [
        source
        for _, source in sorted(semantic_winners.values(), key=lambda item: item[0])
    ]


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
_FEE_FREE_QUERY_RE = re.compile(
    r"\b(?:masrafs[ıi]z|masraf(?:s[ıi]z)?\s+(?:kart|hesap|bankac[ıi]l[ıi]k)|"
    r"aidats[ıi]z|ücretsiz\s+(?:kart|hesap|bankac[ıi]l[ıi]k))\b",
    re.IGNORECASE,
)
_FEE_FREE_EVIDENCE_RE = re.compile(
    r"\b(?:masrafs[ıi]z|masraflara\s+son|masraf\s+yok|aidats[ıi]z|"
    r"kart\s+(?:aidat[ıi]|ücreti)\s+yok|"
    r"ücretsiz\s+(?:kart|hesap|bankac[ıi]l[ıi]k))\b",
    re.IGNORECASE,
)
_FINANCING_EVIDENCE_PATTERNS = {
    "housing": re.compile(r"\b(?:konut|ev\s+al[ıi]m|mortgage)\w*\b", re.IGNORECASE),
    "vehicle": re.compile(
        r"\b(?:"
        r"(?:taş[ıi]t|araç|otomobil|motosiklet|togg|otomotiv)\w*"
        r"(?:\s+\w+){0,2}\s+finansman\w*|"
        r"finansman\w*(?:\s+\w+){0,2}\s+"
        r"(?:taş[ıi]t|araç|otomobil|motosiklet|togg|otomotiv)\w*"
        r")\b",
        re.IGNORECASE,
    ),
    "consumer": re.compile(r"\b(?:ihtiyaç|tüketici)\s+finansman\w*\b", re.IGNORECASE),
    "commercial": re.compile(
        r"\b(?:ticari|işletme|kobi)\s+finansman\w*\b", re.IGNORECASE
    ),
    "agriculture": re.compile(
        r"\b(?:tar[ıi]m|ziraat|çiftçi)\s+finansman\w*\b", re.IGNORECASE
    ),
}
_QUALITATIVE_FINANCE_CLAIM_RE = re.compile(
    r"\b(?:riba|garar|meysir|şeriat|helal|haram|güvenli|"
    r"risk\s+paylaş\w*|varlığa\s+dayalı|kâr[-\s]+zarar\s+ortaklığ\w*|"
    r"en\s+iyi|en\s+uygun|en\s+avantajl\w*|daha\s+avantajl\w*|"
    r"tercih\s+edil\w*|öne\s+çık\w*|kesinlikle\s+öneril\w*|"
    r"garanti\w*)\b",
    re.IGNORECASE,
)
_ABSOLUTE_ADVICE_CLAIM_RE = re.compile(
    r"(?:en\s+iyi|en\s+uygun|en\s+avantajl\w*|"
    r"tercih\s+edil\w*|kesinlikle\s+öneril\w*)",
    re.IGNORECASE,
)
_RELATIVE_COMPARISON_CLAIM_RE = re.compile(
    r"(?:daha\s+avantajl\w*|öne\s+çık\w*)",
    re.IGNORECASE,
)
_METRIC_CLAIM_PATTERNS = {
    "PROFIT_RATE": re.compile(r"\b(?:k[âa]r\s+pay[ıi]|oran)\w*\b", re.IGNORECASE),
    "MATURITY": re.compile(r"\b(?:vade|vadeli|ay)\b", re.IGNORECASE),
    "FEE": re.compile(r"\b(?:masraf|ücret|aidat|maliyet)\w*\b", re.IGNORECASE),
    "REWARD_AMOUNT": re.compile(
        r"\b(?:ödül|puan|iade|kazanç)\w*\b", re.IGNORECASE
    ),
}
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
        output_gate: OutputGate | None = None,
        judge: Any | None = None,
        input_guard: InputGuard | None = None,
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
        if output_gate is not None:
            self.output_gate = output_gate
        else:
            semantic_judge = judge
            if semantic_judge is None and llm is None:
                # Judge çağrısı cevap üreticisinin sağlayıcı metadata'sını ezmesin.
                semantic_judge = SemanticJudge(build_llm_from_env())
            self.output_gate = OutputGate(judge=semantic_judge)
        self.input_guard = input_guard or InputGuard()

    def compile(self, message: str) -> QueryPlan:
        plan, _ = self._compile_with_policy(message)
        return plan

    def _deterministic_plan(self, message: str) -> QueryPlan:
        plan = self.compiler.compile(
            message, known_banks=self.store.bank_summary()
        )
        criteria = extract_comparison_criteria(message)
        explicit_profit_rate_preference = (
            plan.slots.get("metric") == "PROFIT_RATE"
            and plan.slots.get("aggregation") == "MIN"
        )
        implicit_financing_quote = (
            plan.intent != "product_comparison"
            and plan.slots.get("financing_type")
            in {"consumer", "vehicle", "housing", "commercial"}
            and criteria.get("term_months") is not None
            and criteria.get("amount") is not None
        )
        slots = {
            **plan.slots,
            "term_months_min": criteria.get("term_months_min"),
            "term_months_max": criteria.get("term_months_max"),
            "explicit_profit_rate_preference": explicit_profit_rate_preference,
        }
        if not implicit_financing_quote:
            return replace(plan, slots=slots)
        if criteria.get("fee_priority") is True or plan.slots.get("metric") == "FEE":
            slots.update({"metric": "FEE", "aggregation": "MIN"})
        else:
            slots.update({"metric": "PROFIT_RATE", "aggregation": "MIN"})
        return replace(
            plan,
            intent="product_comparison",
            route=self.compiler.route_for(
                "product_comparison", slots, trusted_domain=True
            ),
            slots=slots,
            warnings=[
                *plan.warnings,
                "Tutar ve vade içeren finansman isteği teklif karşılaştırmasına yönlendirildi",
            ],
        )

    def _compile_with_policy(
        self, message: str
    ) -> tuple[QueryPlan, PolicyDecision | None]:
        input_decision = self.input_guard.inspect(message)
        if input_decision is not None:
            plan = self.compiler.compile(message, known_banks=self.store.bank_summary())
            safe_plan = replace(
                plan,
                route="SAFE_REDIRECT",
                intent=input_decision.intent,
                warnings=list(plan.warnings) + [input_decision.reason_code],
            )
            return safe_plan, input_decision
        known_banks = self.store.bank_summary()
        plan = self._deterministic_plan(message)
        if plan.route == "SAFE_REDIRECT":
            return plan, None
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
            if isinstance(decision, PolicyDecision):
                llm_decision = decision
                clarification_allowed = (
                    decision.action == Action.CLARIFY
                    and decision.intent == plan.intent == "product_comparison"
                    and plan.slots.get("aggregation") not in {"MIN", "MAX"}
                    and bool(decision.criteria.missing())
                )
                terminal_override = decision.action in {
                    Action.REFUSE,
                    Action.REDIRECT,
                } or (decision.action == Action.CLARIFY and not clarification_allowed)
                if terminal_override:
                    selected = replace(
                        plan,
                        warnings=[
                            *plan.warnings,
                            "LLM terminal politika önerisi güvenilir yerel planla "
                            "çeliştiği için yok sayıldı",
                        ],
                    )
                    decision = None
                else:
                    selected = self._merge_llm_plan(plan, decision)
                if decision is not None and decision.action == Action.ANSWER:
                    tool_call, effective_criteria = self._tool_call_for_plan(
                        selected, criteria=decision.criteria
                    )
                    model_calls = tuple(decision.tool_calls)
                    # Yalnız model ile deterministik plan aynı aracı seçtiyse
                    # argümanları güvenli plandan yeniden kur. Bilinmeyen veya
                    # rota ile uyuşmayan araç adını sessizce yetkilendirme.
                    equivalent_ontology_call = (
                        selected.intent in {"definition", "relationship_query"}
                        and len(model_calls) == 1
                        and model_calls[0].get("name") == "ontology"
                        and tool_call["name"] == "hybrid_rag"
                    )
                    if (
                        len(model_calls) == 1
                        and model_calls[0].get("name") == tool_call["name"]
                    ) or equivalent_ontology_call:
                        updates: dict[str, Any] = {
                            "intent": selected.intent,
                            "criteria": effective_criteria,
                            "tool_calls": (tool_call,),
                        }
                        if hasattr(decision, "normalized_query"):
                            updates["normalized_query"] = selected.canonical_query
                        if hasattr(decision, "slots"):
                            updates["slots"] = selected.slots
                        decision = replace(decision, **updates)
                    else:
                        selected = replace(
                            plan,
                            warnings=[
                                *plan.warnings,
                                "LLM araç planı yerel sözleşmeyle uyuşmadı; "
                                "güvenilir yerel plan kullanıldı",
                            ],
                        )
                        decision = None
                try:
                    self.intent_trace.record(
                        raw_input=message,
                        bank_catalog=known_banks,
                        deterministic_plan=plan.to_dict(),
                        llm_decision=(
                            llm_decision.to_dict()
                            if callable(getattr(llm_decision, "to_dict", None))
                            else llm_decision
                        ),
                        selected_plan=selected.to_dict(),
                    )
                except OSError:
                    # Eğitim izi yanıt yolunu kesemez; metrikler ana akışta tutulur.
                    pass
                return selected, decision
            return plan, None

        # Enjekte edilmiş eski karar servisleri için geriye uyumlu yol.
        safe = self.decisions.is_safe(message)
        advised_route = self.decisions.route(message)
        warnings = list(plan.warnings)
        if safe is False or advised_route == "SAFE_REDIRECT":
            warnings.append("EVREN güvenlik sinyali güvenli yönlendirme önerdi")
            return replace(plan, route="SAFE_REDIRECT", warnings=warnings), None
        if advised_route == "STRUCTURED_SQL":
            trusted_domain = bool(
                plan.confidence_components.get("trusted_domain", False)
            )
            eligible_route = self.compiler.route_for(
                plan.intent, plan.slots, trusted_domain=trusted_domain
            )
            if eligible_route == "STRUCTURED_SQL":
                return replace(plan, route="STRUCTURED_SQL"), None
            warnings.append(
                "EVREN structured route önerisi ölçülebilir sorgu koşullarını karşılamadı"
            )
            return replace(plan, route=eligible_route, warnings=warnings), None
        if advised_route not in {None, plan.route, "HYBRID_RAG"}:
            warnings.append("EVREN route önerisi yerel sözleşmeyle uyuşmadığı için yok sayıldı")
            return replace(plan, warnings=warnings), None
        return plan, None

    @staticmethod
    def _local_policy_decision(
        plan: QueryPlan, *, criteria: ComparisonCriteria | None = None
    ) -> PolicyDecision:
        """Adapt a trusted compiler plan to the same validated tool contract."""

        if plan.route == "SAFE_REDIRECT":
            action = Action.REFUSE if plan.intent == "unknown" else Action.REDIRECT
            return PolicyDecision(
                action=action,
                in_domain=True,
                intent=plan.intent,
                confidence=plan.confidence,
                reason_code="deterministic_safe_redirect",
                safe_message=(
                    "Yalnız katılım bankacılığı, finansman, kart, hesap ve "
                    "kampanyalar hakkında yardımcı olabilirim."
                    if action == Action.REFUSE
                    else "Bu sistem müşteri işlemi gerçekleştirmez. Lütfen ilgili "
                    "bankanın resmî destek kanalını kullanın."
                ),
            )
        tool_call, effective_criteria = GroundedAssistant._tool_call_for_plan(
            plan, criteria=criteria
        )
        return PolicyDecision(
            action=Action.ANSWER,
            in_domain=True,
            intent=plan.intent,
            confidence=plan.confidence,
            reason_code="deterministic_compiler_plan",
            criteria=effective_criteria,
            tool_calls=(tool_call,),
        )

    @staticmethod
    def _tool_call_for_plan(
        plan: QueryPlan, *, criteria: ComparisonCriteria | None = None
    ) -> tuple[dict[str, Any], ComparisonCriteria]:
        effective_criteria = criteria or ComparisonCriteria()
        term_months = (
            effective_criteria.term_months
            if effective_criteria.term_months is not None
            else plan.slots.get("term_months")
        )
        amount = (
            effective_criteria.amount
            if effective_criteria.amount is not None
            else plan.slots.get("amount")
        )
        fee_priority = (
            effective_criteria.fee_priority
            if effective_criteria.fee_priority is not None
            else plan.slots.get("fee_priority")
        )
        sourced_financing_comparison = (
            plan.intent == "product_comparison"
            and plan.slots.get("financing_type")
            in {"consumer", "vehicle", "housing", "commercial"}
            and plan.slots.get("term_months") is not None
            and plan.slots.get("amount") is not None
            and not effective_criteria.missing()
        )
        tool_name = (
            "financing_quote"
            if sourced_financing_comparison
            else "comparison"
            if plan.intent == "product_comparison"
            else "structured_sql"
            if plan.route == "STRUCTURED_SQL"
            else "hybrid_rag"
        )
        is_financing = (
            plan.slots.get("product_type") == "financing"
            or plan.slots.get("financing_type") is not None
        )
        if (
            not sourced_financing_comparison
            and plan.intent == "product_comparison"
            and (
                plan.slots.get("aggregation") in {"MIN", "MAX"}
                or not is_financing
            )
        ):
            # Objective extrema or non-financing campaign comparisons do not require
            # loan preference criteria; complete only the authorization contract.
            effective_criteria = ComparisonCriteria(1, 0.0, False)
            term_months = effective_criteria.term_months
            amount = effective_criteria.amount
            fee_priority = effective_criteria.fee_priority
        arguments = {
            key: value
            for key, value in {
                "banks": plan.slots.get("banks"),
                "metric": (
                    plan.slots.get("metric")
                    if tool_name == "structured_sql"
                    else None
                ),
                "aggregation": (
                    plan.slots.get("aggregation")
                    if tool_name == "structured_sql"
                    else None
                ),
                "product_type": (
                    plan.slots.get("product_type")
                    if tool_name != "financing_quote"
                    else None
                ),
                "financing_type": plan.slots.get("financing_type"),
                "term_months": term_months
                if tool_name in {"comparison", "financing_quote"}
                else None,
                "amount": amount
                if tool_name in {"comparison", "financing_quote"}
                else None,
                "fee_priority": fee_priority
                if tool_name in {"comparison", "financing_quote"}
                else None,
                "term_months_min": plan.slots.get("term_months_min")
                if tool_name == "financing_quote"
                else None,
                "term_months_max": plan.slots.get("term_months_max")
                if tool_name == "financing_quote"
                else None,
            }.items()
            if value not in (None, [], "")
        }
        return {"name": tool_name, "arguments": arguments}, effective_criteria

    def _merge_llm_plan(
        self, plan: QueryPlan, decision: dict[str, Any]
    ) -> QueryPlan:
        """Model planını yalnız yerel sözleşmenin izin verdiği ölçüde uygular."""

        if decision.get("safe") is False or decision.get("route") == "SAFE_REDIRECT":
            return replace(
                plan,
                warnings=[
                    *plan.warnings,
                    "LLM güvenlik planı güvenilir yerel planla çeliştiği için yok sayıldı",
                ],
            )

        proposed_intent = str(decision["intent"])
        allowed_intent_upgrades = {("campaign_query", "campaign_count")}
        if (
            proposed_intent != plan.intent
            and (plan.intent, proposed_intent) not in allowed_intent_upgrades
        ):
            return replace(
                plan,
                warnings=[
                    *plan.warnings,
                    "LLM intent önerisi güvenilir yerel planla çeliştiği için yok sayıldı",
                ],
            )
        intent = proposed_intent
        advised_route = str(decision["route"])
        decision_slots = decision.get("slots") or {}
        slots = dict(plan.slots)
        # Banka filtresi yalnız kullanıcının metninden deterministik olarak
        # çıkarılabilir; model yeni banka ekleyerek kapsamı genişletemez.
        slots["banks"] = list(plan.slots.get("banks") or [])
        for key in ("metric", "aggregation", "product_type", "financing_type"):
            if plan.slots.get(key) not in (None, [], ""):
                continue
            value = decision_slots.get(key)
            if value not in (None, [], ""):
                slots[key] = value
            else:
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
            plan.terminology_rewrites,
            source="llm_plan",
            trusted_domain_sources=trusted_sources,
        )
        normalized_query = str(decision.get("normalized_query") or "").strip()
        canonical_query = (
            normalized_query
            if route == "STRUCTURED_SQL" and normalized_query
            else plan.canonical_query
        )
        return replace(
            plan,
            canonical_query=canonical_query,
            intent=intent,
            route=route,
            slots=slots,
            filters=filters,
            terminology_rewrites=plan.terminology_rewrites,
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

    @staticmethod
    def _source_has_evidence(source: dict[str, Any]) -> bool:
        evidence = source.get("evidence")
        text = evidence.get("text") if isinstance(evidence, dict) else evidence
        if not str(text or "").strip():
            return False
        return bool(
            str(source.get("campaign_id") or source.get("term_id") or "").strip()
            or str(source.get("document_id") or source.get("source_url") or "").strip()
        )

    def _structured_answer(self, plan: QueryPlan) -> dict[str, Any]:
        metric = plan.slots.get("metric")
        aggregation = plan.slots.get("aggregation")
        if plan.intent == "bank_list":
            banks = self.store.bank_summary()
            names = [str(bank.get("name") or bank.get("slug") or "") for bank in banks]
            names = [name for name in names if name.strip()]
            answer = f"Kayıtlarda {len(names)} katılım bankası bulunuyor:"
            if names:
                answer += "\n" + "\n".join(f"- {name}" for name in names)
            answer_confidence = 0.99 if names else 0.0
            _, confidence_components = _answer_confidence(
                typed=len(names), evidenced=len(names), candidates=len(names)
            )
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
                "confidence": answer_confidence,
                "answer_confidence": answer_confidence,
                "confidence_components": confidence_components,
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
            sources = deduplicate_sources(
                [self._source(row, None) for row in rows[:5]]
            )
            verified = bool(sources) and isinstance(total, int) and total > 0
            answer_confidence = 0.99 if verified else 0.0
            _, confidence_components = _answer_confidence(
                typed=len(sources) if verified else 0,
                evidenced=len(sources) if verified else 0,
                candidates=len(sources) if verified else 0,
            )
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
                "sources": sources,
                "confidence": answer_confidence,
                "answer_confidence": answer_confidence,
                "confidence_components": confidence_components,
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
            answer_confidence, confidence_components = _answer_confidence(
                typed=0, evidenced=0, candidates=0
            )
            return {
                "answer": (
                    "Bu sorgu için yapılandırılmış kayıtlarda "
                    "doğrulanabilir bilgi bulunamadı."
                ),
                "facts": [],
                "sources": [],
                "confidence": answer_confidence,
                "answer_confidence": answer_confidence,
                "confidence_components": confidence_components,
                "warnings": [
                    *plan.warnings,
                    *comparison_warnings,
                    "Kaynakta doğrulanabilir aday bulunamadı",
                ],
            }
        selected_rows = []
        seen_candidates: set[str] = set()
        for row in candidates:
            candidate_key = str(row.get("id") or "").strip()
            if not candidate_key:
                candidate_key = stable_source_key(self._source(row, metric))
            if candidate_key in seen_candidates:
                continue
            seen_candidates.add(candidate_key)
            selected_rows.append(row)
            if len(selected_rows) == 5:
                break
        facts = []
        for row in selected_rows:
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
        sources = deduplicate_sources(
            [self._source(row, metric) for row in selected_rows]
        )
        typed = sum(
            self._comparison_value(row, metric) is not None for row in selected_rows
        )
        evidenced = sum(self._source_has_evidence(source) for source in sources)
        answer_confidence, confidence_components = _answer_confidence(
            typed=typed,
            evidenced=evidenced,
            candidates=len(facts),
        )
        return {
            "answer": "\n".join(lines),
            "facts": facts,
            "sources": sources,
            "confidence": answer_confidence,
            "answer_confidence": answer_confidence,
            "confidence_components": confidence_components,
            "warnings": [*plan.warnings, *comparison_warnings],
        }

    @staticmethod
    def _financing_catalog_items(filename: str, key: str) -> list[dict[str, Any]]:
        path = PROJECT_ROOT / "data" / filename
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = payload.get(key)
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    @staticmethod
    def _try_amount(value: Any) -> str:
        number = _finite(value)
        if number is None:
            return "belirtilmedi"
        return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " TL"

    def _financing_answer(
        self,
        plan: QueryPlan,
        *,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        financing_type = str(arguments["financing_type"])
        amount = float(arguments["amount"])
        term_months = int(arguments["term_months"])
        term_months_min = int(arguments.get("term_months_min") or term_months)
        term_months_max = int(arguments.get("term_months_max") or term_months)
        term_range = list(range(term_months_min, term_months_max + 1))
        fee_priority = bool(arguments["fee_priority"])
        bank_slugs = {
            str(item) for item in arguments.get("banks", []) if str(item).strip()
        }
        eligible = bank_slugs or None
        banks = self._financing_catalog_items("raw/participation_banks.json", "banks")
        records = self.store.list_campaigns()
        if not records:
            records = self._financing_catalog_items("processed/campaigns.json", "records")

        def packet_for_term(months: int) -> tuple[int, dict[str, Any]]:
            official_quotes = fetch_official_quotes(
                financing_type=financing_type,
                amount=amount,
                term_months=months,
                eligible_bank_slugs=eligible,
            )
            return months, build_financing_quotes(
                records=records,
                banks=banks,
                financing_type=financing_type,
                amount=amount,
                term_months=months,
                official_quotes=official_quotes,
                eligible_bank_slugs=eligible,
                fee_priority=fee_priority,
            )

        packets: dict[int, dict[str, Any]] = {}
        if len(term_range) == 1:
            months, packet = packet_for_term(term_range[0])
            packets[months] = packet
        else:
            with ThreadPoolExecutor(max_workers=min(3, len(term_range))) as executor:
                futures = {
                    executor.submit(packet_for_term, months): months
                    for months in term_range
                }
                for future in as_completed(futures):
                    months, packet = future.result()
                    packets[months] = packet

        verified: list[dict[str, Any]] = []
        for months in term_range:
            for quote in packets[months]["quotes"]:
                if (
                    quote.get("status") == "available"
                    and str(quote.get("source_url") or "").startswith("https://")
                    and str(quote.get("retrieved_at") or "").strip()
                    and _finite(quote.get("monthly_installment")) is not None
                    and _finite(quote.get("total_repayment")) is not None
                ):
                    verified.append({**quote, "_term_months": months})
        objective_profit_rate = (
            plan.slots.get("metric") == "PROFIT_RATE"
            and plan.slots.get("aggregation") in {"MIN", "MAX"}
        )
        explicit_profit_rate_preference = bool(
            plan.slots.get("explicit_profit_rate_preference")
        )
        if objective_profit_rate:
            direction = 1 if plan.slots.get("aggregation") == "MIN" else -1
            verified.sort(
                key=lambda quote: (
                    _finite(quote.get("monthly_profit_rate")) is None,
                    direction
                    * (_finite(quote.get("monthly_profit_rate")) or 0.0),
                    _finite(quote.get("total_repayment")) or float("inf"),
                    int(quote["_term_months"]),
                    str(quote.get("bank_name") or ""),
                )
            )
        elif fee_priority:
            verified.sort(
                key=lambda quote: (
                    quote.get("fees_total") is None,
                    _finite(quote.get("fees_total")) or 0.0,
                    _finite(quote.get("total_repayment")) or float("inf"),
                    int(quote["_term_months"]),
                    str(quote.get("bank_name") or ""),
                )
            )
        else:
            verified.sort(
                key=lambda quote: (
                    _finite(quote.get("total_repayment")) or float("inf"),
                    int(quote["_term_months"]),
                    str(quote.get("bank_name") or ""),
                )
            )

        displayed_quotes = verified
        if len(term_range) > 1 and explicit_profit_rate_preference:
            displayed_quotes = []
            for months in term_range:
                candidates = [
                    quote
                    for quote in verified
                    if int(quote["_term_months"]) == months
                ]
                if candidates:
                    displayed_quotes.append(candidates[0])
        elif len(term_range) > 1:
            displayed_quotes = sorted(
                verified,
                key=lambda quote: (
                    int(quote["_term_months"]),
                    _finite(quote.get("monthly_profit_rate")) is None,
                    _finite(quote.get("monthly_profit_rate")) or 0.0,
                    str(quote.get("bank_name") or ""),
                ),
            )

        facts: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []
        lines: list[str] = []
        amount_text = self._try_amount(amount)
        for index, quote in enumerate(displayed_quotes, start=1):
            bank_slug = str(quote.get("bank_slug") or "")
            bank_name = str(quote.get("bank_name") or bank_slug)
            product_name = str(quote.get("product_name") or "Finansman")
            quote_term_months = int(quote["_term_months"])
            monthly_rate = _finite(quote.get("monthly_profit_rate"))
            installment = self._try_amount(quote.get("monthly_installment"))
            total = self._try_amount(quote.get("total_repayment"))
            fees = self._try_amount(quote.get("fees_total"))
            rate_text = (
                f"%{monthly_rate:.2f}".replace(".", ",")
                if monthly_rate is not None
                else "belirtilmedi"
            )
            evidence = (
                f"{bank_name} — {product_name}. Finansman tutarı {amount_text}; "
                f"vade {quote_term_months} ay; aylık kâr payı {rate_text}; "
                f"aylık taksit {installment}; toplam geri ödeme {total}; "
                f"toplam masraf {fees}. Doğrulama zamanı: {quote['retrieved_at']}."
            )
            facts.append(
                {
                    "quote_id": (
                        f"{bank_slug}:{financing_type}:"
                        f"{int(amount)}:{quote_term_months}"
                    ),
                    "bank_slug": bank_slug,
                    "bank_name": bank_name,
                    "product_name": product_name,
                    "financing_type": financing_type,
                    "amount": amount,
                    "term_months": quote_term_months,
                    "fee_priority": fee_priority,
                    "monthly_profit_rate": monthly_rate,
                    "monthly_installment": _finite(quote.get("monthly_installment")),
                    "total_repayment": _finite(quote.get("total_repayment")),
                    "fees_total": _finite(quote.get("fees_total")),
                    "retrieved_at": quote["retrieved_at"],
                }
            )
            sources.append(
                {
                    "campaign_id": (
                        f"financing:{bank_slug}:{financing_type}:"
                        f"{int(amount)}:{quote_term_months}"
                    ),
                    "bank_name": bank_name,
                    "title": product_name,
                    "source_url": quote["source_url"],
                    "retrieved_at": quote["retrieved_at"],
                    "evidence": {"text": evidence, "char_start": 0, "char_end": len(evidence)},
                    "retrieval_score": 1.0,
                    "retrieval_method": "official_financing_quote",
                }
            )
            term_prefix = (
                f"{quote_term_months} ay — " if len(term_range) > 1 else ""
            )
            lines.append(
                f"- {term_prefix}{bank_name} — {product_name}: "
                f"aylık kâr payı {rate_text}; "
                f"aylık taksit {installment}; toplam geri ödeme {total}; "
                f"masraf {fees} [K{index}]"
            )

        if lines:
            priority = (
                "aylık kâr payı oranına"
                if objective_profit_rate
                else "masraf önceliğine"
                if fee_priority
                else "toplam geri ödemeye"
            )
            if len(term_range) > 1:
                range_text = f"{term_months_min}-{term_months_max} ay"
                intro = (
                    f"{amount_text} için {range_text} aralığındaki "
                    f"{len(term_range)} vadenin her biri ayrı hesaplandı."
                )
                if explicit_profit_rate_preference and verified:
                    best = verified[0]
                    best_rate = _finite(best.get("monthly_profit_rate"))
                    best_rate_text = (
                        f"%{best_rate:.2f}".replace(".", ",")
                        if best_rate is not None
                        else "belirtilmedi"
                    )
                    intro += (
                        f" En düşük aylık kâr payı {best_rate_text} ile "
                        f"{best.get('bank_name')} tarafından "
                        f"{int(best['_term_months'])} ay vadede sunuldu. "
                        "Eşit oranlarda daha düşük toplam geri ödeme öne alındı."
                    )
                else:
                    intro += (
                        " Açık bir tercih belirtilmediği için teklifler "
                        "tarafsız biçimde sıralandı."
                    )
                answer = intro + "\n" + "\n".join(lines)
            else:
                answer = (
                    f"{amount_text} ve {term_months} ay için doğrulanmış teklifler "
                    f"{priority} göre tarafsız sıralandı:\n" + "\n".join(lines)
                )
        else:
            term_text = (
                f"{term_months_min}-{term_months_max} ay aralığı"
                if len(term_range) > 1
                else f"{term_months} ay"
            )
            answer = (
                f"{amount_text} ve {term_text} için resmî kaynağı ve doğrulama "
                "zamanı bulunan karşılaştırılabilir bir teklif alınamadı."
            )
        typed = len(facts)
        confidence, components = _answer_confidence(
            typed=typed, evidenced=len(sources), candidates=typed
        )
        return {
            "answer": answer,
            "facts": facts,
            "sources": sources,
            "quote_coverage": (
                packets[term_months]["coverage"]
                if len(term_range) == 1
                else {
                    "term_count": len(term_range),
                    "terms": {
                        str(months): packets[months]["coverage"]
                        for months in term_range
                    },
                }
            ),
            "confidence": confidence,
            "answer_confidence": confidence,
            "confidence_components": components,
            "warnings": plan.warnings,
        }

    def _hybrid_answer(self, plan: QueryPlan, *, limit: int) -> dict[str, Any]:
        filters = dict(plan.filters)
        filters["intent"] = plan.intent
        aidatsiz_card_query = (
            plan.intent == "product_search"
            and plan.slots.get("product_type") == "card"
            and re.search(r"\baidats[ıi]z\b", plan.original_query, re.IGNORECASE)
        )
        if plan.intent == "definition":
            # Ürün/finansman slotları tanım ontolojisinin metadata alanları
            # değildir. Bu filtreleri taşımak geçerli terimleri Chroma'da sıfırlar.
            filters = {
                "intent": plan.intent,
                "source_types": ["terminology", "pdf_evidence"],
            }
        elif plan.intent in {
            "application_requirements",
            "campaign_query",
            "product_comparison",
            "product_search",
        }:
            filters["source_types"] = ["campaign"]
        documents = self.retriever.retrieve(
            plan.canonical_query, filters=filters, limit=limit
        )
        financing_type = str(plan.slots.get("financing_type") or "")
        financing_pattern = _FINANCING_EVIDENCE_PATTERNS.get(financing_type)
        if financing_pattern and plan.intent in {
            "application_requirements",
            "campaign_query",
            "product_comparison",
            "product_search",
        }:
            # NLP/uzak indeks metadata etiketi aday üretir; kullanıcıya sunulması
            # için finansman türü başlık veya getirilen kanıtta açıkça geçmelidir.
            documents = [
                document
                for document in documents
                if financing_pattern.search(
                    "\n".join(
                        (
                            str(document.get("metadata", {}).get("title") or ""),
                            str(document.get("text") or ""),
                        )
                    )
                )
            ]
        if (
            plan.intent == "product_search"
            and _FEE_FREE_QUERY_RE.search(plan.original_query)
        ):
            # "Masrafsız" bir seçim ölçütüdür; yalnız kart kategorisine yakın
            # adaylar yeterli değildir. Açık masraf/aidat kanıtı olmayan kampanya
            # modele ve kullanıcıya seçenek olarak sunulmaz.
            documents = [
                document
                for document in documents
                if _FEE_FREE_EVIDENCE_RE.search(
                    "\n".join(
                        (
                            str(document.get("metadata", {}).get("title") or ""),
                            str(document.get("text") or ""),
                        )
                    )
                )
            ]
        if aidatsiz_card_query and not documents:
            terminology_filters = {**filters, "source_types": ["terminology"]}
            documents = [
                document
                for document in self.retriever.retrieve(
                    plan.canonical_query,
                    filters=terminology_filters,
                    limit=limit,
                )
                if _FEE_FREE_EVIDENCE_RE.search(
                    "\n".join(
                        (
                            str(document.get("metadata", {}).get("title") or ""),
                            str(document.get("text") or ""),
                        )
                    )
                )
            ]
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
                pdf_documents = [
                    document
                    for document in documents
                    if document.get("metadata", {}).get("source_type")
                    == "pdf_evidence"
                ]
                documents = exact_documents + pdf_documents
        if not documents:
            answer_confidence, confidence_components = _answer_confidence(
                typed=0, evidenced=0, candidates=0
            )
            return {
                "answer": "Bu bilgi sağlanan resmî içerik ve terminoloji kayıtlarında bulunamadı.",
                "facts": [],
                "sources": [],
                "confidence": answer_confidence,
                "answer_confidence": answer_confidence,
                "confidence_components": confidence_components,
                "warnings": [*plan.warnings, "Retrieval sonucu bulunamadı"],
            }
        excerpts = []
        sources = []
        relation_sentences: list[str] = []
        for document in documents:
            excerpt = _complete_excerpt(document["text"])
            metadata = document["metadata"]
            evidence_text = excerpt
            char_start = metadata.get("char_start")
            char_end = metadata.get("char_end")
            section = str(metadata.get("section") or "")
            if section == "content" and "İçerik: " in document["text"]:
                evidence_text = _complete_excerpt(
                    document["text"].split("İçerik: ", 1)[1]
                )
                char_end = min(int(char_end), int(char_start) + len(evidence_text))
            elif section == "overview":
                lines = document["text"].splitlines()
                while lines and lines[0].startswith(("Başlık: ", "Banka: ")):
                    lines.pop(0)
                evidence_text = "\n".join(lines).split(
                    "\nYapılandırılmış alanlar:", 1
                )[0]
                evidence_text = _complete_excerpt(evidence_text)
                char_end = min(int(char_end), len(evidence_text))
            elif section == "terminology":
                # Ontolojiye ait dahili sınıflandırma alanları yanıt kanıtı değildir.
                # Modele yalnızca terim ve doğrulanmış tanımı vererek Entity/Ana
                # kategori dökümünün kullanıcı yanıtına sızmasını engelle.
                evidence_text = excerpt.split(" Ana kategori:", 1)[0]
                char_start = None
                char_end = None
            elif section == "structured_fields":
                char_start = None
                char_end = None
            sources.append(
                {
                    "campaign_id": _source_value(document, "campaign_id") or None,
                    "term_id": _source_value(document, "term_id") or None,
                    "document_id": _source_value(document, "document_id") or None,
                    "bank_name": _source_value(document, "bank_name") or None,
                    "title": _source_value(document, "title") or None,
                    "source_url": _source_value(document, "source_url") or None,
                    "page_start": metadata.get("page_start"),
                    "page_end": metadata.get("page_end"),
                    "publisher": metadata.get("publisher") or None,
                    "ontology_term_ids": [
                        term_id
                        for term_id in str(
                            metadata.get("ontology_term_ids") or ""
                        ).split(",")
                        if term_id
                    ],
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
        sources = deduplicate_sources(sources)
        for source in sources:
            if source.get("campaign_id"):
                continue
            for relation in source.get("relations") or []:
                sentence = self._relation_sentence(relation)
                if sentence and sentence not in relation_sentences:
                    relation_sentences.append(sentence)
        excerpts = [
            str(source.get("evidence", {}).get("text") or "")
            for source in sources
        ]
        campaign_lines = []
        for index, source in enumerate(sources, start=1):
            if not source.get("campaign_id"):
                continue
            bank = str(source.get("bank_name") or "").strip()
            title = str(source.get("title") or "Kampanya").strip()
            label = f"{bank} — {title}" if bank else title
            relation_details = []
            for relation in source.get("relations") or []:
                sentence = self._relation_sentence(relation)
                if sentence:
                    relation_details.append(
                        sentence.removeprefix(f"{title}, ")
                    )
            if relation_details:
                label += f" — {relation_details[0]}"
            line = f"- {label} [K{index}]"
            if line not in campaign_lines:
                campaign_lines.append(line)
        if campaign_lines:
            if (
                plan.intent == "product_comparison"
                and plan.slots.get("aggregation") not in {"MIN", "MAX"}
            ):
                answer = (
                    "Belirttiğiniz vade, tutar ve masraf önceliğine göre tek bir "
                    "seçeneği en uygun olarak doğrulayamıyorum; kayıtlarda tarafsız "
                    "bir toplam maliyet karşılaştırması için yeterli ölçülebilir veri yok.\n"
                    "İncelenebilecek doğrulanmış seçenekler:\n"
                    + "\n".join(campaign_lines[:5])
                )
            else:
                answer = "İlgili doğrulanmış kampanya kayıtları:\n" + "\n".join(
                    campaign_lines[:5]
                )
        else:
            answer = "\n\n".join(excerpts[:3])
        if relation_sentences:
            answer = "\n".join(relation_sentences[:5]) + "\n\n" + answer
        if plan.intent == "definition" and excerpts:
            answer = excerpts[0].split(" Ana kategori:", 1)[0].strip()
            if plan.slots.get("financing_type") == "housing":
                answer = (
                    "Konut finansmanı, katılım bankacılığı çerçevesinde faizsiz "
                    "finans prensipleri ve uyum kuralları gözetilerek yürütülür. "
                    "Bu açıklama doğrulanmış kaynakta yer alan genel ilkedir; "
                    "ürünün güncel kâr oranı, vadesi ve masrafları için ilgili "
                    "kampanya/ürün kaydının ayrıca incelenmesi gerekir."
                )
        evidenced = sum(self._source_has_evidence(source) for source in sources)
        answer_confidence, confidence_components = _answer_confidence(
            typed=0, evidenced=evidenced, candidates=len(sources)
        )
        return {
            "answer": answer,
            "facts": [],
            "sources": sources,
            "confidence": answer_confidence,
            "answer_confidence": answer_confidence,
            "confidence_components": confidence_components,
            "warnings": plan.warnings,
        }

    def _grounded_result(
        self,
        message: str,
        *,
        limit: int,
        criteria: ComparisonCriteria | None = None,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 10:
            raise ValueError("limit 1 ile 10 arasında olmalıdır")
        plan, policy_decision = self._compile_with_policy(message)
        if criteria is not None:
            plan = replace(
                plan,
                slots={
                    **plan.slots,
                    "term_months": criteria.term_months,
                    "amount": criteria.amount,
                    "fee_priority": criteria.fee_priority,
                },
            )
            if (
                policy_decision is not None
                and policy_decision.in_domain
                and policy_decision.intent == "product_comparison"
                and policy_decision.action in {Action.ANSWER, Action.CLARIFY}
                and not criteria.missing()
            ):
                # Takip mesajından deterministik olarak çıkarılmış tam kriterler,
                # planlayıcının yalnız özgün soruyu görüp verdiği eski CLARIFY
                # kararından daha güvenilirdir. Terminal safety kararları korunur.
                tool_call, effective_criteria = self._tool_call_for_plan(
                    plan, criteria=criteria
                )
                policy_decision = replace(
                    policy_decision,
                    action=Action.ANSWER,
                    criteria=effective_criteria,
                    missing_criteria=(),
                    tool_calls=(tool_call,),
                    reason_code="comparison_criteria_satisfied",
                )
        decision = policy_decision or self._local_policy_decision(
            plan, criteria=criteria
        )
        orchestrator = ToolOrchestrator(
            allowed_banks=set(ALLOWED_BANKS) | {
                str(bank.get("slug") or "")
                for bank in self.store.bank_summary()
                if str(bank.get("slug") or "")
            }
        )
        validated_plan = orchestrator.validate(decision)
        validated_decision = validated_plan.decision
        if validated_decision.action == Action.CLARIFY:
            return self._clarification_answer(
                message=message,
                plan=plan,
                criteria=validated_decision.criteria,
                financing_type=str(plan.slots.get("financing_type") or "") or None,
            )
        if validated_decision.action in {Action.REFUSE, Action.REDIRECT}:
            result = {
                "answer": validated_decision.safe_message or (
                    "Bu istek politika tarafından güvenli biçimde durduruldu."
                ),
                "action": validated_decision.action.value,
                "policy_reason_code": validated_decision.reason_code,
                "missing_criteria": [],
                "conversation_state": None,
                "facts": [],
                "sources": [],
                "confidence": validated_decision.confidence,
                "warnings": plan.warnings,
            }
        else:
            effective_criteria = criteria or validated_decision.criteria
            expected_call, _ = self._tool_call_for_plan(
                plan, criteria=effective_criteria
            )
            if expected_call["name"] == "financing_quote":
                def operation(call: Any) -> dict[str, Any]:
                    return self._financing_answer(plan, arguments=call["arguments"])
            elif plan.route == "STRUCTURED_SQL":
                def operation(_call: Any) -> dict[str, Any]:
                    return self._structured_answer(plan)
            else:
                def operation(_call: Any) -> dict[str, Any]:
                    return self._hybrid_answer(plan, limit=limit)
            result = orchestrator.execute(
                validated_plan,
                expected_call=expected_call,
                operation=operation,
            )
            if result is not None:
                result["executed_tool"] = expected_call["name"]
        if result is None:
            result = {
                "answer": "Bu istek için doğrulanmış bir araç planı bulunamadı.",
                "facts": [],
                "sources": [],
                "confidence": 0.0,
                "warnings": [*plan.warnings, "Araç çağrısı politika tarafından engellendi"],
            }
        if validated_decision.action != Action.ANSWER or "answer_confidence" not in result:
            answer_confidence, confidence_components = _answer_confidence(
                typed=0, evidenced=0, candidates=0
            )
            result["confidence"] = answer_confidence
            result["answer_confidence"] = answer_confidence
            result["confidence_components"] = confidence_components
        action = result.get("action") or (
            validated_decision.action.value
            if hasattr(validated_decision.action, "value")
            else "ANSWER"
        )
        sources = deduplicate_sources(result.get("sources") or [])
        raw_answer = str(result.get("answer") or "")
        presented = present_answer(raw_answer, sources=sources)
        return {
            "action": action,
            "missing_criteria": result.get("missing_criteria", []),
            "conversation_state": result.get("conversation_state"),
            **result,
            "answer": presented.answer_display,
            "answer_display": presented.answer_display,
            "sources": presented.sources,
            "plan": plan.to_dict(),
        }

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
    def _comparison_claim_supported(
        cls,
        *,
        context: dict[str, Any] | None,
        sources: list[dict[str, Any]],
        citations: set[int],
        segment: str,
    ) -> bool:
        safe_context = context if isinstance(context, dict) else {}
        plan = safe_context.get("plan")
        plan = plan if isinstance(plan, dict) else {}
        slots = plan.get("slots")
        slots = slots if isinstance(slots, dict) else {}
        facts = safe_context.get("facts")
        facts = facts if isinstance(facts, list) else []
        plan_metric = str(slots.get("metric") or "")
        metric_pattern = _METRIC_CLAIM_PATTERNS.get(plan_metric)
        fact_campaign_ids = {
            str(fact.get("campaign_id") or "").strip()
            for fact in facts
            if isinstance(fact, dict)
            and str(fact.get("campaign_id") or "").strip()
            and fact.get("value") is not None
            and fact.get("metric") == plan_metric
        }
        cited_campaign_ids = {
            str(_source_value(sources[citation - 1], "campaign_id") or "").strip()
            for citation in citations
            if 1 <= citation <= len(sources)
        }
        objective = slots.get("aggregation") in {"MIN", "MAX"}
        complete_preferences = all(
            slots.get(key) is not None
            for key in ("term_months", "amount", "fee_priority")
        )
        return (
            plan.get("intent") == "product_comparison"
            and (objective or complete_preferences)
            and metric_pattern is not None
            and bool(metric_pattern.search(segment))
            and bool(_RELATIVE_COMPARISON_CLAIM_RE.search(segment))
            and bool(cited_campaign_ids)
            and cited_campaign_ids.issubset(fact_campaign_ids)
        )

    @classmethod
    def _valid_llm_answer(
        cls,
        answer: str,
        *,
        sources: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
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
        source_texts = []
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
            source_texts.append(supported_text.casefold())
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
            if _ABSOLUTE_ADVICE_CLAIM_RE.search(segment):
                return False
            claims = cls._claim_signatures(segment)
            qualitative_claims = {
                match.group(0).casefold()
                for match in _QUALITATIVE_FINANCE_CLAIM_RE.finditer(segment)
            }
            if not claims and not qualitative_claims:
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
            qualitative_support = "\n".join(
                source_texts[citation - 1] for citation in segment_citations
            )
            comparison_supported = cls._comparison_claim_supported(
                context=context,
                sources=sources,
                citations=segment_citations,
                segment=segment,
            )
            if any(
                term not in qualitative_support
                and not (
                    comparison_supported
                    and _RELATIVE_COMPARISON_CLAIM_RE.fullmatch(term)
                )
                for term in qualitative_claims
            ):
                return False
        return True

    @classmethod
    def _sanitize_llm_answer(
        cls,
        answer: str,
        *,
        sources: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
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
        if not removed or not cls._valid_llm_answer(
            sanitized, sources=sources, context=context
        ):
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
        polished = re.sub(
            r"\s*\[(?:verified_fallback_answer|verified_fallback|fallback_answer|fallback)\]",
            "",
            polished,
            flags=re.IGNORECASE,
        )
        polished = re.sub(r"(?m)^\s*\*\s+", "• ", polished)
        polished = polished.replace("**", "")
        polished = re.sub(r"\*([^*\n]+)\*", r"\1", polished)
        polished = re.sub(r"([:;,.!?])(?:\s*[,;:.!?])+", r"\1", polished)
        return polished

    def _generation(
        self, *, mode: str, fallback_reason: str | None = None
    ) -> dict[str, Any]:
        metadata_factory = getattr(self.llm, "generation_metadata", None)
        llm_attempted = mode == "llm" or fallback_reason in {
            "llm_output_rejected",
            "llm_unavailable",
        }
        provider_metadata = (
            metadata_factory()
            if llm_attempted and callable(metadata_factory)
            else {}
        )
        if fallback_reason in {
            "safe_redirect",
            "policy_redirect",
            "policy_refuse",
            "policy_clarify",
        }:
            retrieval_backend = "not_run"
        elif fallback_reason in {
            "deterministic_bank_list",
            "deterministic_count",
        }:
            retrieval_backend = "structured_sql"
        else:
            retrieval_backend = getattr(self.retriever, "last_backend", "bm25")
        return {
            "mode": mode,
            "model": self.llm.model if mode == "llm" else None,
            "fallback_reason": fallback_reason,
            "prompt": self.prompt_builder.metadata(),
            "retrieval_backend": retrieval_backend,
            **provider_metadata,
        }

    def stream_answer(
        self,
        message: str,
        *,
        limit: int = 5,
        criteria: ComparisonCriteria | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Kanıt paketini ve yalnız doğrulanmış nihai yanıtı aktarır."""

        started = perf_counter()
        success = True
        route = "UNKNOWN"
        mode = "fallback"
        fallback_reason: str | None = None
        try:
            grounded = self._grounded_result(message, limit=limit, criteria=criteria)
            route = str(grounded["plan"]["route"])
            fallback_answer = str(grounded["answer"])
            metadata = {key: value for key, value in grounded.items() if key != "answer"}
            yield {"event": "meta", "data": metadata}

            if grounded.get("action") != "ANSWER":
                fallback_reason = (
                    "safe_redirect"
                    if grounded.get("policy_reason_code")
                    == "deterministic_safe_redirect"
                    else f"policy_{str(grounded.get('action')).casefold()}"
                )
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
                presented_fallback = present_answer(
                    fallback_answer, sources=grounded["sources"]
                )
                for text_chunk in _safe_stream_chunks(presented_fallback.answer_display):
                    yield {"event": "delta", "data": {"text": text_chunk}}
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
                def accepted_candidate(
                    prompt: str, *, repair: bool = False
                ) -> tuple[str | None, bool]:
                    rejected_in_pass = False
                    selected_factory = (
                        getattr(self.llm, "stream_chat_repair_candidates", None)
                        if repair
                        else candidate_factory
                    )
                    if not callable(selected_factory):
                        selected_factory = candidate_factory
                    for chunks, candidate_metadata in selected_factory(
                        system_prompt=system_prompt,
                        user_prompt=prompt,
                    ):
                        generated = "".join(chunks).strip()
                        sanitized = None
                        valid = (
                            candidate_metadata.get("finish_reason") != "length"
                            and self._valid_llm_answer(
                                generated,
                                sources=grounded["sources"],
                                context={
                                    "plan": grounded["plan"],
                                    "facts": grounded["facts"],
                                },
                            )
                        )
                        if (
                            not valid
                            and candidate_metadata.get("finish_reason") != "length"
                        ):
                            sanitized = self._sanitize_llm_answer(
                                generated,
                                sources=grounded["sources"],
                                context={
                                    "plan": grounded["plan"],
                                    "facts": grounded["facts"],
                                },
                            )
                            valid = sanitized is not None
                        if valid:
                            candidate_text = sanitized or generated
                            gate_verdict = self.output_gate.validate(
                                candidate_text,
                                sources=grounded["sources"],
                                question=message,
                                context={
                                    "plan": grounded["plan"],
                                    "facts": grounded["facts"],
                                },
                            )
                            if not gate_verdict.valid:
                                valid = False
                        if not valid:
                            rejected_in_pass = True
                            self.llm.reject_candidate(candidate_metadata)
                            continue
                        if sanitized is not None:
                            candidate_metadata["validation"] = (
                                "unsupported_lines_removed"
                            )
                        self.llm.accept_candidate(candidate_metadata)
                        return self._polish_llm_answer(
                            sanitized or generated
                        ), rejected_in_pass
                    return None, rejected_in_pass

                accepted, rejected = accepted_candidate(user_prompt)
                if accepted is None and rejected:
                    repair_user_prompt = (
                        f"{user_prompt}\n\n"
                        "Önceki yanıt doğrulama veya tekrar denetiminden geçemedi. "
                        "Lütfen KANIT PAKETİ'ne tam olarak sadık kalarak, "
                        "tekrarsız ve tarafsız biçimde yanıtı yeniden üret."
                    )
                    accepted, repair_rejected = accepted_candidate(
                        repair_user_prompt, repair=True
                    )
                    rejected = rejected or repair_rejected
                if accepted is not None:
                    presented = present_answer(
                        accepted, sources=grounded["sources"]
                    )
                    for text_chunk in _safe_stream_chunks(presented.answer_display):
                        yield {"event": "delta", "data": {"text": text_chunk}}
                    mode = "llm"
                    yield {"event": "done", "data": self._generation(mode="llm")}
                    return
                fallback_reason = (
                    "llm_output_rejected" if rejected else "llm_unavailable"
                )
                presented_fallback = present_answer(
                    fallback_answer, sources=grounded["sources"]
                )
                for text_chunk in _safe_stream_chunks(presented_fallback.answer_display):
                    yield {"event": "delta", "data": {"text": text_chunk}}
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
                sanitized = None
                valid = self._valid_llm_answer(
                    generated,
                    sources=grounded["sources"],
                    context={
                        "plan": grounded["plan"],
                        "facts": grounded["facts"],
                    },
                )
                if not valid:
                    sanitized = self._sanitize_llm_answer(
                        generated,
                        sources=grounded["sources"],
                        context={
                            "plan": grounded["plan"],
                            "facts": grounded["facts"],
                        },
                    )
                    valid = sanitized is not None
                if valid:
                    candidate_text = sanitized or generated
                    gate_verdict = self.output_gate.validate(
                        candidate_text,
                        sources=grounded["sources"],
                        question=message,
                        context={
                            "plan": grounded["plan"],
                            "facts": grounded["facts"],
                        },
                    )
                    if not gate_verdict.valid:
                        valid = False
                # Single repair attempt if first generation is non-empty but invalid
                if not valid and generated:
                    repair_chunks: list[str] = []
                    repair_user_prompt = (
                        f"{user_prompt}\n\n"
                        "Önceki yanıt doğrulama veya tekrar denetiminden geçemedi. "
                        "Lütfen KANIT PAKETİ'ne tam olarak sadık kalarak, "
                        "tekrarsız ve tarafsız biçimde yanıtı yeniden üret."
                    )
                    try:
                        for chunk in self.llm.stream_chat(
                            system_prompt=system_prompt,
                            user_prompt=repair_user_prompt,
                        ):
                            repair_chunks.append(chunk)
                        repaired = "".join(repair_chunks).strip()
                        repaired_sanitized = None
                        repaired_valid = self._valid_llm_answer(
                            repaired,
                            sources=grounded["sources"],
                            context={
                                "plan": grounded["plan"],
                                "facts": grounded["facts"],
                            },
                        )
                        if not repaired_valid:
                            repaired_sanitized = self._sanitize_llm_answer(
                                repaired,
                                sources=grounded["sources"],
                                context={
                                    "plan": grounded["plan"],
                                    "facts": grounded["facts"],
                                },
                            )
                            repaired_valid = repaired_sanitized is not None
                        if repaired_valid:
                            repaired_candidate = repaired_sanitized or repaired
                            repaired_verdict = self.output_gate.validate(
                                repaired_candidate,
                                sources=grounded["sources"],
                                question=message,
                                context={
                                    "plan": grounded["plan"],
                                    "facts": grounded["facts"],
                                },
                            )
                            if repaired_verdict.valid:
                                valid = True
                                generated = repaired
                                sanitized = repaired_sanitized
                    except Exception:
                        pass

                if not valid:
                    presented_fallback = present_answer(
                        fallback_answer, sources=grounded["sources"]
                    )
                    for text_chunk in _safe_stream_chunks(presented_fallback.answer_display):
                        yield {"event": "delta", "data": {"text": text_chunk}}
                    yield {
                        "event": "done",
                        "data": self._generation(
                            mode="fallback", fallback_reason="llm_output_rejected"
                        ),
                    }
                    return
                polished = self._polish_llm_answer(sanitized or generated)
                presented = present_answer(polished, sources=grounded["sources"])
                for text_chunk in _safe_stream_chunks(presented.answer_display):
                    yield {"event": "delta", "data": {"text": text_chunk}}
                mode = "llm"
                yield {"event": "done", "data": self._generation(mode="llm")}
            except LLMUnavailableError:
                presented_fallback = present_answer(
                    fallback_answer, sources=grounded["sources"]
                )
                for text_chunk in _safe_stream_chunks(presented_fallback.answer_display):
                    yield {"event": "delta", "data": {"text": text_chunk}}
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
            request_metadata = self._generation(
                mode=mode,
                fallback_reason=fallback_reason,
            )
            self.recorder.record(
                "answer_generated",
                latency_ms=(perf_counter() - started) * 1000,
                success=success,
                route=route,
                generation_mode=mode,
                fallback_reason=fallback_reason,
                provider=request_metadata.get("provider"),
                requested_model=request_metadata.get("requested_model"),
                circuit_state=request_metadata.get("circuit_state"),
                retrieval_backend=request_metadata.get("retrieval_backend"),
            )

    @staticmethod
    def _clarification_answer(
        *,
        message: str,
        plan: QueryPlan,
        criteria: ComparisonCriteria,
        financing_type: str | None = None,
        missing_criteria: list[str] | None = None,
    ) -> dict[str, Any]:
        missing = missing_criteria or criteria.missing()
        labels = {
            "financing_type": "finansman türünü",
            "term_months": "vade süresini",
            "amount": "finansman tutarını",
            "fee_priority": "masraf önceliğinizi",
        }
        if missing == ["financing_type"]:
            supported = "\n".join(
                f"- {label}" for label in FINANCING_TYPE_LABELS.values()
            )
            answer_display = (
                "Hangi finansman türünü almak istiyorsunuz? "
                "Karşılaştırabildiğim finansman türleri:\n" + supported
            )
        else:
            requested = [labels[name] for name in missing]
            if len(requested) == 1:
                requested_text = requested[0]
            else:
                requested_text = ", ".join(requested[:-1]) + f" ve {requested[-1]}"
            financing_label = FINANCING_TYPE_LABELS.get(str(financing_type or ""))
            subject = f"{financing_label} için " if financing_label else ""
            answer_display = (
                f"{subject}karşılaştırma yapabilmem için "
                f"{requested_text} belirtir misiniz?"
            )
        return {
            "answer": answer_display,
            "answer_display": answer_display,
            "action": "CLARIFY",
            "missing_criteria": missing,
            "conversation_state": {
                "pending_intent": "product_comparison",
                "pending_query": message,
                "financing_type": financing_type,
                "criteria": {
                    "term_months": criteria.term_months,
                    "amount": criteria.amount,
                    "fee_priority": criteria.fee_priority,
                },
            },
            "facts": [],
            "sources": [],
            "confidence": 0.0,
            "answer_confidence": 0.0,
            "confidence_components": {
                "typed_field": 0.0,
                "evidence_coverage": 0.0,
                "candidate_coverage": 0.0,
            },
            "warnings": plan.warnings,
            "plan": plan.to_dict(),
            "generation": {
                "mode": "fallback",
                "model": None,
                "fallback_reason": "missing_comparison_criteria",
            },
        }

    def answer(
        self,
        message: str,
        *,
        limit: int = 5,
        conversation_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Streaming sözleşmesini tüketerek geriye uyumlu toplu yanıt döndürür."""

        response: dict[str, Any] = {}
        answer_parts: list[str] = []
        generation = self._generation(mode="fallback", fallback_reason="unknown")
        for item in self.stream_conversation_answer(
            message,
            limit=limit,
            conversation_state=conversation_state,
        ):
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
        answer_display = "".join(answer_parts).strip()
        plan = response.get("plan", {})
        action = str(response.get("action") or "ANSWER")
        if "action" not in response and plan.get("route") == "SAFE_REDIRECT":
            action = "REFUSE" if plan.get("intent") == "unknown" else "REDIRECT"
        return {
            **response,
            "answer": answer_display,
            "answer_display": answer_display,
            "action": action,
            "missing_criteria": response.get("missing_criteria", []),
            "conversation_state": response.get("conversation_state"),
            "generation": generation,
        }

    def stream_conversation_answer(
        self,
        message: str,
        *,
        limit: int = 5,
        conversation_state: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Konuşma kriterlerini çözüp aynı sözleşmeyle SSE olayları üret."""

        # Açıklama ve konuşma belleği yalnız güvenli girdiler için devreye girer.
        # İlk mesaj da takip mesajı da aynı terminal güvenlik kararını uygular.
        if self.input_guard.inspect(message) is not None:
            yield from self.stream_answer(message, limit=limit)
            return

        criteria: ComparisonCriteria | None = None
        execution_message = message
        clarification: dict[str, Any] | None = None
        if conversation_state is not None:
            if conversation_state.get("pending_intent") != "product_comparison":
                raise ValueError("Geçersiz konuşma durumu")
            # Takip mesajı yalnız eksik slotları doldursa da güvenlik katmanını
            # yeniden geçmek zorundadır. Önceki güvenli soru, sonraki mesaj için
            # bir politika yetkisi olarak kullanılamaz.
            follow_up_plan = self._deterministic_plan(message)
            follow_up_criteria = extract_comparison_criteria(message)
            follow_up_financing_type = extract_financing_type(message)
            state_criteria = dict(conversation_state.get("criteria") or {})
            if (
                "fee_priority" not in follow_up_criteria
                and state_criteria.get("fee_priority") is None
            ):
                contextual_fee = extract_contextual_fee_priority(message)
                if contextual_fee is not None:
                    follow_up_criteria["fee_priority"] = contextual_fee

            is_explicit_non_financing = (
                follow_up_plan.slots.get("product_type") in {
                    "card",
                    "investment",
                    "participation_account",
                    "insurance",
                }
                or (
                    follow_up_plan.intent == "product_search"
                    and follow_up_plan.slots.get("product_type") not in {"financing", None}
                )
            )
            is_distinct_intent = follow_up_plan.intent in {
                "definition",
                "bank_list",
                "count_query",
                "campaign_query",
                "rate_query",
                "maturity_query",
            }
            if is_explicit_non_financing or is_distinct_intent:
                yield from self.stream_conversation_answer(
                    message, limit=limit, conversation_state=None
                )
                return

            if not follow_up_criteria and follow_up_financing_type is None:
                if follow_up_plan.route == "SAFE_REDIRECT":
                    yield from self.stream_answer(message, limit=limit)
                    return
            execution_message = str(conversation_state.get("pending_query") or "")
            pending_plan = self._deterministic_plan(execution_message)
            if pending_plan.intent not in {"product_comparison", "product_search"}:
                pending_financing_type = (
                    pending_plan.slots.get("financing_type")
                    or extract_financing_type(execution_message)
                )
                if (
                    pending_plan.slots.get("product_type") == "financing"
                    or pending_financing_type in FINANCING_TYPE_LABELS
                ):
                    pending_plan = replace(
                        pending_plan,
                        intent="product_comparison",
                        route="HYBRID_RAG",
                        slots={
                            **pending_plan.slots,
                            "product_type": "financing",
                            "financing_type": pending_financing_type,
                        },
                    )
                else:
                    raise ValueError("Konuşma durumu karşılaştırma isteğiyle uyuşmuyor")
            financing_type = str(
                conversation_state.get("financing_type")
                or pending_plan.slots.get("financing_type")
                or ""
            ) or None
            if financing_type is not None and financing_type not in FINANCING_TYPE_LABELS:
                raise ValueError("Geçersiz finansman türü")
            if follow_up_financing_type is not None:
                financing_type = follow_up_financing_type
            criteria = merge_criteria(
                ComparisonCriteria(), dict(conversation_state.get("criteria") or {})
            )
            criteria = merge_criteria(
                criteria, follow_up_criteria
            )
            if financing_type is None:
                clarification = self._clarification_answer(
                    message=execution_message,
                    plan=replace(
                        pending_plan,
                        intent="product_comparison",
                        route="HYBRID_RAG",
                        slots={**pending_plan.slots, "product_type": "financing"},
                    ),
                    criteria=criteria,
                    missing_criteria=["financing_type"],
                )
            else:
                comparison_context = [FINANCING_TYPE_LABELS[financing_type]]
                if criteria.term_months is not None:
                    comparison_context.append(f"{criteria.term_months} ay")
                if criteria.amount is not None:
                    comparison_context.append(f"{criteria.amount:.2f} TL")
                if criteria.fee_priority is True:
                    comparison_context.append("masraf öncelikli")
                elif criteria.fee_priority is False:
                    comparison_context.append("masraf önemli değil")
                execution_message = " ".join(
                    (execution_message, *comparison_context)
                )
                pending_plan = self._deterministic_plan(execution_message)
                objective_financing_comparison = (
                    pending_plan.intent == "product_comparison"
                    and pending_plan.slots.get("aggregation") in {"MIN", "MAX"}
                    and pending_plan.slots.get("financing_type")
                    in {"consumer", "vehicle", "housing", "commercial"}
                    and pending_plan.slots.get("explicit_profit_rate_preference")
                    is True
                )
                missing_criteria = (
                    [
                        name
                        for name in ("term_months", "amount")
                        if getattr(criteria, name) is None
                    ]
                    if objective_financing_comparison
                    else criteria.missing()
                )
                if missing_criteria:
                    clarification = self._clarification_answer(
                        message=str(conversation_state.get("pending_query") or ""),
                        plan=replace(
                            pending_plan,
                            intent="product_comparison",
                            route="HYBRID_RAG",
                        ),
                        criteria=criteria,
                        financing_type=financing_type,
                        missing_criteria=missing_criteria,
                    )
                elif objective_financing_comparison and criteria.fee_priority is None:
                    criteria = merge_criteria(criteria, {"fee_priority": False})
        else:
            pending_plan = self._deterministic_plan(message)
            raw_criteria = extract_comparison_criteria(message)
            criteria = merge_criteria(ComparisonCriteria(), raw_criteria)
            financing_type = str(
                pending_plan.slots.get("financing_type")
                or extract_financing_type(message)
                or ""
            ) or None
            financing_context = (
                financing_type in FINANCING_TYPE_LABELS
                and (
                    bool(raw_criteria)
                    or (
                        pending_plan.intent != "definition"
                        and (
                            pending_plan.slots.get("product_type") == "financing"
                            or bool(
                                re.search(
                                    r"\b(?:finansman|kredi)\w*\b",
                                    pending_plan.canonical_query.casefold(),
                                )
                            )
                            or (
                                pending_plan.intent
                                in {"product_search", "product_comparison"}
                                and bool(
                                    re.search(
                                        r"\b(?:al\w*|bank\w*|uygun|oran\w*|vade\w*)\b",
                                        pending_plan.canonical_query.casefold(),
                                    )
                                )
                            )
                        )
                    )
                )
            )
            is_financing_product = (
                pending_plan.intent in {"product_search", "product_comparison"}
                and pending_plan.slots.get("product_type") == "financing"
            ) or (
                financing_context and pending_plan.route != "STRUCTURED_SQL"
            )
            generic_financing_request = (
                is_financing_product
                and financing_type is None
                and (pending_plan.intent == "product_comparison" or bool(raw_criteria))
            )
            specific_financing_request = (
                is_financing_product
                and financing_type in FINANCING_TYPE_LABELS
                and (
                    bool(raw_criteria)
                    or (
                        pending_plan.intent == "product_comparison"
                        and pending_plan.route != "STRUCTURED_SQL"
                    )
                )
            )
            objective_financing_comparison = (
                pending_plan.intent == "product_comparison"
                and pending_plan.slots.get("aggregation") in {"MIN", "MAX"}
                and pending_plan.slots.get("financing_type")
                in {"consumer", "vehicle", "housing", "commercial"}
                and bool(raw_criteria)
                and pending_plan.slots.get("explicit_profit_rate_preference") is True
            )
            subjective_comparison = (
                pending_plan.intent == "product_comparison"
                and is_financing_product
                and pending_plan.slots.get("aggregation") not in {"MIN", "MAX"}
            )
            if generic_financing_request:
                clarification = self._clarification_answer(
                    message=message,
                    plan=replace(
                        pending_plan,
                        intent="product_comparison",
                        route="HYBRID_RAG",
                    ),
                    criteria=criteria,
                    missing_criteria=["financing_type"],
                )
            else:
                missing_criteria = (
                    [
                        name
                        for name in ("term_months", "amount")
                        if getattr(criteria, name) is None
                    ]
                    if objective_financing_comparison
                    else criteria.missing()
                )
                needs_criteria = (
                    subjective_comparison
                    or (
                        specific_financing_request
                        and (
                            criteria.term_months is None
                            or criteria.amount is None
                        )
                    )
                )
                if needs_criteria and missing_criteria:
                    clarification = self._clarification_answer(
                        message=message,
                        plan=(
                            replace(
                                pending_plan,
                                intent="product_comparison",
                                route="HYBRID_RAG",
                            )
                            if specific_financing_request
                            else pending_plan
                        ),
                        criteria=criteria,
                        financing_type=financing_type,
                        missing_criteria=missing_criteria,
                    )
            if (
                (objective_financing_comparison or specific_financing_request)
                and criteria.term_months is not None
                and criteria.amount is not None
            ):
                if criteria.fee_priority is None:
                    criteria = merge_criteria(criteria, {"fee_priority": False})
            elif not subjective_comparison and not specific_financing_request:
                criteria = None
        if clarification is not None:
            yield {
                "event": "meta",
                "data": {
                    key: value
                    for key, value in clarification.items()
                    if key not in {"answer", "generation"}
                },
            }
            for text_chunk in _safe_stream_chunks(clarification["answer_display"]):
                yield {"event": "delta", "data": {"text": text_chunk}}
            yield {
                "event": "done",
                "data": self._generation(
                    mode="fallback", fallback_reason="missing_comparison_criteria"
                ),
            }
            return

        yield from self.stream_answer(
            execution_message, limit=limit, criteria=criteria
        )
