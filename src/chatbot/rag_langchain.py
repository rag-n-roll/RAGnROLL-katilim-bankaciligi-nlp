"""
Teknofest Katılım Bankacılığı RAG Pipeline

LangChain + Chroma + Qwen3-Embedding + Ollama/Gemma4

Gerçek proje verileri:
- data/processed/campaigns.json
- data/ontology/rag_chunks.jsonl

Ana veri dosyaları değiştirilmez; sadece okunur.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaLLM
from sentence_transformers import SentenceTransformer


# ============================================================
# AYARLAR
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OLLAMA_MODEL = "gemma4:e4b"
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"

CHROMA_COLLECTION_NAME = "katilim_bankaciligi_qwen3"

CAMPAIGNS_PATH = (
    PROJECT_ROOT / "data" / "processed" / "campaigns.json"
)

RAG_CHUNKS_PATH = (
    PROJECT_ROOT / "data" / "ontology" / "rag_chunks.jsonl"
)

CHROMA_PATH = PROJECT_ROOT / "chroma_db"

# Lokal bilgisayarda kaynak kullanımını kontrollü tutmak için.
BATCH_SIZE = 8


# ============================================================
# QWEN3 EMBEDDING
# ============================================================

class Qwen3Embeddings(Embeddings):
    """Qwen3-Embedding'i LangChain Embeddings arayüzüyle kullanır."""

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL,
    ):
        print(
            f"Embedding modeli yükleniyor: {model_name}"
        )

        self.model = SentenceTransformer(model_name)

    def embed_documents(
        self,
        texts: List[str],
    ) -> List[List[float]]:
        """Dokümanları Qwen3 ile embed eder."""

        embeddings = self.model.encode(
            texts,
            batch_size=BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

        return embeddings.tolist()

    def embed_query(
        self,
        text: str,
    ) -> List[float]:
        """Kullanıcı sorgusunu Qwen3 query embedding'i olarak üretir."""

        embedding = self.model.encode(
            [text],
            prompt_name="query",
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]

        return embedding.tolist()


# ============================================================
# INTENT DETECTION
# ============================================================

# Kural bazlı, basit ve hızlı bir intent sınıflandırıcı.
# Amaç: kullanıcı sorusunun ne tür bir istek olduğunu (tanım,
# kampanya bilgisi, karşılaştırma, genel) etiketlemek.
# Gelecek iterasyonda ML tabanlı bir sınıflandırıcıya geçilebilir.
INTENT_KEYWORDS = {
    "tanim_sorgusu": ["nedir", "ne demek", "tanım", "tanımı"],
    "kampanya_sorgusu": [
        "hangi banka", "kampanya", "faiz", "oran", "getiri", "ödül",
    ],
    "karsilastirma_sorgusu": [
        "fark", "karşılaştır", "hangisi daha iyi", "hangisi daha",
    ],
}


def detect_intent(question: str) -> str:
    """Kullanıcı sorusunun niyetini basit anahtar kelime eşleşmesiyle sınıflandırır."""

    q = question.lower()

    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in q for keyword in keywords):
            return intent

    return "genel_soru"


# ============================================================
# RAG
# ============================================================

