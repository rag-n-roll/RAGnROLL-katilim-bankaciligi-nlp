"""Üretilmiş PDF kanıt paketinin kapsam ve bütünlüğünü denetler."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any


class PdfPacketVerificationError(ValueError):
    pass


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PdfPacketVerificationError(f"PDF paket dosyası okunamadı: {path.name}") from exc


def verify_pdf_packet(
    *, manifest_path: Path, evidence_path: Path, report_path: Path
) -> dict[str, int]:
    manifest_payload = _read_json(manifest_path)
    report_payload = _read_json(report_path)
    if not isinstance(manifest_payload, list) or not isinstance(report_payload, dict):
        raise PdfPacketVerificationError("PDF paket şeması geçersiz")
    manifest = {
        str(item.get("document_id") or ""): item
        for item in manifest_payload
        if isinstance(item, dict)
    }
    reports = report_payload.get("documents")
    if not isinstance(reports, list) or len(reports) != len(manifest):
        raise PdfPacketVerificationError("PDF çıkarım raporu belge kapsamı eksik")
    for item in reports:
        document_id = str(item.get("document_id") or "")
        expected = manifest.get(document_id)
        if expected is None:
            raise PdfPacketVerificationError("PDF çıkarım raporunda bilinmeyen belge var")
        if (
            int(item.get("attempted") or 0) != int(expected.get("page_count") or 0)
            or item.get("complete") is not True
        ):
            raise PdfPacketVerificationError(
                f"PDF tam sayfa kapsamı sağlanmadı: {document_id}"
            )

    chunk_count = 0
    seen_ids: set[str] = set()
    for line_number, line in enumerate(
        evidence_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        row = json.loads(line)
        document_id = str(row.get("document_id") or "")
        expected = manifest.get(document_id)
        if expected is None:
            raise PdfPacketVerificationError(f"Bilinmeyen PDF belgesi: satır {line_number}")
        if row.get("document_sha256") != expected.get("sha256"):
            raise PdfPacketVerificationError(f"PDF belge hash uyuşmazlığı: satır {line_number}")
        text = str(row.get("text") or "")
        if row.get("quote_hash") != sha256(text.encode("utf-8")).hexdigest():
            raise PdfPacketVerificationError(f"PDF parça hash uyuşmazlığı: satır {line_number}")
        chunk_id = str(row.get("chunk_id") or "")
        if not chunk_id.startswith("pdf:") or chunk_id in seen_ids:
            raise PdfPacketVerificationError(f"PDF parça kimliği geçersiz: satır {line_number}")
        if "local_path" in row or "C:\\Users\\" in line:
            raise PdfPacketVerificationError(
                f"PDF paketinde yerel yol sızıntısı: satır {line_number}"
            )
        seen_ids.add(chunk_id)
        chunk_count += 1

    reported_chunks = int((report_payload.get("totals") or {}).get("chunks") or 0)
    if reported_chunks != chunk_count:
        raise PdfPacketVerificationError("PDF parça sayısı raporla uyuşmuyor")
    return {
        "documents": len(manifest),
        "pages": sum(int(item.get("page_count") or 0) for item in manifest.values()),
        "chunks": chunk_count,
    }
