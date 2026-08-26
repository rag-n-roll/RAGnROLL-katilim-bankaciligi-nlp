from hashlib import sha256
import json
from pathlib import Path

import pytest

from src.retrieval.documents import PdfEvidenceIntegrityError, pdf_evidence_documents


def _write_packet(tmp_path: Path, *, text: str, quote_hash: str | None = None):
    document_hash = "a" * 64
    evidence = tmp_path / "pdf_evidence.jsonl"
    evidence.write_text(
        json.dumps(
            {
                "chunk_id": "pdf:stable",
                "document_id": "guide",
                "document_sha256": document_hash,
                "page_start": 12,
                "page_end": 12,
                "chunk_index": 0,
                "title": "Katılım Finans Rehberi",
                "publisher": "TKBB",
                "topics": ["fon_havuzu"],
                "text": text,
                "quote_hash": quote_hash or sha256(text.encode("utf-8")).hexdigest(),
                "source_url": "https://example.test/guide.pdf",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "pdf_evidence.manifest.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "document_id": "guide",
                    "sha256": document_hash,
                    "title": "Katılım Finans Rehberi",
                    "publisher": "TKBB",
                    "source_url": "https://example.test/guide.pdf",
                    "page_count": 20,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return evidence, manifest


def test_pdf_evidence_documents_preserves_page_provenance(tmp_path: Path):
    evidence, manifest = _write_packet(
        tmp_path, text="Katılma hesaplarından oluşan fon havuzu."
    )

    documents = pdf_evidence_documents(evidence, manifest_path=manifest)

    assert len(documents) == 1
    identifier, text, metadata = documents[0]
    assert identifier == "pdf:stable"
    assert text.startswith("Katılma")
    assert metadata["source_type"] == "pdf_evidence"
    assert metadata["document_id"] == "guide"
    assert metadata["page_start"] == 12
    assert metadata["page_end"] == 12
    assert metadata["title"] == "Katılım Finans Rehberi"
    assert metadata["index_hash"]


def test_pdf_evidence_documents_links_topics_to_ontology_terms(tmp_path: Path):
    evidence, manifest = _write_packet(
        tmp_path, text="Katılma hesaplarından oluşan fon havuzu."
    )
    mapping = tmp_path / "pdf_topic_mapping.json"
    mapping.write_text(
        json.dumps({"fon_havuzu": ["TRM0452", "TRM0385"]}),
        encoding="utf-8",
    )

    documents = pdf_evidence_documents(
        evidence,
        manifest_path=manifest,
        topic_mapping_path=mapping,
    )

    assert documents[0][2]["ontology_term_ids"] == "TRM0452,TRM0385"


def test_pdf_evidence_documents_rejects_invalid_ontology_mapping(tmp_path: Path):
    evidence, manifest = _write_packet(tmp_path, text="Fon havuzu.")
    mapping = tmp_path / "pdf_topic_mapping.json"
    mapping.write_text(
        json.dumps({"fon_havuzu": ["not-a-term"]}),
        encoding="utf-8",
    )

    with pytest.raises(PdfEvidenceIntegrityError, match="ontoloji eşlemesi"):
        pdf_evidence_documents(
            evidence,
            manifest_path=manifest,
            topic_mapping_path=mapping,
        )


def test_pdf_loader_rejects_tampered_quote(tmp_path: Path):
    evidence, manifest = _write_packet(
        tmp_path, text="değiştirilmiş", quote_hash="0" * 64
    )

    with pytest.raises(PdfEvidenceIntegrityError, match="parça hash"):
        pdf_evidence_documents(evidence, manifest_path=manifest)


def test_pdf_loader_rejects_document_hash_not_in_manifest(tmp_path: Path):
    evidence, manifest = _write_packet(tmp_path, text="Geçerli parça")
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["document_sha256"] = "b" * 64
    evidence.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(PdfEvidenceIntegrityError, match="belge hash"):
        pdf_evidence_documents(evidence, manifest_path=manifest)


def test_pdf_evidence_documents_missing_file_is_optional(tmp_path: Path):
    assert pdf_evidence_documents(tmp_path / "missing.jsonl") == []
