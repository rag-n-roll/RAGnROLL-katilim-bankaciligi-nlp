"""Kalıcı Chroma koleksiyonu için semantik arama ve güvenli ingest desteği."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from src.persistence import CampaignStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHROMA_PATH = PROJECT_ROOT / "chroma_db"
DEFAULT_COLLECTION = "katilim_bankaciligi"
DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-small"


class SemanticEmbeddingProvider:
    """Doküman ve sorgu gömmelerini aynı normalize edilmiş uzayda üretir."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL) -> None:
        self.model_name = model_name
        self._model = None
        self.batch_size = int(os.getenv("RAGNROLL_EMBEDDING_BATCH_SIZE", "32"))

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_documents(self, texts: Iterable[str]) -> list[list[float]]:
        values = list(texts)
        if not values:
            return []
        inputs = [f"passage: {value}" for value in values]
        embeddings = self._load().encode(
            inputs,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        embedding = self._load().encode(
            [f"query: {text}"], normalize_embeddings=True, show_progress_bar=False
        )[0]
        return embedding.tolist()


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
            indexed_model = str((collection.metadata or {}).get("embedding_model") or "")
            return collection.count() > 0 and indexed_model == self.embedding_model
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
    """Düzeltilmiş SQLite kayıtlarını ve ontolojiyi tekrar çalıştırılabilir yükler."""

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

    @staticmethod
    def _campaign_document(record: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        structured = record.get("structured") or {}
        fields = structured.get("fields") if isinstance(structured, dict) else {}
        field_lines = []
        if isinstance(fields, dict):
            for name, contract in sorted(fields.items()):
                if not isinstance(contract, dict) or contract.get("value") is None:
                    continue
                unit = f" {contract.get('unit')}" if contract.get("unit") else ""
                field_lines.append(f"{name}: {contract['value']}{unit}")
        text = "\n".join(
            part
            for part in (
                f"Başlık: {record.get('title') or ''}",
                f"Banka: {record.get('bank_name') or ''}",
                f"İçerik: {record.get('clean_text') or record.get('content') or ''}",
                "Yapılandırılmış alanlar: " + "; ".join(field_lines)
                if field_lines
                else "",
            )
            if part
        )[:12_000]
        identifier = str(record.get("id") or "")
        metadata = {
            "source_type": "campaign",
            "campaign_id": identifier,
            "term_id": "",
            "bank_slug": str(record.get("bank_slug") or ""),
            "bank_name": str(record.get("bank_name") or ""),
            "product_type": str(structured.get("product_type") or ""),
            "title": str(record.get("title") or ""),
            "source_url": str(record.get("source_url") or ""),
            "scraped_at": str(record.get("scraped_at") or ""),
            "content_hash": str(record.get("content_hash") or ""),
        }
        return f"campaign:{identifier}", text, metadata

    @staticmethod
    def _terminology_documents() -> list[tuple[str, str, dict[str, Any]]]:
        path = PROJECT_ROOT / "data" / "ontology" / "rag_chunks.jsonl"
        documents = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            nested = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            term_id = str(item.get("term_id") or nested.get("term_id") or "")
            chunk_id = str(item.get("chunk_id") or term_id)
            documents.append(
                (
                    f"term:{chunk_id}",
                    str(item.get("text") or "")[:12_000],
                    {
                        "source_type": "terminology",
                        "campaign_id": "",
                        "term_id": term_id,
                        "bank_slug": "",
                        "bank_name": "",
                        "product_type": "",
                        "title": str(item.get("title") or item.get("term") or ""),
                        "source_url": str(nested.get("source_url") or ""),
                        "scraped_at": "",
                        "content_hash": "",
                    },
                )
            )
        return documents

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
            },
        )
        metadata = dict(collection.metadata or {})
        indexed_model = metadata.get("embedding_model")
        if indexed_model and indexed_model != self.retriever.embedding_model:
            raise RuntimeError(
                "Chroma koleksiyonu farklı bir embedding modeliyle oluşturulmuş"
            )
        if not indexed_model:
            metadata["embedding_model"] = self.retriever.embedding_model
            collection.modify(metadata=metadata)

        documents = [
            self._campaign_document(record) for record in self.store.list_campaigns()
        ]
        documents.extend(self._terminology_documents())
        documents = [item for item in documents if item[0] and item[1].strip()]
        expected_ids = {item[0] for item in documents}
        for start in range(0, len(documents), batch_size):
            batch = documents[start : start + batch_size]
            texts = [item[1] for item in batch]
            embedding_inputs = [text[:2000] for text in texts]
            collection.upsert(
                ids=[item[0] for item in batch],
                documents=texts,
                metadatas=[item[2] for item in batch],
                embeddings=self.retriever.provider.embed_documents(embedding_inputs),
            )
        existing_ids = set(collection.get().get("ids") or [])
        stale_ids = sorted(existing_ids - expected_ids)
        if stale_ids:
            collection.delete(ids=stale_ids)
        return {
            "campaigns": sum(item[2]["source_type"] == "campaign" for item in documents),
            "terminology": sum(
                item[2]["source_type"] == "terminology" for item in documents
            ),
            "total": collection.count(),
            "stale_deleted": len(stale_ids),
            "embedding_model": self.retriever.embedding_model,
            "collection": self.retriever.collection_name,
            "path": str(self.retriever.path),
        }
