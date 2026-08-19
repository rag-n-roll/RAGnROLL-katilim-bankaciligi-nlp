"""
Teknofest Katılım Bankacılığı RAG Pipeline

LangChain + Chroma + Qwen3-Embedding + Ollama/Gemma4

Gerçek proje verileri:
- data/processed/campaigns.json
- data/ontology/rag_chunks.jsonl

Ana veri dosyaları değiştirilmez; sadece okunur.
"""

from __future__ import annotations

import re
import json
import hashlib
from pathlib import Path
from typing import Any, List

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

CHROMA_COLLECTION_NAME = "katilim_bankaciligi_qwen3_v2"

PROCESSED_CAMPAIGNS_PATH = (
    PROJECT_ROOT / "data" / "processed" / "campaigns.json"
)

RAW_CAMPAIGNS_PATH = (
    PROJECT_ROOT / "data" / "raw" / "campaigns.json"
)

PARTICIPATION_BANKS_PATH = (
    PROJECT_ROOT / "data" / "raw" / "participation_banks.json"
)

RAG_CHUNKS_PATH = (
    PROJECT_ROOT / "data" / "ontology" / "rag_chunks.jsonl"
)

TERMINOLOGY_PATH = PROJECT_ROOT / "data" / "terminology"
ONTOLOGY_PATH = PROJECT_ROOT / "data" / "ontology"
CHROMA_PATH = PROJECT_ROOT / "chroma_db"

# Lokal bilgisayarda kaynak kullanımını kontrollü tutmak için.
BATCH_SIZE = 1
GENERIC_CHUNK_SIZE = 2800
GENERIC_CHUNK_OVERLAP = 250


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
    "selamlama": [
        "merhaba", "selam", "slm", "hello", "hi", "iyi günler",
        "günaydın", "iyi akşamlar",
    ],
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

    q = question.lower().strip()

    for intent, keywords in INTENT_KEYWORDS.items():
        if any(keyword in q for keyword in keywords):
            return intent

    return "genel_soru"


def small_talk_response(intent: str) -> str | None:
    """RAG gerektirmeyen kısa sohbet mesajlarını cevaplar."""

    if intent == "selamlama":
        return (
            "Merhaba! Katılım bankacılığı, kampanyalar, kâr payı, "
            "finansman veya banka karşılaştırmaları hakkında soru sorabilirsin."
        )

    return None


# ============================================================
# DOKÜMAN HAZIRLAMA YARDIMCILARI
# ============================================================

def _clean_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    return {
        str(key): str(value)
        for key, value in metadata.items()
        if value is not None
    }


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(
        value.encode("utf-8")
    ).hexdigest()[:16]

    return f"{prefix}_{digest}"


def _append_document(
    documents: list[Document],
    ids: list[str],
    text: str,
    metadata: dict[str, Any],
    doc_id: str,
) -> None:
    text = text.strip()

    if not text:
        return

    documents.append(
        Document(
            page_content=text,
            metadata=_clean_metadata(metadata),
        )
    )

    ids.append(doc_id)


def _chunk_text(
    text: str,
    chunk_size: int = GENERIC_CHUNK_SIZE,
    overlap: int = GENERIC_CHUNK_OVERLAP,
) -> list[str]:
    text = text.strip()

    if len(text) <= chunk_size:
        return [text] if text else []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end].strip())

        if end == len(text):
            break

        start = max(0, end - overlap)

    return [chunk for chunk in chunks if chunk]


