"""Hybrid campaign NER: neural contextual spans plus audited deterministic patterns."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import spacy

from src.ner.prepare_campaign_ner import annotate
from src.ner.train import read_jsonl, select_split


DEFAULT_RULE_LABELS = {
    "ALISVERIS_PUANI",
    "FINANSMAN_TUTARI",
    "INDIRIM_ORANI",
    "KAMPANYA_KOSULU",
    "KAR_PAYI_ORANI",
    "MASRAF_BILGISI",
    "ODUL_MIKTARI",
    "PROMOSYON_KODU",
    "TAHSIS_UCRETI",
}


def predict_entities(nlp: Any, text: str, rule_labels: set[str]) -> list[dict[str, Any]]:
    neural = [
        {
            "start": entity.start_char,
            "end": entity.end_char,
            "text": entity.text,
            "label": entity.label_,
        }
        for entity in nlp(text).ents
        if entity.label_ not in rule_labels
    ]
    occupied = {
        position
        for entity in neural
        for position in range(int(entity["start"]), int(entity["end"]))
    }
    rule_entities = []
    for entity in annotate(text, "")[0]:
        if entity["label"] not in rule_labels:
            continue
        positions = set(range(int(entity["start"]), int(entity["end"])))
        if occupied & positions:
            continue
        occupied |= positions
        rule_entities.append({key: entity[key] for key in ("start", "end", "text", "label")})
    return sorted([*neural, *rule_entities], key=lambda item: (item["start"], item["end"]))


def evaluate(
    model_path: str | Path,
    dataset: str | Path,
    split: str,
    rule_labels: Iterable[str],
) -> dict[str, Any]:
    nlp = spacy.load(model_path)
    records = select_split(read_jsonl(dataset), split)
    selected_rules = set(rule_labels)
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for record in records:
        gold = {(entity["start"], entity["end"], entity["label"]) for entity in record["entities"]}
        predicted = {
            (entity["start"], entity["end"], entity["label"])
            for entity in predict_entities(nlp, record["text"], selected_rules)
        }
        for _, _, label in gold & predicted:
            counts[label]["tp"] += 1
        for _, _, label in predicted - gold:
            counts[label]["fp"] += 1
        for _, _, label in gold - predicted:
            counts[label]["fn"] += 1
    tp = sum(item["tp"] for item in counts.values())
    fp = sum(item["fp"] for item in counts.values())
    fn = sum(item["fn"] for item in counts.values())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "model_path": str(model_path),
        "split": split,
        "documents": len(records),
        "rule_labels": sorted(selected_rules),
        "metrics": {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "tp": tp,
            "fp": fp,
            "fn": fn,
        },
        "per_entity": {label: dict(counter) for label, counter in sorted(counts.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    parser.add_argument("dataset")
    parser.add_argument("--split", default="test")
    parser.add_argument("--rule-labels", default=",".join(sorted(DEFAULT_RULE_LABELS)))
    parser.add_argument("--output")
    args = parser.parse_args()
    result = evaluate(
        args.model,
        args.dataset,
        args.split,
        [label for label in args.rule_labels.split(",") if label],
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
