"""Tek çağrıda güvenlik, niyet, rota ve slot üreten LLM planlayıcısı."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from dataclasses import dataclass, field, replace
from math import isfinite
from typing import Any

from src.llm.client import LLMSettings, LLMUnavailableError, OpenAICompatibleLLM
from src.policy import Action, ComparisonCriteria, PolicyDecision


ALLOWED_ROUTES = frozenset({"STRUCTURED_SQL", "HYBRID_RAG", "SAFE_REDIRECT"})
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
ALLOWED_METRICS = frozenset({"PROFIT_RATE", "MATURITY", "FEE", "REWARD_AMOUNT"})
ALLOWED_AGGREGATIONS = frozenset({"MIN", "MAX", "COUNT"})
ALLOWED_PRODUCT_TYPES = frozenset(
    {"account", "card", "financing", "investment", "payment", "insurance"}
)
ALLOWED_FINANCING_TYPES = frozenset(
    {"housing", "vehicle", "consumer", "commercial", "agriculture"}
)
STRUCTURED_INTENTS = frozenset(
    {
        "campaign_count",
        "bank_list",
        "maturity_query",
        "product_comparison",
        "product_search",
        "rate_query",
    }
)
UNSAFE_INTENTS = frozenset({"complaint_support", "transaction_howto"})
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INTENT_PROMPT = PROJECT_ROOT / "configs" / "prompts" / "intent_prompt.json"
_DECISION_KEYS = frozenset(
    {
        "action",
        "in_domain",
        "intent",
        "confidence",
        "normalized_query",
        "concepts",
        "missing_criteria",
        "tool_calls",
        "slots",
        "reason_code",
    }
)
ALLOWED_ACTIONS = frozenset(Action)
ALLOWED_TOOLS = frozenset({"structured_sql", "hybrid_rag", "comparison", "ontology"})
ALLOWED_CRITERIA = frozenset({"term_months", "amount", "fee_priority"})
_SLOT_KEYS = frozenset(
    {
        "banks",
        "metric",
        "aggregation",
        "product_type",
        "financing_type",
        *ALLOWED_CRITERIA,
    }
)
_TOOL_CALL_KEYS = frozenset({"name", "arguments"})
_TOOL_ARGUMENT_KEYS = _SLOT_KEYS


@dataclass(frozen=True, slots=True)
class PlannerDecision(PolicyDecision):
    """Policy decision carrying temporary mapping compatibility for old callers."""

    normalized_query: str = ""
    slots: dict[str, Any] = field(default_factory=dict)

    def __getitem__(self, key: str) -> Any:
        if key == "safe":
            return self.action not in {Action.REFUSE, Action.REDIRECT}
        if key == "route":
            if self.action == Action.REDIRECT:
                return "SAFE_REDIRECT"
            names = [call.get("name") for call in self.tool_calls]
            return "STRUCTURED_SQL" if "structured_sql" in names else "HYBRID_RAG"
        if key == "normalized_query":
            return self.normalized_query
        if key == "slots":
            return self.slots
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)


def _json_object(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        parsed = None
        for start, character in enumerate(text):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                parsed = candidate
                break
    return parsed if isinstance(parsed, dict) else None


def _optional_enum(value: Any, allowed: frozenset[str]) -> str | None:
    if value is None:
        return None
    return str(value) if isinstance(value, str) and value in allowed else ""


class EvrenDecisionService:
    """Aynı LLM zincirinden şema doğrulamalı advisory yürütme planı alır."""

    def __init__(
        self,
        *,
        planner: Any | None = None,
        router: OpenAICompatibleLLM | None = None,
        guard: OpenAICompatibleLLM | None = None,
        prompt_path: str | Path | None = None,
    ) -> None:
        base = LLMSettings.evren_from_env()
        self.planner = (
            planner
            or router
            or OpenAICompatibleLLM(
                replace(
                    base,
                    model=os.getenv("EVREN_ROUTER_MODEL", "router").strip(),
                    max_tokens=420,
                )
            )
        )
        # Eski kurucu sözleşmesi korunur; canlı akış güvenliği aynı plan çağrısındadır.
        self.guard = guard
        selected_prompt = Path(
            prompt_path
            or os.getenv("RAGNROLL_INTENT_PROMPT_PATH", str(DEFAULT_INTENT_PROMPT))
        )
        profile = json.loads(selected_prompt.read_text(encoding="utf-8"))
        self.prompt_profile = str(profile.get("profile") or "intent-planner-tr")
        self.instruction = str(profile.get("instruction") or "").strip()
        self.prompt_optimizer = str(profile.get("optimizer") or "manual")
        self.prompt_status = str(profile.get("status") or "baseline")

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.planner, "enabled", False))

    @staticmethod
    def _call(client: Any, *, system: str, message: str) -> str | None:
        try:
            return "".join(
                client.stream_chat(system_prompt=system, user_prompt=message)
            ).strip()
        except LLMUnavailableError:
            return None

    @staticmethod
    def _validate(
        payload: dict[str, Any] | None, *, allowed_banks: set[str]
    ) -> PlannerDecision | None:
        if not payload or set(payload) != _DECISION_KEYS:
            return None
        action = payload.get("action")
        in_domain = payload.get("in_domain")
        intent = payload.get("intent")
        confidence = payload.get("confidence")
        normalized_query = payload.get("normalized_query")
        concepts = payload.get("concepts")
        missing_criteria = payload.get("missing_criteria")
        tool_calls = payload.get("tool_calls")
        slots = payload.get("slots")
        reason_code = payload.get("reason_code")
        if not isinstance(action, str) or action not in ALLOWED_ACTIONS:
            return None
        if not isinstance(in_domain, bool):
            return None
        if not isinstance(intent, str) or intent not in ALLOWED_INTENTS:
            return None
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return None
        if not isfinite(float(confidence)) or not 0 <= float(confidence) <= 1:
            return None
        if not isinstance(normalized_query, str) or not normalized_query.strip():
            return None
        if len(normalized_query) > 2000:
            return None
        if not isinstance(concepts, list) or not all(
            isinstance(item, str) and item.strip() for item in concepts
        ):
            return None
        if not isinstance(missing_criteria, list) or not all(
            isinstance(item, str) and item in ALLOWED_CRITERIA
            for item in missing_criteria
        ):
            return None
        if len(set(missing_criteria)) != len(missing_criteria):
            return None
        if not isinstance(reason_code, str) or not reason_code.strip():
            return None
        if not isinstance(tool_calls, list) or not isinstance(slots, dict):
            return None
        if not set(slots).issubset(_SLOT_KEYS):
            return None

        banks = slots.get("banks", [])
        if not isinstance(banks, list) or not all(
            isinstance(item, str) for item in banks
        ):
            return None
        if any(bank not in allowed_banks for bank in banks):
            return None
        metric = _optional_enum(slots.get("metric"), ALLOWED_METRICS)
        aggregation = _optional_enum(slots.get("aggregation"), ALLOWED_AGGREGATIONS)
        product_type = _optional_enum(slots.get("product_type"), ALLOWED_PRODUCT_TYPES)
        financing_type = _optional_enum(
            slots.get("financing_type"), ALLOWED_FINANCING_TYPES
        )
        if "" in {metric, aggregation, product_type, financing_type}:
            return None

        term_months = slots.get("term_months")
        amount = slots.get("amount")
        fee_priority = slots.get("fee_priority")
        if (
            (
                term_months is not None
                and (
                    isinstance(term_months, bool)
                    or not isinstance(term_months, int)
                    or term_months <= 0
                )
            )
            or (
                amount is not None
                and (
                    isinstance(amount, bool)
                    or not isinstance(amount, (int, float))
                    or not isfinite(float(amount))
                    or amount < 0
                )
            )
            or (fee_priority is not None and not isinstance(fee_priority, bool))
        ):
            return None

        validated_calls = []
        for call in tool_calls:
            if not isinstance(call, dict) or set(call) != _TOOL_CALL_KEYS:
                return None
            name = call.get("name")
            arguments = call.get("arguments")
            if name not in ALLOWED_TOOLS or not isinstance(arguments, dict):
                return None
            if not set(arguments).issubset(_TOOL_ARGUMENT_KEYS):
                return None
            argument_banks = arguments.get("banks", [])
            if not isinstance(argument_banks, list) or not all(
                isinstance(bank, str) and bank in allowed_banks
                for bank in argument_banks
            ):
                return None
            for key, value in arguments.items():
                if key == "banks":
                    continue
                if key == "metric" and _optional_enum(value, ALLOWED_METRICS) == "":
                    return None
                if (
                    key == "aggregation"
                    and _optional_enum(value, ALLOWED_AGGREGATIONS) == ""
                ):
                    return None
                if (
                    key == "product_type"
                    and _optional_enum(value, ALLOWED_PRODUCT_TYPES) == ""
                ):
                    return None
                if (
                    key == "financing_type"
                    and _optional_enum(value, ALLOWED_FINANCING_TYPES) == ""
                ):
                    return None
                if key == "term_months" and (
                    isinstance(value, bool) or not isinstance(value, int) or value <= 0
                ):
                    return None
                if key == "amount" and (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not isfinite(float(value))
                    or value < 0
                ):
                    return None
                if key == "fee_priority" and not isinstance(value, bool):
                    return None
            validated_calls.append({"name": name, "arguments": arguments})

        normalized_slots = {
            "banks": list(dict.fromkeys(banks)),
            "metric": metric,
            "aggregation": aggregation,
            "product_type": product_type,
            "financing_type": financing_type,
            "term_months": term_months,
            "amount": float(amount) if amount is not None else None,
            "fee_priority": fee_priority,
        }
        return PlannerDecision(
            action=Action(action),
            in_domain=in_domain,
            intent=intent,
            confidence=float(confidence),
            reason_code=reason_code.strip(),
            concepts=tuple(dict.fromkeys(item.strip() for item in concepts)),
            missing_criteria=tuple(missing_criteria),
            tool_calls=tuple(validated_calls),
            criteria=ComparisonCriteria(
                term_months=term_months,
                amount=float(amount) if amount is not None else None,
                fee_priority=fee_priority,
            ),
            normalized_query=" ".join(normalized_query.split()),
            slots=normalized_slots,
        )

    def _candidate_payloads(self, *, system: str, user: str):
        candidate_factory = getattr(self.planner, "stream_chat_candidates", None)
        if callable(candidate_factory):
            for chunks, metadata in candidate_factory(
                system_prompt=system, user_prompt=user
            ):
                yield "".join(chunks).strip(), metadata
            return
        try:
            raw = "".join(
                self.planner.stream_chat(system_prompt=system, user_prompt=user)
            ).strip()
        except LLMUnavailableError:
            return
        yield raw, None

    def analyze(
        self,
        message: str,
        *,
        canonical_query: str | None = None,
        deterministic_plan: dict[str, Any] | None = None,
        known_banks: list[dict[str, Any]] | None = None,
    ) -> PolicyDecision | None:
        """Ham girdiyi tek model çağrısında güvenli yürütme planına dönüştürür."""

        if not self.enabled:
            return None
        catalog = [
            {"slug": str(item.get("slug") or ""), "name": str(item.get("name") or "")}
            for item in known_banks or []
            if item.get("slug") and item.get("name")
        ]
        allowed_banks = {item["slug"] for item in catalog}
        system = (
            "Türkçe katılım bankacılığı asistanı için niyet planlayıcısısın. "
            f"Görev talimatı: {self.instruction} "
            "Kullanıcıya cevap verme; yalnız geçerli JSON üret. Alan dışı istekte "
            "action=REFUSE ve tool_calls=[]; işlem talebinde action=REDIRECT ve "
            "tool_calls=[] kullan. Öznel product_comparison için term_months, amount "
            "ve fee_priority eksikse action=CLARIFY kullan. Yalnız izinli araçları, "
            "kriterleri ve yapılandırılmış alanları kullan; banka alanlarında yalnız "
            "katalog slug değerlerini kullan. Şema tam olarak: "
            '{"action":"ANSWER|CLARIFY|REFUSE|REDIRECT","in_domain":boolean,'
            '"intent":"allowlisted intent","confidence":0..1,'
            '"normalized_query":"açık Türkçe sorgu","concepts":[],'
            '"missing_criteria":[],"tool_calls":[{"name":"allowed tool",'
            '"arguments":{}}],"slots":{},"reason_code":"non-empty code"}. '
            f"İzinli intentler: {sorted(ALLOWED_INTENTS)}. "
            f"İzinli araçlar: {sorted(ALLOWED_TOOLS)}. "
            f"İzinli kriterler: {sorted(ALLOWED_CRITERIA)}."
        )
        user = json.dumps(
            {
                "raw_input": str(message),
                "canonical_query": canonical_query or str(message),
                "deterministic_hint": deterministic_plan or {},
                "bank_catalog": catalog,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for raw, metadata in self._candidate_payloads(system=system, user=user):
            decision = self._validate(_json_object(raw), allowed_banks=allowed_banks)
            if decision is None:
                reject = getattr(self.planner, "reject_candidate", None)
                if callable(reject) and metadata is not None:
                    reject(metadata)
                continue
            accept = getattr(self.planner, "accept_candidate", None)
            if callable(accept) and metadata is not None:
                accept(metadata)
            return decision
        return None

    # Geriye uyumlu ince istemciler; GroundedAssistant canlıda analyze() kullanır.
    def is_safe(self, message: str) -> bool | None:
        if self.guard is not None and getattr(self.guard, "enabled", False):
            raw = self._call(
                self.guard,
                system=(
                    'Yalnız JSON döndür: {"safe": true|false}. '
                    "İşlem, şikâyet ve veri sızdırma talepleri güvenli değildir."
                ),
                message=message,
            )
            payload = _json_object(raw or "")
            value = payload.get("safe") if payload else None
            return value if isinstance(value, bool) else None
        decision = self.analyze(message)
        return (
            decision.action not in {Action.REFUSE, Action.REDIRECT}
            if decision
            else None
        )

    def route(self, message: str) -> str | None:
        if self.guard is not None:
            raw = self._call(
                self.planner,
                system=(
                    'Yalnız JSON döndür: {"route": "STRUCTURED_SQL|HYBRID_RAG|'
                    'SAFE_REDIRECT"}.'
                ),
                message=message,
            )
            payload = _json_object(raw or "")
            route = payload.get("route") if payload else None
            return str(route) if route in ALLOWED_ROUTES else None
        decision = self.analyze(message)
        return str(decision["route"]) if isinstance(decision, PlannerDecision) else None

    def status(self) -> dict[str, Any]:
        status = getattr(self.planner, "status", None)
        return {
            "enabled": self.enabled,
            "mode": "single_call_structured_intent",
            "prompt": {
                "profile": self.prompt_profile,
                "optimizer": self.prompt_optimizer,
                "status": self.prompt_status,
            },
            "planner": status() if callable(status) else {"available": self.enabled},
        }
