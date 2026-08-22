import json

import pytest

from src.classifier.main import load_examples
from src.classifier.prepare_campaign_data import prepare, suggest_annotations


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Konut finansmanında 120 ay vade", "housing_finance"),
        ("Yeni müşterilere hoş geldin kampanyası", "needs_review"),
        ("Kart alışverişlerinize 4 taksit", "card"),
        ("Altın katılma hesabı", "participation_account"),
        ("DASK sigortanızı mobil uygulamadan yaptırın", "insurance"),
        ("Katılım sigortacılığı ve tekafül ürünü", "takaful"),
    ],
)
def test_suggests_prd_campaign_product(text, expected):
    assert suggest_annotations(text)[0]["product_category"] == expected


def test_suggests_multiple_campaign_dimensions():
    annotations, _ = suggest_annotations(
        "Yeni müşteriler mobil uygulamada kartla alışverişe 500 TL nakit iade kazanır"
    )

    assert annotations["product_category"] == "card"
    assert annotations["campaign_mechanics"] == ["cashback"]
    assert annotations["target_segments"] == ["new_customer"]
    assert annotations["channels"] == ["mobile"]


def test_suggests_reward_points_as_mechanic_and_benefit():
    annotations, _ = suggest_annotations(
        "Albaraka kredi kartınızla 500 TL Worldpuan kazanın"
    )

    assert "reward_points" in annotations["campaign_mechanics"]
    assert "reward_points" in annotations["benefits"]


def test_suggests_distinct_installment_benefits():
    annotations, _ = suggest_annotations(
        "Peşin fiyatına 3 taksit ve mevcut taksitlere ek taksit fırsatı"
    )

    assert "installment" in annotations["benefits"]
    assert "no_extra_cost_installment" in annotations["benefits"]
    assert "additional_installment" in annotations["benefits"]
    assert "extra_installment" not in annotations["benefits"]


def test_suggests_discount_and_percentage_discount_benefits():
    annotations, _ = suggest_annotations("Online alışverişlerde %20 indirim fırsatı")

    assert "discount" in annotations["benefits"]
    assert "percentage_discount" in annotations["benefits"]


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
    assert row["annotations"]["product_category"] == "housing_finance"
    assert row["human_verified"] is False
    with pytest.raises(ValueError, match="No usable examples"):
        load_examples(output, require_verified=True, split=None)
