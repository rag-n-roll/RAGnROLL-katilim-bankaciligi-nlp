"""Kalıcı Chroma koleksiyonu için semantik arama ve güvenli ingest desteği."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import os
from pathlib import Path
from typing import Any, Iterable

from src.persistence import CampaignStore
from src.retrieval.documents import (
    INDEX_SCHEMA,
    campaign_documents,
    pdf_evidence_documents,
    terminology_documents,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHROMA_PATH = PROJECT_ROOT / "chroma_db"
DEFAULT_COLLECTION = "katilim_bankaciligi_qwen3"
DEFAULT_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_QUERY_PROMPT = (
    "Instruct: Retrieve authoritative Turkish participation banking campaign or "
    "terminology passages that directly answer the query.\nQuery: "
)


class SemanticEmbeddingProvider:
    """Doküman ve sorgu gömmelerini aynı normalize edilmiş uzayda üretir."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        self.model_name = model_name
        self._model = None
        self.batch_size = int(os.getenv("RAGNROLL_EMBEDDING_BATCH_SIZE", "4"))
        self.query_prompt = os.getenv(
            "RAGNROLL_EMBEDDING_QUERY_PROMPT", DEFAULT_QUERY_PROMPT
        )

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            device = os.getenv("RAGNROLL_EMBEDDING_DEVICE") or None
            self._model = SentenceTransformer(self.model_name, device=device)
        return self._model

    @property
    def _is_qwen3(self) -> bool:
        return "qwen3-embedding" in self.model_name.casefold()

    @property
    def _is_e5(self) -> bool:
        return "e5" in self.model_name.casefold()

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        values = list(texts)
        if not values:
            return []
        inputs = [f"passage: {value}" for value in values] if self._is_e5 else values
        embeddings = self._load().encode(
            inputs,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        return list(self._embed_query_cached(str(text or "").strip()))

    @lru_cache(maxsize=256)
    def _embed_query_cached(self, text: str) -> tuple[float, ...]:
        """Tekrarlanan sorgularda model çağrısını sınırlı LRU ile önler."""

        value = f"query: {text}" if self._is_e5 else text
        options: dict[str, Any] = {}
        if self._is_qwen3:
            options["prompt"] = self.query_prompt
        embedding = self._load().encode(
            [value],
            normalize_embeddings=True,
            show_progress_bar=False,
            **options,
        )[0]
        return tuple(embedding.tolist())


class ChromaVectorRetriever:
    """İndeks sağlıklıysa Chroma'dan filtrelenmiş semantik kanıt getirir."""

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        collection_name: str | None = None,
        embedding_model: str | None = None,
        provider: SemanticEmbeddingProvider | None = None,
    ) -> None:
        configured_path = path or os.getenv("RAGNROLL_CHROMA_PATH") or DEFAULT_CHROMA_PATH
        self.path = Path(configured_path)
        if not self.path.is_absolute():
            self.path = PROJECT_ROOT / self.path
        self.collection_name = (
            collection_name
            or os.getenv("RAGNROLL_CHROMA_COLLECTION")
            or DEFAULT_COLLECTION
        )
        self.embedding_model = (
            embedding_model
            or os.getenv("RAGNROLL_EMBEDDING_MODEL")
            or DEFAULT_EMBEDDING_MODEL
        )
        self.provider = provider or SemanticEmbeddingProvider(self.embedding_model)
        self._collection = None

    def _get_collection(self):
        if self._collection is None:
            import chromadb

            client = chromadb.PersistentClient(path=str(self.path))
            self._collection = client.get_collection(self.collection_name)
        return self._collection

    def ready(self) -> bool:
        try:
            collection = self._get_collection()
            metadata = dict(collection.metadata or {})
            indexed_model = str(metadata.get("embedding_model") or "")
            index_schema = str(metadata.get("index_schema") or "")
            index_status = str(metadata.get("index_status") or "ready")
            compatible_schema = not index_schema or index_schema == INDEX_SCHEMA
            return (
                collection.count() > 0
                and indexed_model == self.embedding_model
                and compatible_schema
                and index_status == "ready"
            )
        except Exception:
            return False

    @staticmethod
    def _where(filters: dict[str, Any]) -> dict[str, Any] | None:
        clauses: list[dict[str, Any]] = []
        source_types = list(filters.get("source_types") or [])
        bank_slugs = list(filters.get("bank_slugs") or [])
        if source_types:
            clauses.append({"source_type": {"$in": source_types}})
        if bank_slugs:
            clauses.append({"bank_slug": {"$in": bank_slugs}})
        if filters.get("product_type"):
            clauses.append({"product_type": str(filters["product_type"])})
        if filters.get("financing_type"):
            clauses.append({"financing_type": str(filters["financing_type"])})
        if not clauses:
            return None
        return clauses[0] if len(clauses) == 1 else {"$and": clauses}

    def retrieve(
        self,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if not self.ready():
            return []
        collection = self._get_collection()
        result = collection.query(
            query_embeddings=[self.provider.embed_query(query)],
            n_results=limit,
            where=self._where(filters or {}),
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        items = []
        for identifier, document, metadata, distance in zip(
            ids, documents, metadatas, distances
        ):
            score = max(0.0, 1.0 - float(distance))
            items.append(
                {
                    "id": str(identifier),
                    "text": str(document or ""),
                    "metadata": dict(metadata or {}),
                    "score": round(score, 6),
                    "retrieval_method": "chroma+semantic",
                }
            )
        return items


class ChromaIndexer:
    """Yalnız değişen semantik parçaları embed eden güvenli Chroma indeksleyicisi."""

    def __init__(
        self,
        store: CampaignStore,
        *,
        path: str | Path | None = None,
        collection_name: str | None = None,
        provider: SemanticEmbeddingProvider | None = None,
    ) -> None:
        self.store = store
        self.retriever = ChromaVectorRetriever(
            path=path,
            collection_name=collection_name,
            provider=provider,
            embedding_model=provider.model_name if provider else None,
        )

    def build(self, *, batch_size: int = 8) -> dict[str, Any]:
        if not 1 <= batch_size <= 128:
            raise ValueError("batch_size 1 ile 128 arasında olmalıdır")
        import chromadb

        self.retriever.path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(self.retriever.path))
        collection = client.get_or_create_collection(
            self.retriever.collection_name,
            metadata={
                "embedding_model": self.retriever.embedding_model,
                "hnsw:space": "cosine",
                "index_schema": INDEX_SCHEMA,
                "index_status": "building",
            },
        )
        metadata = dict(collection.metadata or {})
        metadata.pop("hnsw:space", None)
        indexed_model = metadata.get("embedding_model")
        if indexed_model and indexed_model != self.retriever.embedding_model:
            raise RuntimeError(
                "Chroma koleksiyonu farklı bir embedding modeliyle oluşturulmuş"
            )
        indexed_schema = metadata.get("index_schema")
        if indexed_schema and indexed_schema != INDEX_SCHEMA:
            raise RuntimeError("Chroma koleksiyonu farklı bir parçalama şemasıyla oluşturulmuş")
        metadata.update(
            embedding_model=self.retriever.embedding_model,
            index_schema=INDEX_SCHEMA,
            index_status="building",
        )
        collection.modify(metadata=metadata)

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
        expected_ids = {item[0] for item in documents}
        existing = collection.get(include=["metadatas"])
        existing_hashes = {
            str(identifier): str((item_metadata or {}).get("index_hash") or "")
            for identifier, item_metadata in zip(
                existing.get("ids") or [], existing.get("metadatas") or []
            )
        }
        changed = [
            item
            for item in documents
            if existing_hashes.get(item[0]) != str(item[2].get("index_hash") or "")
        ]
        for start in range(0, len(changed), batch_size):
            batch = changed[start : start + batch_size]
            texts = [item[1] for item in batch]
            collection.upsert(
                ids=[item[0] for item in batch],
                documents=texts,
                metadatas=[item[2] for item in batch],
                embeddings=self.retriever.provider.embed_documents(texts),
            )
        existing_ids = set(existing.get("ids") or [])
        stale_ids = sorted(existing_ids - expected_ids)
        if stale_ids:
            collection.delete(ids=stale_ids)
        completed_at = datetime.now(timezone.utc).isoformat()
        metadata.update(
            index_status="ready",
            document_count=collection.count(),
            indexed_at=completed_at,
        )
        collection.modify(metadata=metadata)
        return {
            "campaigns": source_counts["campaign"],
            "terminology": source_counts["terminology"],
            "pdf_evidence": source_counts["pdf_evidence"],
            "source_counts": source_counts,
            "total": collection.count(),
            "embedded": len(changed),
            "unchanged": len(documents) - len(changed),
            "stale_deleted": len(stale_ids),
            "embedding_model": self.retriever.embedding_model,
            "index_schema": INDEX_SCHEMA,
            "collection": self.retriever.collection_name,
            "path": str(self.retriever.path),
        }
