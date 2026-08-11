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


CAMPAIGN_LABELS = (
    "housing_finance",
    "vehicle_finance",
    "consumer_finance",
    "general_finance",
    "card_campaign",
    "shopping_points",
    "new_customer",
    "investment_product",
    "needs_review",
)
SPLITS = ("train", "validation", "test")


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
    label: str,
    split: str,
) -> dict[str, Any]:
    annotator = annotator.strip()
    if not annotator:
        raise ValueError("Annotator name is required")
    if label not in CAMPAIGN_LABELS:
        raise ValueError(f"Unknown label: {label}")
    if split not in SPLITS:
        raise ValueError(f"Unknown split: {split}")
    record = _find(records, record_id)
    previous = {"label": record.get("label"), "split": record.get("split")}
    record.update(
        {
            "label": label,
            "split": split,
            "annotator": annotator,
            "reviewer": None,
            "review_status": "awaiting_review",
            "human_verified": False,
        }
    )
    record.setdefault("annotation_history", []).append(
        _event("annotated", annotator, previous=previous, label=label, split=split)
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
    if record.get("label") == "needs_review":
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
    labels = Counter(record.get("label", "missing") for record in records)
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
        "labels": dict(labels),
        "verified_splits": dict(splits),
    }
