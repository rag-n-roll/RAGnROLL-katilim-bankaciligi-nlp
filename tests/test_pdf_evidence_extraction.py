from pathlib import Path

from src.ingestion.pdf_evidence import PdfPage, extract_pdf_document
from src.ingestion.pdf_registry import VerifiedPdfSource


class FakeExtractor:
    def __init__(self, pages: list[PdfPage]) -> None:
        self.pages = pages

    def extract_all(self, _: Path, *, max_pages: int | None = None) -> list[PdfPage]:
        return self.pages if max_pages is None else self.pages[:max_pages]


def _source() -> VerifiedPdfSource:
    return VerifiedPdfSource(
        document_id="guide",
        title="Katılım Finans Rehberi",
        sha256="a" * 64,
        source_url="https://example.test/guide.pdf",
        publisher="Örnek Yayıncı",
        filename="guide.pdf",
        path=Path("guide.pdf"),
    )


def test_topic_is_detected_in_the_emitted_chunk_context():
    extractor = FakeExtractor(
        [
            PdfPage(
                number=1,
                text=(
                    "Katılım Finans Rehberi\n"
                    "Kâr payı havuzu katılma hesaplarından toplanan fonların "
                    "katılım finans ilkelerine uygun işlemlerde değerlendirilmesini sağlar.\n"
                    "1"
                ),
            )
        ]
    )

    result = extract_pdf_document(_source(), extractor=extractor, max_tokens=64)

    chunk = next(item for item in result.chunks if "fon_havuzu" in item["topics"])
    assert "kâr payı havuzu" in chunk["text"].casefold()
    assert chunk["page_start"] == 1
    assert chunk["page_end"] == 1
    assert "local_path" not in chunk


def test_extraction_is_deterministic_and_topic_order_is_stable():
    pages = [
        PdfPage(
            number=7,
            text="Katılma hesabı, kâr paylaşım oranı ve murabaha işlemi birlikte açıklanır.",
        )
    ]

    first = extract_pdf_document(_source(), extractor=FakeExtractor(pages))
    second = extract_pdf_document(_source(), extractor=FakeExtractor(pages))

    assert [item["chunk_id"] for item in first.chunks] == [
        item["chunk_id"] for item in second.chunks
    ]
    assert first.chunks[0]["topics"] == second.chunks[0]["topics"]


def test_every_page_is_accounted_for_in_report():
    pages = [
        PdfPage(number=1, text="Katılım finansında fonlar değerlendirilir."),
        PdfPage(number=2, text=""),
        PdfPage(number=3, text="", error="extract_timeout"),
    ]

    result = extract_pdf_document(_source(), extractor=FakeExtractor(pages))

    assert result.report["page_count"] == 3
    assert result.report["attempted"] == 3
    assert result.report["extracted"] == 1
    assert result.report["empty"] == 1
    assert result.report["failed"] == 1
    assert result.report["failed_pages"] == [
        {"page": 3, "reason": "extract_timeout"}
    ]


def test_non_topic_text_is_still_kept_for_full_corpus():
    result = extract_pdf_document(
        _source(),
        extractor=FakeExtractor(
            [PdfPage(number=9, text="Denetim komitesi toplantı esasları açıklanmıştır.")]
        ),
    )

    assert len(result.chunks) == 1
    assert result.chunks[0]["topics"] == []
