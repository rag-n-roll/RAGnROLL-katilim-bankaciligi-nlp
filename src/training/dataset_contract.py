"""Deterministic manifests and leakage checks for model-training datasets."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import unquote, urlsplit, urlunsplit

from src.scraper.models import normalize_source_url


PROJECT_ROOT = Path(__file__).resolve().parents[2]
VALID_SPLITS = frozenset({"train", "validation", "test"})
DEFAULT_MANIFEST_PATH = (
    PROJECT_ROOT / "data" / "model_training_data" / "training_dataset_manifest.json"
)
DEFAULT_FILE_SPECS = (
    ("data/model_training_data/classifier_campaigns_review.jsonl", "classification"),
    ("data/model_training_data/ner_dataset_approved.jsonl", "ner"),
    ("data/model_training_data/classifier_dataset_final.jsonl", "classification"),
    ("data/model_training_data/ner_dataset_final.jsonl", "ner"),
    (
        "data/model_training_data/target_audience_llm_large.jsonl",
        "target_audience_extraction",
    ),
    (
        "data/enrichment/context_entities_llm_large.jsonl",
        "context_entity_extraction",
    ),
    ("data/model_training_data/campaign_nlp_output_schema.json", "schema"),
)


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read a non-empty JSONL file and report its first malformed line."""
    source = Path(path)
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON on line {line_number} of {source}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"Line {line_number} of {source} must be a JSON object")
        rows.append(row)
    if not rows:
        raise ValueError(f"No records found in {source}")
    return rows


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def is_synthetic(row: Mapping[str, Any]) -> bool:
    metadata = row.get("metadata") or {}
    return bool(metadata.get("synthetic")) or str(row.get("id") or "").startswith(
        "synthetic-"
    )


def record_source_id(row: Mapping[str, Any]) -> str:
    metadata = row.get("metadata") or {}
    return str(metadata.get("source_id") or row.get("source_id") or row.get("id") or "")


def record_provenance(row: Mapping[str, Any]) -> str:
    """Return an exclusive provenance class; generated templates are never human."""
    if is_synthetic(row):
        return "synthetic"
    metadata = row.get("metadata") or {}
    statuses = {
        str(row.get("label_status") or ""),
        str(row.get("review_status") or ""),
        str(metadata.get("label_status") or ""),
    }
    if (
        row.get("training_eligible") is False
        or statuses & {"excluded", "rejected", "deleted", "review_required"}
    ):
        return "excluded"
    human_verified = row.get("human_verified") is True or metadata.get(
        "human_verified"
    ) is True
    if human_verified:
        return "human"
    if statuses & {"auto_high_confidence", "auto", "weak_label"}:
        return "auto"
    return "auto"


def canonical_source_url(row: Mapping[str, Any]) -> str:
    """Return the normalized real-record URL, failing closed when it is absent."""
    source_url = row.get("source_url")
    if not isinstance(source_url, str) or not source_url.strip():
        if is_synthetic(row):
            return ""
        raise ValueError(f"Real record {row.get('id')!r} has no source_url")
    normalized = normalize_source_url(source_url)
    if not normalized:
        raise ValueError(f"Real record {row.get('id')!r} has an invalid source_url")
    parsed = urlsplit(normalized)
    path = parsed.path.rstrip("/") or "/"
    query_parts = [part for part in parsed.query.split("&") if part]
    query_parts.sort(
        key=lambda part: (
            unquote(part.partition("=")[0]).casefold(),
            unquote(part.partition("=")[2]),
            part,
        )
    )
    return urlunsplit(
        (parsed.scheme, parsed.netloc, path, "&".join(query_parts), "")
    )


