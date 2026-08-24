"""Create and validate classifier/NER splits at canonical source-family level."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.training.dataset_contract import (
    VALID_SPLITS,
    is_synthetic,
    read_jsonl,
    record_source_id,
    source_family_id,
    split_for_family,
    validate_source_family_splits,
)


def _write_jsonl(path: str | Path, rows: list[dict[str, Any]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _classifier_family_splits(
    rows: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    by_family: dict[str, str] = {}
    by_id: dict[str, str] = {}
    for row in rows:
        if is_synthetic(row):
            continue
        record_id = str(row.get("id") or "")
        split = str(row.get("split") or "")
        if split not in VALID_SPLITS:
            raise ValueError(f"Classifier record {record_id!r} has invalid split {split!r}")
        family_id = source_family_id(row)
        previous = by_family.setdefault(family_id, split)
        if previous != split:
            raise ValueError(
                f"Classifier source family {family_id} occurs in {previous} and {split}"
            )
        by_id[record_id] = split
    return by_family, by_id


def create_unified_splits(
    classifier_input: str | Path,
    ner_input: str | Path,
    classifier_output: str | Path,
    ner_output: str | Path,
    manifest_output: str | Path,
) -> dict[str, Any]:
    classifier_rows = read_jsonl(classifier_input)
    ner_rows = read_jsonl(ner_input)
    classifier_families, classifier_ids = _classifier_family_splits(classifier_rows)

    realigned_classifier = 0
    for row in classifier_rows:
        if not is_synthetic(row):
            continue
        source_id = record_source_id(row)
        if not source_id:
            raise ValueError(f"Synthetic classifier row {row.get('id')!r} has no source_id")
        if classifier_ids.get(source_id) not in (None, "train"):
            raise ValueError(
                f"Synthetic classifier row {row.get('id')!r} derives from held-out "
                f"record {source_id!r}"
            )
        if row.get("split") != "train":
            realigned_classifier += 1
        row["split"] = "train"

    realigned_ner = 0
    missing_classifier_families = 0
    for row in ner_rows:
        if is_synthetic(row):
            if not record_source_id(row):
                raise ValueError(f"Synthetic NER row {row.get('id')!r} has no source_id")
            split = "train"
        else:
            family_id = source_family_id(row)
            split = classifier_families.get(family_id)
            if split is None:
                split = split_for_family(family_id)
                missing_classifier_families += 1
        if row.get("split") != split:
            realigned_ner += 1
        row["split"] = split

    invariant = validate_source_family_splits(
        {"classifier": classifier_rows, "ner": ner_rows}
    )
    _write_jsonl(classifier_output, classifier_rows)
    _write_jsonl(ner_output, ner_rows)
    report = {
        "policy": "canonical_source_family; classifier_split_canonical; synthetic_train_only",
        "classifier_splits": dict(
            sorted(Counter(str(row["split"]) for row in classifier_rows).items())
        ),
        "ner_splits": dict(
            sorted(Counter(str(row["split"]) for row in ner_rows).items())
        ),
        "realigned_classifier_records": realigned_classifier,
        "realigned_ner_records": realigned_ner,
        "ner_families_missing_from_classifier": missing_classifier_families,
        **invariant,
    }
    manifest = Path(manifest_output)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def validate_unified_split_files(
    classifier_path: str | Path,
    ner_path: str | Path,
) -> dict[str, Any]:
    return validate_source_family_splits(
        {
            "classifier": read_jsonl(classifier_path),
            "ner": read_jsonl(ner_path),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--classifier-input", required=True)
    create.add_argument("--ner-input", required=True)
    create.add_argument("--classifier-output", required=True)
    create.add_argument("--ner-output", required=True)
    create.add_argument("--manifest-output", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--classifier", required=True)
    validate.add_argument("--ner", required=True)
    args = parser.parse_args()
    if args.command == "create":
        report = create_unified_splits(
            args.classifier_input,
            args.ner_input,
            args.classifier_output,
            args.ner_output,
            args.manifest_output,
        )
    else:
        report = validate_unified_split_files(args.classifier, args.ner)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
