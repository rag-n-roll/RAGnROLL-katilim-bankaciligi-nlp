"""Doğrulanmış PDF kaynak manifestosu."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
from pypdf import PdfReader

from src.ingestion.pdf_registry import PdfSourceRegistry


def _page_count(path: Path) -> int:
    return len(PdfReader(str(path)).pages)


def build_pdf_manifest(
    paths: list[Path], *, registry: PdfSourceRegistry
) -> list[dict]:
    result = []
    for path in paths:
        source = registry.verify(path)
        result.append({
            "document_id": source.document_id,
            "filename": source.filename,
            "sha256": source.sha256,
            "page_count": _page_count(source.path),
            "title": source.title,
            "publisher": source.publisher,
            "source_url": source.source_url,
            "source_kind": "user_supplied_pdf",
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        })
    return result