def source_family_id(row: Mapping[str, Any]) -> str:
    """Hash the canonical URL so every record from one source page stays together."""
    canonical = canonical_source_url(row)
    if not canonical:
        source_id = record_source_id(row)
        if not source_id:
            raise ValueError(f"Synthetic record {row.get('id')!r} has no source_id")
        canonical = f"synthetic:{source_id}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def split_for_family(family_id: str) -> str:
    bucket = int(family_id[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "validation"
    return "test"


def validate_source_family_splits(
    datasets: Mapping[str, Iterable[Mapping[str, Any]]],
) -> dict[str, Any]:
    """Validate family-level splits jointly across classifier and NER datasets."""
    family_splits: dict[str, set[str]] = defaultdict(set)
    family_records: dict[str, list[str]] = defaultdict(list)
    real_id_splits: dict[str, set[str]] = defaultdict(set)
    synthetic_count = 0
    real_count = 0
    for dataset_name, rows in datasets.items():
        for row in rows:
            record_id = str(row.get("id") or row.get("source_id") or "")
            split = str(row.get("split") or "")
            if split not in VALID_SPLITS:
                raise ValueError(
                    f"Record {record_id!r} in {dataset_name} has invalid split {split!r}"
                )
            if is_synthetic(row):
                synthetic_count += 1
                if split != "train":
                    raise ValueError(
                        f"Synthetic record {record_id!r} must be assigned to train"
                    )
                if not record_source_id(row):
                    raise ValueError(f"Synthetic record {record_id!r} has no source_id")
                continue
            real_count += 1
            family_id = source_family_id(row)
            family_splits[family_id].add(split)
            family_records[family_id].append(f"{dataset_name}:{record_id}")
            real_id_splits[record_id].add(split)

    cross_family = {
        family_id: sorted(splits)
        for family_id, splits in family_splits.items()
        if len(splits) > 1
    }
    if cross_family:
        family_id = sorted(cross_family)[0]
        raise ValueError(
            "Source family crosses splits: "
            f"{family_id} -> {cross_family[family_id]} "
            f"({', '.join(family_records[family_id])})"
        )
    cross_id = {
        record_id: sorted(splits)
        for record_id, splits in real_id_splits.items()
        if len(splits) > 1
    }
    if cross_id:
        record_id = sorted(cross_id)[0]
        raise ValueError(f"Record {record_id!r} crosses splits: {cross_id[record_id]}")
    return {
        "real_records": real_count,
        "synthetic_records": synthetic_count,
        "source_families": len(family_splits),
        "source_family_cross_split": 0,
        "record_id_cross_split": 0,
        "synthetic_non_train": 0,
    }


def _jsonl_summary(path: Path, task: str) -> dict[str, Any]:
    rows = read_jsonl(path)
    provenance = Counter(record_provenance(row) for row in rows)
    synthetic = sum(is_synthetic(row) for row in rows)
    return {
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "line_count": len(rows),
        "record_count": len(rows),
        "split_counts": dict(
            sorted(Counter(str(row.get("split") or "unassigned") for row in rows).items())
        ),
        "task_counts": {task: len(rows)},
        "record_kind_counts": {"real": len(rows) - synthetic, "synthetic": synthetic},
        "provenance_counts": {
            key: provenance.get(key, 0)
            for key in ("human", "auto", "synthetic", "excluded")
        },
    }


def build_training_manifest(project_root: str | Path = PROJECT_ROOT) -> dict[str, Any]:
    root = Path(project_root)
    files: dict[str, dict[str, Any]] = {}
    for relative, task in DEFAULT_FILE_SPECS:
        path = root / relative
        if task == "schema":
            json.loads(path.read_text(encoding="utf-8"))
            files[relative] = {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "line_count": len(path.read_text(encoding="utf-8").splitlines()),
                "record_count": 0,
                "split_counts": {},
                "task_counts": {},
                "record_kind_counts": {"real": 0, "synthetic": 0},
                "provenance_counts": {
                    "human": 0,
                    "auto": 0,
                    "synthetic": 0,
                    "excluded": 0,
                },
            }
        else:
            files[relative] = _jsonl_summary(path, task)

    classifier_final = read_jsonl(
        root / "data/model_training_data/classifier_dataset_final.jsonl"
    )
    ner_final = read_jsonl(root / "data/model_training_data/ner_dataset_final.jsonl")
    invariants = validate_source_family_splits(
        {"classifier": classifier_final, "ner": ner_final}
    )
    return {
        "schema_version": 1,
        "contract": "training-dataset-lineage",
        "files": files,
        "invariants": invariants,
        "metric_contract": {
            "automatic_references": "proxy_only",
            "proxy_reports_require_provenance_slices": True,
        },
        "independent_gold": {
            "status": "not_provided",
            "score": None,
            "reason": "No independently authored and reviewed holdout is committed.",
        },
    }


def write_training_manifest(
    output_path: str | Path = DEFAULT_MANIFEST_PATH,
    *,
    project_root: str | Path = PROJECT_ROOT,
) -> dict[str, Any]:
    manifest = build_training_manifest(project_root)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def validate_training_manifest(
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    *,
    project_root: str | Path = PROJECT_ROOT,
) -> dict[str, Any]:
    committed = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    current = build_training_manifest(project_root)
    if committed != current:
        raise ValueError("Training dataset manifest does not match committed files")
    return current


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    manifest = (
        validate_training_manifest(args.output)
        if args.check
        else write_training_manifest(args.output)
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
