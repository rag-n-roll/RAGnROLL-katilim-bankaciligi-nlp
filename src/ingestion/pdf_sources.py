"""PDF kaynak manifestosu."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from datetime import datetime, timezone
from pypdf import PdfReader


def build_pdf_manifest(paths: list[Path]) -> list[dict]:
    result = []
    for path in paths:
        if not path.is_file() or path.suffix.casefold() != ".pdf":
            raise ValueError(f"PDF bulunamadı: {path}")
        digest = sha256(path.read_bytes()).hexdigest()
        page_count = len(PdfReader(str(path)).pages)
        result.append({
            "document_id": path.stem,
            "filename": path.name,
            "path": str(path.resolve()),
            "sha256": digest,
            "page_count": page_count,
            "source_kind": "user_supplied_pdf",
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        })
    return result
