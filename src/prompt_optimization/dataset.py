"""Build deterministic, source-family-safe prompt examples from reviewed data."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from src.training.dataset_contract import (
    PROJECT_ROOT,
    canonical_source_url,
    read_jsonl,
    record_provenance,
    sha256_file,
    source_family_id,
    split_for_family,
)


DEFAULT_CLASSIFIER_PATH = (
    PROJECT_ROOT / "data" / "model_training_data" / "classifier_campaigns_review.jsonl"
)
DEFAULT_NER_PATH = (
    PROJECT_ROOT / "data" / "model_training_data" / "ner_dataset_approved.jsonl"
)
DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "model_training_data" / "dspy_prompt_examples.jsonl"
)
DEFAULT_MANIFEST_PATH = (
    PROJECT_ROOT
    / "data"
    / "model_training_data"
    / "dspy_prompt_examples.manifest.json"
)

FIELD_LABELS = {
    "product_category": "Ana ürün kategorisi",
    "campaign_mechanics": "Kampanya mekaniği",
    "target_segments": "Hedef müşteri",
    "channels": "Kullanım kanalı",
    "benefits": "Avantajlar",
    "requirements": "Koşullar",
}


def repair_mojibake(value: str) -> str:
    if not any(marker in value for marker in ("Ã", "Ä", "Å", "â€", "Â")):
        return value
    for encoding in ("cp1252", "latin1"):
        try:
            repaired = value.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        broken = sum(value.count(marker) for marker in ("Ã", "Ä", "Å", "â€", "Â"))
        repaired_broken = sum(
            repaired.count(marker) for marker in ("Ã", "Ä", "Å", "â€", "Â")
        )
        if repaired_broken < broken:
            return repaired
    return value


def _eligible(record: dict[str, Any]) -> bool:
    return record_provenance(record) != "excluded"


def _index(records: list[dict[str, Any]], *, dataset: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for item in records:
        record_id = str(item.get("id") or item.get("source_id") or "")
        if not record_id or not _eligible(item):
            continue
        if record_id in indexed:
            raise ValueError(f"Duplicate {dataset} record id: {record_id}")
        indexed[record_id] = item
    return indexed


def _unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = repair_mojibake(str(raw).strip())
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _annotation_payload(record: dict[str, Any] | None) -> dict[str, Any]:
    annotations = (record or {}).get("annotations") or {}
    return {
        key: annotations.get(key)
        for key in FIELD_LABELS
        if annotations.get(key) not in (None, "", [])
    }


def _entity_payload(record: dict[str, Any] | None) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for entity in (record or {}).get("entities") or []:
        label = str(entity.get("label") or "").strip()
        text = str(entity.get("text") or "").strip()
        if label and text:
            grouped.setdefault(label, []).append(text)
    return {label: _unique(values) for label, values in sorted(grouped.items())}


def _classification_answer(annotations: dict[str, Any]) -> tuple[str, list[str]]:
    sentences: list[str] = []
    facts: list[str] = []
    for field, display_name in FIELD_LABELS.items():
        raw = annotations.get(field)
        values = raw if isinstance(raw, list) else [raw]
        values = _unique(str(value) for value in values if value)
        if values:
            facts.extend(values)
            sentences.append(f"{display_name}: {', '.join(values)}.")
    return " ".join(sentences), facts


def _entity_answer(entities: dict[str, list[str]]) -> tuple[str, list[str]]:
    sentences = [f"{label}: {', '.join(values)}." for label, values in entities.items()]
    facts = [value for values in entities.values() for value in values]
    return " ".join(sentences), facts


def build_examples(
    classifier_records: list[dict[str, Any]],
    ner_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    classifier = _index(classifier_records, dataset="classifier")
    ner = _index(ner_records, dataset="NER")
    examples: list[dict[str, Any]] = []
    for campaign_id in sorted(set(classifier) | set(ner)):
        cls_record = classifier.get(campaign_id)
        ner_record = ner.get(campaign_id)
        sources = [record for record in (cls_record, ner_record) if record]
        family_ids = {source_family_id(record) for record in sources}
        if len(family_ids) != 1:
            raise ValueError(f"Campaign {campaign_id!r} maps to multiple source families")
        family_id = next(iter(family_ids))
        provenances = {record_provenance(record) for record in sources}
        if "synthetic" in provenances and provenances != {"synthetic"}:
            raise ValueError(f"Campaign {campaign_id!r} mixes synthetic and real sources")
        split = "train" if provenances == {"synthetic"} else split_for_family(family_id)
        source = cls_record or ner_record or {}
        text = repair_mojibake(str(source.get("text") or "").strip())
        annotations = _annotation_payload(cls_record)
        entities = _entity_payload(ner_record)
        common = {
            "campaign_id": campaign_id,
            "source_family_id": family_id,
            "split": split,
            "campaign_text": text,
            "classification_json": json.dumps(
                annotations, ensure_ascii=False, sort_keys=True
            ),
            "entities_json": json.dumps(entities, ensure_ascii=False, sort_keys=True),
            "source_url": canonical_source_url(source),
            "reference_kind": "derived_label_projection",
        }
        if annotations and cls_record:
            answer, facts = _classification_answer(annotations)
            examples.append(
                {
                    **common,
                    "example_id": f"{campaign_id}:classification",
                    "task": "classification_summary",
                    "reference_provenance": record_provenance(cls_record),
                    "question": (
                        "Bu kampanyayı ana ürün, kampanya mekaniği, hedef müşteri, "
                        "kanal, avantaj ve koşullar açısından özetle."
                    ),
                    "answer": answer,
                    "required_facts": facts,
                }
            )
        if entities and ner_record:
            answer, facts = _entity_answer(entities)
            examples.append(
                {
                    **common,
                    "example_id": f"{campaign_id}:entities",
                    "task": "entity_detail",
                    "reference_provenance": record_provenance(ner_record),
                    "question": (
                        "Bu kampanyadaki banka, ürün, tarih, tutar, oran, vade, "
                        "taksit, kod, hedef kitle, avantaj ve önemli koşulları belirt."
                    ),
                    "answer": answer,
                    "required_facts": facts,
                }
            )
    validate_examples(examples)
    return examples


def validate_examples(examples: list[dict[str, Any]]) -> dict[str, Any]:
    seen_ids: set[str] = set()
    family_splits: dict[str, set[str]] = defaultdict(set)
    for example in examples:
        example_id = str(example.get("example_id") or "")
        if not example_id or example_id in seen_ids:
            raise ValueError(f"Duplicate or missing example_id: {example_id!r}")
        seen_ids.add(example_id)
        if example.get("reference_kind") != "derived_label_projection":
            raise ValueError(f"Example {example_id} has unsupported reference_kind")
        if example.get("reference_provenance") not in {"human", "auto", "synthetic"}:
            raise ValueError(f"Example {example_id} has invalid reference provenance")
        family_splits[str(example["source_family_id"])].add(str(example["split"]))
    leaked = [family for family, splits in family_splits.items() if len(splits) > 1]
    if leaked:
        raise ValueError(f"Source family crosses prompt splits: {sorted(leaked)[0]}")
    return {
        "examples": len(examples),
        "source_families": len(family_splits),
        "source_family_cross_split": 0,
    }


def _render_examples(examples: list[dict[str, Any]]) -> bytes:
    return "".join(
        json.dumps(item, ensure_ascii=False) + "\n" for item in examples
    ).encode("utf-8")


def _path_label(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def build_manifest(
    examples: list[dict[str, Any]],
    *,
    classifier_path: str | Path,
    ner_path: str | Path,
) -> dict[str, Any]:
    validation = validate_examples(examples)
    families: dict[str, dict[str, Any]] = {}
    for example in examples:
        family_id = str(example["source_family_id"])
        item = families.setdefault(
            family_id,
            {"source_family_id": family_id, "split": example["split"], "campaign_ids": set()},
        )
        item["campaign_ids"].add(example["campaign_id"])
    assignments = [
        {
            "source_family_id": item["source_family_id"],
            "split": item["split"],
            "campaign_ids": sorted(item["campaign_ids"]),
        }
        for item in sorted(families.values(), key=lambda value: value["source_family_id"])
    ]
    assignment_bytes = json.dumps(
        assignments, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    rendered = _render_examples(examples)
    classifier = Path(classifier_path)
    ner = Path(ner_path)
    return {
        "schema_version": 1,
        "contract": "derived-label-prompt-dataset",
        "inputs": {
            _path_label(classifier): {
                "sha256": sha256_file(classifier),
                "line_count": len(read_jsonl(classifier)),
            },
            _path_label(ner): {
                "sha256": sha256_file(ner),
                "line_count": len(read_jsonl(ner)),
            },
        },
        "output": {
            "sha256": hashlib.sha256(rendered).hexdigest(),
            "line_count": len(examples),
            "split_counts": dict(
                sorted(Counter(str(item["split"]) for item in examples).items())
            ),
            "task_counts": dict(
                sorted(Counter(str(item["task"]) for item in examples).items())
            ),
            "provenance_counts": dict(
                sorted(
                    Counter(str(item["reference_provenance"]) for item in examples).items()
                )
            ),
        },
        "split_policy": {
            "unit": "canonical_source_family",
            "hash": "sha256",
            "buckets": {"train": "0-69", "validation": "70-84", "test": "85-99"},
            "assignment_sha256": hashlib.sha256(assignment_bytes).hexdigest(),
        },
        "family_assignment_count": len(assignments),
        "invariants": validation,
        "metric_contract": {
            "reference_kind": "derived_label_projection",
            "automatic_references": "proxy_only",
        },
        "independent_gold": {
            "status": "not_provided",
            "score": None,
        },
    }


def write_examples_and_manifest(
    examples: list[dict[str, Any]],
    output_path: str | Path,
    manifest_path: str | Path,
    *,
    classifier_path: str | Path,
    ner_path: str | Path,
) -> dict[str, Any]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(_render_examples(examples))
    manifest = build_manifest(
        examples, classifier_path=classifier_path, ner_path=ner_path
    )
    destination = Path(manifest_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def validate_committed_dataset(
    output_path: str | Path = DEFAULT_OUTPUT_PATH,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    *,
    classifier_path: str | Path = DEFAULT_CLASSIFIER_PATH,
    ner_path: str | Path = DEFAULT_NER_PATH,
) -> dict[str, Any]:
    output = Path(output_path)
    examples = build_examples(read_jsonl(classifier_path), read_jsonl(ner_path))
    if output.read_bytes() != _render_examples(examples):
        raise ValueError(
            "Prompt dataset does not match deterministic regeneration from inputs"
        )
    expected = build_manifest(
        examples, classifier_path=classifier_path, ner_path=ner_path
    )
    committed = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if committed != expected:
        raise ValueError("Prompt dataset manifest does not match committed files")
    return expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classifier", type=Path, default=DEFAULT_CLASSIFIER_PATH)
    parser.add_argument("--ner", type=Path, default=DEFAULT_NER_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        manifest = validate_committed_dataset(
            args.output,
            args.manifest,
            classifier_path=args.classifier,
            ner_path=args.ner,
        )
    else:
        examples = build_examples(read_jsonl(args.classifier), read_jsonl(args.ner))
        manifest = write_examples_and_manifest(
            examples,
            args.output,
            args.manifest,
            classifier_path=args.classifier,
            ner_path=args.ner,
        )
    print(json.dumps(manifest["output"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
