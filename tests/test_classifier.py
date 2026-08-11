import json

import pytest

from src.classifier.main import load_examples
from src.classifier.prepare_campaign_data import prepare, suggest_label


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Konut finansmanında 120 ay vade", "housing_finance"),
        ("Yeni müşterilere hoş geldin kampanyası", "new_customer"),
        ("Kart alışverişlerinize 4 taksit", "card_campaign"),
        ("Altın katılma hesabı", "investment_product"),
    ],
)
def test_suggests_prd_campaign_label(text, expected):
    assert suggest_label(text)[0] == expected


def test_prepare_requires_human_verification(tmp_path):
    source = tmp_path / "campaigns.json"
    output = tmp_path / "annotations.jsonl"
    source.write_text(
        json.dumps([{"id": "1", "title": "Konut finansmanı", "content": "120 ay"}]),
        encoding="utf-8",
    )
    report = prepare(source, output)
    row = json.loads(output.read_text(encoding="utf-8"))

    assert report["human_verification_required"] is True
    assert row["label"] == "housing_finance"
    assert row["human_verified"] is False
    with pytest.raises(ValueError, match="No usable examples"):
        load_examples(output, require_verified=True, split=None)
