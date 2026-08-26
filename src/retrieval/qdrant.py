"""Takım-izole EVREN Qdrant retrieval ve idempotent indeksleme."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
import re
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from src.persistence import CampaignStore
from src.providers import CircuitBreaker, CircuitOpenError
from src.retrieval.documents import INDEX_SCHEMA, campaign_documents, pdf_evidence_documents, terminology_documents
from src.retrieval.evren import EvrenEmbeddingProvider


FALSE_VALUES = {"0", "false", "hayır", "hayir", "off"}


class EvrenQdrantError(RuntimeError):
    """EVREN Qdrant yolunun güvenle kullanılamadığını belirtir."""


@dataclass(frozen=True, slots=True)
class EvrenQdrantSettings:
    enabled: bool
    url: str
    port: int
    prefix: str
    api_key: str
    collection: str
    timeout: int = 600

    @classmethod
    def from_env(cls) -> "EvrenQdrantSettings":
        api_key = os.getenv("EVREN_QDRANT_API_KEY", "").strip()
        prefix = os.getenv("EVREN_QDRANT_PREFIX", "").strip()
        configured = os.getenv(
            "RAGNROLL_EVREN_RETRIEVAL_ENABLED", "true"
        ).strip().casefold()
        return cls(
            enabled=(
                bool(api_key)
                and bool(prefix)
                and configured not in FALSE_VALUES
            ),
            url=os.getenv(
                "EVREN_QDRANT_URL", "https://evren-vektor.ssyz.org.tr"
            ).rstrip("/"),
            port=int(os.getenv("EVREN_QDRANT_PORT", "443")),
            prefix=prefix,
            api_key=api_key,
            collection=os.getenv(
                "EVREN_QDRANT_COLLECTION", "katilim_campaigns_bge_m3_202608"
            ).strip(),
            timeout=int(os.getenv("EVREN_QDRANT_TIMEOUT", "600")),
        )

    def validate(self) -> None:
        if self.port != 443:
            raise EvrenQdrantError("EVREN Qdrant portu 443 olmalıdır")
        if not re.fullmatch(r"team\d+", self.prefix):
            raise EvrenQdrantError("EVREN Qdrant takım prefix'i geçersiz")
        if not self.url.startswith("https://"):
            raise EvrenQdrantError("EVREN Qdrant HTTPS kullanmalıdır")
        if not self.collection:
            raise EvrenQdrantError("EVREN Qdrant koleksiyonu boş olamaz")


class EvrenQdrantRetriever:
    """EVREN embedding ve takım Qdrant ile birincil semantik retrieval."""

    def __init__(
        self,
        *,
        settings: EvrenQdrantSettings | None = None,
        embedding_provider: EvrenEmbeddingProvider | None = None,
        client: Any | None = None,
        client_factory: Callable[..., Any] | None = None,
        circuit: CircuitBreaker | None = None,
    ) -> None:
        self.settings = settings or EvrenQdrantSettings.from_env()
        self.embedding_provider = embedding_provider or EvrenEmbeddingProvider()
        self._client = client
        self._client_factory = client_factory
        self.circuit = circuit or CircuitBreaker(
            failure_threshold=int(
                os.getenv("RAGNROLL_EVREN_CIRCUIT_FAILURE_THRESHOLD", "3")
            ),
            open_seconds=float(
                os.getenv("RAGNROLL_EVREN_CIRCUIT_OPEN_SECONDS", "30")
            ),
        )

    @property
    def enabled(self) -> bool:
        return self.settings.enabled and self.embedding_provider.enabled

    def _get_client(self):
        if self._client is None:
            self.settings.validate()
            if self._client_factory is None:
                from qdrant_client import QdrantClient

                self._client_factory = QdrantClient
            self._client = self._client_factory(
                url=self.settings.url,
                port=self.settings.port,
                prefix=self.settings.prefix,
                api_key=self.settings.api_key,
                timeout=self.settings.timeout,
                prefer_grpc=False,
                https=True,
            )
        return self._client

    @staticmethod
    def _filter(filters: dict[str, Any]):
        from qdrant_client import models

        conditions = []
        for field, values in (
            ("source_type", list(filters.get("source_types") or [])),
            ("bank_slug", list(filters.get("bank_slugs") or [])),
        ):
            if values:
                conditions.append(
                    models.FieldCondition(
                        key=field, match=models.MatchAny(any=[str(value) for value in values])
                    )
                )
        for field in ("product_type", "financing_type"):
            if filters.get(field):
                conditions.append(
                    models.FieldCondition(
                        key=field,
                        match=models.MatchValue(value=str(filters[field])),
                    )
                )
        return models.Filter(must=conditions) if conditions else None

    def ready(self) -> bool:
        if not self.enabled:
            return False
        try:
            self.settings.validate()
            info = self._get_client().get_collection(self.settings.collection)
            vectors = info.config.params.vectors
            metadata = dict(info.config.metadata or {})
            return (
                getattr(vectors, "size", None) == self.embedding_provider.settings.dimensions
                and metadata.get("embedding_model") == self.embedding_provider.model_name
                and metadata.get("index_schema") == INDEX_SCHEMA
                and metadata.get("index_status") == "ready"
                and int(info.points_count or 0) > 0
            )
        except Exception:
            return False

    def retrieve(
        self,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if not self.ready():
            return []
        try:
            self.circuit.acquire()
            vector = self.embedding_provider.embed_query(query)
            response = self._get_client().query_points(
                collection_name=self.settings.collection,
                query=vector,
                query_filter=self._filter(filters or {}),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            items = []
            for point in response.points:
                payload = dict(point.payload or {})
                text = str(payload.pop("document_text", ""))
                document_id = str(payload.get("document_id") or point.id)
                items.append(
                    {
                        "id": document_id,
                        "text": text,
                        "metadata": payload,
                        "score": round(float(point.score), 6),
                        "retrieval_method": "evren-qdrant+bge-m3-embed",
                    }
                )
            self.circuit.success()
            return items
        except CircuitOpenError:
            return []
        except Exception:
            self.circuit.failure()
            return []

    def status(self) -> dict[str, Any]:
        snapshot = self.circuit.snapshot()
        return {
            "available": self.ready(),
            "provider": "evren_qdrant",
            "collection": self.settings.collection,
            "embedding_model": self.embedding_provider.model_name,
            "circuit_state": snapshot.state,
            **({} if self.enabled else {"reason": "disabled"}),
        }


class EvrenQdrantIndexer:
    """Yalnız değişen dokümanları takım Qdrant koleksiyonuna yazar."""

    def __init__(
        self,
        store: CampaignStore,
        *,
        retriever: EvrenQdrantRetriever | None = None,
    ) -> None:
        self.store = store
        self.retriever = retriever or EvrenQdrantRetriever()

    @staticmethod
    def _point_id(document_id: str):
        return uuid5(NAMESPACE_URL, f"ragnroll:{document_id}")

    def build(self, *, batch_size: int = 32) -> dict[str, Any]:
        if not 1 <= batch_size <= 128:
            raise ValueError("batch_size 1 ile 128 arasında olmalıdır")
        if not self.retriever.enabled:
            return {"status": "disabled", "reason": "credentials_missing"}
        from qdrant_client import models

        settings = self.retriever.settings
        settings.validate()
        client = self.retriever._get_client()
        metadata = {
            "embedding_provider": "evren",
            "embedding_model": self.retriever.embedding_provider.model_name,
            "index_schema": INDEX_SCHEMA,
            "index_status": "building",
        }
        if not client.collection_exists(settings.collection):
            client.create_collection(
                collection_name=settings.collection,
                vectors_config=models.VectorParams(
                    size=self.retriever.embedding_provider.settings.dimensions,
                    distance=models.Distance.COSINE,
                ),
                metadata=metadata,
            )
        info = client.get_collection(settings.collection)
        vectors = info.config.params.vectors
        existing_metadata = dict(info.config.metadata or {})
        if getattr(vectors, "size", None) != self.retriever.embedding_provider.settings.dimensions:
            raise EvrenQdrantError("Qdrant koleksiyonu farklı vektör boyutunda")
        if existing_metadata.get("embedding_model") not in {
            None,
            self.retriever.embedding_provider.model_name,
        }:
            raise EvrenQdrantError("Qdrant koleksiyonu farklı embedding modeli kullanıyor")
        if existing_metadata.get("index_schema") not in {None, INDEX_SCHEMA}:
            raise EvrenQdrantError("Qdrant koleksiyonu farklı indeks şeması kullanıyor")
        client.update_collection(collection_name=settings.collection, metadata=metadata)

        documents = [
            document
            for record in self.store.list_campaigns()
            for document in campaign_documents(record)
        ]
        documents.extend(terminology_documents())
        documents.extend(pdf_evidence_documents())
        documents = [item for item in documents if item[0] and item[1].strip()]
        source_counts = {
            source_type: sum(
                item[2].get("source_type") == source_type for item in documents
            )
            for source_type in ("campaign", "terminology", "pdf_evidence")
        }
        existing: dict[str, tuple[Any, str]] = {}
        offset = None
        while True:
            records, offset = client.scroll(
                settings.collection,
                limit=256,
                offset=offset,
                with_payload=["document_id", "index_hash"],
                with_vectors=False,
            )
            for record in records:
                payload = dict(record.payload or {})
                document_id = str(payload.get("document_id") or "")
                if document_id:
                    existing[document_id] = (
                        record.id,
                        str(payload.get("index_hash") or ""),
                    )
            if offset is None:
                break
        changed = [
            item
            for item in documents
            if existing.get(item[0], (None, ""))[1]
            != str(item[2].get("index_hash") or "")
        ]
        for start in range(0, len(changed), batch_size):
            batch = changed[start : start + batch_size]
            embeddings = self.retriever.embedding_provider.embed_documents(
                [item[1] for item in batch]
            )
            points = [
                models.PointStruct(
                    id=self._point_id(document_id),
                    vector=embedding,
                    payload={
                        **item_metadata,
                        "document_id": document_id,
                        "document_text": text,
                        "embedding_provider": "evren",
                        "embedding_model": self.retriever.embedding_provider.model_name,
                        "embedding_dimensions": (
                            self.retriever.embedding_provider.settings.dimensions
                        ),
                        "indexed_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                for (document_id, text, item_metadata), embedding in zip(batch, embeddings)
            ]
            client.upsert(settings.collection, points=points, wait=True)
        expected_ids = {item[0] for item in documents}
        stale = [point_id for key, (point_id, _) in existing.items() if key not in expected_ids]
        if stale:
            client.delete(settings.collection, points_selector=stale, wait=True)
        completed_at = datetime.now(timezone.utc).isoformat()
        ready_metadata = {
            **metadata,
            "index_status": "ready",
            "document_count": len(documents),
            "indexed_at": completed_at,
        }
        client.update_collection(
            collection_name=settings.collection, metadata=ready_metadata
        )
        return {
            "status": "ready",
            "total": len(documents),
            "source_counts": source_counts,
            "embedded": len(changed),
            "unchanged": len(documents) - len(changed),
            "stale_deleted": len(stale),
            "embedding_model": self.retriever.embedding_provider.model_name,
            "collection": settings.collection,
            "index_schema": INDEX_SCHEMA,
        }
