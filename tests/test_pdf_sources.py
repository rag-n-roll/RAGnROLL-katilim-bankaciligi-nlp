import json
from pathlib import Path

from src.retrieval.documents import pdf_evidence_documents


def test_pdf_evidence_documents_preserves_page_provenance(tmp_path: Path):
    source = tmp_path / "evidence.jsonl"
    source.write_text(
        json.dumps(
            {
                "document_id": "guide",
                "page": 12,
                "topic": "fon_havuzu",
                "quote": "Katılma hesaplarından oluşan fon havuzu.",
                "quote_hash": "abc123",
                "source_url": "https://example.test/guide.pdf",
                "local_path": "C:/docs/guide.pdf",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    documents = pdf_evidence_documents(source)

    assert len(documents) == 1
    identifier, text, metadata = documents[0]
    assert identifier == "pdf:guide:12:abc123"
    assert text.startswith("Katılma")
    assert metadata["source_type"] == "pdf_evidence"
    assert metadata["document_id"] == "guide"
    assert metadata["page"] == 12
    assert metadata["index_hash"]


def test_pdf_evidence_documents_missing_file_is_optional(tmp_path: Path):
    assert pdf_evidence_documents(tmp_path / "missing.jsonl") == []
