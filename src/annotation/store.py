"""Validated, atomic storage operations for the campaign annotation UI."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.annotation.taxonomy import (
    BENEFITS,
    CAMPAIGN_MECHANICS,
    CHANNELS,
    PRODUCT_CATEGORIES,
    REQUIREMENTS,
    TARGET_SEGMENTS,
)

SPLITS = ("train", "validation", "test")
ANNOTATION_FIELDS = {
    "campaign_mechanics": set(CAMPAIGN_MECHANICS),
    "target_segments": set(TARGET_SEGMENTS),
    "channels": set(CHANNELS),
    "benefits": set(BENEFITS),
    "requirements": set(REQUIREMENTS),
}


class ConcurrentUpdateError(RuntimeError):
    """Raised when the annotation file changed after it was loaded."""


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def load_records(path: str | Path) -> tuple[list[dict[str, Any]], str]:
    source = Path(path)
    content = source.read_bytes()
    records = []
    seen_ids: set[str] = set()
    for line_number, raw_line in enumerate(content.decode("utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        record = json.loads(raw_line)
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"Line {line_number}: record id must be non-empty")
        if record_id in seen_ids:
            raise ValueError(f"Line {line_number}: duplicate id {record_id!r}")
        seen_ids.add(record_id)
        records.append(record)
    if not records:
        raise ValueError("Annotation file is empty")
    return records, _digest(content)


def save_records(
    path: str | Path,
    records: list[dict[str, Any]],
    *,
    expected_digest: str | None = None,
) -> str:
    destination = Path(path)
    if expected_digest is not None and destination.exists():
        current_digest = _digest(destination.read_bytes())
        if current_digest != expected_digest:
            raise ConcurrentUpdateError(
                "Annotation file changed. Reload before saving to avoid overwriting a teammate."
            )
    destination.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(
        json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n" for record in records
    ).encode("utf-8")
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
    except BaseException:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
        raise
    return _digest(rendered)


def _find(records: list[dict[str, Any]], record_id: str) -> dict[str, Any]:
    for record in records:
        if record.get("id") == record_id:
            return record
    raise KeyError(f"Unknown annotation record: {record_id}")


def _event(action: str, user: str, **extra: Any) -> dict[str, Any]:
    return {
        "action": action,
        "user": user,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **extra,
    }


def submit_annotation(
    records: list[dict[str, Any]],
    record_id: str,
    *,
    annotator: str,
    annotations: dict[str, Any],
    split: str,
) -> dict[str, Any]:
    annotator = annotator.strip()
    if not annotator:
        raise ValueError("Annotator name is required")
    validate_annotations(annotations)
    if split not in SPLITS:
        raise ValueError(f"Unknown split: {split}")
    record = _find(records, record_id)
    previous = {
        "annotations": record.get("annotations"),
        "split": record.get("split"),
    }
    record.update(
        {
            "annotations": annotations,
            "split": split,
            "annotator": annotator,
            "reviewer": None,
            "review_status": "awaiting_review",
            "human_verified": False,
        }
    )
    record.setdefault("annotation_history", []).append(
        _event(
            "annotated",
            annotator,
            previous=previous,
            annotations=annotations,
            split=split,
        )
    )
    return record


def approve_annotation(
    records: list[dict[str, Any]], record_id: str, *, reviewer: str
) -> dict[str, Any]:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("Reviewer name is required")
    record = _find(records, record_id)
    if not record.get("annotator"):
        raise ValueError("Record must be annotated before review")
    if reviewer.casefold() == str(record["annotator"]).casefold():
        raise ValueError("Reviewer must be different from annotator")
    annotations = record.get("annotations")
    validate_annotations(annotations)
    if annotations.get("product_category") == "needs_review":
        raise ValueError("needs_review must be resolved before approval")
    if record.get("split") not in SPLITS:
        raise ValueError("A valid split is required before approval")
    record.update(
        {
            "reviewer": reviewer,
            "review_status": "approved",
            "human_verified": True,
        }
    )
    record.setdefault("annotation_history", []).append(_event("approved", reviewer))
    return record


def reject_annotation(
    records: list[dict[str, Any]], record_id: str, *, reviewer: str, note: str
) -> dict[str, Any]:
    reviewer = reviewer.strip()
    note = note.strip()
    if not reviewer or not note:
        raise ValueError("Reviewer and rejection note are required")
    record = _find(records, record_id)
    if reviewer.casefold() == str(record.get("annotator", "")).casefold():
        raise ValueError("Reviewer must be different from annotator")
    record.update(
        {
            "reviewer": reviewer,
            "review_status": "changes_requested",
            "human_verified": False,
        }
    )
    record.setdefault("annotation_history", []).append(
        _event("changes_requested", reviewer, note=note)
    )
    return record


def dataset_progress(records: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(record.get("review_status", "pending") for record in records)
    products = Counter(
        record.get("annotations", {}).get("product_category", "missing")
        for record in records
    )
    splits = Counter(
        record.get("split") or "unassigned"
        for record in records
        if record.get("human_verified") is True
    )
    verified = sum(record.get("human_verified") is True for record in records)
    return {
        "total": len(records),
        "verified": verified,
        "verified_percent": verified / len(records) if records else 0.0,
        "statuses": dict(statuses),
        "product_categories": dict(products),
        "verified_splits": dict(splits),
    }


def validate_annotations(annotations: Any) -> None:
    if not isinstance(annotations, dict):
        raise ValueError("annotations must be an object")
    product = annotations.get("product_category")
    if product not in PRODUCT_CATEGORIES:
        raise ValueError(f"Unknown product category: {product}")
    for field, allowed in ANNOTATION_FIELDS.items():
        values = annotations.get(field)
        if not isinstance(values, list):
            raise ValueError(f"{field} must be a list")
        if len(values) != len(set(values)):
            raise ValueError(f"{field} contains duplicate values")
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Unknown {field}: {sorted(unknown)}")
