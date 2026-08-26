"""Metadata ön filtreli, BM25 ve ontoloji genişletmeli yerel retrieval."""

from __future__ import annotations

from collections import Counter
from math import log
import os
from pathlib import Path
from typing import Any

from src.knowledge import TerminologyService
from src.persistence import CampaignStore
from src.preprocessing.clean_text import tokenize_turkish
from src.retrieval.chroma import ChromaVectorRetriever
from src.retrieval.documents import PDF_EVIDENCE_PATH, campaign_documents, pdf_evidence_documents, terminology_documents
from src.retrieval.graph import KnowledgeGraphRetriever
from src.retrieval.qdrant import EvrenQdrantRetriever


ONTOLOGY_CHUNKS_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "ontology" / "rag_chunks.jsonl"
)


class HybridRetriever:
    """Kampanya ve terminoloji kayıtlarından kanıt paketi üretir."""

    def __init__(
        self,
        store: CampaignStore,
        terminology: TerminologyService | None = None,
        *,
        chroma_enabled: bool | None = None,
        vector_retriever: ChromaVectorRetriever | None = None,
        evren_retriever: EvrenQdrantRetriever | None = None,
        graph_retriever: KnowledgeGraphRetriever | None = None,
    ) -> None:
        self.store = store
        self.terminology = terminology or TerminologyService()
        if chroma_enabled is None:
            configured = os.getenv("RAGNROLL_CHROMA_ENABLED", "false").casefold()
            chroma_enabled = configured not in {"0", "false", "off", "hayır", "hayir"}
        provider_order = {
            value.strip().casefold()
            for value in os.getenv(
                "RAGNROLL_RETRIEVAL_PROVIDER_ORDER",
                "evren_qdrant,local_qwen_chroma,bm25_graph",
            ).split(",")
            if value.strip()
        }
        chroma_enabled = chroma_enabled and "local_qwen_chroma" in provider_order
        if vector_retriever is not None:
            self.vector_retriever = vector_retriever
        else:
            self.vector_retriever = ChromaVectorRetriever() if chroma_enabled else None
        if evren_retriever is not None:
            self.evren_retriever = evren_retriever
        elif "evren_qdrant" in provider_order:
            candidate = EvrenQdrantRetriever()
            self.evren_retriever = candidate if candidate.enabled else None
        else:
            self.evren_retriever = None
        self.graph_retriever = graph_retriever or KnowledgeGraphRetriever(
            self.terminology
        )
        self.last_backend = "bm25"
        self._corpus_key: tuple[int, int, int] | None = None
        self._campaign_cache: list[dict[str, Any]] = []
        self._terminology_cache: list[dict[str, Any]] = []
        self._token_cache: dict[tuple[str, str], list[str]] = {}

    @staticmethod
    def _document(item: tuple[str, str, dict[str, Any]]) -> dict[str, Any]:
        identifier, text, metadata = item
        return {"id": identifier, "text": text, "metadata": metadata}

    @staticmethod
    def _rank_key(item: dict[str, Any]) -> str:
        metadata = item.get("metadata", {})
        campaign_id = str(metadata.get("campaign_id") or "")
        return f"campaign:{campaign_id}" if campaign_id else str(item["id"])

    def _load_corpus(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        database_mtime = self.store.path.stat().st_mtime_ns if self.store.path.exists() else 0
        ontology_mtime = ONTOLOGY_CHUNKS_PATH.stat().st_mtime_ns
        pdf_mtime = PDF_EVIDENCE_PATH.stat().st_mtime_ns if PDF_EVIDENCE_PATH.exists() else 0
        corpus_key = (database_mtime, ontology_mtime, pdf_mtime)
        if corpus_key != self._corpus_key:
            self._campaign_cache = [
                self._document(document)
                for row in self.store.list_campaigns()
                for document in campaign_documents(row)
            ]
            self._terminology_cache = [
                self._document(document) for document in terminology_documents()
            ]
            self._terminology_cache.extend(
                self._document(document) for document in pdf_evidence_documents()
            )
            active_tokens = {
                (
                    str(document["id"]),
                    str(document["metadata"].get("index_hash") or ""),
                )
                for document in self._campaign_cache + self._terminology_cache
            }
            self._token_cache = {
                key: value
                for key, value in self._token_cache.items()
                if key in active_tokens
            }
            self._corpus_key = (
                self.store.path.stat().st_mtime_ns,
                ONTOLOGY_CHUNKS_PATH.stat().st_mtime_ns,
                pdf_mtime,
            )
        return self._campaign_cache, self._terminology_cache

    def _document_tokens(self, document: dict[str, Any]) -> list[str]:
        key = (
            str(document["id"]),
            str(document["metadata"].get("index_hash") or ""),
        )
        if key not in self._token_cache:
            self._token_cache[key] = tokenize_turkish(document["text"])
        return self._token_cache[key]

    @classmethod
    def _fuse(
        cls,
        rankings: list[list[dict[str, Any]]],
        *,
        limit: int,
        method: str,
        rrf_constants: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        constants = rrf_constants or [60] * len(rankings)
        if len(constants) != len(rankings):
            raise ValueError("Her sıralama için bir RRF sabiti verilmelidir")
        representatives: dict[str, dict[str, Any]] = {}
        fused: dict[str, float] = {}
        for ranking, rrf_constant in zip(rankings, constants):
            seen: set[str] = set()
            for rank, item in enumerate(ranking, start=1):
                key = cls._rank_key(item)
                if key in seen:
                    continue
                seen.add(key)
                if key not in representatives:
                    representatives[key] = item
                elif item.get("metadata", {}).get("graph_relations"):
                    representatives[key] = {
                        **representatives[key],
                        "metadata": {
                            **representatives[key].get("metadata", {}),
                            "graph_relations": item["metadata"]["graph_relations"],
                        },
                    }
                fused[key] = fused.get(key, 0.0) + 1 / (rrf_constant + rank)
        ranked_keys = sorted(fused, key=lambda key: (-fused[key], key))
        return [
            {
                **representatives[key],
                "score": round(fused[key], 6),
                "retrieval_method": method,
            }
            for key in ranked_keys[:limit]
        ]

    def _bm25(
        self, query_tokens: list[str], documents: list[dict[str, Any]]
    ) -> list[float]:
        tokenized = [self._document_tokens(document) for document in documents]
        if not tokenized:
            return []
        average_length = sum(map(len, tokenized)) / len(tokenized) or 1.0
        document_frequency = Counter(
            token for tokens in tokenized for token in set(tokens)
        )
        scores = []
        for tokens in tokenized:
            frequencies = Counter(tokens)
            score = 0.0
            for token in query_tokens:
                frequency = frequencies[token]
                if not frequency:
                    continue
                inverse_frequency = log(
                    1 + (len(tokenized) - document_frequency[token] + 0.5)
                    / (document_frequency[token] + 0.5)
                )
                denominator = frequency + 1.5 * (
                    1 - 0.75 + 0.75 * len(tokens) / average_length
                )
                score += inverse_frequency * frequency * 2.5 / denominator
            scores.append(score)
        return scores

    def retrieve(
        self,
        query: str,
        *,
        filters: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        if not 1 <= limit <= 20:
            raise ValueError("limit 1 ile 20 arasında olmalıdır")
        filters = filters or {}
        bank_slugs = set(filters.get("bank_slugs") or [])
        product_type = filters.get("product_type")
        source_types = set(filters.get("source_types") or [])
        financing_type = filters.get("financing_type")
        cached_campaigns, cached_terminology = self._load_corpus()
        campaigns = cached_campaigns
        campaigns = [
            document
            for document in campaigns
            if (not source_types or "campaign" in source_types)
            and (not bank_slugs or document["metadata"]["bank_slug"] in bank_slugs)
            and (
                not product_type
                or document["metadata"]["product_type"] in {"", product_type}
            )
            and (
                not financing_type
                or document["metadata"]["financing_type"] in {"", financing_type}
            )
        ]
        terminology = [
            document
            for document in cached_terminology
            if not source_types
            or document["metadata"].get("source_type") in source_types
        ]
        documents = campaigns + terminology
        graph_expansion = self.graph_retriever.expand(
            query, intent=str(filters.get("intent") or "") or None
        )
        expanded = [query]
        expanded.extend(
            str(item["canonical"])
            for item in self.terminology.find_terms(query, limit=8)
            if item.get("canonical")
        )
        expanded.extend(graph_expansion.terms)
        query_tokens = list(dict.fromkeys(tokenize_turkish(" ".join(expanded))))
        scores = self._bm25(query_tokens, documents)
        lexical = sorted(
            (
                {
                    **document,
                    "score": round(score, 6),
                    "retrieval_method": "metadata+bm25+ontology",
                }
                for document, score in zip(documents, scores)
                if score > 0
            ),
            key=lambda item: (-item["score"], item["id"]),
        )
        graph = self.graph_retriever.rank_documents(documents, graph_expansion)
        vector: list[dict[str, Any]] = []
        vector_backend = ""
        vector_fallback_attempted = (
            self.evren_retriever is not None or self.vector_retriever is not None
        )
        if self.evren_retriever is not None:
            try:
                vector = self.evren_retriever.retrieve(
                    query, filters=filters, limit=min(20, limit * 3)
                )
            except Exception:
                vector = []
            if vector:
                vector_backend = "evren-qdrant+bge-m3-embed"
        if not vector and self.vector_retriever is not None:
            try:
                vector = self.vector_retriever.retrieve(
                    query, filters=filters, limit=min(20, limit * 3)
                )
            except Exception:
                vector = []
            if vector:
                vector_backend = "chroma"
        if not vector:
            if graph:
                self.last_backend = "bm25+knowledge-graph"
                if vector_fallback_attempted:
                    self.last_backend += "-fallback"
                return self._fuse(
                    [lexical, graph],
                    limit=limit,
                    method="metadata+bm25+ontology+knowledge-graph",
                    rrf_constants=[60, 10],
                )
            self.last_backend = "bm25"
            if vector_fallback_attempted:
                self.last_backend += "-fallback"
            return lexical[:limit]

        rankings = [vector, lexical]
        if vector_backend == "evren-qdrant+bge-m3-embed":
            method = "evren-qdrant+bge-m3-embed+bm25+ontology"
            self.last_backend = "evren-qdrant+bm25"
        else:
            method = "chroma+semantic+bm25+ontology"
            self.last_backend = "chroma+bm25"
        if graph:
            rankings.append(graph)
            method += "+knowledge-graph"
            self.last_backend += "+knowledge-graph"
        constants = [60, 60, 10] if graph else None
        return self._fuse(
            rankings,
            limit=limit,
            method=method,
            rrf_constants=constants,
        )

    def status(self) -> dict[str, Any]:
        """Birincil ve fallback retrieval yeteneklerinin durumunu döndürür."""

        return {
            "active_backend": self.last_backend,
            "evren_qdrant": (
                self.evren_retriever.status()
                if self.evren_retriever is not None
                else {"available": False, "reason": "disabled"}
            ),
            "local_qwen_chroma": {
                "available": bool(
                    self.vector_retriever is not None
                    and self.vector_retriever.ready()
                ),
                "model": (
                    self.vector_retriever.embedding_model
                    if self.vector_retriever is not None
                    else None
                ),
            },
            "bm25_graph": {"available": True},
        }
