"""Kampanya ve terminoloji kayıtlarını kararlı, aranabilir parçalara dönüştürür."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from src.nlp_runtime.advisory import SUGGESTION_ALLOWLIST
from src.nlp_runtime.integrity import REQUIRED_RUNTIME_PROVENANCE, RUNTIME_CONTRACT


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_SCHEMA = "semantic-sections-1"
DEFAULT_CHUNK_WORDS = 320
DEFAULT_CHUNK_OVERLAP_WORDS = 40

IndexDocument = tuple[str, str, dict[str, Any]]
RETRIEVAL_ENTITY_ALLOWLIST = frozenset(
    {
        "BANKA",
        "HEDEF_KITLE",
        "KAMPANYA_AVANTAJI",
        "KAMPANYA_TARIHI",
        "PROMOSYON_KODU",
        "URUN_TURU",
    }
)


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


def _evidence_matches(text: str, evidence: Any) -> bool:
    if not isinstance(evidence, dict):
        return False
    start = evidence.get("char_start")
    end = evidence.get("char_end")
    value = evidence.get("text")
    return (
        isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(end, int)
        and not isinstance(end, bool)
        and isinstance(value, str)
        and start >= 0
        and end > start
        and text[start:end] == value
    )


def _render_advisory_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def _advisory_lines(record: dict[str, Any], content: str) -> list[str]:
    analysis = record.get("nlp_analysis")
    if (
        not isinstance(analysis, dict)
        or analysis.get("contract") != RUNTIME_CONTRACT
        or analysis.get("provenance") != REQUIRED_RUNTIME_PROVENANCE
    ):
        return []
    analyzed_text = "\n".join(
        part for part in (str(record.get("title") or "").strip(), content) if part
    )
    nested_record = analysis.get("record")
    if not isinstance(nested_record, dict):
        return []
    source_hash = nested_record.get("source_content_hash")
    current_hash = record.get("content_hash")
    if (
        not isinstance(source_hash, str)
        or not source_hash
        or not isinstance(current_hash, str)
        or not current_hash
        or source_hash != current_hash
    ):
        return []
    source_version = nested_record.get("source_version")
    current_version = record.get("source_version")
    if (
        isinstance(source_version, bool)
        or not isinstance(source_version, int)
        or isinstance(current_version, bool)
        or not isinstance(current_version, int)
        or source_version != current_version
    ):
        return []
    if nested_record.get("text_sha256") != sha256(analyzed_text.encode("utf-8")).hexdigest():
        return []
    lines = []
    suggestions = analysis.get("suggestions")
    if isinstance(suggestions, dict):
        for field, suggestion in sorted(suggestions.items()):
            if (
                field not in SUGGESTION_ALLOWLIST
                or not isinstance(suggestion, dict)
                or suggestion.get("advisory") is not True
                or suggestion.get("value") is None
            ):
                continue
            evidence = suggestion.get("evidence")
            if not _evidence_matches(analyzed_text, evidence):
                continue
            lines.append(
                "Alan önerisi "
                f"{field}: {_render_advisory_value(suggestion.get('value'))}; "
                f"kanıt: {evidence['text']}"
            )
    classification = analysis.get("classification")
    if isinstance(classification, dict):
        product = classification.get("product_category")
        if isinstance(product, dict) and _evidence_matches(
            analyzed_text, product.get("evidence")
        ):
            lines.append(
                "Sınıflandırma sinyali product_category: "
                f"{product.get('value')}; kanıt: {product['evidence']['text']}"
            )
        dimensions = classification.get("dimensions")
        if isinstance(dimensions, dict):
            for dimension, values in sorted(dimensions.items()):
                if not isinstance(values, list):
                    continue
                for value in values:
                    if not isinstance(value, dict) or not _evidence_matches(
                        analyzed_text, value.get("evidence")
                    ):
                        continue
                    lines.append(
                        f"Sınıflandırma sinyali {dimension}: {value.get('value')}; "
                        f"kanıt: {value['evidence']['text']}"
                    )
    entities = analysis.get("entities")
    if isinstance(entities, list):
        for entity in entities:
            if (
                not isinstance(entity, dict)
                or entity.get("label") not in RETRIEVAL_ENTITY_ALLOWLIST
            ):
                continue
            evidence = {
                "text": entity.get("text"),
                "char_start": entity.get("start"),
                "char_end": entity.get("end"),
            }
            if not _evidence_matches(analyzed_text, evidence):
                continue
            lines.append(
                f"NER sinyali {entity.get('label')}: {entity.get('text')}; "
                f"kanıt: {entity.get('text')}"
            )
    return list(dict.fromkeys(lines))


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
    advisory_lines = _advisory_lines(record, content)
    advisory_text = "\n".join(advisory_lines)
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
    if advisory_text:
        combined_parts.append(
            "NLP danışmanlık sinyalleri (otoriter filtre değildir):\n" + advisory_text
        )
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
    if field_text or advisory_text:
        text = "\n".join(
            part
            for part in (
                header,
                "Yapılandırılmış alanlar: " + field_text if field_text else "",
                (
                    "NLP danışmanlık sinyalleri (otoriter filtre değildir):\n"
                    + advisory_text
                    if advisory_text
                    else ""
                ),
            )
            if part
        )
        metadata = _metadata_with_hash(
            text,
            {
                **base_metadata,
                "section": "structured_fields" if field_text else "nlp_advisory",
                "chunk_index": 0,
                "char_start": -1,
                "char_end": -1,
            },
        )
        suffix = "structured" if field_text else "nlp-advisory"
        documents.append((f"campaign:{identifier}:{suffix}:000", text, metadata))
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