class LangChainRAG:
    def __init__(self):
        print("Qwen embedding hazırlanıyor...")

        self.embeddings = Qwen3Embeddings()

        print(
            f"Ollama bağlanıyor: {OLLAMA_MODEL}"
        )

        self.llm = OllamaLLM(
            model=OLLAMA_MODEL,
            temperature=0.1,
        )

        print("Chroma hazırlanıyor...")

        self.vector_store = Chroma(
            collection_name=CHROMA_COLLECTION_NAME,
            embedding_function=self.embeddings,
            persist_directory=str(CHROMA_PATH),
        )

    # ========================================================
    # VERİLERİ OKUMA
    # ========================================================

    def prepare_documents(self) -> tuple[
        list[Document],
        list[str],
    ]:
        """
        Projenin mevcut gerçek verilerini okur.

        Ana data dosyaları değiştirilmez.
        """

        documents = []
        ids = []

        # ----------------------------------------------------
        # 1. RAG CHUNK'LARI
        # ----------------------------------------------------

        print("RAG chunk'ları okunuyor...")

        with RAG_CHUNKS_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:

            for line in file:

                if not line.strip():
                    continue

                item = json.loads(line)

                text = item.get(
                    "text",
                    "",
                ).strip()

                if not text:
                    continue

                chunk_id = item.get(
                    "chunk_id",
                    f"rag_chunk_{len(ids)}",
                )

                metadata = {
                    "source_type": "rag_chunk",
                    "title": item.get(
                        "title",
                        "",
                    ),
                    "chunk_id": chunk_id,
                    **{
                        str(key): str(value)
                        for key, value in item.get(
                            "metadata",
                            {},
                        ).items()
                        if value is not None
                    },
                }

                documents.append(
                    Document(
                        page_content=text,
                        metadata=metadata,
                    )
                )

                ids.append(
                    f"rag_{chunk_id}"
                )

        # ----------------------------------------------------
        # 2. GERÇEK KAMPANYA KAYITLARI
        # ----------------------------------------------------

        print("Kampanya verileri okunuyor...")

        with CAMPAIGNS_PATH.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(file)

        records = data.get(
            "records",
            [],
        )

        print(
            f"{len(records)} kampanya kaydı bulundu."
        )

        for record in records:

            content = str(
                record.get("content")
                or record.get("summary")
                or ""
            ).strip()

            title = str(
                record.get("title")
                or ""
            ).strip()

            bank_name = str(
                record.get("bank_name")
                or ""
            ).strip()

            if not content:
                continue

            text_parts = []

            if title:
                text_parts.append(
                    f"Başlık: {title}"
                )

            if bank_name:
                text_parts.append(
                    f"Banka: {bank_name}"
                )

            text_parts.append(
                f"İçerik:\n{content}"
            )

            structured = record.get(
                "structured",
                {},
            )

            if isinstance(
                structured,
                dict,
            ):

                reward = structured.get(
                    "reward_amount"
                )

                if reward:
                    text_parts.append(
                        f"Ödül bilgisi: {reward}"
                    )

                target = structured.get(
                    "target_audience"
                )

                if target:
                    text_parts.append(
                        f"Hedef kitle: {target}"
                    )

                product_type = structured.get(
                    "product_type"
                )

                if product_type:
                    text_parts.append(
                        f"Ürün tipi: {product_type}"
                    )

            document_text = "\n".join(
                text_parts
            )

            metadata = {
                "source_type": "campaign",
                "record_kind": str(
                    record.get(
                        "record_kind"
                    )
                    or "campaign"
                ),
                "campaign_id": str(
                    record.get("id")
                    or ""
                ),
                "bank_name": bank_name,
                "title": title,
                "start_date": str(
                    record.get(
                        "start_date"
                    )
                    or ""
                ),
                "end_date": str(
                    record.get(
                        "end_date"
                    )
                    or ""
                ),
                "source_url": str(
                    record.get(
                        "source_url"
                    )
                    or ""
                ),
            }

            campaign_id = str(
                record.get("id")
                or f"campaign_{len(ids)}"
            )

            documents.append(
                Document(
                    page_content=document_text,
                    metadata=metadata,
                )
            )

            ids.append(
                f"campaign_{campaign_id}"
            )

        return documents, ids

    # ========================================================
    # BATCHLİ CHROMA YÜKLEME
    # ========================================================

    def load_project_data(self) -> int:
        """
        Gerçek proje verilerini küçük batch'ler halinde
        Qwen embedding + Chroma'ya ekler.

        Bütün 1712 dokümanı tek seferde modele göndermez.
        """

        documents, ids = (
            self.prepare_documents()
        )

        if not documents:
            raise RuntimeError(
                "RAG için hiç doküman bulunamadı."
            )

        total = len(documents)

        print()
        print(
            f"Toplam {total} doküman hazır."
        )
        print(
            f"Embedding batch boyutu: {BATCH_SIZE}"
        )
        print(
            f"Yaklaşık {((total - 1) // BATCH_SIZE) + 1} batch işlenecek."
        )
        print()

        added_count = 0

        for start in range(
            0,
            total,
            BATCH_SIZE,
        ):

            end = min(
                start + BATCH_SIZE,
                total,
            )

            batch_documents = (
                documents[start:end]
            )

            batch_ids = ids[start:end]

            batch_number = (
                start // BATCH_SIZE
            ) + 1

            total_batches = (
                (total - 1)
                // BATCH_SIZE
            ) + 1

            print(
                f"[{batch_number}/{total_batches}] "
                f"{start + 1}-{end}/{total} "
                f"embedding yapılıyor..."
            )

            self.vector_store.add_documents(
                documents=batch_documents,
                ids=batch_ids,
            )

            added_count += len(
                batch_documents
            )

            print(
                f"    ✓ Chroma'ya yazıldı "
                f"({added_count}/{total})"
            )

        print()
        print(
            f"Toplam {added_count} doküman "
            f"Chroma'ya eklendi."
        )

        return added_count

    # ========================================================
    # PROMPT OLUŞTURMA (ortak, tekrar etmesin diye)
    # ========================================================

    def _build_prompt(self, question: str, context: str) -> str:
        return f"""
Sen Türkçe konuşan bir katılım bankacılığı
asistanısın.

Sadece aşağıdaki bağlamdaki bilgileri kullan.

Bağlamda bulunmayan bilgileri kesinlikle uydurma.

Sorunun cevabı bağlamda bulunmuyorsa aynen:

"Bu bilgi sağlanan dokümanlarda bulunmamaktadır."

cevabını ver.

Cevabı Türkçe, kısa ve anlaşılır şekilde ver.

Bağlam:
{context}

Kullanıcı sorusu:
{question}

Cevap:
"""

    # ========================================================
    # SORU-CEVAP
    # ========================================================

    def ask_question(
        self,
        question: str,
        k: int = 3,
    ) -> str:
        """Soruyu RAG üzerinden cevaplar."""

        intent = detect_intent(question)
        print(f"[Intent: {intent}]")

        docs = (
            self.vector_store.similarity_search(
                question,
                k=k,
            )
        )
        if not docs:
            return (
                "Bu bilgi sağlanan dokümanlarda "
                "bulunmamaktadır."
            )

        context = "\n\n---\n\n".join(
            doc.page_content
            for doc in docs
        )

        prompt = self._build_prompt(question, context)

        chunks = []

        print("\nGemma4: ", end="", flush=True)

        for chunk in self.llm.stream(prompt):
            print(chunk, end="", flush=True)
            chunks.append(chunk)

        print()

        return "".join(chunks).strip()

    def ask_question_stream(
        self,
        question: str,
        k: int = 3,
    ):
        """API için: cevabı chunk chunk (token token) yield eder.
        Kutay backend'de bunu StreamingResponse ile sarmalayacak."""

        intent = detect_intent(question)
        print(f"[Intent: {intent}]")

        docs = (
            self.vector_store.similarity_search(
                question,
                k=k,
            )
        )

        if not docs:
            yield (
                "Bu bilgi sağlanan dokümanlarda "
                "bulunmamaktadır."
            )
            return

        context = "\n\n---\n\n".join(
            doc.page_content
            for doc in docs
        )

        prompt = self._build_prompt(question, context)

        for chunk in self.llm.stream(prompt):
            yield chunk


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    rag = LangChainRAG()

    # Mevcut Chroma collection'ını kontrol et.
    # 1712 doküman zaten indekslendiyse tekrar embedding yapma.
    collection_count = rag.vector_store._collection.count()

    print(
        f"\nChroma'da mevcut doküman sayısı: "
        f"{collection_count}\n"
    )

    if collection_count == 0:

        print(
            "Chroma boş. Gerçek proje verileri "
            "indeksleniyor...\n"
        )

        count = rag.load_project_data()

        print(
            f"\nRAG hazır. "
            f"{count} doküman indekslendi.\n"
        )

    else:

        print(
            f"Mevcut Chroma collection kullanılıyor. "
            f"{collection_count} doküman hazır.\n"
        )

    print(
        "Chatbot hazır. Çıkmak için 'q' yaz.\n"
    )

    while True:

        question = input(
            "Sen: "
        ).strip()

        if question.lower() == "q":
            break

        if not question:
            continue

        try:
            rag.ask_question(question)
            print()

        except Exception as exc:

            print(
                f"\nHata: {exc}\n"
            )
