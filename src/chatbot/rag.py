"""
Katılım Bankacılığı Chatbot - RAG (Retrieval-Augmented Generation) Pipeline
Ollama (yerel LLM) + ChromaDB (vektör veritabanı) kullanır.
Dış API çağrısı yapılmaz, tamamen yerelde çalışır.
"""
from __future__ import annotations

import chromadb
from chromadb.utils import embedding_functions
import ollama

# ---- Ayarlar ----
OLLAMA_MODEL = "gemma2"  # Hafta 2 karşılaştırmasında en iyi sonucu veren model
CHROMA_COLLECTION_NAME = "katilim_bankaciligi"
EMBEDDING_MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"  # Türkçe destekli


class RAGPipeline:
    """Katılım bankacılığı verisi üzerinde soru-cevap yapan RAG sistemi."""

    def __init__(self):
        # ChromaDB'yi bellekte başlat (kalıcı depolama Hafta 3'te eklenecek)
        self.chroma_client = chromadb.Client()

        # Türkçe destekli embedding fonksiyonu
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL_NAME
        )

        # Koleksiyon oluştur (varsa mevcut olanı kullan)
        self.collection = self.chroma_client.get_or_create_collection(
            name=CHROMA_COLLECTION_NAME,
            embedding_function=self.embedding_fn,
        )

    def add_documents(self, documents: list[str], ids: list[str]) -> None:
        """Kampanya/ürün metinlerini vektör veritabanına ekler."""
        self.collection.add(documents=documents, ids=ids)

    def retrieve(self, query: str, n_results: int = 3) -> list[str]:
        """Soruyla en alakalı metin parçalarını bulur."""
        results = self.collection.query(query_texts=[query], n_results=n_results)
        return results["documents"][0] if results["documents"] else []

    def generate_answer(self, query: str) -> str:
        """RAG akışını çalıştırır: bul + Ollama ile cevap üret."""
        context_chunks = self.retrieve(query)
        context_text = "\n".join(context_chunks) if context_chunks else "İlgili bilgi bulunamadı."

        prompt = f"""Aşağıdaki bilgilere dayanarak soruyu Türkçe ve kısa şekilde cevapla.
Eğer bilgi yetersizse, "Bu konuda elimde yeterli bilgi yok" de, uydurma cevap verme.

Bilgiler:
{context_text}

Soru: {query}
Cevap:"""

        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"]


# Basit test (dosya direkt çalıştırılırsa)
if __name__ == "__main__":
    rag = RAGPipeline()

    # Örnek/test verisi (gerçek veri scraper'dan gelecek)
    rag.add_documents(
        documents=[
            "Kuveyt Türk, yeni müşterilere ilk 3 ay boyunca kâr payı avantajı sunan bir hesap kampanyası başlattı.",
            "Albaraka Türk, konut finansmanında düşük başlangıç maliyeti sunan bir kampanya yürütüyor.",
        ],
        ids=["doc1", "doc2"],
    )

    answer = rag.generate_answer("Kuveyt Türk'ün kampanyası nedir?")
    print("Cevap:", answer)
