"""Align classifier and NER datasets to one campaign-level split policy.

The classifier split is treated as the canonical split because it is already
multilabel-stratified. Every NER record referring to the same campaign receives
that split. Synthetic records are allowed only in train.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


VALID_SPLITS = {"train", "validation", "test"}


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _record_source_id(row: dict[str, Any]) -> str:
    metadata = row.get("metadata") or {}
    return str(metadata.get("source_id") or row.get("source_id") or row["id"])


def _fallback_split(record_id: str) -> str:
    """Assign records absent from the classifier set deterministically."""
    bucket = int(hashlib.sha256(record_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "validation"
    return "test"


def _is_synthetic(row: dict[str, Any]) -> bool:
    metadata = row.get("metadata") or {}
    return bool(metadata.get("synthetic")) or str(row.get("id", "")).startswith("synthetic-")


def create_unified_splits(
    classifier_input: str | Path,
    ner_input: str | Path,
    classifier_output: str | Path,
    ner_output: str | Path,
    manifest_output: str | Path,
) -> dict[str, Any]:
    classifier_rows = _read_jsonl(classifier_input)
    ner_rows = _read_jsonl(ner_input)

    canonical: dict[str, str] = {}
    for row in classifier_rows:
        if _is_synthetic(row):
            continue
        split = str(row.get("split"))
        if split not in VALID_SPLITS:
            raise ValueError(f"Invalid classifier split for {row.get('id')}: {split}")
        record_id = str(row["id"])
        previous = canonical.setdefault(record_id, split)
        if previous != split:
            raise ValueError(f"Campaign {record_id} occurs in multiple classifier splits")

    realigned_ner = 0
    missing_from_classifier = 0
    for row in classifier_rows:
        source_id = _record_source_id(row)
        row["split"] = "train" if _is_synthetic(row) else canonical[str(row["id"])]
        if _is_synthetic(row) and canonical.get(source_id) not in (None, "train"):
            raise ValueError(f"Synthetic classifier row derives from held-out campaign {source_id}")

    for row in ner_rows:
        if _is_synthetic(row):
            row["split"] = "train"
            continue
        record_id = str(row["id"])
        split = canonical.get(record_id)
        if split is None:
            split = _fallback_split(record_id)
            missing_from_classifier += 1
        if row.get("split") != split:
            realigned_ner += 1
        row["split"] = split

    classifier_real = {
        str(row["id"]): row["split"]
        for row in classifier_rows
        if not _is_synthetic(row)
    }
    ner_real = {str(row["id"]): row["split"] for row in ner_rows if not _is_synthetic(row)}
    shared = set(classifier_real) & set(ner_real)
    mismatches = [
        record_id
        for record_id in shared
        if classifier_real[record_id] != ner_real[record_id]
    ]
    if mismatches:
        raise AssertionError(f"Unified split invariant failed for {len(mismatches)} campaigns")

    _write_jsonl(classifier_output, classifier_rows)
    _write_jsonl(ner_output, ner_rows)
    report = {
        "policy": "classifier_multilabel_split_is_canonical; synthetic_train_only",
        "classifier_input": str(classifier_input),
        "ner_input": str(ner_input),
        "classifier_output": str(classifier_output),
        "ner_output": str(ner_output),
        "classifier_splits": dict(Counter(str(row["split"]) for row in classifier_rows)),
        "ner_splits": dict(Counter(str(row["split"]) for row in ner_rows)),
        "classifier_synthetic": sum(_is_synthetic(row) for row in classifier_rows),
        "ner_synthetic": sum(_is_synthetic(row) for row in ner_rows),
        "shared_real_campaigns": len(shared),
        "cross_task_split_mismatches": len(mismatches),
        "realigned_ner_records": realigned_ner,
        "ner_records_missing_from_classifier": missing_from_classifier,
    }
    manifest = Path(manifest_output)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classifier-input", required=True)
    parser.add_argument("--ner-input", required=True)
    parser.add_argument("--classifier-output", required=True)
    parser.add_argument("--ner-output", required=True)
    parser.add_argument("--manifest-output", required=True)
    args = parser.parse_args()
    report = create_unified_splits(
        args.classifier_input,
        args.ner_input,
        args.classifier_output,
        args.ner_output,
        args.manifest_output,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
