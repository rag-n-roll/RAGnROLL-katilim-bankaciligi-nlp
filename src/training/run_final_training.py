"""Train and select the final leakage-safe campaign NLP pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.classifier.multilabel import evaluate_bundle, train_bundle
from src.evaluation.evaluate_campaign_nlp import evaluate_system
from src.ner.hybrid_inference import DEFAULT_RULE_LABELS, evaluate as evaluate_hybrid
from src.ner.train import train_model


NER_CANDIDATES = (
    {
        "name": "augmented_25e",
        "epochs": 25,
        "dropout": 0.2,
        "rare_label_document_threshold": 0,
        "rare_example_multiplier": 1,
    },
    {
        "name": "augmented_weighted_30e",
        "epochs": 30,
        "dropout": 0.2,
        "rare_label_document_threshold": 40,
        "rare_example_multiplier": 2,
    },
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def evaluate_existing(
    classifier_dataset: str | Path,
    ner_dataset: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    """Refresh reports without retraining already persisted model artifacts."""
    root = Path(output_root)
    classifier_model = root / "campaign_classifier.joblib"
    classifier_test = evaluate_bundle(
        classifier_model,
        classifier_dataset,
        split="test",
        allow_auto_high_confidence=True,
    )
    _write_json(root / "classifier_test.json", classifier_test)

    candidates = []
    for config in NER_CANDIDATES:
        model_path = root / config["name"]
        neural = json.loads((model_path / "evaluation.json").read_text(encoding="utf-8"))
        hybrid = json.loads((model_path / "hybrid_validation.json").read_text(encoding="utf-8"))
        candidates.append(
            {
                "name": config["name"],
                "model_path": str(model_path),
                "config": config,
                "neural_validation_f1": neural["metrics"]["f1"],
                "hybrid_validation_f1": hybrid["metrics"]["f1"],
            }
        )
    winner = max(
        candidates,
        key=lambda item: (item["hybrid_validation_f1"], item["neural_validation_f1"]),
    )
    winning_model = Path(winner["model_path"])
    ner_test = evaluate_hybrid(winning_model, ner_dataset, "test", DEFAULT_RULE_LABELS)
    system_test = evaluate_system(
        classifier_dataset,
        ner_dataset,
        classifier_model=classifier_model,
        ner_model=winning_model,
        split="test",
    )
    _write_json(root / "ner_test.json", ner_test)
    _write_json(root / "system_test.json", system_test)

    manifest_path = root / "training_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "classifier_test": classifier_test,
            "ner_candidates": candidates,
            "selected_ner": winner,
            "ner_test": ner_test,
            "system_test": system_test,
        }
    )
    _write_json(manifest_path, manifest)
    return manifest


def run(
    classifier_dataset: str | Path,
    ner_dataset: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)

    classifier_model = root / "campaign_classifier.joblib"
    classifier_validation = train_bundle(
        classifier_dataset,
        classifier_model,
        train_split="train",
        evaluation_split="validation",
        allow_auto_high_confidence=True,
    )
    classifier_test = evaluate_bundle(
        classifier_model,
        classifier_dataset,
        split="test",
        allow_auto_high_confidence=True,
    )
    _write_json(root / "classifier_test.json", classifier_test)

    candidates = []
    for config in NER_CANDIDATES:
        model_path = root / config["name"]
        neural_validation = train_model(
            ner_dataset,
            model_path,
            train_split="train",
            evaluation_split="validation",
            epochs=config["epochs"],
            dropout=config["dropout"],
            rare_label_document_threshold=config["rare_label_document_threshold"],
            rare_example_multiplier=config["rare_example_multiplier"],
        )
        hybrid_validation = evaluate_hybrid(
            model_path,
            ner_dataset,
            "validation",
            DEFAULT_RULE_LABELS,
        )
        _write_json(model_path / "hybrid_validation.json", hybrid_validation)
        candidates.append(
            {
                "name": config["name"],
                "model_path": str(model_path),
                "config": config,
                "neural_validation_f1": neural_validation["metrics"]["f1"],
                "hybrid_validation_f1": hybrid_validation["metrics"]["f1"],
            }
        )

    winner = max(
        candidates,
        key=lambda item: (item["hybrid_validation_f1"], item["neural_validation_f1"]),
    )
    winning_model = Path(winner["model_path"])
    ner_test = evaluate_hybrid(winning_model, ner_dataset, "test", DEFAULT_RULE_LABELS)
    _write_json(root / "ner_test.json", ner_test)

    system_test = evaluate_system(
        classifier_dataset,
        ner_dataset,
        classifier_model=classifier_model,
        ner_model=winning_model,
        split="test",
    )
    _write_json(root / "system_test.json", system_test)

    manifest = {
        "selection_policy": (
            "architecture fixed by prior validation; NER candidate selected on "
            "unified validation; test used once"
        ),
        "classifier_dataset": str(classifier_dataset),
        "ner_dataset": str(ner_dataset),
        "classifier_model": str(classifier_model),
        "classifier_validation": classifier_validation,
        "classifier_test": classifier_test,
        "ner_candidates": candidates,
        "selected_ner": winner,
        "ner_test": ner_test,
        "system_test": system_test,
    }
    _write_json(root / "training_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--classifier-dataset",
        default="data/model_training_data/classifier_dataset_final.jsonl",
    )
    parser.add_argument(
        "--ner-dataset",
        default="data/model_training_data/ner_dataset_final.jsonl",
    )
    parser.add_argument("--output-root", default="models/final_training")
    parser.add_argument("--evaluation-only", action="store_true")
    args = parser.parse_args()
    runner = evaluate_existing if args.evaluation_only else run
    result = runner(args.classifier_dataset, args.ner_dataset, args.output_root)
    summary = {
        "classifier_product_accuracy": result["classifier_test"]["product_accuracy"],
        "selected_ner": result["selected_ner"],
        "ner_test_f1": result["ner_test"]["metrics"]["f1"],
        "competition_proxy_score": result["system_test"]["competition_proxy_score"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
