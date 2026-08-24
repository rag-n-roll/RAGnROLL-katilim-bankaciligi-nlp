"""Exact ve near-duplicate kayıtlar için deterministik parmak izleri."""

from __future__ import annotations

from hashlib import sha256
import re
from typing import Any, Iterable
import unicodedata


TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def _canonical_text(value: str) -> str:
    return " ".join(
        TOKEN_RE.findall(unicodedata.normalize("NFC", str(value or "")).casefold())
    )


def content_hash(*parts: str) -> str:
    """Metinsel içeriği boşluk ve Unicode farklarından arındırarak hash'ler."""
    canonical = "\0".join(_canonical_text(part) for part in parts)
    return sha256(canonical.encode("utf-8")).hexdigest()


def simhash(value: str) -> str:
    """Yakın metinleri Hamming uzaklığıyla karşılaştırmak için 64 bit iz üretir."""
    tokens = TOKEN_RE.findall(_canonical_text(value))
    features = (
        tokens
        if len(tokens) < 3
        else [" ".join(tokens[i : i + 3]) for i in range(len(tokens) - 2)]
    )
    weights = [0] * 64
    for feature in features:
        hashed = int.from_bytes(sha256(feature.encode("utf-8")).digest()[:8], "big")
        for bit in range(64):
            weights[bit] += 1 if hashed & (1 << bit) else -1
    fingerprint = sum(1 << bit for bit, weight in enumerate(weights) if weight >= 0)
    return f"{fingerprint:016x}"


def hamming_distance(left: str, right: str) -> int:
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except (TypeError, ValueError):
        return 64


def cluster_near_duplicates(
    records: Iterable[dict[str, Any]], *, threshold: int = 6
) -> list[dict[str, Any]]:
    """Aynı bankadaki yakın kayıtları kararlı cluster kimlikleri altında toplar."""
    if not 0 <= threshold <= 64:
        raise ValueError("threshold 0 ile 64 arasında olmalıdır")
    rows = [dict(record) for record in records]
    fingerprints = [
        str(record.get("duplicate_fingerprint") or simhash(record.get("content", "")))
        for record in rows
    ]
    parents = list(range(len(rows)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[max(left_root, right_root)] = min(left_root, right_root)

    for left in range(len(rows)):
        for right in range(left + 1, len(rows)):
            if rows[left].get("bank_slug") != rows[right].get("bank_slug"):
                continue
            if hamming_distance(fingerprints[left], fingerprints[right]) <= threshold:
                union(left, right)

    members: dict[int, list[int]] = {}
    for index in range(len(rows)):
        members.setdefault(find(index), []).append(index)
    for indexes in members.values():
        hashes = [
            str(
                rows[index].get("content_hash")
                or content_hash(rows[index].get("title", ""), rows[index].get("content", ""))
            )
            for index in indexes
        ]
        bank_slug = str(rows[indexes[0]].get("bank_slug") or "")
        cluster_id = f"dup-{content_hash(bank_slug, min(hashes))[:16]}"
        for index in indexes:
            rows[index]["duplicate_fingerprint"] = fingerprints[index]
            rows[index]["duplicate_cluster_id"] = cluster_id
    return rows
