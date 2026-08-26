"""Doğrulanmış PDF'lerden tam, deterministik RAG parçaları üretir."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Callable, Protocol
import unicodedata

from src.ingestion.pdf_registry import VerifiedPdfSource


TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("fon_havuzu", ("fon havuzu", "kâr payı havuzu", "kar payı havuzu", "katılma hesabı")),
    ("kar_paylasim", ("kâr paylaşım", "kar paylaşım", "kâr/zarar", "kar/zarar")),
    ("kar_dagitim", ("kâr dağıt", "kar dağıt", "birim değer", "hesap değeri")),
    ("muhasebe", ("muhasebe", "yevmiye", "hesap planı", "finansal rapor")),
    ("urun_sureci", ("murabaha", "müşareke", "mudârebe", "mudarebe", "finansal kiralama")),
)


@dataclass(frozen=True)
class PdfPage:
    number: int
    text: str
    error: str | None = None


@dataclass(frozen=True)
class PdfExtractionResult:
    chunks: list[dict[str, Any]]
    report: dict[str, Any]


class PageExtractor(Protocol):
    def extract_all(self, path: Path, *, max_pages: int | None = None) -> list[PdfPage]: ...


class PyMuPdfExtractor:
    """PyMuPDF ile her sayfayı ayrı hata kaydıyla çıkarır."""

    def extract_all(self, path: Path, *, max_pages: int | None = None) -> list[PdfPage]:
        import pymupdf

        pages: list[PdfPage] = []
        with pymupdf.open(path) as document:
            page_count = len(document)
            limit = page_count if max_pages is None or max_pages <= 0 else min(max_pages, page_count)
            for index in range(limit):
                try:
                    pages.append(PdfPage(number=index + 1, text=document[index].get_text("text")))
                except Exception as exc:
                    pages.append(
                        PdfPage(
                            number=index + 1,
                            text="",
                            error=f"{type(exc).__name__}: {str(exc)[:240]}",
                        )
                    )
        return pages


class RapidOcrFallback:
    """Bozuk font haritalı sayfaları yerel ONNX OCR ile kurtarır."""

    def __init__(self, *, scale: float = 1.5, minimum_confidence: float = 0.45) -> None:
        self.scale = scale
        self.minimum_confidence = minimum_confidence
        self._engine = None

    def __call__(self, path: Path, page_number: int) -> str:
        import numpy as np
        import pymupdf
        from rapidocr_onnxruntime import RapidOCR

        if self._engine is None:
            self._engine = RapidOCR()
        with pymupdf.open(path) as document:
            page = document[page_number - 1]
            pixmap = page.get_pixmap(
                matrix=pymupdf.Matrix(self.scale, self.scale),
                colorspace=pymupdf.csRGB,
                alpha=False,
            )
        image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
            pixmap.height, pixmap.width, pixmap.n
        )
        result, _ = self._engine(image)
        if not result:
            return ""
        return "\n".join(
            str(item[1]).strip()
            for item in result
            if len(item) >= 3
            and float(item[2]) >= self.minimum_confidence
            and str(item[1]).strip()
        )


def _line_key(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _repeated_margin_lines(pages: list[PdfPage]) -> set[str]:
    counts: Counter[str] = Counter()
    text_pages = 0
    for page in pages:
        lines = [line for line in page.text.splitlines() if line.strip()]
        if not lines:
            continue
        text_pages += 1
        margins = {
            _line_key(line)
            for line in [*lines[:2], *lines[-2:]]
            if len(_line_key(line)) >= 4
        }
        counts.update(margins)
    threshold = max(3, int(text_pages * 0.35))
    return {line for line, count in counts.items() if count >= threshold}


def _clean_page(text: str, *, repeated_lines: set[str]) -> str:
    # PDF fontları satır sonundaki isteğe bağlı heceleme işaretini görünmez
    # U+00AD olarak bırakabilir. Önce bu özel satır bölünmesini birleştir.
    text = re.sub("\u00ad[ \t]*\n[ \t]*", "", text)
    text = "".join(
        character
        if character in "\r\n\t"
        or not unicodedata.category(character).startswith("C")
        else ""
        if unicodedata.category(character) == "Cf"
        else " "
        for character in text
    )
    kept = [
        line.rstrip()
        for line in text.replace("\r", "").split("\n")
        if _line_key(line) not in repeated_lines
    ]
    joined = "\n".join(kept)
    joined = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", joined)
    joined = re.sub(r"[ \t]+", " ", joined)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()


def _control_character_ratio(text: str) -> float:
    if not text:
        return 0.0
    controls = sum(
        unicodedata.category(char).startswith("C")
        for char in text
        if char not in "\r\n\t"
    )
    return controls / len(text)


def _is_table_of_contents(text: str) -> bool:
    head = text[:500].casefold()
    dotted_lines = len(re.findall(r"\.{5,}\s*\d+", text))
    return ("içindekiler" in head or "contents" in head) and dotted_lines >= 3


def _semantic_windows(text: str, *, max_tokens: int, overlap_tokens: int) -> list[str]:
    if max_tokens < 32:
        raise ValueError("max_tokens en az 32 olmalıdır")
    if not 0 <= overlap_tokens < max_tokens:
        raise ValueError("overlap_tokens max_tokens değerinden küçük olmalıdır")
    words = list(re.finditer(r"\S+", text))
    if not words:
        return []
    windows: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_tokens, len(words))
        if end < len(words):
            minimum = min(end, start + max(24, int(max_tokens * 0.65)))
            for candidate in range(end, minimum, -1):
                if re.search(r"[.!?:;][\"')\]]?$", words[candidate - 1].group(0)):
                    end = candidate
                    break
        chunk = text[words[start].start() : words[end - 1].end()].strip()
        if chunk:
            windows.append(chunk)
        if end >= len(words):
            break
        next_start = end - overlap_tokens
        start = next_start if next_start > start else end
    return windows


def _topics(text: str) -> list[str]:
    normalized = text.casefold()
    return [
        topic
        for topic, needles in TOPIC_RULES
        if any(needle in normalized for needle in needles)
    ]


def _chunk_id(source_hash: str, page_start: int, page_end: int, text: str) -> str:
    payload = f"{source_hash}:{page_start}:{page_end}:{text}".encode("utf-8")
    return "pdf:" + sha256(payload).hexdigest()


def extract_pdf_document(
    source: VerifiedPdfSource,
    *,
    extractor: PageExtractor | None = None,
    max_tokens: int = 450,
    overlap_tokens: int = 50,
    max_pages: int | None = None,
    ocr_fallback: Callable[[Path, int], str] | None = None,
) -> PdfExtractionResult:
    selected = extractor or PyMuPdfExtractor()
    pages = selected.extract_all(source.path, max_pages=max_pages)
    repeated_lines = _repeated_margin_lines(pages)
    chunks: list[dict[str, Any]] = []
    failed_pages: list[dict[str, Any]] = []
    extracted = 0
    empty = 0
    low_quality = 0
    ocr_recovered = 0
    skipped_toc = 0

    for page in pages:
        if page.error:
            failed_pages.append({"page": page.number, "reason": page.error})
            continue
        page_text = page.text
        if _control_character_ratio(page_text) > 0.02:
            recovered = ""
            if ocr_fallback is not None:
                try:
                    recovered = ocr_fallback(source.path, page.number)
                except Exception:
                    recovered = ""
            if not recovered or _control_character_ratio(recovered) > 0.02:
                low_quality += 1
                continue
            page_text = recovered
            ocr_recovered += 1
        cleaned = _clean_page(page_text, repeated_lines=repeated_lines)
        if not cleaned:
            empty += 1
            continue
        extracted += 1
        if _is_table_of_contents(cleaned):
            skipped_toc += 1
            continue
        for chunk_index, text in enumerate(
            _semantic_windows(
                cleaned, max_tokens=max_tokens, overlap_tokens=overlap_tokens
            )
        ):
            quote_hash = sha256(text.encode("utf-8")).hexdigest()
            chunks.append(
                {
                    "chunk_id": _chunk_id(
                        source.sha256, page.number, page.number, text
                    ),
                    "document_id": source.document_id,
                    "document_sha256": source.sha256,
                    "title": source.title,
                    "publisher": source.publisher,
                    "page_start": page.number,
                    "page_end": page.number,
                    "chunk_index": chunk_index,
                    "text": text,
                    "quote_hash": quote_hash,
                    "topics": _topics(text),
                    "source_url": source.source_url,
                }
            )

    report = {
        "document_id": source.document_id,
        "page_count": len(pages),
        "attempted": len(pages),
        "extracted": extracted,
        "empty": empty,
        "low_quality": low_quality,
        "ocr_recovered": ocr_recovered,
        "failed": len(failed_pages),
        "skipped_toc": skipped_toc,
        "chunk_count": len(chunks),
        "character_count": sum(len(item["text"]) for item in chunks),
        "failed_pages": failed_pages,
    }
    return PdfExtractionResult(chunks=chunks, report=report)
