"""EVREN bge-m3 yoğun embedding sağlayıcısı."""

from __future__ import annotations

from dataclasses import dataclass
import os
from time import monotonic, sleep
from typing import Any, Iterable

import httpx

from src.providers import CircuitBreaker, CircuitOpenError


FALSE_VALUES = {"0", "false", "hayır", "hayir", "off"}


class EvrenEmbeddingError(RuntimeError):
    """EVREN embedding çıktısının güvenle kullanılamadığını belirtir."""


@dataclass(frozen=True, slots=True)
class EvrenEmbeddingSettings:
    enabled: bool
    base_url: str
    api_key: str
    model: str = "bge-m3-embed"
    dimensions: int = 1024
    connect_timeout: float = 5.0
    read_timeout: float = 1800.0
    models_cache_ttl: float = 300.0
    max_retries: int = 1

    @classmethod
    def from_env(cls) -> "EvrenEmbeddingSettings":
        api_key = os.getenv("EVREN_API_KEY", "").strip()
        configured = os.getenv(
            "RAGNROLL_EVREN_RETRIEVAL_ENABLED", "true"
        ).strip().casefold()
        return cls(
            enabled=bool(api_key) and configured not in FALSE_VALUES,
            base_url=os.getenv(
                "EVREN_LLM_BASE_URL", "https://evren-llmapi.ssyz.org.tr/v1"
            ).rstrip("/"),
            api_key=api_key,
            model=os.getenv("EVREN_EMBEDDING_MODEL", "bge-m3-embed").strip(),
            dimensions=int(os.getenv("EVREN_EMBEDDING_DIMENSIONS", "1024")),
            connect_timeout=float(os.getenv("EVREN_CONNECT_TIMEOUT", "5")),
            read_timeout=float(os.getenv("EVREN_READ_TIMEOUT", "1800")),
            models_cache_ttl=float(os.getenv("EVREN_MODELS_CACHE_TTL", "300")),
            max_retries=int(os.getenv("RAGNROLL_EVREN_MAX_PRETOKEN_RETRIES", "1")),
        )


class EvrenEmbeddingProvider:
    """Model aliası ve vektör boyutunu doğrulayan OpenAI embedding istemcisi."""

    def __init__(
        self,
        settings: EvrenEmbeddingSettings | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
        circuit: CircuitBreaker | None = None,
    ) -> None:
        self.settings = settings or EvrenEmbeddingSettings.from_env()
        self.model_name = self.settings.model
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

    @property
    def enabled(self) -> bool:
        return self.settings.enabled and bool(self.model_name)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.settings.connect_timeout,
            read=self.settings.read_timeout,
            write=30.0,
            pool=self.settings.connect_timeout,
        )

    def _served_models(self) -> tuple[str, ...]:
        now = monotonic()
        if (
            self._models
            and now - self._models_checked_at < self.settings.models_cache_ttl
        ):
            return self._models
        with httpx.Client(timeout=self._timeout(), transport=self._transport) as client:
            response = client.get(
                f"{self.settings.base_url}/models", headers=self._headers()
            )
            response.raise_for_status()
            payload = response.json()
        self._models = tuple(
            str(item.get("id"))
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        )
        self._models_checked_at = now
        return self._models

    def _embed_once(self, values: list[str]) -> list[list[float]]:
        if self.model_name not in self._served_models():
            raise EvrenEmbeddingError("Embedding modeli servis listesinde bulunamadı")
        with httpx.Client(timeout=self._timeout(), transport=self._transport) as client:
            response = client.post(
                f"{self.settings.base_url}/embeddings",
                headers=self._headers(),
                json={"model": self.model_name, "input": values},
            )
            response.raise_for_status()
            payload = response.json()
        served_model = payload.get("model")
        if served_model != self.model_name:
            raise EvrenEmbeddingError("İstenen ve sunulan embedding aliası eşleşmiyor")
        rows = payload.get("data")
        if not isinstance(rows, list) or len(rows) != len(values):
            raise EvrenEmbeddingError("Embedding yanıt satırı sayısı geçersiz")
        ordered = sorted(rows, key=lambda item: int(item.get("index", 0)))
        vectors = [item.get("embedding") for item in ordered]
        if any(
            not isinstance(vector, list)
            or len(vector) != self.settings.dimensions
            or any(
                isinstance(value, bool) or not isinstance(value, (int, float))
                for value in vector
            )
            for vector in vectors
        ):
            raise EvrenEmbeddingError("Embedding boyutu veya değeri geçersiz")
        return [[float(value) for value in vector] for vector in vectors]

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        values = [str(text) for text in texts]
        if not values:
            return []
        if not self.enabled:
            raise EvrenEmbeddingError("EVREN embedding yapılandırılmadı")
        try:
            self.circuit.acquire()
        except CircuitOpenError as exc:
            raise EvrenEmbeddingError("EVREN embedding devresi açık") from exc
        attempts = self.settings.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                vectors = self._embed_once(values)
                self.circuit.success()
                return vectors
            except (httpx.HTTPError, OSError, ValueError, TypeError, EvrenEmbeddingError) as exc:
                last_error = exc
                permanent = (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code in {401, 403}
                ) or any(
                    marker in str(exc).casefold()
                    for marker in ("alias", "model")
                )
                self.circuit.failure(permanent=permanent)
                retryable = isinstance(exc, (httpx.TransportError, OSError)) or (
                    isinstance(exc, httpx.HTTPStatusError)
                    and exc.response.status_code in {429, 500, 502, 503, 504}
                )
                if permanent or not retryable or attempt + 1 >= attempts:
                    break
                sleep(min(0.25 * (2**attempt), 1.0))
        raise EvrenEmbeddingError(
            "EVREN embedding servisi kullanılamadı veya geçersiz çıktı üretti"
        ) from last_error

    def embed_query(self, text: str) -> list[float]:
        value = str(text or "").strip()
        if not value:
            raise ValueError("Embedding sorgusu boş olamaz")
        return self.embed_documents([value])[0]

    def status(self) -> dict[str, Any]:
        snapshot = self.circuit.snapshot()
        if not self.enabled:
            return {
                "available": False,
                "model": self.model_name,
                "reason": "disabled",
                "circuit_state": snapshot.state,
            }
        try:
            models = list(self._served_models())
        except (httpx.HTTPError, OSError, ValueError, TypeError) as exc:
            return {
                "available": False,
                "model": self.model_name,
                "reason": type(exc).__name__,
                "circuit_state": snapshot.state,
            }
        return {
            "available": self.model_name in models,
            "model": self.model_name,
            "dimensions": self.settings.dimensions,
            "circuit_state": snapshot.state,
            **({} if self.model_name in models else {"reason": "model_not_served"}),
        }
