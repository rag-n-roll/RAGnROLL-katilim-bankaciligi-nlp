import json

import pytest

from src.ner.train import dataset_report, read_jsonl, validate_record
from src.ner.prepare_campaign_ner import prepare


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


def test_ner_preparation_groups_canonical_source_variants(tmp_path):
    source = tmp_path / "campaigns.json"
    output = tmp_path / "ner.jsonl"
    source.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "id": "campaign-a",
                        "bank_name": "Örnek Bank",
                        "title": "Kart kampanyası",
                        "content": "En az 500 TL harcama yapın.",
                        "source_url": (
                            "https://bank.example/campaign/?sort=recent&campaign=42"
                        ),
                    },
                    {
                        "id": "campaign-b",
                        "bank_name": "Örnek Bank",
                        "title": "Kart kampanyası",
                        "content": "En az 500 TL harcama yapın.",
                        "source_url": (
                            "https://BANK.example/campaign?campaign=42&sort=recent"
                            "&utm_source=email#details"
                        ),
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    prepare(source, output)
    rows = [json.loads(line) for line in output.read_text().splitlines()]

    assert len({row["split"] for row in rows}) == 1


def test_ner_preparation_rejects_real_record_without_source_url(tmp_path):
    source = tmp_path / "campaigns.json"
    source.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "id": "campaign-a",
                        "bank_name": "Örnek Bank",
                        "title": "Kart kampanyası",
                        "content": "En az 500 TL harcama yapın.",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="has no source_url"):
        prepare(source, tmp_path / "ner.jsonl")
