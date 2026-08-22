"""Build leakage-safe DSPy examples from the approved classifier and NER data."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CLASSIFIER_PATH = (
    PROJECT_ROOT / "data" / "model_training_data" / "classifier_campaigns_review.jsonl"
)
DEFAULT_NER_PATH = (
    PROJECT_ROOT / "data" / "model_training_data" / "ner_dataset_approved.jsonl"
)
DEFAULT_OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "model_training_data" / "dspy_prompt_examples.jsonl"
)

FIELD_LABELS = {
    "product_category": "Ana ürün kategorisi",
    "campaign_mechanics": "Kampanya mekaniği",
    "target_segments": "Hedef müşteri",
    "channels": "Kullanım kanalı",
    "benefits": "Avantajlar",
    "requirements": "Koşullar",
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def repair_mojibake(value: str) -> str:
    """Repair common UTF-8-as-Windows-1252 text without changing clean text."""
    if not any(marker in value for marker in ("Ã", "Ä", "Å", "â€", "Â")):
        return value
    for encoding in ("cp1252", "latin1"):
        try:
            repaired = value.encode(encoding).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
        if sum(repaired.count(marker) for marker in ("Ã", "Ä", "Å", "â€", "Â")) < sum(
            value.count(marker) for marker in ("Ã", "Ä", "Å", "â€", "Â")
        ):
            return repaired
    return value


def _eligible(record: dict[str, Any]) -> bool:
    return record.get("training_eligible", True) is not False and record.get(
        "review_status", "approved"
    ) not in {"rejected", "deleted"}


def _unified_split(campaign_id: str) -> str:
    """Assign all tasks for a campaign to one 70/15/15 group split."""
    bucket = int(hashlib.sha256(campaign_id.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 70:
        return "train"
    if bucket < 85:
        return "validation"
    return "test"


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
    classifier = {
        str(item["id"]): item
        for item in classifier_records
        if item.get("id") and _eligible(item)
    }
    ner = {
        str(item.get("id") or item.get("source_id")): item
        for item in ner_records
        if (item.get("id") or item.get("source_id")) and _eligible(item)
    }
    examples: list[dict[str, Any]] = []
    for campaign_id in sorted(set(classifier) | set(ner)):
        cls_record = classifier.get(campaign_id)
        ner_record = ner.get(campaign_id)
        source = cls_record or ner_record or {}
        text = repair_mojibake(str(source.get("text") or "").strip())
        annotations = _annotation_payload(cls_record)
        entities = _entity_payload(ner_record)
        common = {
            "campaign_id": campaign_id,
            "split": _unified_split(campaign_id),
            "campaign_text": text,
            "classification_json": json.dumps(annotations, ensure_ascii=False, sort_keys=True),
            "entities_json": json.dumps(entities, ensure_ascii=False, sort_keys=True),
            "source_url": source.get("source_url", ""),
        }
        if annotations:
            answer, facts = _classification_answer(annotations)
            examples.append(
                {
                    **common,
                    "example_id": f"{campaign_id}:classification",
                    "task": "classification_summary",
                    "question": (
                        "Bu kampanyayı ana ürün, kampanya mekaniği, hedef müşteri, "
                        "kanal, avantaj ve koşullar açısından özetle."
                    ),
                    "answer": answer,
                    "required_facts": facts,
                }
            )
        if entities:
            answer, facts = _entity_answer(entities)
            examples.append(
                {
                    **common,
                    "example_id": f"{campaign_id}:entities",
                    "task": "entity_detail",
                    "question": (
                        "Bu kampanyadaki banka, ürün, tarih, tutar, oran, vade, taksit, "
                        "kod, hedef kitle, avantaj ve önemli koşulları belirt."
                    ),
                    "answer": answer,
                    "required_facts": facts,
                }
            )
    return examples


def write_examples(examples: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in examples),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classifier", type=Path, default=DEFAULT_CLASSIFIER_PATH)
    parser.add_argument("--ner", type=Path, default=DEFAULT_NER_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    examples = build_examples(_read_jsonl(args.classifier), _read_jsonl(args.ner))
    write_examples(examples, args.output)
    print(f"Wrote {len(examples)} DSPy examples to {args.output}")
    print("Splits:", dict(Counter(item["split"] for item in examples)))
    print("Tasks:", dict(Counter(item["task"] for item in examples)))


if __name__ == "__main__":
    main()
