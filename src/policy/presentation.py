from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
import re
from typing import Any


def _source_value(source: dict[str, Any], key: str) -> Any:
    value = source.get(key)
    if value is not None and (not isinstance(value, str) or value.strip()):
        return value
    metadata = source.get("metadata")
    return metadata.get(key) if isinstance(metadata, dict) else None


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def stable_source_key(source: dict[str, Any]) -> str:
    """Return a stable evidence identity across raw and normalized source shapes."""
    for key in ("campaign_id", "term_id", "document_id"):
        value = str(_source_value(source, key) or "").strip()
        if value:
            return f"{key}:{value}"
    source_url = str(_source_value(source, "source_url") or "").strip()
    if source_url:
        return f"source_url:{source_url}"
    evidence = source.get("evidence")
    evidence_text = evidence.get("text") if isinstance(evidence, dict) else evidence
    if evidence_text in (None, ""):
        evidence_text = source.get("text")
    material = f"{_source_value(source, 'title') or ''}\n{evidence_text or ''}"
    return f"content:{sha256(material.encode('utf-8')).hexdigest()}"


def deduplicate_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the greatest-scoring source per stable identity in input-key order."""
    winners: dict[
        str, tuple[int, tuple[int, float], dict[str, Any]]
    ] = {}
    for index, source in enumerate(sources):
        key = stable_source_key(source)
        score = _finite(source.get("retrieval_score"))
        if score is None:
            score = _finite(source.get("score"))
        rank = (1, score) if score is not None else (0, 0.0)
        current = winners.get(key)
        if current is None or rank > current[1]:
            winners[key] = (current[0] if current else index, rank, source)
    deduplicated = []
    for _, rank, source in sorted(winners.values(), key=lambda item: item[0]):
        normalized = dict(source)
        normalized["retrieval_score"] = rank[1] if rank[0] else 0.0
        deduplicated.append(normalized)
    return deduplicated


@dataclass(frozen=True, slots=True)
class PresentedAnswer:
    answer_display: str
    sources: list[dict[str, Any]]


def present_answer(
    answer: str, *, sources: list[dict[str, Any]]
) -> PresentedAnswer:
    display = re.sub(r"\s*\[K\d+(?:\s*,\s*K?\d+)*\]", "", answer)
    display = re.sub(r"[ \t]+([.,;:!?])", r"\1", display).strip()
    return PresentedAnswer(display, deduplicate_sources(sources))
