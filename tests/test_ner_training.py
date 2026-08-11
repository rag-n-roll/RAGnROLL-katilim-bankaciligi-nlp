import json

import pytest

from src.ner.train import dataset_report, read_jsonl, validate_record


def test_validates_and_summarizes_ner_jsonl(tmp_path):
    path = tmp_path / "ner.jsonl"
    rows = [
        {
            "text": "Kuveyt Türk %1,89",
            "entities": [
                {"start": 0, "end": 11, "text": "Kuveyt Türk", "label": "BANK"},
                {"start": 12, "end": 17, "text": "%1,89", "label": "PROFIT_RATE"},
            ],
            "split": "train",
            "metadata": {"synthetic": False},
        }
    ]
    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(content, encoding="utf-8")

    assert len(read_jsonl(path)) == 1
    report = dataset_report(path)
    assert report["splits"] == {"train": 1}
    assert report["labels"] == {"BANK": 1, "PROFIT_RATE": 1}


def test_rejects_wrong_entity_text():
    with pytest.raises(ValueError, match="entity text mismatch"):
        validate_record(
            {
                "text": "Kuveyt Türk",
                "entities": [{"start": 0, "end": 6, "text": "Ziraat", "label": "BANK"}],
            }
        )
