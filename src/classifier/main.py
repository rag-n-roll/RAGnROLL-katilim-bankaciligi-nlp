"""Train and evaluate reproducible Turkish text classification baselines."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def _nested_value(record: dict[str, Any], field: str) -> Any:
    value: Any = record
    for part in field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def read_records(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.casefold() == ".jsonl":
        records = [
            json.loads(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    elif source.suffix.casefold() == ".csv":
        with source.open(encoding="utf-8-sig", newline="") as stream:
            records = list(csv.DictReader(stream))
    else:
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            records = payload
        else:
            records = payload.get("records", payload.get("campaigns", []))
    if not records:
        raise ValueError(f"No records found in {path}")
    return records


def load_examples(
    path: str | Path,
    *,
    text_field: str = "text",
    label_field: str = "label",
    split: str | None = None,
    require_verified: bool = False,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    selected = []
    for record in read_records(path):
        if split is not None and record.get("split") != split:
            continue
        if require_verified and record.get("human_verified") is not True:
            continue
        text = _nested_value(record, text_field)
        label = _nested_value(record, label_field)
        if isinstance(text, str) and text.strip() and isinstance(label, str) and label.strip():
            selected.append((text, label, record))
    if not selected:
        raise ValueError(
            "No usable examples. Check field names, split and human_verified values."
        )
    texts, labels, metadata = zip(*selected)
    if len(set(labels)) < 2:
        raise ValueError("Classification requires at least two labels")
    return list(texts), list(labels), list(metadata)


def build_pipeline(*, min_df: int = 2, seed: int = 42) -> Any:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.pipeline import Pipeline
    from sklearn.svm import LinearSVC

    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(3, 5),
                    min_df=min_df,
                    sublinear_tf=True,
                    max_features=100_000,
                ),
            ),
            ("classifier", LinearSVC(class_weight="balanced", random_state=seed)),
        ]
    )


def classification_metrics(labels: list[str], predictions: list[str]) -> dict[str, Any]:
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

    ordered = sorted(set(labels) | set(predictions))
    report = classification_report(
        labels, predictions, labels=ordered, output_dict=True, zero_division=0
    )
    return {
        "accuracy": accuracy_score(labels, predictions),
        "macro_f1": report["macro avg"]["f1-score"],
        "weighted_f1": report["weighted avg"]["f1-score"],
        "per_class": {label: report[label] for label in ordered},
        "labels": ordered,
        "confusion_matrix": confusion_matrix(labels, predictions, labels=ordered).tolist(),
    }


def train_model(
    train_path: str | Path,
    output_path: str | Path,
    *,
    text_field: str = "text",
    label_field: str = "label",
    train_split: str | None = None,
    evaluation_path: str | Path | None = None,
    evaluation_split: str | None = "validation",
    require_verified: bool = False,
    seed: int = 42,
) -> dict[str, Any]:
    import joblib

    texts, labels, records = load_examples(
        train_path,
        text_field=text_field,
        label_field=label_field,
        split=train_split,
        require_verified=require_verified,
    )
    holdout: tuple[list[str], list[str]] | None = None
    if evaluation_path is None:
        from sklearn.model_selection import train_test_split

        texts, eval_texts, labels, eval_labels = train_test_split(
            texts, labels, test_size=0.2, random_state=seed, stratify=labels
        )
        holdout = (eval_texts, eval_labels)
    model = build_pipeline(min_df=1 if len(texts) < 20 else 2, seed=seed)
    model.fit(texts, labels)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output)
    report: dict[str, Any] = {
        "model": "tfidf-char-linear-svc",
        "training_examples": len(texts),
        "label_distribution": dict(Counter(labels)),
        "seed": seed,
        "synthetic_data_warning": any(
            bool(record.get("metadata", {}).get("synthetic")) for record in records
        ),
    }
    if holdout:
        eval_texts, eval_labels = holdout
        report["evaluation_split"] = "stratified_holdout_20_percent"
        report["evaluation"] = classification_metrics(eval_labels, model.predict(eval_texts))
    elif evaluation_path:
        eval_texts, eval_labels, _ = load_examples(
            evaluation_path,
            text_field=text_field,
            label_field=label_field,
            split=evaluation_split,
            require_verified=require_verified,
        )
        report["evaluation"] = classification_metrics(eval_labels, model.predict(eval_texts))
    report_path = output.with_suffix(".metrics.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def evaluate_model(
    model_path: str | Path,
    dataset: str | Path,
    *,
    text_field: str = "text",
    label_field: str = "label",
    split: str | None = "validation",
    require_verified: bool = False,
) -> dict[str, Any]:
    import joblib

    texts, labels, records = load_examples(
        dataset,
        text_field=text_field,
        label_field=label_field,
        split=split,
        require_verified=require_verified,
    )
    result = classification_metrics(labels, joblib.load(model_path).predict(texts))
    result["examples"] = len(texts)
    result["synthetic_data_warning"] = any(
        bool(record.get("metadata", {}).get("synthetic")) for record in records
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    train = commands.add_parser("train")
    train.add_argument("dataset")
    train.add_argument("output")
    train.add_argument("--text-field", default="text")
    train.add_argument("--label-field", default="label")
    train.add_argument("--train-split")
    train.add_argument("--evaluation-dataset")
    train.add_argument("--evaluation-split", default="validation")
    train.add_argument("--require-verified", action="store_true")
    train.add_argument("--seed", type=int, default=42)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("model")
    evaluate.add_argument("dataset")
    evaluate.add_argument("--text-field", default="text")
    evaluate.add_argument("--label-field", default="label")
    evaluate.add_argument("--split", default="validation")
    evaluate.add_argument("--require-verified", action="store_true")
    args = parser.parse_args()
    if args.command == "train":
        result = train_model(
            args.dataset,
            args.output,
            text_field=args.text_field,
            label_field=args.label_field,
            train_split=args.train_split,
            evaluation_path=args.evaluation_dataset,
            evaluation_split=args.evaluation_split,
            require_verified=args.require_verified,
            seed=args.seed,
        )
    else:
        result = evaluate_model(
            args.model,
            args.dataset,
            text_field=args.text_field,
            label_field=args.label_field,
            split=args.split,
            require_verified=args.require_verified,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
