"""Train and evaluate the ontology-aligned campaign classification bundle."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from src.annotation.store import ANNOTATION_FIELDS, validate_annotations
from src.classifier.main import build_pipeline, read_records
from src.training.dataset_contract import record_provenance


MULTI_FIELDS = tuple(ANNOTATION_FIELDS)


def load_multidimensional_examples(
    path: str | Path,
    *,
    split: str | None,
    require_verified: bool = True,
    allow_auto_high_confidence: bool = False,
    allow_synthetic: bool = False,
) -> tuple[list[str], list[dict[str, Any]]]:
    texts: list[str] = []
    annotations: list[dict[str, Any]] = []
    for record in read_records(path):
        if split is not None and record.get("split") != split:
            continue
        provenance = record_provenance(record)
        allowed = {"human"}
        if allow_auto_high_confidence:
            allowed.add("auto")
        if allow_synthetic:
            allowed.add("synthetic")
        if provenance == "excluded" or (require_verified and provenance not in allowed):
            continue
        text = record.get("text")
        annotation = record.get("annotations")
        if not isinstance(text, str) or not text.strip():
            continue
        validate_annotations(annotation)
        if annotation["product_category"] == "needs_review":
            continue
        texts.append(text)
        annotations.append(annotation)
    if not texts:
        raise ValueError("No verified multidimensional examples found")
    return texts, annotations


def _multilabel_pipeline(seed: int) -> Any:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.multiclass import OneVsRestClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.svm import LinearSVC

    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    min_df=1,
                    sublinear_tf=True,
                    max_features=100_000,
                ),
            ),
            (
                "classifier",
                OneVsRestClassifier(
                    LinearSVC(class_weight="balanced", random_state=seed)
                ),
            ),
        ]
    )


def train_bundle(
    dataset: str | Path,
    output_path: str | Path,
    *,
    train_split: str = "train",
    evaluation_split: str = "validation",
    seed: int = 42,
    allow_auto_high_confidence: bool = False,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    import joblib
    from sklearn.preprocessing import MultiLabelBinarizer

    train_texts, train_annotations = load_multidimensional_examples(
        dataset,
        split=train_split,
        allow_auto_high_confidence=allow_auto_high_confidence,
        allow_synthetic=allow_synthetic,
    )
    eval_texts, eval_annotations = load_multidimensional_examples(
        dataset,
        split=evaluation_split,
        allow_auto_high_confidence=allow_auto_high_confidence,
        allow_synthetic=allow_synthetic,
    )
    product_labels = [item["product_category"] for item in train_annotations]
    if len(set(product_labels)) < 2:
        raise ValueError("Product classifier requires at least two product categories")
    product_model = build_pipeline(
        min_df=1 if len(train_texts) < 20 else 2, seed=seed
    ).fit(train_texts, product_labels)
    field_models: dict[str, Any] = {}
    skipped_fields: dict[str, str] = {}
    for field in MULTI_FIELDS:
        binarizer = MultiLabelBinarizer()
        encoded = binarizer.fit_transform([item[field] for item in train_annotations])
        if encoded.shape[1] < 2:
            skipped_fields[field] = "fewer_than_two_observed_labels"
            continue
        model = _multilabel_pipeline(seed).fit(train_texts, encoded)
        field_models[field] = {"model": model, "binarizer": binarizer}
    bundle = {
        "product_model": product_model,
        "field_models": field_models,
        "taxonomy_version": "campaign-2026-08-25-target-audience",
        "seed": seed,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, output)
    report = evaluate_bundle_object(bundle, eval_texts, eval_annotations)
    report.update(
        {
            "train_examples": len(train_texts),
            "evaluation_examples": len(eval_texts),
            "skipped_fields": skipped_fields,
            "competition_metric_eligible": not allow_auto_high_confidence
            and not allow_synthetic,
            "evaluation_metric_kind": (
                "proxy" if allow_auto_high_confidence or allow_synthetic else "human_labeled"
            ),
        }
    )
    output.with_suffix(".metrics.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def evaluate_bundle_object(
    bundle: dict[str, Any], texts: list[str], gold: list[dict[str, Any]]
) -> dict[str, Any]:
    from sklearn.metrics import accuracy_score, f1_score

    product_gold = [item["product_category"] for item in gold]
    product_predicted = bundle["product_model"].predict(texts)
    fields = {}
    for field, components in bundle["field_models"].items():
        binarizer = components["binarizer"]
        expected = binarizer.transform([item[field] for item in gold])
        predicted = components["model"].predict(texts)
        fields[field] = {
            "micro_f1": f1_score(expected, predicted, average="micro", zero_division=0),
            "macro_f1": f1_score(expected, predicted, average="macro", zero_division=0),
            "subset_accuracy": accuracy_score(expected, predicted),
            "labels": list(binarizer.classes_),
        }
    return {
        "product_accuracy": accuracy_score(product_gold, product_predicted),
        "dimensions": fields,
    }


def evaluate_bundle(
    model_path: str | Path,
    dataset: str | Path,
    *,
    split: str = "test",
    allow_auto_high_confidence: bool = False,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    import joblib

    texts, annotations = load_multidimensional_examples(
        dataset,
        split=split,
        allow_auto_high_confidence=allow_auto_high_confidence,
        allow_synthetic=allow_synthetic,
    )
    report = evaluate_bundle_object(joblib.load(model_path), texts, annotations)
    report["evaluation_examples"] = len(texts)
    report["split"] = split
    rows = [
        record
        for record in read_records(dataset)
        if record.get("split") == split and record_provenance(record) != "excluded"
    ]
    report["available_provenance_counts"] = dict(
        sorted(Counter(record_provenance(record) for record in rows).items())
    )
    report["evaluation_metric_kind"] = (
        "proxy" if allow_auto_high_confidence or allow_synthetic else "human_labeled"
    )
    report["competition_metric_eligible"] = not allow_auto_high_confidence and not allow_synthetic
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train")
    train.add_argument("dataset")
    train.add_argument("output")
    train.add_argument("--train-split", default="train")
    train.add_argument("--evaluation-split", default="validation")
    train.add_argument("--seed", type=int, default=42)
    train.add_argument("--allow-auto-high-confidence", action="store_true")
    train.add_argument("--allow-synthetic", action="store_true")
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("model")
    evaluate.add_argument("dataset")
    evaluate.add_argument("--split", default="test")
    evaluate.add_argument("--allow-auto-high-confidence", action="store_true")
    evaluate.add_argument("--allow-synthetic", action="store_true")
    args = parser.parse_args()
    if args.command == "train":
        result = train_bundle(
            args.dataset,
            args.output,
            train_split=args.train_split,
            evaluation_split=args.evaluation_split,
            seed=args.seed,
            allow_auto_high_confidence=args.allow_auto_high_confidence,
            allow_synthetic=args.allow_synthetic,
        )
    else:
        result = evaluate_bundle(
            args.model,
            args.dataset,
            split=args.split,
            allow_auto_high_confidence=args.allow_auto_high_confidence,
            allow_synthetic=args.allow_synthetic,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
