from __future__ import annotations

import json

from src.extraction.enrich_campaigns_for_rag import _rag_field_contracts
from src.training.create_unified_splits import create_unified_splits


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_unified_split_aligns_tasks_and_keeps_synthetic_in_train(tmp_path):
    classifier = tmp_path / "classifier.jsonl"
    ner = tmp_path / "ner.jsonl"
    classifier_output = tmp_path / "classifier-final.jsonl"
    ner_output = tmp_path / "ner-final.jsonl"
    manifest = tmp_path / "manifest.json"
    _write_jsonl(
        classifier,
        [
            {"id": "campaign-a", "split": "test"},
            {
                "id": "synthetic-classifier-a",
                "split": "train",
                "metadata": {"synthetic": True, "source_id": "campaign-b"},
            },
            {"id": "campaign-b", "split": "train"},
        ],
    )
    _write_jsonl(
        ner,
        [
            {"id": "campaign-a", "split": "train"},
            {"id": "campaign-b", "split": "validation"},
            {
                "id": "synthetic-ner-a",
                "split": "test",
                "metadata": {"synthetic": True},
            },
        ],
    )

    report = create_unified_splits(
        classifier, ner, classifier_output, ner_output, manifest
    )
    ner_rows = [json.loads(line) for line in ner_output.read_text(encoding="utf-8").splitlines()]

    assert report["cross_task_split_mismatches"] == 0
    assert report["realigned_ner_records"] == 2
    assert {row["id"]: row["split"] for row in ner_rows} == {
        "campaign-a": "test",
        "campaign-b": "train",
        "synthetic-ner-a": "train",
    }


def test_rag_contracts_include_classifier_and_entity_evidence():
    analysis = {
        "classification": {
            "product_category": {
                "value": "card",
                "confidence": 0.91,
                "evidence": "Kredi kartınızla alışveriş yapın.",
            },
            "dimensions": {
                "target_segments": [],
                "channels": [{"value": "mobile", "confidence": 0.88}],
            },
        },
        "entities": [
            {
                "start": 10,
                "end": 17,
                "text": "1.000 TL",
                "label": "KAMPANYA_KOSULU",
                "confidence": 0.79,
                "source": "deterministic_rule",
                "normalized": {"type": "money", "amount": 1000, "currency": "TRY"},
            }
        ],
    }
    fields = _rag_field_contracts(analysis, {"product_type": "card"})

    assert fields["product_type"]["method"] == "classifier+mapping"
    assert fields["condition"]["evidence"]["char_start"] == 10
    assert fields["application_channel"]["value"] == ["mobile"]
