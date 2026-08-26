import json

import chromadb
import numpy as np

from src.persistence import CampaignStore
from src.preprocessing.clean_text import preprocess_record
from src.retrieval.chroma import (
    DEFAULT_EMBEDDING_MODEL,
    ChromaIndexer,
    ChromaVectorRetriever,
    SemanticEmbeddingProvider,
)
from src.retrieval.documents import terminology_documents
from src.scraper.models import Campaign


class FakeEmbeddingProvider:
    model_name = "test-embedding"

    def embed_query(self, text):
        return [1.0, 0.0] if "konut" in text else [0.0, 1.0]


def _collection(path):
    client = chromadb.PersistentClient(path=str(path))
    collection = client.get_or_create_collection(
        "test_collection",
        metadata={"embedding_model": "test-embedding", "hnsw:space": "cosine"},
    )
    collection.upsert(
        ids=["campaign:housing", "campaign:vehicle"],
        documents=["Konut finansmanı", "Taşıt finansmanı"],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadatas=[
            {
                "source_type": "campaign",
                "bank_slug": "ornek",
                "product_type": "housing",
                "campaign_id": "housing",
            },
            {
                "source_type": "campaign",
                "bank_slug": "diger",
                "product_type": "vehicle",
                "campaign_id": "vehicle",
            },
        ],
    )


def test_chroma_retriever_uses_semantic_embedding_and_metadata_filters(tmp_path):
    path = tmp_path / "chroma"
    _collection(path)
    retriever = ChromaVectorRetriever(
        path=path,
        collection_name="test_collection",
        embedding_model="test-embedding",
        provider=FakeEmbeddingProvider(),
    )

    results = retriever.retrieve(
        "konut oranı",
        filters={"bank_slugs": ["ornek"], "product_type": "housing"},
        limit=5,
    )

    assert retriever.ready() is True
    assert [item["metadata"]["campaign_id"] for item in results] == ["housing"]
    assert results[0]["retrieval_method"] == "chroma+semantic"


def test_chroma_retriever_rejects_embedding_model_mismatch(tmp_path):
    path = tmp_path / "chroma"
    _collection(path)
    retriever = ChromaVectorRetriever(
        path=path,
        collection_name="test_collection",
        embedding_model="different-model",
        provider=FakeEmbeddingProvider(),
    )

    assert retriever.ready() is False
    assert retriever.retrieve("konut") == []


class RecordingModel:
    def __init__(self):
        self.calls = []

    def encode(self, values, **options):
        self.calls.append((values, options))
        return np.array([[1.0, 0.0] for _ in values])


def test_qwen_provider_uses_domain_instruction_only_for_queries():
    provider = SemanticEmbeddingProvider()
    provider._model = RecordingModel()

    provider.embed_documents(["Konut finansmanı belgesi"])
    provider.embed_query("Hangi belgeler gerekir?")

    assert DEFAULT_EMBEDDING_MODEL == "Qwen/Qwen3-Embedding-0.6B"
    document_values, document_options = provider._model.calls[0]
    query_values, query_options = provider._model.calls[1]
    assert document_values == ["Konut finansmanı belgesi"]
    assert "prompt" not in document_options
    assert query_values == ["Hangi belgeler gerekir?"]
    assert "Turkish participation banking" in query_options["prompt"]


def test_embedding_provider_caches_repeated_query_without_exposing_mutable_state():
    provider = SemanticEmbeddingProvider()
    provider._model = RecordingModel()

    first = provider.embed_query("Konut koşulları")
    first[0] = 99.0
    second = provider.embed_query("Konut koşulları")

    assert len(provider._model.calls) == 1
    assert second == [1.0, 0.0]


class CountingEmbeddingProvider:
    model_name = "test-incremental"

    def __init__(self):
        self.embedded = []

    def embed_documents(self, texts):
        self.embedded.extend(texts)
        return [[1.0, float(index % 2)] for index, _ in enumerate(texts)]

    def embed_query(self, text):
        return [1.0, 0.0]


def _incremental_store(tmp_path):
    store = CampaignStore(tmp_path / "campaigns.sqlite3")
    row = Campaign(
        id="education",
        bank_slug="ornek",
        bank_name="Örnek Katılım",
        title="Eğitim kampanyası",
        content="Öğrencilere 500 TL ödül sunulur.",
        source_url="https://ornek.example/education",
    ).to_dict()
    store.upsert_rows([preprocess_record(row)], run_status="success")
    return store, row


def test_indexer_embeds_only_changed_documents(tmp_path, monkeypatch):
    terminology_path = tmp_path / "terms.jsonl"
    terminology_path.write_text(
        json.dumps(
            {
                "chunk_id": "CHK_1",
                "title": "Murabaha",
                "text": "Murabaha bir katılım finans akdidir.",
                "metadata": {"term_id": "TRM_1"},
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    terms = terminology_documents(terminology_path)
    monkeypatch.setattr("src.retrieval.chroma.terminology_documents", lambda: terms)
    pdf_documents = [
        (
            "pdf:verified:1",
            "Kâr payı havuzu katılma hesaplarından oluşur.",
            {
                "source_type": "pdf_evidence",
                "index_hash": "pdf-hash-1",
                "source_url": "https://tkbb.org.tr/ornek.pdf",
            },
        )
    ]
    monkeypatch.setattr(
        "src.retrieval.chroma.pdf_evidence_documents", lambda: pdf_documents
    )
    store, row = _incremental_store(tmp_path)
    provider = CountingEmbeddingProvider()
    indexer = ChromaIndexer(
        store,
        path=tmp_path / "chroma",
        collection_name="incremental",
        provider=provider,
    )

    first = indexer.build(batch_size=8)
    second = indexer.build(batch_size=8)
    row["content"] = "Öğrencilere 750 TL ödül sunulur."
    store.upsert_rows([preprocess_record(row)], run_status="success")
    third = indexer.build(batch_size=8)

    assert first["source_counts"] == {
        "campaign": 1,
        "terminology": 1,
        "pdf_evidence": 1,
    }
    assert first["embedded"] == 3
    assert first["unchanged"] == 0
    assert second["embedded"] == 0
    assert second["unchanged"] == 3
    assert third["embedded"] == 1
    assert third["unchanged"] == 2
    assert third["stale_deleted"] == 0
    assert indexer.retriever.ready() is True


def test_indexer_deletes_stale_chunks_after_campaign_becomes_short(tmp_path, monkeypatch):
    monkeypatch.setattr("src.retrieval.chroma.terminology_documents", lambda: [])
    monkeypatch.setattr("src.retrieval.chroma.pdf_evidence_documents", lambda: [])
    store, row = _incremental_store(tmp_path)
    row["content"] = " ".join(f"uzun koşul {index}." for index in range(500))
    store.upsert_rows([preprocess_record(row)], run_status="success")
    indexer = ChromaIndexer(
        store,
        path=tmp_path / "chroma",
        collection_name="stale-chunks",
        provider=CountingEmbeddingProvider(),
    )
    first = indexer.build(batch_size=8)

    row["content"] = "Kısa kampanya koşulu."
    store.upsert_rows([preprocess_record(row)], run_status="success")
    second = indexer.build(batch_size=8)

    assert first["campaigns"] > 1
    assert second["campaigns"] == 1
    assert second["embedded"] == 1
    assert second["stale_deleted"] == first["campaigns"]
