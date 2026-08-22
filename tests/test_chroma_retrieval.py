import chromadb

from src.retrieval.chroma import ChromaVectorRetriever


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
