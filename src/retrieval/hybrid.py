"""Metadata ön filtreli, BM25 ve ontoloji genişletmeli yerel retrieval."""

from __future__ import annotations

from collections import Counter
import json
from math import log
from pathlib import Path
from typing import Any

from src.knowledge import TerminologyService
from src.persistence import CampaignStore
from src.preprocessing.clean_text import tokenize_turkish


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class HybridRetriever:
    """Kampanya ve terminoloji kayıtlarından kanıt paketi üretir."""

    def __init__(
        self,
        store: CampaignStore,
        terminology: TerminologyService | None = None,
    ) -> None:
        self.store = store
        self.terminology = terminology or TerminologyService()

    @staticmethod
    def _campaign_document(record: dict[str, Any]) -> dict[str, Any]:
        content = str(record.get("clean_text") or record.get("content") or "")
        return {
            "id": str(record.get("id") or ""),
            "text": "\n".join(
                part
                for part in (
                    str(record.get("title") or ""),
                    str(record.get("bank_name") or ""),
                    content,
                )
                if part
            ),
            "metadata": {
                "source_type": "campaign",
                "campaign_id": str(record.get("id") or ""),
                "bank_slug": str(record.get("bank_slug") or ""),
                "bank_name": str(record.get("bank_name") or ""),
                "product_type": str(
                    (record.get("structured") or {}).get("product_type") or ""
                ),
                "source_url": str(record.get("source_url") or ""),
                "title": str(record.get("title") or ""),
            },
        }

    @staticmethod
    def _terminology_documents() -> list[dict[str, Any]]:
        path = PROJECT_ROOT / "data" / "ontology" / "rag_chunks.jsonl"
        documents = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            item_metadata = (
                item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            )
            documents.append(
                {
                    "id": str(
                        item.get("chunk_id")
                        or item.get("term_id")
                        or item_metadata.get("term_id")
                        or ""
                    ),
                    "text": str(item.get("text") or ""),
                    "metadata": {
                        "source_type": "terminology",
                        "term_id": str(
                            item.get("term_id") or item_metadata.get("term_id") or ""
                        ),
                        "title": str(item.get("title") or item.get("term") or ""),
                        "source_url": str(item_metadata.get("source_url") or ""),
                    },
                }
            )
        return documents

    @staticmethod
    def _bm25(query_tokens: list[str], documents: list[dict[str, Any]]) -> list[float]:
        tokenized = [tokenize_turkish(document["text"]) for document in documents]
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
        campaigns = [self._campaign_document(row) for row in self.store.list_campaigns()]
        campaigns = [
            document
            for document in campaigns
            if (not source_types or "campaign" in source_types)
            and (not bank_slugs or document["metadata"]["bank_slug"] in bank_slugs)
            and (
                not product_type
                or document["metadata"]["product_type"] in {"", product_type}
            )
        ]
        terminology = (
            self._terminology_documents()
            if not source_types or "terminology" in source_types
            else []
        )
        documents = campaigns + terminology
        expanded = [query]
        expanded.extend(
            str(item["canonical"])
            for item in self.terminology.find_terms(query, limit=8)
            if item.get("canonical")
        )
        query_tokens = list(dict.fromkeys(tokenize_turkish(" ".join(expanded))))
        scores = self._bm25(query_tokens, documents)
        ranked = sorted(
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
        return ranked[:limit]