def _record_to_text(
    record: dict[str, Any],
    source_label: str,
) -> str:
    text_parts = [
        f"Kaynak: {source_label}",
    ]

    field_labels = [
        ("title", "Başlık"),
        ("bank_name", "Banka"),
        ("bank_slug", "Banka kodu"),
        ("category", "Kategori"),
        ("summary", "Özet"),
        ("start_date", "Başlangıç tarihi"),
        ("end_date", "Bitiş tarihi"),
        ("source_url", "Kaynak URL"),
    ]

    for key, label in field_labels:
        value = record.get(key)
        if value:
            text_parts.append(f"{label}: {value}")

    content = (
        record.get("clean_text")
        or record.get("content")
        or ""
    )

    if content:
        text_parts.append(f"İçerik:\n{content}")

    structured = record.get("structured")
    if isinstance(structured, dict):
        structured_text = json.dumps(
            structured,
            ensure_ascii=False,
            indent=2,
        )
        text_parts.append(f"Yapılandırılmış alanlar:\n{structured_text}")

    return "\n".join(text_parts)


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


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
        Projenin gerçek RAG kaynaklarını okur.

        Ana data dosyaları değiştirilmez; sadece Chroma için
        doküman temsilleri üretilir.
        """

        documents = []
        ids = []

        # ----------------------------------------------------
        # 1. BDDK KATILIM BANKALARI KATALOĞU
        # ----------------------------------------------------

        if PARTICIPATION_BANKS_PATH.exists():
            print("BDDK katılım bankaları kataloğu okunuyor...")

            catalog = _load_json(PARTICIPATION_BANKS_PATH)
            banks = catalog.get("banks", [])

            bank_lines = [
                (
                    f"{index}. {bank.get('name')} "
                    f"(slug: {bank.get('slug')}, "
                    f"web: {bank.get('website')}, "
                    f"dijital: {bank.get('is_digital')})"
                )
                for index, bank in enumerate(banks, start=1)
            ]

            catalog_text = "\n".join(
                [
                    "BDDK katılım bankaları listesi.",
                    "Türkiye'deki katılım bankaları şunlardır:",
                    *bank_lines,
                    f"Toplam katılım bankası sayısı: {catalog.get('count')}",
                    f"Kaynak: {catalog.get('source_url')}",
                    f"Alınma zamanı: {catalog.get('retrieved_at')}",
                ]
            )

            _append_document(
                documents,
                ids,
                catalog_text,
                {
                    "source_type": "bank_catalog",
                    "source_file": str(PARTICIPATION_BANKS_PATH),
                    "title": "BDDK Katılım Bankaları Listesi",
                    "bank_count": catalog.get("count"),
                },
                "bank_catalog_bddk_participation_banks",
            )

            for bank in banks:
                bank_text = "\n".join(
                    [
                        "Katılım bankası katalog kaydı.",
                        f"Banka adı: {bank.get('name')}",
                        f"Banka kodu: {bank.get('slug')}",
                        f"Web sitesi: {bank.get('website')}",
                        f"Dijital banka mı: {bank.get('is_digital')}",
                        f"Kaynak: {catalog.get('source_url')}",
                    ]
                )

                _append_document(
                    documents,
                    ids,
                    bank_text,
                    {
                        "source_type": "bank_catalog_item",
                        "source_file": str(PARTICIPATION_BANKS_PATH),
                        "bank_name": bank.get("name"),
                        "bank_slug": bank.get("slug"),
                        "website": bank.get("website"),
                    },
                    f"bank_catalog_item_{bank.get('slug')}",
                )

        # ----------------------------------------------------
        # 2. RAG CHUNK'LARI
        # ----------------------------------------------------

        if RAG_CHUNKS_PATH.exists():
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
                        "source_file": str(RAG_CHUNKS_PATH),
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

                    _append_document(
                        documents,
                        ids,
                        text,
                        metadata,
                        f"rag_{chunk_id}",
                    )

        # ----------------------------------------------------
        # 3. RAW + PROCESSED KAMPANYA KAYITLARI
        # ----------------------------------------------------

        campaign_sources = [
            ("raw_campaign", RAW_CAMPAIGNS_PATH),
            ("processed_campaign", PROCESSED_CAMPAIGNS_PATH),
        ]

        for source_type, path in campaign_sources:
            if not path.exists():
                continue

            print(f"{source_type} verileri okunuyor...")

            data = _load_json(path)
            records = data.get("records", [])

            print(
                f"{path.name}: {len(records)} kampanya kaydı bulundu."
            )

            for index, record in enumerate(records):
                if not isinstance(record, dict):
                    continue

                document_text = _record_to_text(
                    record,
                    source_type,
                )

                campaign_id = str(
                    record.get("id")
                    or f"{source_type}_{index}"
                )

                _append_document(
                    documents,
                    ids,
                    document_text,
                    {
                        "source_type": source_type,
                        "source_file": str(path),
                        "record_kind": record.get("record_kind")
                        or "campaign",
                        "campaign_id": campaign_id,
                        "bank_name": record.get("bank_name"),
                        "bank_slug": record.get("bank_slug"),
                        "title": record.get("title"),
                        "start_date": record.get("start_date"),
                        "end_date": record.get("end_date"),
                        "source_url": record.get("source_url"),
                    },
                    f"{source_type}_{campaign_id}",
                )

        # ----------------------------------------------------
        # 4. TERMİNOLOJİ + ONTOLOJİ DOSYALARI
        # ----------------------------------------------------

        knowledge_dirs = [
            ("terminology", TERMINOLOGY_PATH),
            ("ontology", ONTOLOGY_PATH),
        ]

        for source_type, directory in knowledge_dirs:
            if not directory.exists():
                continue

            print(f"{source_type} klasörü okunuyor...")

            for path in sorted(directory.iterdir()):
                if path.suffix.lower() not in {".json", ".jsonl", ".md"}:
                    continue

                if path == RAG_CHUNKS_PATH:
                    continue

                with path.open("r", encoding="utf-8") as file:
                    raw_text = file.read()

                if path.suffix.lower() == ".json":
                    try:
                        parsed = json.loads(raw_text)
                        raw_text = json.dumps(
                            parsed,
                            ensure_ascii=False,
                            indent=2,
                        )
                    except json.JSONDecodeError:
                        pass

                for chunk_index, chunk in enumerate(_chunk_text(raw_text)):
                    title = (
                        f"{source_type} dosyası: "
                        f"{path.name} parça {chunk_index + 1}"
                    )

                    text = "\n".join(
                        [
                            title,
                            f"Kaynak dosya: {path}",
                            chunk,
                        ]
                    )

                    doc_id = _stable_id(
                        source_type,
                        f"{path}:{chunk_index}",
                    )

                    _append_document(
                        documents,
                        ids,
                        text,
                        {
                            "source_type": source_type,
                            "source_file": str(path),
                            "title": title,
                            "chunk_index": chunk_index,
                        },
                        doc_id,
                    )

        return documents, ids

    # ========================================================
    # BATCHLİ CHROMA YÜKLEME
    # ========================================================

    def load_project_data(self) -> int:
        """
        Gerçek proje verilerini küçük batch'ler halinde
        Qwen embedding + Chroma'ya ekler.

        Bütün dokümanları tek seferde modele göndermez.
        Yarım kalan çalıştırmalarda Chroma'daki mevcut id'leri atlayıp
        sadece eksik dokümanlardan devam eder.
        """

        documents, ids = (
            self.prepare_documents()
        )

        if not documents:
            raise RuntimeError(
                "RAG için hiç doküman bulunamadı."
            )

        total = len(documents)
        existing = self.vector_store._collection.get(
            include=[],
        )
        existing_ids = set(existing.get("ids", []))

        pending_pairs = [
            (document, doc_id)
            for document, doc_id in zip(documents, ids)
            if doc_id not in existing_ids
        ]

        pending_total = len(pending_pairs)

        print()
        print(
            f"Toplam {total} doküman hazır."
        )
        print(
            f"Chroma'da mevcut doküman sayısı: {len(existing_ids)}"
        )
        print(
            f"Eklenecek eksik doküman sayısı: {pending_total}"
        )

        if pending_total == 0:
            print("Chroma zaten güncel; embedding yapılmayacak.")
            return 0

        print(
            f"Embedding batch boyutu: {BATCH_SIZE}"
        )
        print(
            f"Yaklaşık {((pending_total - 1) // BATCH_SIZE) + 1} batch işlenecek."
        )
        print()

        added_count = 0

        for start in range(
            0,
            pending_total,
            BATCH_SIZE,
        ):

            end = min(
                start + BATCH_SIZE,
                pending_total,
            )

            batch_pairs = pending_pairs[start:end]
            batch_documents = [
                document
                for document, _ in batch_pairs
            ]
            batch_ids = [
                doc_id
                for _, doc_id in batch_pairs
            ]

            batch_number = (
                start // BATCH_SIZE
            ) + 1

            total_batches = (
                (pending_total - 1)
                // BATCH_SIZE
            ) + 1

            print(
                f"[{batch_number}/{total_batches}] "
                f"{start + 1}-{end}/{pending_total} "
                f"embedding yapılıyor..."
            )
            print(
                "    Kaynak: "
                f"{batch_documents[0].metadata.get('source_type')} | "
                f"{batch_ids[0]}",
                flush=True,
            )

            self.vector_store.add_documents(
                documents=batch_documents,
                ids=batch_ids,
            )

            added_count += len(
                batch_documents
            )

            print(
                f"    OK Chroma'ya yazıldı "
                f"({added_count}/{pending_total})"
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

Kullanıcı tam liste veya sayım istiyorsa bağlamdaki tüm maddeleri eksiltmeden listele.

Bağlam:
{context}

Kullanıcı sorusu:
{question}

Cevap:
"""

    # ========================================================
    # SORU-CEVAP
    # ========================================================
        # ========================================================
    # HYBRID RETRIEVAL
    # ========================================================

    def _keyword_score(
        self,
        question: str,
        doc: Document,
    ) -> int:
        """
        Basit keyword + metadata eşleşmesi.
        Mevcut Chroma embedding'lerini değiştirmez.
        """

        q = question.lower()

        text = doc.page_content.lower()

        metadata_text = " ".join(
            str(value).lower()
            for value in doc.metadata.values()
        )

        score = 0

        # Tam kelime/ifade eşleşmeleri
        words = re.findall(r"\w+", q, flags=re.UNICODE)

        for word in words:
            if len(word) < 3:
                continue

            if word in text:
                score += 2

            if word in metadata_text:
                score += 3

        # Sık kullanılan önemli ifadeler
        important_phrases = [
            "katılım bankacılığı",
            "katılım bankası",
            "katılım bankalarını",
            "katılım bankaları",
            "hangi banka",
            "banka listesi",
            "bankaları say",
            "bankalarını say",
        ]

        for phrase in important_phrases:
            if phrase in q:
                if phrase in text:
                    score += 8

                if phrase in metadata_text:
                    score += 10

        source_type = str(
            doc.metadata.get("source_type")
            or ""
        )

        bank_catalog_query = any(
            phrase in q
            for phrase in [
                "katılım bankalarını",
                "katılım bankaları",
                "banka listesi",
                "bankaları say",
                "bankalarını say",
            ]
        )

        if bank_catalog_query and source_type == "bank_catalog":
            score += 80

        if bank_catalog_query and source_type == "bank_catalog_item":
            score += 25

        return score

    def _hybrid_retrieval(
        self,
        question: str,
        k: int = 5,
    ) -> list[Document]:
        """
        Semantic retrieval + keyword/metadata scoring.

        Chroma'daki mevcut embedding'ler yeniden oluşturulmaz.
        """

        # Önce semantic olarak daha geniş aday havuzu getir.
        semantic_docs = (
            self.vector_store.similarity_search(
                question,
                k=30,
            )
        )

        if not semantic_docs:
            return []

        # Keyword + metadata skoruyla yeniden sırala.
        scored_docs = []

        for index, doc in enumerate(semantic_docs):

            keyword_score = self._keyword_score(
                question,
                doc,
            )

            # Semantic sırasını da tamamen çöpe atmıyoruz.
            semantic_score = 30 - index

            total_score = (
                keyword_score * 3
                + semantic_score
            )

            scored_docs.append(
                (
                    total_score,
                    doc,
                )
            )

        scored_docs.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return [
            doc
            for _, doc in scored_docs[:k]
        ]
    
    def ask_question(
        self,
        question: str,
        k: int = 5,
    ) -> str:
        """Soruyu RAG üzerinden cevaplar."""

        intent = detect_intent(question)
        print(f"[Intent: {intent}]")

        direct_response = small_talk_response(intent)
        if direct_response:
            print(f"\nGemma4: {direct_response}")
            return direct_response

        docs = self._hybrid_retrieval(
            question,
            k=k,
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
        k: int = 5,
    ):
        """API için: cevabı chunk chunk (token token) yield eder.
        Kutay backend'de bunu StreamingResponse ile sarmalayacak."""

        intent = detect_intent(question)
        print(f"[Intent: {intent}]")

        direct_response = small_talk_response(intent)
        if direct_response:
            yield direct_response
            return

        docs = self._hybrid_retrieval(
            question,
            k=k,
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
    # Yarım kalan indeksleme varsa load_project_data mevcut id'leri
    # atlayıp sadece eksik dokümanları ekler.
    collection_count = rag.vector_store._collection.count()

    print(
        f"\nChroma'da mevcut doküman sayısı: "
        f"{collection_count}\n"
    )

    count = rag.load_project_data()

    final_count = rag.vector_store._collection.count()

    print(
        f"\nRAG hazır. Bu çalıştırmada {count} yeni doküman "
        f"indekslendi. Chroma toplamı: {final_count}\n"
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
