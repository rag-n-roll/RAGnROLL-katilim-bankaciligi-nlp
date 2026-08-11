import json

import pytest

from src.classifier.multilabel import load_multidimensional_examples


def annotation(product="card"):
    return {
        "product_category": product,
        "campaign_mechanics": ["cashback"],
        "target_segments": ["new_customer"],
        "channels": ["mobile"],
        "benefits": [],
        "requirements": ["date_limited"],
    }


def test_loads_only_verified_requested_split(tmp_path):
    path = tmp_path / "campaigns.jsonl"
    rows = [
        {
            "id": "1",
            "text": "Kart kampanyası",
            "annotations": annotation(),
            "human_verified": True,
            "split": "train",
        },
        {
            "id": "2",
            "text": "Konut kampanyası",
            "annotations": annotation("housing_finance"),
            "human_verified": False,
            "split": "train",
        },
    ]
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    texts, annotations = load_multidimensional_examples(path, split="train")
    assert texts == ["Kart kampanyası"]
    assert annotations[0]["product_category"] == "card"


def test_rejects_empty_verified_split(tmp_path):
    path = tmp_path / "campaigns.jsonl"
    row = {
        "id": "1",
        "text": "Kart kampanyası",
        "annotations": annotation(),
        "human_verified": False,
        "split": "test",
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="No verified"):
        load_multidimensional_examples(path, split="test")
