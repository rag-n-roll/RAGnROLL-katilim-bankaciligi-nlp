from hashlib import sha256
import json
from pathlib import Path

import pytest

from src.ingestion.pdf_registry import PdfSourceIntegrityError, PdfSourceRegistry
from src.ingestion.pdf_sources import build_pdf_manifest


def _registry(content: bytes) -> PdfSourceRegistry:
    return PdfSourceRegistry.from_items(
        [
            {
                "document_id": "guide",
                "filenames": ["guide.pdf"],
                "sha256": sha256(content).hexdigest(),
                "title": "Katılım Finans Rehberi",
                "source_url": "https://example.test/guide.pdf",
                "publisher": "Örnek Yayıncı",
            }
        ]
    )


def test_registry_accepts_only_expected_pdf_hash(tmp_path: Path):
    source = tmp_path / "guide.pdf"
    source.write_bytes(b"verified")
    registry = _registry(b"verified")

    verified = registry.verify(source)

    assert verified.document_id == "guide"
    assert verified.title == "Katılım Finans Rehberi"
    source.write_bytes(b"tampered")
    with pytest.raises(PdfSourceIntegrityError, match="doğrulanamadı"):
        registry.verify(source)


def test_registry_rejects_unregistered_filename(tmp_path: Path):
    source = tmp_path / "renamed.pdf"
    source.write_bytes(b"verified")

    with pytest.raises(PdfSourceIntegrityError, match="kayıtlı değil"):
        _registry(b"verified").verify(source)


def test_registry_allows_unicode_aliases_that_normalize_to_same_filename():
    registry = PdfSourceRegistry.from_items(
        [
            {
                "document_id": "aaoifi",
                "filenames": ["Güncellenmiş.pdf", "Güncellenmiş.pdf"],
                "sha256": "a" * 64,
                "title": "AAOIFI",
                "source_url": "https://example.test/aaoifi.pdf",
                "publisher": "TKBB",
            }
        ]
    )

    assert registry is not None


def test_manifest_does_not_serialize_local_path(monkeypatch, tmp_path: Path):
    source = tmp_path / "guide.pdf"
    source.write_bytes(b"verified")
    registry = _registry(b"verified")
    monkeypatch.setattr("src.ingestion.pdf_sources._page_count", lambda _: 3)

    manifest = build_pdf_manifest([source], registry=registry)
    serialized = json.dumps(manifest, ensure_ascii=False)

    assert manifest[0]["page_count"] == 3
    assert "path" not in manifest[0]
    assert str(tmp_path) not in serialized
