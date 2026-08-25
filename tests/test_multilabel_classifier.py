import json

import pytest

from src.classifier.multilabel import (
    load_multidimensional_examples,
    train_bundle,
)


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


def test_controlled_template_requires_explicit_synthetic_opt_in(tmp_path):
    path = tmp_path / "campaigns.jsonl"
    row = {
        "id": "synthetic-classifier-a",
        "text": "Kontrollü şablon kart kampanyası",
        "annotations": annotation(),
        "human_verified": True,
        "label_status": "synthetic_verified_template",
        "training_eligible": True,
        "split": "train",
        "metadata": {"synthetic": True, "source_id": "campaign-a"},
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="No verified"):
        load_multidimensional_examples(path, split="train")

    texts, _ = load_multidimensional_examples(
        path, split="train", allow_synthetic=True
    )
    assert texts == ["Kontrollü şablon kart kampanyası"]


def _annotation_set(variant: int) -> dict:
    mechanics = ["cashback", "discount", "installment"]
    segments = ["new_customer", "existing_customer", "salary_customer"]
    channels = ["mobile", "physical_branch", "internet_branch"]
    benefits = ["cashback", "percentage_discount", "fee_exemption"]
    requirements = ["date_limited", "minimum_spend", "first_transaction"]
    index = variant % 3
    return {
        "product_category": ("card", "housing_finance", "vehicle_finance")[index],
        "campaign_mechanics": [mechanics[index]],
        "target_segments": [segments[index]],
        "channels": [channels[index]],
        "benefits": [benefits[index]],
        "requirements": [requirements[index]],
    }


def _bundle_dataset(path):
    rows = []
    for i in range(9):
        rows.append(
            {
                "id": f"train-{i}",
                "text": f"kart kampanyası örnek metin {i}",
                "annotations": _annotation_set(i),
                "human_verified": True,
                "split": "train",
            }
        )
    for i in range(3):
        rows.append(
            {
                "id": f"val-{i}",
                "text": f"validation kampanya metni {i}",
                "annotations": _annotation_set(i),
                "human_verified": True,
                "split": "validation",
            }
        )
    for i in range(2):
        rows.append(
            {
                "id": f"test-{i}",
                "text": f"test kampanya metni {i}",
                "annotations": _annotation_set(i),
                "human_verified": True,
                "split": "test",
            }
        )
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_train_bundle_trains_product_and_field_models(tmp_path):
    dataset = tmp_path / "campaigns.jsonl"
    _bundle_dataset(dataset)
    output = tmp_path / "bundle.joblib"

    report = train_bundle(dataset, output)

    assert output.exists()
    assert (tmp_path / "bundle.metrics.json").exists()
    assert report["train_examples"] == 9
    assert report["evaluation_examples"] == 3
    assert report["competition_metric_eligible"] is True
    assert report["evaluation_metric_kind"] == "human_labeled"
    assert set(report["dimensions"]) == {
        "campaign_mechanics",
        "target_segments",
        "channels",
        "benefits",
        "requirements",
    }
    assert 0.0 <= report["product_accuracy"] <= 1.0


def test_train_bundle_skips_fields_with_single_label(tmp_path):
    dataset = tmp_path / "campaigns.jsonl"
    rows = [
        {
            "id": f"{split}-{i}",
            "text": f"{split} metni {i}",
            "annotations": annotation(),
            "human_verified": True,
            "split": split,
        }
        for split in ("train", "train", "train", "validation")
        for i in [0]
    ]
    rows[0]["annotations"]["product_category"] = "card"
    rows[1]["annotations"]["product_category"] = "housing_finance"
    rows[2]["annotations"]["product_category"] = "card"
    path = dataset
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    report = train_bundle(dataset, tmp_path / "bundle.joblib")

    assert report["skipped_fields"] == {
        field: "fewer_than_two_observed_labels"
        for field in (
            "campaign_mechanics",
            "target_segments",
            "channels",
            "benefits",
            "requirements",
        )
    }
    assert report["dimensions"] == {}


def test_evaluate_bundle_reports_split_and_provenance_counts(tmp_path):
    import joblib

    from src.classifier.multilabel import evaluate_bundle

    dataset = tmp_path / "campaigns.jsonl"
    _bundle_dataset(dataset)
    train_bundle(dataset, tmp_path / "bundle.joblib")

    bundle = joblib.load(tmp_path / "bundle.joblib")
    report = evaluate_bundle(tmp_path / "bundle.joblib", dataset, split="test")

    assert report["split"] == "test"
    assert report["evaluation_examples"] == 2
    assert set(report["available_provenance_counts"]) == {"human"}
    assert isinstance(bundle["product_model"], object)


def test_train_bundle_requires_two_product_categories(tmp_path):
    dataset = tmp_path / "campaigns.jsonl"
    rows = [
        {
            "id": f"{split}-{i}",
            "text": f"{split} metni {i}",
            "annotations": annotation(),
            "human_verified": True,
            "split": split,
        }
        for split, i in (("train", 0), ("train", 1), ("validation", 0))
    ]
    dataset.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="at least two product categories"):
        train_bundle(dataset, tmp_path / "bundle.joblib")


def test_cli_train_and_evaluate(tmp_path, capsys):
    import sys

    from src.classifier.multilabel import main

    dataset = tmp_path / "campaigns.jsonl"
    _bundle_dataset(dataset)
    output = tmp_path / "bundle.joblib"

    def run(argv):
        original = sys.argv
        sys.argv = argv
        try:
            main()
        finally:
            sys.argv = original

    run(["main.py", "train", str(dataset), str(output), "--evaluation-split", "validation"])
    train_report = json.loads(capsys.readouterr().out)
    assert train_report["evaluation_metric_kind"] == "human_labeled"
    assert output.exists()

    run(
        [
            "main.py",
            "evaluate",
            str(output),
            str(dataset),
            "--split",
            "test",
            "--allow-synthetic",
        ]
    )
    eval_report = json.loads(capsys.readouterr().out)
    assert eval_report["evaluation_metric_kind"] == "proxy"
    assert eval_report["competition_metric_eligible"] is False
