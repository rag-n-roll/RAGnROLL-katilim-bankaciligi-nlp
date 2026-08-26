"""PDF'lerden sayfa kaynaklı, sınırlı RAG kanıt parçaları çıkarır."""
from __future__ import annotations

from hashlib import sha256
import re
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader


TOPICS = {
    "fon_havuzu": ("fon havuzu", "katılma hesabı", "kâr dağıt", "kar dağıt"),
    "kar_paylasim": ("kâr paylaşım", "kar paylaşım", "kâr/zarar", "kar/zarar"),
    "muhasebe": ("birim değer", "hesap değeri", "havuz", "katılım hesabı"),
    "urun_sureci": ("murabaha", "müşareke", "mudârebe", "finansal kiralama"),
}

SOURCE_URLS = {
    "KATILIM_BANKACILIGINDA_KAR_DAGITIMI": "https://tkbb.org.tr/upload/KATILIM_BANKACILIGINDA_KAR_DAGITIMI.pdf",
    "FAIZSIZ-FINANS-KURULUSLARI-MUHASEBESI": "https://www.tkbb.org.tr/upload/FAIZSIZ-FINANS-KURULUSLARI-MUHASEBESI.pdf",
    "Faizsiz Finans Standartları AAOIFI (Güncellenmiş Versiyon)": "https://tkbb.org.tr/faaliyetler/yayinlar/kitap-yayinlari",
    "Katilim_Finans_Urunleri_ve_Muhasebe_Surecleri_2": "https://tkbb.org.tr/faaliyetler/yayinlar/kitap-yayinlari",
    "8803561630-2025-faaliyet-raporu": "https://www.tkbb.org.tr/faaliyetler/yayinlar/yillik-sektor-raporlari",
}


def extract_pdf_evidence(
    path: Path,
    *,
    topics: Iterable[str] | None = None,
    max_pages: int | None = None,
) -> list[dict[str, Any]]:
    wanted = set(topics or TOPICS)
    rows: list[dict[str, Any]] = []
    reader = PdfReader(str(path))
    pages = reader.pages if max_pages is None or max_pages <= 0 else reader.pages[:max_pages]
    for page_number, page in enumerate(pages, start=1):
        text = re.sub(r"\s+", " ", page.extract_text() or "").strip()
        if not text:
            continue
        for topic in wanted:
            needles = TOPICS.get(topic, (topic,))
            if not any(needle.casefold() in text.casefold() for needle in needles):
                continue
            quote = text[:1200].strip()
            rows.append({
                "document_id": path.stem,
                "page": page_number,
                "topic": topic,
                "quote": quote,
                "quote_hash": sha256(quote.encode("utf-8")).hexdigest(),
                "local_path": str(path),
                    "source_url": SOURCE_URLS.get(path.stem, ""),
            })
    unique: dict[tuple[str, int, str], dict[str, Any]] = {}
    for row in rows:
        unique[(row["document_id"], row["page"], row["quote_hash"])] = row
    return list(unique.values())


def pdf_evidence_documents(rows_path: Path) -> list[tuple[str, str, dict[str, Any]]]:
    import json
    documents = []
    for line in rows_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        metadata = {
            "source_type": "pdf_evidence",
            "document_id": row["document_id"],
            "page": int(row["page"]),
            "topic": row["topic"],
            "quote_hash": row["quote_hash"],
            "source_url": row.get("source_url", ""),
            "local_path": row.get("local_path", ""),
        }
        identifier = f"pdf:{row['document_id']}:{row['page']}:{row['quote_hash'][:12]}"
        documents.append((identifier, row["quote"], metadata))
    return documents
