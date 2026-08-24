"""Tek çağrıda güvenlik, niyet, rota ve slot üreten LLM planlayıcısı."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from dataclasses import replace
from typing import Any

from src.llm.client import LLMSettings, LLMUnavailableError, OpenAICompatibleLLM


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
    {"safe", "intent", "route", "confidence", "normalized_query", "slots"}
)
_SLOT_KEYS = frozenset(
    {"banks", "metric", "aggregation", "product_type", "financing_type"}
)


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
        self.planner = planner or router or OpenAICompatibleLLM(
            replace(
                base,
                model=os.getenv("EVREN_ROUTER_MODEL", "router").strip(),
                max_tokens=420,
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
    ) -> dict[str, Any] | None:
        if not payload or set(payload) != _DECISION_KEYS:
            return None
        safe = payload.get("safe")
        intent = payload.get("intent")
        route = payload.get("route")
        confidence = payload.get("confidence")
        normalized_query = payload.get("normalized_query")
        slots = payload.get("slots")
        if not isinstance(safe, bool):
            return None
        if not isinstance(intent, str) or intent not in ALLOWED_INTENTS:
            return None
        if not isinstance(route, str) or route not in ALLOWED_ROUTES:
            return None
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return None
        if not 0 <= float(confidence) <= 1:
            return None
        if not isinstance(normalized_query, str) or not normalized_query.strip():
            return None
        if len(normalized_query) > 2000 or not isinstance(slots, dict):
            return None
        if not set(slots).issubset(_SLOT_KEYS):
            return None

        banks = slots.get("banks", [])
        if not isinstance(banks, list) or not all(isinstance(item, str) for item in banks):
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
        if intent in {"bank_list", "campaign_count"} and aggregation != "COUNT":
            return None
        if safe is (intent in UNSAFE_INTENTS):
            return None
        if (route == "SAFE_REDIRECT") is safe:
            return None
        if safe and (route == "STRUCTURED_SQL") != (intent in STRUCTURED_INTENTS):
            return None
        return {
            "safe": safe,
            "intent": intent,
            "route": route,
            "confidence": float(confidence),
            "normalized_query": " ".join(normalized_query.split()),
            "slots": {
                "banks": list(dict.fromkeys(banks)),
                "metric": metric,
                "aggregation": aggregation,
                "product_type": product_type,
                "financing_type": financing_type,
            },
        }

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
    ) -> dict[str, Any] | None:
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
            "Kullanıcıya cevap verme; yalnız geçerli JSON üret. Güvenlik, niyet, "
            "rota ve slotları birlikte çöz. Yerel taslak yalnız ipucudur. Banka "
            "slotlarında sadece katalogdaki slug değerlerini kullan. İşlem yapma, "
            "şikâyet kaydı, kişisel veri sızdırma veya zararlı taleplerde safe=false "
            "ve SAFE_REDIRECT seç. Sayımda intent=campaign_count, "
            "route=STRUCTURED_SQL ve aggregation=COUNT kullan. Banka listesi veya "
            "banka sayısı sorularında intent=bank_list, route=STRUCTURED_SQL ve "
            "aggregation=COUNT kullan; bunu kampanya sayımıyla karıştırma. Şema tam olarak: "
            '{"safe":boolean,"intent":"allowlisted intent","route":'
            '"STRUCTURED_SQL|HYBRID_RAG|SAFE_REDIRECT","confidence":0..1,'
            '"normalized_query":"arama için açık Türkçe sorgu","slots":'
            '{"banks":[],"metric":null,"aggregation":null,'
            '"product_type":null,"financing_type":null}}. '
            f"İzinli intentler: {sorted(ALLOWED_INTENTS)}."
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
        return decision.get("safe") if decision else None

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
        return str(decision["route"]) if decision else None

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
