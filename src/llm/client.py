"""vLLM'in OpenAI uyumlu API'si için sınırlı ve akış destekli istemci."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Iterable

import httpx


class LLMUnavailableError(RuntimeError):
    """Dil modeli servisine güvenli biçimde erişilemediğini belirtir."""


@dataclass(frozen=True, slots=True)
class LLMSettings:
    enabled: bool = True
    base_url: str = "http://127.0.0.1:8001/v1"
    model: str = "gemma4:e4b-mlx"
    api_key: str = "EMPTY"
    connect_timeout: float = 1.0
    read_timeout: float = 120.0
    max_tokens: int = 900
    temperature: float = 0.05

    @classmethod
    def from_env(cls) -> "LLMSettings":
        enabled = os.getenv("RAGNROLL_LLM_ENABLED", "true").strip().casefold()
        return cls(
            enabled=enabled not in {"0", "false", "hayır", "hayir", "off"},
            base_url=os.getenv(
                "RAGNROLL_LLM_BASE_URL", "http://127.0.0.1:8001/v1"
            ).rstrip("/"),
            model=os.getenv("RAGNROLL_LLM_MODEL", "gemma4:e4b-mlx").strip(),
            api_key=os.getenv("RAGNROLL_LLM_API_KEY", "EMPTY").strip() or "EMPTY",
            connect_timeout=float(os.getenv("RAGNROLL_LLM_CONNECT_TIMEOUT", "1")),
            read_timeout=float(os.getenv("RAGNROLL_LLM_READ_TIMEOUT", "120")),
            max_tokens=int(os.getenv("RAGNROLL_LLM_MAX_TOKENS", "900")),
            temperature=float(os.getenv("RAGNROLL_LLM_TEMPERATURE", "0.05")),
        )


class OpenAICompatibleLLM:
    """OpenAI Chat Completions SSE akışını sağlayıcıdan bağımsız tüketir."""

    def __init__(
        self,
        settings: LLMSettings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings or LLMSettings.from_env()
        self._transport = transport

    @property
    def enabled(self) -> bool:
        return self.settings.enabled and bool(self.settings.model)

    @property
    def model(self) -> str:
        return self.settings.model

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }

    def stream_chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> Iterable[str]:
        if not self.enabled:
            raise LLMUnavailableError("Dil modeli kullanımı kapalı")
        timeout = httpx.Timeout(
            connect=self.settings.connect_timeout,
            read=self.settings.read_timeout,
            write=10.0,
            pool=self.settings.connect_timeout,
        )
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.settings.temperature,
            "max_tokens": self.settings.max_tokens,
            "stream": True,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            with httpx.Client(timeout=timeout, transport=self._transport) as client:
                with client.stream(
                    "POST",
                    f"{self.settings.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line or line.startswith(":"):
                            continue
                        data = line[5:].strip() if line.startswith("data:") else line
                        if data == "[DONE]":
                            return
                        try:
                            event = json.loads(data)
                            choices = event.get("choices") or []
                            delta = choices[0].get("delta", {}) if choices else {}
                            content = delta.get("content")
                        except (AttributeError, IndexError, TypeError, json.JSONDecodeError):
                            continue
                        if isinstance(content, str) and content:
                            yield content
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise LLMUnavailableError(
                "Dil modeli servisi yanıt vermedi veya geçersiz yanıt üretti"
            ) from exc

    def status(self) -> dict[str, Any]:
        if not self.enabled:
            return {"available": False, "model": self.model, "reason": "disabled"}
        timeout = httpx.Timeout(self.settings.connect_timeout)
        try:
            with httpx.Client(timeout=timeout, transport=self._transport) as client:
                response = client.get(
                    f"{self.settings.base_url}/models", headers=self._headers()
                )
                response.raise_for_status()
                models = [
                    str(item.get("id"))
                    for item in response.json().get("data", [])
                    if isinstance(item, dict) and item.get("id")
                ]
        except (httpx.HTTPError, OSError, ValueError, TypeError) as exc:
            return {
                "available": False,
                "model": self.model,
                "reason": type(exc).__name__,
            }
        return {
            "available": self.model in models or bool(models),
            "model": self.model,
            "served_models": models,
        }
