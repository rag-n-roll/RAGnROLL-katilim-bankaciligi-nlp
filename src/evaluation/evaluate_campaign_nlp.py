"""Evaluate the selected classifier and hybrid NER as one campaign NLP system."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.extraction.campaign_nlp_pipeline import CampaignNLPPipeline, _classification
from src.ner.hybrid_inference import DEFAULT_RULE_LABELS, predict_entities
from src.ner.train import read_jsonl, select_split


DIMENSIONS = ("campaign_mechanics", "target_segments", "channels", "benefits", "requirements")


def _f1(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": score, "tp": tp, "fp": fp, "fn": fn}


def _load_classifier_records(path: str | Path, split: str) -> list[dict[str, Any]]:
    records = [
        json.loads(line)
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return [
        record for record in records
        if record.get("split") == split and record.get("training_eligible", True)
    ]


def evaluate_system(
    classifier_dataset: str | Path,
    ner_dataset: str | Path,
    *,
    classifier_model: str | Path,
    ner_model: str | Path,
    split: str = "test",
) -> dict[str, Any]:
    pipeline = CampaignNLPPipeline.load(classifier_model, ner_model)
    classifier_records = _load_classifier_records(classifier_dataset, split)
    ner_records = select_split(read_jsonl(ner_dataset), split)

    product_correct = 0
    classification_strict = 0
    dimension_counts = {field: {"tp": 0, "fp": 0, "fn": 0} for field in DIMENSIONS}
    classification_predictions: dict[str, tuple[str, dict[str, set[str]]]] = {}
    for record in classifier_records:
        prediction = _classification(pipeline.classifier_bundle, record["text"])
        predicted_product = prediction["product_category"]["value"]
        gold_annotations = record["annotations"]
        product_match = predicted_product == gold_annotations["product_category"]
        product_correct += int(product_match)
        all_dimensions_match = True
        predicted_dimensions: dict[str, set[str]] = {}
        for field in DIMENSIONS:
            predicted = {item["value"] for item in prediction["dimensions"][field]}
            gold = set(gold_annotations.get(field, []))
            predicted_dimensions[field] = predicted
            dimension_counts[field]["tp"] += len(predicted & gold)
            dimension_counts[field]["fp"] += len(predicted - gold)
            dimension_counts[field]["fn"] += len(gold - predicted)
            all_dimensions_match &= predicted == gold
        classification_strict += int(product_match and all_dimensions_match)
        classification_predictions[str(record["id"])] = (predicted_product, predicted_dimensions)

    ner_tp = ner_fp = ner_fn = 0
    ner_predictions: dict[str, set[tuple[int, int, str]]] = {}
    ner_gold: dict[str, set[tuple[int, int, str]]] = {}
    for record in ner_records:
        gold = {
            (int(item["start"]), int(item["end"]), str(item["label"]))
            for item in record["entities"]
        }
        predicted = {
            (int(item["start"]), int(item["end"]), str(item["label"]))
            for item in predict_entities(pipeline.nlp, record["text"], DEFAULT_RULE_LABELS)
        }
        ner_tp += len(gold & predicted)
        ner_fp += len(predicted - gold)
        ner_fn += len(gold - predicted)
        record_id = str(record["id"])
        ner_predictions[record_id] = predicted
        ner_gold[record_id] = gold

    dimension_total = {
        key: sum(values[key] for values in dimension_counts.values())
        for key in ("tp", "fp", "fn")
    }
    dimension_metrics = _f1(**dimension_total)
    ner_metrics = _f1(ner_tp, ner_fp, ner_fn)

    classifier_by_id = {str(record["id"]): record for record in classifier_records}
    shared_ids = sorted(set(classification_predictions) & set(ner_predictions))
    joint_strict = 0
    for record_id in shared_ids:
        predicted_product, predicted_dimensions = classification_predictions[record_id]
        annotations = classifier_by_id[record_id]["annotations"]
        classification_exact = (
            predicted_product == annotations["product_category"]
            and all(
                predicted_dimensions[field] == set(annotations.get(field, []))
                for field in DIMENSIONS
            )
        )
        joint_strict += int(
            classification_exact
            and ner_predictions[record_id] == ner_gold[record_id]
        )

    product_accuracy = product_correct / len(classifier_records) if classifier_records else 0.0
    competition_proxy = (
        product_accuracy
        + float(dimension_metrics["f1"])
        + float(ner_metrics["f1"])
    ) / 3
    return {
        "evaluation_policy": "untouched_test_splits; no test-driven model selection",
        "split": split,
        "classifier": {
            "documents": len(classifier_records),
            "product_accuracy": product_accuracy,
            "strict_document_accuracy": (
                classification_strict / len(classifier_records)
                if classifier_records
                else 0.0
            ),
            "dimensions_micro": dimension_metrics,
            "per_dimension": {field: _f1(**counts) for field, counts in dimension_counts.items()},
        },
        "ner": {"documents": len(ner_records), "exact_span_micro": ner_metrics},
        "joint": {
            "shared_documents": len(shared_ids),
            "strict_document_accuracy": joint_strict / len(shared_ids) if shared_ids else 0.0,
            "note": (
                "Strict means every classification label and every NER span "
                "is exact in the same document."
            ),
        },
        "competition_proxy_score": competition_proxy,
        "models": {"classifier": str(classifier_model), "ner": str(ner_model)},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--classifier-dataset",
        default="data/model_training_data/classifier_campaigns_review.jsonl",
    )
    parser.add_argument(
        "--ner-dataset",
        default="data/model_training_data/ner_dataset_approved.jsonl",
    )
    parser.add_argument("--classifier-model", default="models/campaign_classifier_final.joblib")
    parser.add_argument("--ner-model", default="models/campaign_ner_improved")
    parser.add_argument("--split", default="test")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("models/campaign_nlp_system_evaluation.json"),
    )
    args = parser.parse_args()
    result = evaluate_system(
        args.classifier_dataset,
        args.ner_dataset,
        classifier_model=args.classifier_model,
        ner_model=args.ner_model,
        split=args.split,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
