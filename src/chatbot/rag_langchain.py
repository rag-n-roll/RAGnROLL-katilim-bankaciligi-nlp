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
Sen Türkçe konuşan bir katılım bankacılığı asistanısın.
Sadece aşağıdaki bağlamdaki bilgileri kullan; bağlamda olmayan bilgiyi uydurma.
Bağlamda cevap yoksa aynen "Bu bilgi sağlanan dokümanlarda bulunmamaktadır." de.
Kullanıcı teşekkür, onay veya kısa olumlu geri bildirim yazıyorsa yeni konu açma;
kısaca "Rica ederim. Başka bir sorunuz olursa yardımcı olabilirim." benzeri cevap ver.
Kısa tanım sorularında 1-2 cümle yaz; metadata, eş anlamlı ve İngilizce çeviri ekleme.
Tanım cevabında "Metadata", "Eş Anlamlıları", "İngilizce Çevirisi",
"Ana Kategori", "Alt Kategori" veya "İlişkili Terimler" başlıklarını asla yazma.
Kampanya/avantaj sorularında doğal konuş, rapor gibi uzatma; en alakalı bilgileri özetle.
Geniş banka kampanyası sorularında tüm kampanyaları dökme; hangi alanı merak ettiğini sor
ve bağlamdaki örnek alanlardan birkaçını kısa şekilde belirt.
Kullanıcı katılım bankalarını saymanı veya listelemeni isterse örnek liste deme;
bağlamdaki BDDK katılım bankaları listesindeki tüm bankaları eksiksiz numaralandır.
Markdown başlığı, tablo ve emoji kullanma.

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

    def _search_text(
        self,
        value: object,
    ) -> str:
        """Türkçe büyük İ gibi arama eşleşmelerini normalize eder."""

        return str(value).lower().replace("i̇", "i")

    def _keyword_score(
        self,
        question: str,
        doc: Document,
    ) -> int:
        """
        Basit keyword + metadata eşleşmesi.
        Mevcut Chroma embedding'lerini değiştirmez.
        """

        q = self._search_text(question)

        text = self._search_text(doc.page_content)

        metadata_text = " ".join(
            self._search_text(value)
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
            "kampanya",
            "kampanyaları",
            "kampanyalarında",
            "avantaj",
            "kredi kart",
            "kart",
            "türkiye finans",
            "turkiye finans",
            "kuveyt türk",
            "kuveytturk",
            "albaraka",
            "ziraat katılım",
            "vakıf katılım",
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

        finance_product_query = any(
            phrase in q
            for phrase in [
                "ihtiyaç finansmanı",
                "ihtiyac finansmani",
                "konut finansmanı",
                "konut finansmani",
                "ev finansmanı",
                "ev finansmani",
                "taşıt finansmanı",
                "tasit finansmani",
                "seyahat finansmanı",
                "seyahat finansmani",
                "döviz işlemleri",
                "doviz islemleri",
                "döviz",
                "doviz",
                "altın",
                "altin",
                "kıymetli maden",
                "kiymetli maden",
                "kur",
            ]
        )

        campaign_query = any(
            phrase in q
            for phrase in [
                "kampanya",
                "kampanyaları",
                "kampanyalarında",
                "fırsat",
                "firsat",
            ]
        ) or ("avantaj" in q and not finance_product_query)

        if campaign_query and source_type in {
            "processed_campaign",
            "raw_campaign",
        }:
            score += 35

        if finance_product_query and source_type in {
            "rag_chunk",
            "terminology",
            "ontology",
        }:
            score += 110

        known_banks = [
            "türkiye finans",
            "turkiye finans",
            "kuveyt türk",
            "kuveytturk",
            "albaraka",
            "ziraat katılım",
            "vakıf katılım",
            "emlak katılım",
            "hayat finans",
            "dünya katılım",
        ]

        for bank in known_banks:
            if bank in q and (
                bank in text
                or bank in metadata_text
            ):
                score += 180

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
                k=80,
            )
        )

        q = self._search_text(question)
        bank_slugs = []

        bank_slug_aliases = {
            "türkiye finans": "turkiye-finans",
            "turkiye finans": "turkiye-finans",
            "finans katılım": "turkiye-finans",
            "finans katilim": "turkiye-finans",
            "kuveyt türk": "kuveyt-turk",
            "kuveytturk": "kuveyt-turk",
            "albaraka": "albaraka",
            "ziraat katılım": "ziraat-katilim",
            "ziraat katilim": "ziraat-katilim",
            "vakıf katılım": "vakif-katilim",
            "vakif katilim": "vakif-katilim",
            "emlak katılım": "emlak-katilim",
            "emlak katilim": "emlak-katilim",
            "hayat finans": "hayat-finans",
            "dünya katılım": "dunya-katilim",
            "dunya katilim": "dunya-katilim",
        }

        for alias, slug in bank_slug_aliases.items():
            if alias in q:
                if slug not in bank_slugs:
                    bank_slugs.append(slug)

        finance_product_query = any(
            phrase in q
            for phrase in [
                "ihtiyaç finansmanı",
                "ihtiyac finansmani",
                "konut finansmanı",
                "konut finansmani",
                "ev finansmanı",
                "ev finansmani",
                "taşıt finansmanı",
                "tasit finansmani",
                "seyahat finansmanı",
                "seyahat finansmani",
                "döviz işlemleri",
                "doviz islemleri",
                "döviz",
                "doviz",
                "altın",
                "altin",
                "kıymetli maden",
                "kiymetli maden",
                "kur",
            ]
        )

        campaign_query = any(
            phrase in q
            for phrase in [
                "kampanya",
                "kampanyaları",
                "kampanyalarında",
                "fırsat",
                "firsat",
            ]
        ) or ("avantaj" in q and not finance_product_query)

        if campaign_query and bank_slugs:
            try:
                for scoped_bank_slug in bank_slugs:
                    semantic_docs.extend(
                        self.vector_store.similarity_search(
                            question,
                            k=40,
                            filter={"bank_slug": scoped_bank_slug},
                        )
                    )
            except Exception as exc:  # noqa: BLE001
                print(
                    "Banka filtreli Chroma araması atlandı: "
                    f"{exc}"
                )

        if finance_product_query:
            product_queries = []

            if any(
                phrase in q
                for phrase in [
                    "konut finansmanı",
                    "konut finansmani",
                    "ev finansmanı",
                    "ev finansmani",
                ]
            ):
                product_queries.extend(
                    [
                        "Konut Finansmanı",
                        "İlk Evim Konut Finansmanı",
                        "Konut Edindirme Finansmanı",
                    ]
                )

            if any(
                phrase in q
                for phrase in [
                    "ihtiyaç finansmanı",
                    "ihtiyac finansmani",
                ]
            ):
                product_queries.append("İhtiyaç Finansmanı")

            if any(
                phrase in q
                for phrase in [
                    "taşıt finansmanı",
                    "tasit finansmani",
                ]
            ):
                product_queries.append("Taşıt Finansmanı")

            if any(
                phrase in q
                for phrase in [
                    "seyahat finansmanı",
                    "seyahat finansmani",
                ]
            ):
                product_queries.append("Seyahat Finansmanı")

            if any(
                phrase in q
                for phrase in [
                    "döviz işlemleri",
                    "doviz islemleri",
                    "döviz",
                    "doviz",
                    "altın",
                    "altin",
                    "kıymetli maden",
                    "kiymetli maden",
                    "kur",
                ]
            ):
                product_queries.extend(
                    [
                        "Döviz Alım-Satımı",
                        "Döviz Katılma Hesabı",
                        "Para Birimi",
                        "Altın Alım-Satımı",
                        "Altın Katılma Hesabı",
                    ]
                )

            for product_query in product_queries:
                semantic_docs.extend(
                    self.vector_store.similarity_search(
                        product_query,
                        k=12,
                    )
                )

                for scoped_bank_slug in bank_slugs:
                    try:
                        semantic_docs.extend(
                            self.vector_store.similarity_search(
                                f"{question} {product_query}",
                                k=25,
                                filter={"bank_slug": scoped_bank_slug},
                            )
                        )
                    except Exception as exc:  # noqa: BLE001
                        print(
                            "Banka filtreli ürün araması atlandı: "
                            f"{exc}"
                        )

        if not semantic_docs:
            return []

        # Keyword + metadata skoruyla yeniden sırala.
        scored_docs = []
        seen_doc_keys = set()

        for index, doc in enumerate(semantic_docs):
            doc_key = (
                doc.metadata.get("campaign_id")
                or doc.metadata.get("term_id")
                or doc.metadata.get("chunk_id")
                or doc.metadata.get("title")
                or doc.metadata.get("source_file")
                or doc.page_content[:120]
            )

            if doc_key in seen_doc_keys:
                continue

            seen_doc_keys.add(doc_key)

            keyword_score = self._keyword_score(
                question,
                doc,
            )

            if bank_slugs:
                doc_bank_slug = str(
                    doc.metadata.get("bank_slug")
                    or ""
                )

                if finance_product_query and doc_bank_slug in bank_slugs:
                    keyword_score += 35
                elif doc_bank_slug in bank_slugs:
                    keyword_score += 160
                elif doc_bank_slug:
                    keyword_score -= 120

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

        if campaign_query and bank_slugs and not finance_product_query:
            bank_scored_docs = [
                item
                for item in scored_docs
                if str(
                    item[1].metadata.get("bank_slug")
                    or ""
                ) in bank_slugs
            ]

            if bank_scored_docs:
                scored_docs = bank_scored_docs

        if finance_product_query and bank_slugs:
            scoped_scored_docs = []

            for item in scored_docs:
                doc_bank_slug = str(
                    item[1].metadata.get("bank_slug")
                    or ""
                )

                if doc_bank_slug == "" or doc_bank_slug in bank_slugs:
                    scoped_scored_docs.append(item)

            if scoped_scored_docs:
                scored_docs = scoped_scored_docs

        campaign_area_terms = {
            "card": [
                "kart",
                "kredi kart",
                "mastercard",
                "sağlam kart",
                "saglam kart",
                "ihtiyaç kart",
                "ihtiyac kart",
            ],
            "mobile": [
                "mobil",
                "self nokta",
                "dijital",
            ],
            "invoice": [
                "fatura",
                "talimat",
            ],
            "vehicle": [
                "taşıt",
                "tasit",
                "araç",
                "arac",
                "otomobil",
            ],
            "housing": [
                "konut finansmanı",
                "konut finansmani",
                "ev finansmanı",
                "ev finansmani",
                "ilk evim",
                "ilk konut",
                "konut",
            ],
            "need_finance": [
                "ihtiyaç finansmanı",
                "ihtiyac finansmani",
                "ihtiyaç finansmani",
                "ihtiyac finansmanı",
                "ihtiyaç",
                "ihtiyac",
            ],
            "wedding": [
                "evlilik",
                "düğün",
                "dugun",
                "çeyiz",
                "ceyiz",
                "ev eşyası",
                "ev esyasi",
                "balayı",
                "balayi",
            ],
            "cashback": [
                "nakit iade",
                "iade",
                "bonus",
                "puan",
            ],
            "installment": [
                "taksit",
                "vade farksız",
                "vade farksiz",
            ],
            "travel": [
                "seyahat planları",
                "seyehat planları",
                "seyahat planlari",
                "seyehat planlari",
                "seyahat",
                "seyehat",
                "miles",
                "smiles",
                "uçak",
                "ucak",
                "yurt dışı",
                "yurt disi",
            ],
            "exchange": [
                "döviz işlemleri",
                "doviz islemleri",
                "döviz",
                "doviz",
                "altın",
                "altin",
                "kıymetli maden",
                "kiymetli maden",
                "kur",
                "para birimi",
            ],
        }

        matched_area_terms = []
        matched_area_name = ""

        for area_name, terms in campaign_area_terms.items():
            query_matched_terms = [
                term
                for term in terms
                if term in q
            ]

            if query_matched_terms:
                matched_area_name = area_name
                matched_area_terms.extend(query_matched_terms)

                if area_name == "exchange" and any(
                    term in query_matched_terms
                    for term in [
                        "döviz işlemleri",
                        "doviz islemleri",
                        "döviz",
                        "doviz",
                    ]
                ):
                    matched_area_terms.extend(["kur"])

        if (campaign_query or finance_product_query) and matched_area_terms:
            area_scored_docs = []

            for item in scored_docs:
                doc = item[1]
                title_text = self._search_text(
                    doc.metadata.get("title")
                    or ""
                )
                source_url_text = self._search_text(
                    doc.metadata.get("source_url")
                    or ""
                )
                metadata_text = self._search_text(
                    " ".join(
                        self._search_text(value)
                        for value in doc.metadata.values()
                    )
                )
                content_text = self._search_text(doc.page_content)

                area_score = 0

                for term in matched_area_terms:
                    if term in title_text:
                        area_score += 260

                    if term in source_url_text:
                        area_score += 160

                    if term in metadata_text:
                        area_score += 35

                    if term in content_text:
                        area_score += 12

                if area_score > 0:
                    area_scored_docs.append(
                        (
                            item[0] + area_score * 4,
                            doc,
                        )
                    )

            area_scored_docs.sort(
                key=lambda item: item[0],
                reverse=True,
                )

            if area_scored_docs:
                scored_docs = area_scored_docs

        if (campaign_query or finance_product_query) and matched_area_name == "exchange":
            title_matched_docs = []
            other_docs = []

            for item in scored_docs:
                doc = item[1]
                title_and_url = self._search_text(
                    " ".join(
                        [
                            str(doc.metadata.get("title") or ""),
                            str(doc.metadata.get("source_url") or ""),
                        ]
                    )
                )

                if any(term in title_and_url for term in matched_area_terms):
                    title_matched_docs.append(item)
                else:
                    other_docs.append(item)

            if title_matched_docs:
                scored_docs = title_matched_docs + other_docs

        return [
            doc
            for _, doc in scored_docs[:k]
        ]

    def _is_campaign_query(
        self,
        question: str,
    ) -> bool:
        q = self._search_text(question)

        finance_product_query = any(
            phrase in q
            for phrase in [
                "ihtiyaç finansmanı",
                "ihtiyac finansmani",
                "konut finansmanı",
                "konut finansmani",
                "ev finansmanı",
                "ev finansmani",
                "taşıt finansmanı",
                "tasit finansmani",
                "seyahat finansmanı",
                "seyahat finansmani",
                "döviz işlemleri",
                "doviz islemleri",
                "döviz",
                "doviz",
                "altın",
                "altin",
                "kıymetli maden",
                "kiymetli maden",
                "kur",
            ]
        )

        return any(
            phrase in q
            for phrase in [
                "kampanya",
                "kampanyaları",
                "kampanyalarında",
                "fırsat",
                "firsat",
            ]
        ) or ("avantaj" in q and not finance_product_query)

    def _is_finance_product_query(
        self,
        question: str,
    ) -> bool:
        q = self._search_text(question)

        return any(
            phrase in q
            for phrase in [
                "ihtiyaç finansmanı",
                "ihtiyac finansmani",
                "konut finansmanı",
                "konut finansmani",
                "ev finansmanı",
                "ev finansmani",
                "taşıt finansmanı",
                "tasit finansmani",
                "seyahat finansmanı",
                "seyahat finansmani",
            ]
        )

    def _is_definition_query(
        self,
        question: str,
    ) -> bool:
        q = self._search_text(question)

        return any(
            phrase in q
            for phrase in [
                "nedir",
                "ne demek",
                "tanım",
                "tanımı",
            ]
        )

    def _is_bank_catalog_query(
        self,
        question: str,
    ) -> bool:
        q = self._search_text(question)

        return any(
            phrase in q
            for phrase in [
                "katılım bankalarını",
                "katilim bankalarini",
                "katılım bankaları",
                "katilim bankalari",
                "bankaları say",
                "bankalari say",
                "bankalarını say",
                "bankalarini say",
                "banka listesi",
                "tüm bankalar",
                "tum bankalar",
                "tam liste",
            ]
        )

    def _needs_comparable_selection(
        self,
        question: str,
    ) -> bool:
        q = self._search_text(question)

        return any(
            phrase in q
            for phrase in [
                "en iyi",
                "en uygun",
                "hangisi daha iyi",
                "hangi banka daha iyi",
                "hangi banka",
            ]
        ) and any(
            phrase in q
            for phrase in [
                "konut finansmanı",
                "konut finansmani",
                "ev finansmanı",
                "ev finansmani",
                "ihtiyaç finansmanı",
                "ihtiyac finansmani",
                "taşıt finansmanı",
                "tasit finansmani",
            ]
        )

    def _selection_missing_data_response(
        self,
    ) -> str:
        return (
            "Bunu tek bir banka diye seçebilmem için bankaların aynı ürüne ait "
            "oran, vade, masraf ve kampanya şartları birlikte verilmiş olmalı. "
            "Sağlanan dokümanlarda bu karşılaştırmayı güvenilir şekilde yapacak "
            "yeterli veri bulunmuyor."
        )

    def _format_context(
        self,
        question: str,
        docs: list[Document],
    ) -> str:
        """
        Kampanya kayıtları uzun olduğu için prompt penceresinde en alakalı
        başlıkların düşmesini engelleyen kısa RAG bağlamı üretir.
        """

        if self._is_bank_catalog_query(question):
            catalog_docs = [
                doc
                for doc in docs
                if doc.metadata.get("source_type") == "bank_catalog"
            ]

            if catalog_docs:
                return catalog_docs[0].page_content

            return "\n\n---\n\n".join(
                doc.page_content
                for doc in docs
                if doc.metadata.get("source_type") == "bank_catalog_item"
            )

        if self._is_definition_query(question):
            context_items = []

            for doc in docs[:1]:
                title = str(doc.metadata.get("title") or "").strip()
                content = re.sub(
                    r"\s+",
                    " ",
                    doc.page_content,
                ).strip()
                content = re.split(
                    (
                        r"\bAna kategori:|\bAlt kategori:|\bEntity:|"
                        r"\bEş anlamlılar:|\bİlişkili terimler:"
                    ),
                    content,
                    maxsplit=1,
                )[0].strip()

                if title and not content.startswith(title):
                    content = f"{title}: {content}"

                context_items.append(content)

            return "\n\n---\n\n".join(context_items)

        if (
            not self._is_campaign_query(question)
            or self._is_finance_product_query(question)
        ):
            return "\n\n---\n\n".join(
                doc.page_content
                for doc in docs
            )

        context_items = []

        for index, doc in enumerate(docs[:5]):
            metadata = doc.metadata
            title = str(metadata.get("title") or "").strip()
            bank = str(metadata.get("bank_name") or "").strip()
            source_type = str(metadata.get("source_type") or "").strip()
            source_url = str(metadata.get("source_url") or "").strip()
            content = re.sub(
                r"\s+",
                " ",
                doc.page_content,
            ).strip()

            content_limit = 1800 if index == 0 else 850

            if len(content) > content_limit:
                content = f"{content[:content_limit].rstrip()}..."

            context_items.append(
                "\n".join(
                    part
                    for part in [
                        f"Kaynak türü: {source_type}" if source_type else "",
                        f"Banka: {bank}" if bank else "",
                        f"Kampanya başlığı: {title}" if title else "",
                        f"Kaynak URL: {source_url}" if source_url else "",
                        f"İçerik: {content}",
                    ]
                    if part
                )
            )

        return "\n\n---\n\n".join(context_items)

    def _answer_char_limit(
        self,
        question: str,
    ) -> int:
        """Demo UI'da cevapların rapora dönüşmesini engeller."""

        q = self._search_text(question)

        full_list_query = any(
            phrase in q
            for phrase in [
                "katılım bankalarını",
                "katılım bankaları",
                "banka listesi",
                "bankaları say",
                "bankalarını say",
                "tüm bankalar",
                "tam liste",
            ]
        )

        if full_list_query:
            return 1800

        if self._is_definition_query(question):
            return 1200

        finance_product_query = any(
            phrase in q
            for phrase in [
                "ihtiyaç finansmanı",
                "ihtiyac finansmani",
                "konut finansmanı",
                "konut finansmani",
                "ev finansmanı",
                "ev finansmani",
                "taşıt finansmanı",
                "tasit finansmani",
                "seyahat finansmanı",
                "seyahat finansmani",
            ]
        )

        if finance_product_query:
            return 3200

        broad_campaign_query = any(
            word in q
            for word in [
                "kampanya",
                "avantaj",
                "fırsat",
                "karşılaştır",
                "en uygun",
            ]
        )

        if broad_campaign_query:
            broad_bank_campaign_query = (
                "kampanya" in q
                and any(word in q for word in ["hangi", "neler", "nelerdir"])
                and not any(
                    term in q
                    for term in [
                        "kart",
                        "mobil",
                        "fatura",
                        "davet",
                        "seyahat",
                        "seyehat",
                        "evlilik",
                        "düğün",
                        "dugun",
                        "çeyiz",
                        "ceyiz",
                        "döviz",
                        "doviz",
                        "kur",
                        "ihtiyaç finansmanı",
                        "ihtiyac finansmani",
                        "konut finansmanı",
                        "konut finansmani",
                        "taşıt finansmanı",
                        "tasit finansmani",
                    ]
                )
            )

            return 1800 if broad_bank_campaign_query else 1700

        return 1400

    def _limit_suffix(
        self,
        question: str,
    ) -> str:
        if self._is_campaign_query(question):
            return (
                "\n\nBelirli bir kampanya veya ürün adı verirsen "
                "daha net bakabilirim."
            )

        return ""

    def _strip_partial_suffix(
        self,
        answer: str,
    ) -> str:
        partial_suffix_pattern = (
            r"\s*Belirli bir kampanya(?:\s+veya(?:\s+ürün"
            r"(?:\s+adı(?:\s+verirsen(?:\s+daha"
            r"(?:\s+net(?:\s+bakabilirim\.?)?)?)?)?)?)?)?\s*$"
        )

        return re.sub(
            partial_suffix_pattern,
            "",
            answer,
            flags=re.IGNORECASE,
        ).rstrip()

    def _limited_answer(
        self,
        question: str,
        answer: str,
        limit: int,
    ) -> str | None:
        """
        Model çok uzatırsa cevabı cümle sonunda kapatır.
        None dönerse cevap henüz sınırı aşmamıştır.
        """

        if len(answer) <= limit:
            return None

        suffix = self._limit_suffix(question)

        usable_limit = max(
            120,
            limit - len(suffix),
        )
        candidate = answer[:usable_limit].rstrip()

        sentence_ends = list(
            re.finditer(
                r"[.!?]\s+",
                candidate,
            )
        )

        if sentence_ends:
            last_end = sentence_ends[-1].end()

            if last_end >= usable_limit * 0.55:
                candidate = candidate[:last_end].strip()

        if not suffix:
            return candidate

        candidate = self._strip_partial_suffix(candidate)
        return f"{candidate}{suffix}"

    def _cleanup_answer_text(
        self,
        answer: str,
    ) -> str:
        """Model markdown/rapor formatına kaçarsa demo cevabını sadeleştirir."""

        cleaned = answer

        replacements = {
            "\\*\\*": "",
            "**": "",
            "\\*": "-",
            "###": "",
            "---": "",
        }

        for old, new in replacements.items():
            cleaned = cleaned.replace(old, new)

        cleaned = re.sub(
            r"[\U0001F300-\U0001FAFF]",
            "",
            cleaned,
        )
        cleaned = re.sub(
            r"[ \t]{2,}",
            " ",
            cleaned,
        )
        cleaned = re.sub(
            r"\n{3,}",
            "\n\n",
            cleaned,
        )

        lines = []

        for raw_line in cleaned.splitlines():
            line = raw_line.strip()

            if not line:
                continue

            if any(
                phrase in self._search_text(line)
                for phrase in [
                    "şeffaf maliyetlendirme",
                    "seffaf maliyetlendirme",
                    "önemli hatırlatma",
                    "onemli hatirlatma",
                    "genel bilgilendirme",
                    "maliyet tabloları",
                    "maliyet tablolari",
                    "özetle yapmanız gerekenler",
                    "ozetle yapmaniz gerekenler",
                    "yapmanız gerekenler",
                    "yapmaniz gerekenler",
                ]
            ):
                continue

            line = re.sub(
                r"^\s*[-•]\s*",
                "- ",
                line,
            )
            line = re.sub(
                r"^\s*\d+\.\s+",
                "",
                line,
            )

            lines.append(line)

        return "\n".join(lines).strip()

    def _stream_clean_answer(
        self,
        question: str,
        prompt: str,
    ):
        """LLM stream'ini küçük parçalar halinde dışarı verir."""

        limit = self._answer_char_limit(question)
        q = self._search_text(question)
        finance_product_query = any(
            phrase in q
            for phrase in [
                "ihtiyaç finansmanı",
                "ihtiyac finansmani",
                "konut finansmanı",
                "konut finansmani",
                "ev finansmanı",
                "ev finansmani",
                "taşıt finansmanı",
                "tasit finansmani",
                "seyahat finansmanı",
                "seyahat finansmani",
            ]
        )
        emitted = ""
        buffer = ""
        stop_markers = [
            "özetle yapmanız gerekenler",
            "ozetle yapmaniz gerekenler",
            "yapmanız gerekenler",
            "yapmaniz gerekenler",
        ]

        def emit_piece(piece: str) -> tuple[str, bool]:
            nonlocal emitted

            cleaned = self._cleanup_answer_text(piece)

            if not cleaned:
                return "", False

            separator = ""

            if emitted and not emitted.endswith(("\n", " ")):
                separator = " "

            next_text = f"{separator}{cleaned}"
            next_total = f"{emitted}{next_text}"

            if finance_product_query and any(
                marker in self._search_text(next_total)
                for marker in stop_markers
            ):
                return "", True

            if len(emitted) + len(next_text) > limit:
                if emitted:
                    closing = (
                        " Detay istersen belirli bir başlığı ayrıca sorabilirsin."
                        if emitted.rstrip().endswith((".", "!", "?"))
                        else ". Detay istersen belirli bir başlığı ayrıca sorabilirsin."
                    )
                    emitted += closing
                    return closing, True

                limited = self._limited_answer(
                    question,
                    cleaned,
                    limit,
                )
                cleaned = self._cleanup_answer_text(
                    limited or cleaned,
                )
                emitted = cleaned
                return cleaned, True

            emitted += next_text

            if self._is_definition_query(question):
                sentence_count = len(
                    re.findall(
                        r"[.!?](?:\s|$)",
                        emitted,
                    )
                )

                if sentence_count >= 2:
                    return next_text, True

            if (
                finance_product_query
                and "özetle" in self._search_text(emitted)
                and emitted.rstrip().endswith((".", "!", "?"))
            ):
                return next_text, True

            return next_text, False

        for chunk in self.llm.stream(prompt):
            buffer += chunk

            while True:
                boundary_match = re.search(
                    r"\s+",
                    buffer,
                )

                if not boundary_match and len(buffer) < 24:
                    break

                boundary = (
                    boundary_match.end()
                    if boundary_match
                    else len(buffer)
                )
                piece = buffer[:boundary]
                buffer = buffer[boundary:]

                outgoing, should_stop = emit_piece(piece)

                if outgoing:
                    yield outgoing

                if should_stop:
                    return

        if buffer:
            outgoing, _ = emit_piece(buffer)

            if outgoing:
                yield outgoing

    def _stream_visible_answer(
        self,
        prompt: str,
    ):
        """Stream cevabında kullanıcıya metadata/çeviri satırlarını göstermez."""

        blocked_labels = (
            "Metadata:",
            "Eş Anlamlıları:",
            "Es Anlamlilari:",
            "İngilizce Çevirisi:",
            "Ingilizce Cevirisi:",
            "Ana Kategori:",
            "Alt Kategori:",
            "İlişkili Terimler:",
            "Iliskili Terimler:",
        )
        buffer = ""

        for chunk in self.llm.stream(prompt):
            buffer += str(chunk)

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)

                if any(label in line for label in blocked_labels):
                    continue

                yield f"{line}\n"

        if buffer and not any(label in buffer for label in blocked_labels):
            yield buffer

    def ask_question(
        self,
        question: str,
        k: int = 8,
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
            if self._needs_comparable_selection(question):
                return self._selection_missing_data_response()

            return (
                "Bu bilgi sağlanan dokümanlarda "
                "bulunmamaktadır."
            )

        context = self._format_context(question, docs)

        prompt = self._build_prompt(question, context)

        print("\nGemma4: ", end="", flush=True)

        chunks = []

        for chunk in self._stream_visible_answer(prompt):
            print(chunk, end="", flush=True)
            chunks.append(chunk)

        print()

        return "".join(chunks).strip()

    def ask_question_stream(
        self,
        question: str,
        k: int = 8,
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
            if self._needs_comparable_selection(question):
                yield self._selection_missing_data_response()
                return

            yield (
                "Bu bilgi sağlanan dokümanlarda "
                "bulunmamaktadır."
            )
            return

        context = self._format_context(question, docs)

        prompt = self._build_prompt(question, context)

        yield from self._stream_visible_answer(prompt)


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
