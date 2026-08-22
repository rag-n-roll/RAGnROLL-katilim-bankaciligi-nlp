"""Train, evaluate and use a local spaCy NER model.

The input format is the repository JSONL schema: one document per line with
``text``, ``entities`` and ``split`` fields. Entity offsets are validated before
training so corrupt annotations fail fast instead of silently lowering scores.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def _json_default(value: Any) -> Any:
    """Convert NumPy scalar values returned by spaCy's scorer."""
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
            validate_record(record, line_number)
            records.append(record)
    if not records:
        raise ValueError(f"No NER records found in {path}")
    return records


def validate_record(record: dict[str, Any], line_number: int = 0) -> None:
    prefix = f"line {line_number}: " if line_number else ""
    text = record.get("text")
    entities = record.get("entities")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{prefix}text must be a non-empty string")
    if not isinstance(entities, list):
        raise ValueError(f"{prefix}entities must be a list")
    occupied: set[int] = set()
    for entity in entities:
        try:
            start = int(entity["start"])
            end = int(entity["end"])
            label = entity["label"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{prefix}malformed entity: {entity!r}") from exc
        if not isinstance(label, str) or not label:
            raise ValueError(f"{prefix}entity label must be non-empty")
        if not 0 <= start < end <= len(text):
            raise ValueError(f"{prefix}invalid entity offsets {start}:{end}")
        if "text" in entity and entity["text"] != text[start:end]:
            raise ValueError(
                f"{prefix}entity text mismatch at {start}:{end}: "
                f"{entity['text']!r} != {text[start:end]!r}"
            )
        positions = set(range(start, end))
        if occupied & positions:
            raise ValueError(f"{prefix}overlapping entity at {start}:{end}")
        occupied |= positions


def select_split(records: Iterable[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    selected = [record for record in records if record.get("split") == split]
    if not selected:
        available = sorted({str(record.get("split")) for record in records})
        raise ValueError(f"Split {split!r} is empty; available splits: {available}")
    return selected


def _examples(nlp: Any, records: Iterable[dict[str, Any]]) -> list[Any]:
    from spacy.training import Example

    examples = []
    for record in records:
        spans = [
            (entity["start"], entity["end"], entity["label"])
            for entity in record["entities"]
        ]
        examples.append(Example.from_dict(nlp.make_doc(record["text"]), {"entities": spans}))
    return examples


def score_model(nlp: Any, records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    from spacy.scorer import Scorer
    from spacy.training import Example

    examples = []
    for record in records:
        reference = _examples(nlp, [record])[0].reference
        examples.append(Example(nlp(record["text"]), reference))
    raw = Scorer().score(examples)
    return {
        "precision": raw["ents_p"],
        "recall": raw["ents_r"],
        "f1": raw["ents_f"],
        "per_entity": raw["ents_per_type"],
        "documents": len(examples),
    }


def train_model(
    dataset: str | Path,
    output_dir: str | Path,
    *,
    train_split: str = "train",
    evaluation_split: str = "validation",
    epochs: int = 20,
    batch_size: int = 32,
    dropout: float = 0.2,
    seed: int = 42,
    rare_label_document_threshold: int = 0,
    rare_example_multiplier: int = 1,
) -> dict[str, Any]:
    import spacy
    from spacy.util import fix_random_seed, minibatch

    if epochs < 1 or batch_size < 1 or rare_example_multiplier < 1:
        raise ValueError("epochs and batch_size must be positive")
    records = read_jsonl(dataset)
    train_records = select_split(records, train_split)
    evaluation_records = select_split(records, evaluation_split)
    fix_random_seed(seed)
    random.seed(seed)
    nlp = spacy.blank("tr")
    ner = nlp.add_pipe("ner")
    labels = sorted(
        {entity["label"] for record in train_records for entity in record["entities"]}
    )
    for label in labels:
        ner.add_label(label)
    label_document_counts = Counter(
        label
        for record in train_records
        for label in {entity["label"] for entity in record["entities"]}
    )
    examples = []
    oversampled_documents = 0
    for record in train_records:
        record_examples = _examples(nlp, [record])
        labels_in_record = {entity["label"] for entity in record["entities"]}
        is_rare = rare_label_document_threshold > 0 and any(
            label_document_counts[label] <= rare_label_document_threshold
            for label in labels_in_record
        )
        multiplier = rare_example_multiplier if is_rare else 1
        if multiplier > 1:
            oversampled_documents += 1
        examples.extend(record_examples * multiplier)
    optimizer = nlp.initialize(lambda: examples)
    losses: list[float] = []
    for _ in range(epochs):
        random.shuffle(examples)
        epoch_losses: dict[str, float] = {}
        for batch in minibatch(examples, size=batch_size):
            nlp.update(batch, sgd=optimizer, drop=dropout, losses=epoch_losses)
        losses.append(epoch_losses.get("ner", 0.0))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    nlp.to_disk(output)
    metrics = score_model(nlp, evaluation_records)
    synthetic = sum(bool(record.get("metadata", {}).get("synthetic")) for record in records)
    report = {
        "model": "spacy-blank-tr-ner",
        "train_split": train_split,
        "evaluation_split": evaluation_split,
        "train_documents": len(train_records),
        "labels": labels,
        "epochs": epochs,
        "seed": seed,
        "dropout": dropout,
        "rare_label_document_threshold": rare_label_document_threshold,
        "rare_example_multiplier": rare_example_multiplier,
        "oversampled_documents": oversampled_documents,
        "synthetic_documents": synthetic,
        "synthetic_data_warning": synthetic > 0,
        "metrics": metrics,
        "last_training_loss": losses[-1],
    }
    (output / "evaluation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return report


def evaluate_model(
    model_dir: str | Path, dataset: str | Path, *, split: str = "validation"
) -> dict[str, Any]:
    import spacy

    records = read_jsonl(dataset)
    selected = select_split(records, split)
    report = {
        "model_path": str(model_dir),
        "split": split,
        "synthetic_data_warning": any(
            bool(record.get("metadata", {}).get("synthetic")) for record in selected
        ),
        "metrics": score_model(spacy.load(model_dir), selected),
    }
    return report


def dataset_report(dataset: str | Path) -> dict[str, Any]:
    records = read_jsonl(dataset)
    return {
        "documents": len(records),
        "splits": dict(Counter(str(record.get("split")) for record in records)),
        "labels": dict(
            Counter(entity["label"] for record in records for entity in record["entities"])
        ),
        "synthetic_documents": sum(
            bool(record.get("metadata", {}).get("synthetic")) for record in records
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate JSONL and show distribution")
    validate.add_argument("dataset")
    train = commands.add_parser("train", help="Train and evaluate a spaCy NER model")
    train.add_argument("dataset")
    train.add_argument("output")
    train.add_argument("--epochs", type=int, default=20)
    train.add_argument("--batch-size", type=int, default=32)
    train.add_argument("--seed", type=int, default=42)
    train.add_argument("--dropout", type=float, default=0.2)
    train.add_argument("--rare-label-document-threshold", type=int, default=0)
    train.add_argument("--rare-example-multiplier", type=int, default=1)
    train.add_argument("--train-split", default="train")
    train.add_argument("--evaluation-split", default="validation")
    evaluate = commands.add_parser("evaluate", help="Evaluate an existing model")
    evaluate.add_argument("model")
    evaluate.add_argument("dataset")
    evaluate.add_argument("--split", default="validation")
    args = parser.parse_args()
    if args.command == "validate":
        result = dataset_report(args.dataset)
    elif args.command == "train":
        result = train_model(
            args.dataset,
            args.output,
            train_split=args.train_split,
            evaluation_split=args.evaluation_split,
            epochs=args.epochs,
            batch_size=args.batch_size,
            seed=args.seed,
            dropout=args.dropout,
            rare_label_document_threshold=args.rare_label_document_threshold,
            rare_example_multiplier=args.rare_example_multiplier,
        )
    else:
        result = evaluate_model(args.model, args.dataset, split=args.split)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))


if __name__ == "__main__":
    main()
