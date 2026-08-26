"""OpenAI uyumlu yerel ve EVREN modelleri için güvenli istemciler."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from time import monotonic, sleep
from typing import Any, Iterable, Iterator

import httpx

from src.providers import CircuitBreaker, CircuitOpenError


FALSE_VALUES = {"0", "false", "hayır", "hayir", "off"}


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
    provider: str = "local"
    strict_model: bool = False
    models_cache_ttl: float = 300.0
    max_pre_token_retries: int = 0

    @classmethod
    def from_env(cls) -> "LLMSettings":
        enabled = os.getenv("RAGNROLL_LLM_ENABLED", "true").strip().casefold()
        return cls(
            enabled=enabled not in FALSE_VALUES,
            base_url=os.getenv(
                "RAGNROLL_LLM_BASE_URL", "http://127.0.0.1:8001/v1"
            ).rstrip("/"),
            model=os.getenv("RAGNROLL_LLM_MODEL", "gemma4:e4b-mlx").strip(),
            api_key=os.getenv("RAGNROLL_LLM_API_KEY", "EMPTY").strip() or "EMPTY",
            connect_timeout=float(os.getenv("RAGNROLL_LLM_CONNECT_TIMEOUT", "1")),
            read_timeout=float(os.getenv("RAGNROLL_LLM_READ_TIMEOUT", "120")),
            max_tokens=int(os.getenv("RAGNROLL_LLM_MAX_TOKENS", "900")),
            temperature=float(os.getenv("RAGNROLL_LLM_TEMPERATURE", "0.05")),
            provider="local",
        )

    @classmethod
    def evren_from_env(cls) -> "LLMSettings":
        api_key = os.getenv("EVREN_API_KEY", "").strip()
        configured = os.getenv("RAGNROLL_EVREN_ENABLED", "true").strip().casefold()
        return cls(
            enabled=bool(api_key) and configured not in FALSE_VALUES,
            base_url=os.getenv(
                "EVREN_LLM_BASE_URL", "https://evren-llmapi.ssyz.org.tr/v1"
            ).rstrip("/"),
            model=os.getenv("EVREN_LLM_MODEL", "llm-fast").strip(),
            api_key=api_key,
            connect_timeout=float(os.getenv("EVREN_CONNECT_TIMEOUT", "5")),
            read_timeout=float(os.getenv("EVREN_READ_TIMEOUT", "1800")),
            max_tokens=int(os.getenv("EVREN_LLM_MAX_TOKENS", "1024")),
            temperature=float(os.getenv("EVREN_LLM_TEMPERATURE", "0")),
            provider="evren",
            strict_model=True,
            models_cache_ttl=float(os.getenv("EVREN_MODELS_CACHE_TTL", "300")),
            max_pre_token_retries=int(
                os.getenv("RAGNROLL_EVREN_MAX_PRETOKEN_RETRIES", "1")
            ),
        )

    @classmethod
    def ollama_from_env(cls) -> "LLMSettings":
        configured = os.getenv("RAGNROLL_OLLAMA_ENABLED", "true").strip().casefold()
        return cls(
            enabled=configured not in FALSE_VALUES,
            base_url=os.getenv(
                "RAGNROLL_OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"
            ).rstrip("/"),
            model=os.getenv("RAGNROLL_OLLAMA_MODEL", "gemma3:4b").strip(),
            api_key=os.getenv("RAGNROLL_OLLAMA_API_KEY", "OLLAMA").strip()
            or "OLLAMA",
            connect_timeout=float(os.getenv("RAGNROLL_OLLAMA_CONNECT_TIMEOUT", "2")),
            read_timeout=float(os.getenv("RAGNROLL_OLLAMA_READ_TIMEOUT", "180")),
            max_tokens=int(os.getenv("RAGNROLL_OLLAMA_MAX_TOKENS", "900")),
            temperature=float(os.getenv("RAGNROLL_OLLAMA_TEMPERATURE", "0.05")),
            provider="ollama",
            strict_model=True,
        )


class OpenAICompatibleLLM:
    """OpenAI Chat Completions SSE akışını sağlayıcıdan bağımsız tüketir."""

    def __init__(
        self,
        settings: LLMSettings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        circuit: CircuitBreaker | None = None,
    ) -> None:
        self.settings = settings or LLMSettings.from_env()
        self._transport = transport
        self.circuit = circuit or CircuitBreaker(
            failure_threshold=int(
                os.getenv("RAGNROLL_EVREN_CIRCUIT_FAILURE_THRESHOLD", "3")
            ),
            open_seconds=float(
                os.getenv("RAGNROLL_EVREN_CIRCUIT_OPEN_SECONDS", "30")
            ),
        )
        self._models: tuple[str, ...] = ()
        self._models_checked_at = 0.0
        self._last_metadata: dict[str, Any] = {}

    @property
    def enabled(self) -> bool:
        return self.settings.enabled and bool(self.settings.model)

    @property
    def model(self) -> str:
        return self.settings.model

    @property
    def provider(self) -> str:
        return self.settings.provider

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.settings.connect_timeout,
            read=self.settings.read_timeout,
            write=10.0,
            pool=self.settings.connect_timeout,
        )

    @staticmethod
    def _permanent_http_error(exc: Exception) -> bool:
        return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {
            401,
            403,
        }

    @staticmethod
    def _retryable(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in {429, 500, 502, 503, 504}
        return isinstance(exc, (httpx.TransportError, OSError))

    def _served_models(self, *, force: bool = False) -> tuple[str, ...]:
        now = monotonic()
        if (
            not force
            and self._models
            and now - self._models_checked_at < self.settings.models_cache_ttl
        ):
            return self._models
        with httpx.Client(timeout=self._timeout(), transport=self._transport) as client:
            response = client.get(
                f"{self.settings.base_url}/models", headers=self._headers()
            )
            response.raise_for_status()
            payload = response.json()
        models = tuple(
            str(item.get("id"))
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        )
        self._models = models
        self._models_checked_at = now
        return models

    def _ensure_model(self) -> None:
        if self.settings.strict_model and self.model not in self._served_models():
            raise LLMUnavailableError("Yapılandırılan model servis listesinde bulunamadı")

    def _stream_once(self, *, system_prompt: str, user_prompt: str) -> list[str]:
        self._ensure_model()
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
        chunks: list[str] = []
        served_model: str | None = None
        finish_reason: str | None = None
        with httpx.Client(timeout=self._timeout(), transport=self._transport) as client:
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
                        break
                    try:
                        event = json.loads(data)
                        event_model = event.get("model")
                        if event_model:
                            served_model = str(event_model)
                        choices = event.get("choices") or []
                        choice = choices[0] if choices else {}
                        delta = choice.get("delta", {})
                        finish_reason = choice.get("finish_reason") or finish_reason
                        content = delta.get("content")
                    except (AttributeError, IndexError, TypeError, json.JSONDecodeError):
                        continue
                    if isinstance(content, str) and content:
                        chunks.append(content)
        if self.settings.strict_model:
            if served_model is None:
                raise LLMUnavailableError("Model yanıtı sunulan alias bilgisini içermiyor")
            if served_model != self.model:
                raise LLMUnavailableError("İstenen ve sunulan model aliası eşleşmiyor")
        self._last_metadata = {
            "provider": self.provider,
            "requested_model": self.model,
            "served_model": served_model or self.model,
            "finish_reason": finish_reason,
        }
        return chunks

    def stream_chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> Iterable[str]:
        if not self.enabled:
            raise LLMUnavailableError("Dil modeli kullanımı kapalı")
        try:
            self.circuit.acquire()
        except CircuitOpenError as exc:
            raise LLMUnavailableError("Dil modeli devresi geçici olarak açık") from exc
        attempts = self.settings.max_pre_token_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                chunks = self._stream_once(
                    system_prompt=system_prompt, user_prompt=user_prompt
                )
                if not chunks:
                    raise LLMUnavailableError("Dil modeli boş yanıt üretti")
                self.circuit.success()
                yield from chunks
                return
            except (httpx.HTTPError, OSError, ValueError, TypeError, LLMUnavailableError) as exc:
                last_error = exc
                permanent = self._permanent_http_error(exc) or (
                    isinstance(exc, LLMUnavailableError)
                    and any(
                        marker in str(exc).casefold()
                        for marker in ("alias", "model")
                    )
                )
                self.circuit.failure(permanent=permanent)
                if permanent or attempt + 1 >= attempts or not self._retryable(exc):
                    break
                sleep(min(0.25 * (2**attempt), 1.0))
        self._last_metadata = {
            "provider": self.provider,
            "requested_model": self.model,
            "served_model": None,
            "error": type(last_error).__name__ if last_error else "unknown",
        }
        raise LLMUnavailableError(
            "Dil modeli servisi yanıt vermedi veya geçersiz yanıt üretti"
        ) from last_error

    def generation_metadata(self) -> dict[str, Any]:
        snapshot = self.circuit.snapshot()
        return {**self._last_metadata, "circuit_state": snapshot.state}

    def status(self) -> dict[str, Any]:
        snapshot = self.circuit.snapshot()
        extended = (
            {"provider": self.provider, "circuit_state": snapshot.state}
            if self.provider != "local" or self.settings.strict_model
            else {}
        )
        if not self.enabled:
            return {
                "available": False,
                "model": self.model,
                "reason": "disabled",
                **extended,
            }
        try:
            models = list(self._served_models(force=True))
        except (httpx.HTTPError, OSError, ValueError, TypeError) as exc:
            return {
                "available": False,
                "model": self.model,
                "reason": type(exc).__name__,
                **extended,
            }
        return {
            "available": self.model in models,
            "model": self.model,
            "served_models": models,
            **extended,
            **({} if self.model in models else {"reason": "model_not_served"}),
        }


class ProviderLLMChain:
    """EVREN -> yerel model sırasını taşıma ve çıktı bazında uygular."""

    def __init__(self, providers: Iterable[OpenAICompatibleLLM]) -> None:
        self.providers = tuple(providers)
        self._attempts: list[dict[str, Any]] = []
        self._selected: dict[str, Any] = {}

    @property
    def enabled(self) -> bool:
        return any(provider.enabled for provider in self.providers)

    @property
    def model(self) -> str:
        selected = self._selected.get("requested_model")
        if selected:
            return str(selected)
        for provider in self.providers:
            if provider.enabled:
                return provider.model
        return ""

    def stream_chat_candidates(
        self, *, system_prompt: str, user_prompt: str
    ) -> Iterator[tuple[list[str], dict[str, Any]]]:
        yield from self._stream_chat_candidates(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            reset_attempts=True,
        )

    def stream_chat_repair_candidates(
        self, *, system_prompt: str, user_prompt: str
    ) -> Iterator[tuple[list[str], dict[str, Any]]]:
        """Run one repair pass while retaining the original attempt audit trail."""

        yield from self._stream_chat_candidates(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            reset_attempts=False,
        )

    def _stream_chat_candidates(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        reset_attempts: bool,
    ) -> Iterator[tuple[list[str], dict[str, Any]]]:
        if reset_attempts:
            self._attempts = []
            self._selected = {}
        for provider in self.providers:
            if not provider.enabled:
                continue
            try:
                chunks = list(
                    provider.stream_chat(
                        system_prompt=system_prompt, user_prompt=user_prompt
                    )
                )
                metadata = provider.generation_metadata()
                self._attempts.append({**metadata, "outcome": "candidate"})
                yield chunks, metadata
            except LLMUnavailableError:
                metadata = provider.generation_metadata()
                self._attempts.append({**metadata, "outcome": "unavailable"})

    def accept_candidate(self, metadata: dict[str, Any]) -> None:
        self._selected = dict(metadata)
        if self._attempts:
            self._attempts[-1]["outcome"] = "accepted"

    def reject_candidate(self, metadata: dict[str, Any]) -> None:
        self._selected = dict(metadata)
        if self._attempts:
            self._attempts[-1]["outcome"] = "output_rejected"

    def stream_chat(self, *, system_prompt: str, user_prompt: str) -> Iterable[str]:
        for chunks, metadata in self.stream_chat_candidates(
            system_prompt=system_prompt, user_prompt=user_prompt
        ):
            self.accept_candidate(metadata)
            yield from chunks
            return
        raise LLMUnavailableError("Yapılandırılan dil modeli sağlayıcıları kullanılamadı")

    def generation_metadata(self) -> dict[str, Any]:
        return {
            **self._selected,
            "fallback_chain": [dict(item) for item in self._attempts],
        }

    def status(self) -> dict[str, Any]:
        providers = [provider.status() for provider in self.providers]
        available_pair = next(
            (
                (provider, item)
                for provider, item in zip(self.providers, providers)
                if item["available"]
            ),
            None,
        )
        available = available_pair[1] if available_pair else None
        return {
            "available": available is not None,
            "model": available["model"] if available else self.model,
            "provider": available_pair[0].provider if available_pair else None,
            "providers": providers,
        }


def build_llm_from_env() -> ProviderLLMChain:
    """Secret yokken yerel zincire, EVREN varken EVREN önceliğine geçer."""

    order = [
        value.strip().casefold()
        for value in os.getenv(
            "RAGNROLL_GENERATION_PROVIDER_ORDER",
            "evren,local,ollama,deterministic",
        ).split(",")
        if value.strip()
    ]
    providers: list[OpenAICompatibleLLM] = []
    for name in order:
        if name == "evren":
            providers.append(OpenAICompatibleLLM(LLMSettings.evren_from_env()))
        elif name == "local":
            providers.append(OpenAICompatibleLLM(LLMSettings.from_env()))
        elif name == "ollama":
            providers.append(OpenAICompatibleLLM(LLMSettings.ollama_from_env()))
    return ProviderLLMChain(providers)
