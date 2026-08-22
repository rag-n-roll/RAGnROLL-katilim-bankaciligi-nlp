"""Kampanya ve terminoloji kayıtlarını kararlı, aranabilir parçalara dönüştürür."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_SCHEMA = "semantic-sections-1"
DEFAULT_CHUNK_WORDS = 320
DEFAULT_CHUNK_OVERLAP_WORDS = 40

IndexDocument = tuple[str, str, dict[str, Any]]


def _digest(*values: Any) -> str:
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode("utf-8")).hexdigest()


def _field_lines(structured: dict[str, Any]) -> list[str]:
    fields = structured.get("fields") if isinstance(structured, dict) else {}
    if not isinstance(fields, dict):
        return []
    lines = []
    for name, contract in sorted(fields.items()):
        if not isinstance(contract, dict) or contract.get("value") is None:
            continue
        unit = f" {contract.get('unit')}" if contract.get("unit") else ""
        lines.append(f"{name}: {contract['value']}{unit}")
    return lines


def _word_windows(
    text: str,
    *,
    max_words: int,
    overlap_words: int,
) -> list[tuple[str, int, int]]:
    """Kelime sınırlarını korur; mümkünse pencereyi cümle sonunda kapatır."""

    if max_words < 32:
        raise ValueError("max_words en az 32 olmalıdır")
    if not 0 <= overlap_words < max_words:
        raise ValueError("overlap_words sıfır ile max_words arasında olmalıdır")
    matches = list(re.finditer(r"\S+", text))
    if not matches:
        return []
    windows: list[tuple[str, int, int]] = []
    start = 0
    while start < len(matches):
        end = min(start + max_words, len(matches))
        if end < len(matches):
            minimum_end = start + max(32, int(max_words * 0.7))
            for candidate in range(end, minimum_end, -1):
                if re.search(r"[.!?][\"')\]]?$", matches[candidate - 1].group(0)):
                    end = candidate
                    break
        char_start = matches[start].start()
        char_end = matches[end - 1].end()
        windows.append((text[char_start:char_end].strip(), char_start, char_end))
        if end == len(matches):
            break
        next_start = end - overlap_words
        start = next_start if next_start > start else end
    return windows


def _metadata_with_hash(text: str, metadata: dict[str, Any]) -> dict[str, Any]:
    stable = {key: value for key, value in metadata.items() if key != "index_hash"}
    return {**stable, "index_hash": _digest(INDEX_SCHEMA, text, stable)}


def campaign_documents(
    record: dict[str, Any],
    *,
    max_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_CHUNK_OVERLAP_WORDS,
) -> list[IndexDocument]:
    """Uzun kampanyaları kaynak konumu bilinen semantik pencerelere böler."""

    identifier = str(record.get("id") or "").strip()
    if not identifier:
        return []
    title = str(record.get("title") or "").strip()
    bank_name = str(record.get("bank_name") or "").strip()
    content = str(record.get("clean_text") or record.get("content") or "").strip()
    structured = (
        record.get("structured")
        if isinstance(record.get("structured"), dict)
        else {}
    )
    field_lines = _field_lines(structured)
    header = "\n".join(
        part
        for part in (
            f"Başlık: {title}" if title else "",
            f"Banka: {bank_name}" if bank_name else "",
        )
        if part
    )
    field_text = "; ".join(field_lines)
    base_metadata = {
        "source_type": "campaign",
        "campaign_id": identifier,
        "term_id": "",
        "bank_slug": str(record.get("bank_slug") or ""),
        "bank_name": bank_name,
        "product_type": str(structured.get("product_type") or ""),
        "financing_type": str(structured.get("financing_type") or ""),
        "title": title,
        "source_url": str(record.get("source_url") or ""),
        "scraped_at": str(record.get("scraped_at") or ""),
        "content_hash": str(record.get("content_hash") or _digest(title, content)),
        "index_schema": INDEX_SCHEMA,
    }
    combined_parts = [part for part in (header, content) if part]
    if field_text:
        combined_parts.append("Yapılandırılmış alanlar: " + field_text)
    combined = "\n".join(combined_parts)
    if len(re.findall(r"\S+", combined)) <= max_words:
        if not combined:
            return []
        metadata = _metadata_with_hash(
            combined,
            {
                **base_metadata,
                "section": "overview",
                "chunk_index": 0,
                "char_start": 0,
                "char_end": len(content),
            },
        )
        return [(f"campaign:{identifier}:overview:000", combined, metadata)]

    documents: list[IndexDocument] = []
    for index, (chunk, char_start, char_end) in enumerate(
        _word_windows(content, max_words=max_words, overlap_words=overlap_words)
    ):
        text = "\n".join(part for part in (header, f"İçerik: {chunk}") if part)
        metadata = _metadata_with_hash(
            text,
            {
                **base_metadata,
                "section": "content",
                "chunk_index": index,
                "char_start": char_start,
                "char_end": char_end,
            },
        )
        documents.append((f"campaign:{identifier}:content:{index:03d}", text, metadata))
    if field_text:
        text = "\n".join(
            part
            for part in (header, "Yapılandırılmış alanlar: " + field_text)
            if part
        )
        metadata = _metadata_with_hash(
            text,
            {
                **base_metadata,
                "section": "structured_fields",
                "chunk_index": 0,
                "char_start": -1,
                "char_end": -1,
            },
        )
        documents.append((f"campaign:{identifier}:structured:000", text, metadata))
    return documents


def terminology_documents(path: Path | None = None) -> list[IndexDocument]:
    """Ontoloji parçalarına içerik parmak izi ve kararlı metadata ekler."""

    source = path or PROJECT_ROOT / "data" / "ontology" / "rag_chunks.jsonl"
    documents: list[IndexDocument] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        nested = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        term_id = str(item.get("term_id") or nested.get("term_id") or "")
        chunk_id = str(item.get("chunk_id") or term_id)
        text = str(item.get("text") or "").strip()
        if not chunk_id or not text:
            continue
        content_hash = _digest(text, nested)
        metadata = _metadata_with_hash(
            text,
            {
                "source_type": "terminology",
                "campaign_id": "",
                "term_id": term_id,
                "bank_slug": "",
                "bank_name": "",
                "product_type": "",
                "financing_type": "",
                "title": str(item.get("title") or item.get("term") or ""),
                "source_url": str(nested.get("source_url") or ""),
                "scraped_at": "",
                "content_hash": content_hash,
                "index_schema": INDEX_SCHEMA,
                "section": "terminology",
                "chunk_index": 0,
                "char_start": 0,
                "char_end": len(text),
            },
        )
        documents.append((f"term:{chunk_id}", text, metadata))
    return documents
