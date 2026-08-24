"""EVREN router ve guard modelleri için doğrulanmış advisory kararları."""

from __future__ import annotations

import json
import os
import re
from dataclasses import replace
from typing import Any

from src.llm.client import LLMSettings, LLMUnavailableError, OpenAICompatibleLLM


ALLOWED_ROUTES = frozenset({"STRUCTURED_SQL", "HYBRID_RAG", "SAFE_REDIRECT"})


def _json_object(value: str) -> dict[str, Any] | None:
    text = str(value or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class EvrenDecisionService:
    """Model kararını yalnız allowlist ve tip kontrollerinden sonra advisory kullanır."""

    def __init__(
        self,
        *,
        router: OpenAICompatibleLLM | None = None,
        guard: OpenAICompatibleLLM | None = None,
    ) -> None:
        base = LLMSettings.evren_from_env()
        self.router = router or OpenAICompatibleLLM(
            replace(
                base,
                model=os.getenv("EVREN_ROUTER_MODEL", "router").strip(),
                max_tokens=128,
            )
        )
        self.guard = guard or OpenAICompatibleLLM(
            replace(
                base,
                model=os.getenv("EVREN_GUARD_MODEL", "guard").strip(),
                max_tokens=128,
            )
        )

    @property
    def enabled(self) -> bool:
        return self.router.enabled and self.guard.enabled

    @staticmethod
    def _call(client: OpenAICompatibleLLM, *, system: str, message: str) -> str | None:
        try:
            return "".join(
                client.stream_chat(system_prompt=system, user_prompt=message)
            ).strip()
        except LLMUnavailableError:
            return None

    def is_safe(self, message: str) -> bool | None:
        if not self.guard.enabled:
            return None
        raw = self._call(
            self.guard,
            system=(
                "Yalnız JSON döndür: {\"safe\": true|false}. "
                "Finansal bilgi soruları güvenlidir; işlem yapma, şikâyet kaydı, "
                "zararlı veya kişisel veri sızdırma talepleri güvenli değildir."
            ),
            message=message,
        )
        payload = _json_object(raw or "")
        value = payload.get("safe") if payload else None
        return value if isinstance(value, bool) else None

    def route(self, message: str) -> str | None:
        if not self.router.enabled:
            return None
        raw = self._call(
            self.router,
            system=(
                "Yalnız JSON döndür: {\"route\": \"STRUCTURED_SQL|HYBRID_RAG|"
                "SAFE_REDIRECT\"}. Sayısal filtre ve karşılaştırma STRUCTURED_SQL; "
                "tanım ve açıklama HYBRID_RAG; işlem/şikâyet SAFE_REDIRECT."
            ),
            message=message,
        )
        payload = _json_object(raw or "")
        route = payload.get("route") if payload else None
        return str(route) if route in ALLOWED_ROUTES else None

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "router": self.router.status(),
            "guard": self.guard.status(),
        }
