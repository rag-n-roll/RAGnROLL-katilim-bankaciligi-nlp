import json

import pytest

from src.classifier.main import (
    build_pipeline,
    classification_metrics,
    evaluate_model,
    load_examples,
    read_records,
    train_model,
)


def _write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_read_records_supports_jsonl_csv_and_json(tmp_path):
    jsonl = tmp_path / "a.jsonl"
    _write_jsonl(jsonl, [{"id": "1"}, {"id": "2"}])
    assert [r["id"] for r in read_records(jsonl)] == ["1", "2"]

    csv_path = tmp_path / "b.csv"
    csv_path.write_text("id,text\n1,Kampanya\n", encoding="utf-8")
    assert read_records(csv_path)[0]["text"] == "Kampanya"

    json_list = tmp_path / "c.json"
    json_list.write_text('[{"id": "9"}]', encoding="utf-8")
    assert read_records(json_list)[0]["id"] == "9"


def test_read_records_reads_records_and_campaigns_keys(tmp_path):
    records_key = tmp_path / "records.json"
    records_key.write_text('{"records": [{"id": "1"}]}', encoding="utf-8")
    assert read_records(records_key)[0]["id"] == "1"

    campaigns_key = tmp_path / "campaigns.json"
    campaigns_key.write_text('{"campaigns": [{"id": "2"}]}', encoding="utf-8")
    assert read_records(campaigns_key)[0]["id"] == "2"

    bare_object = tmp_path / "bare.json"
    bare_object.write_text('{"id": "3"}', encoding="utf-8")
    with pytest.raises(ValueError, match="No records found"):
        read_records(bare_object)


def test_read_records_rejects_empty_input(tmp_path):
    empty = tmp_path / "empty.jsonl"
    _write_jsonl(empty, [])
    with pytest.raises(ValueError, match="No records found"):
        read_records(empty)


def test_load_examples_filters_split_verification_and_blank_rows(tmp_path):
    path = tmp_path / "dataset.jsonl"
    _write_jsonl(
        path,
        [
            {"text": "Kart kampanyası", "label": "card", "split": "train", "human_verified": True},
            {
                "text": "Konut finansmanı",
                "label": "housing_finance",
                "split": "train",
                "human_verified": True,
            },
            {
                "text": "Doğrulanmamış",
                "label": "card",
                "split": "train",
                "human_verified": False,
            },
            {"text": "   ", "label": "card", "split": "train"},
            {"text": "Yanlış split", "label": "card", "split": "validation"},
        ],
    )

    texts, labels, metadata = load_examples(path, split="train", require_verified=True)
    assert texts == ["Kart kampanyası", "Konut finansmanı"]
    assert labels == ["card", "housing_finance"]

    texts_all, labels_all, _ = load_examples(path)
    assert len(texts_all) == 4
    assert sorted(labels_all) == ["card", "card", "card", "housing_finance"]


def test_load_examples_reads_nested_fields_and_rejects_single_label(tmp_path):
    nested = tmp_path / "nested.json"
    nested.write_text(
        json.dumps(
            [
                {"data": {"text": "A metni"}, "meta": {"label": "card"}},
                {"data": {"text": "B metni"}, "meta": {"label": "other"}},
            ]
        ),
        encoding="utf-8",
    )
    texts, labels, _ = load_examples(
        nested, text_field="data.text", label_field="meta.label", split=None
    )
    assert labels == ["card", "other"]

    single = tmp_path / "single.jsonl"
    _write_jsonl(single, [{"text": "Tek sınıf", "label": "card"}])
    with pytest.raises(ValueError, match="at least two labels"):
        load_examples(single)

    unusable = tmp_path / "unusable.jsonl"
    _write_jsonl(unusable, [{"text": None, "label": "card"}])
    with pytest.raises(ValueError, match="No usable examples"):
        load_examples(unusable)


def test_build_pipeline_predicts_after_fit():
    pipeline = build_pipeline(min_df=1)
    texts = ["kart taksit fırsatı", "konut finansmanı kampanyası"] * 4
    pipeline.fit(texts, ["a", "b"] * 4)
    predictions = pipeline.predict(texts[:2])
    assert set(predictions) == {"a", "b"}


def test_classification_metrics_computes_confusion_and_scores():
    metrics = classification_metrics(
        ["card", "other"], ["card", "card"]
    )
    assert metrics["accuracy"] == 0.5
    assert metrics["labels"] == ["card", "other"]
    assert metrics["confusion_matrix"] == [[1, 0], [1, 0]]
    assert "macro_f1" in metrics and "weighted_f1" in metrics


def test_train_model_uses_stratified_holdout_when_no_eval_dataset(tmp_path):
    train_path = tmp_path / "train.jsonl"
    rows = [
        {"text": f"kart kampanyası {i}", "label": "card"} for i in range(4)
    ] + [
        {"text": f"konut finansmanı {i}", "label": "housing_finance"} for i in range(4)
    ]
    _write_jsonl(train_path, rows)

    report = train_model(train_path, tmp_path / "model.joblib")

    output = tmp_path / "model.joblib"
    assert output.exists()
    assert (tmp_path / "model.metrics.json").exists()
    assert report["evaluation_split"] == "stratified_holdout_20_percent"
    assert report["training_examples"] == 6
    assert report["synthetic_data_warning"] is False


def test_train_model_with_separate_evaluation_dataset(tmp_path):
    train_path = tmp_path / "train.jsonl"
    _write_jsonl(
        train_path,
        [
            {"text": "kart kampanyası", "label": "card"},
            {"text": "kredi kartı taksit", "label": "card"},
            {"text": "konut finansmanı", "label": "housing_finance"},
            {"text": "ev kredisi", "label": "housing_finance"},
        ],
    )
    eval_path = tmp_path / "eval.jsonl"
    _write_jsonl(
        eval_path,
        [
            {
                "text": "yeni kart kampanyası",
                "label": "card",
                "split": "validation",
                "metadata": {"synthetic": True},
            },
            {
                "text": "konut finansmanı başvurusu",
                "label": "housing_finance",
                "split": "validation",
            },
        ],
    )

    report = train_model(train_path, tmp_path / "m.joblib", evaluation_path=eval_path)

    assert "evaluation" in report
    assert report["evaluation"]["accuracy"] >= 0.0
    assert "evaluation_split" not in report

    result = evaluate_model(tmp_path / "m.joblib", eval_path, split="validation")
    assert result["examples"] == 2
    assert result["synthetic_data_warning"] is True


def _run_cli(module_main, argv):
    import sys

    original = sys.argv
    sys.argv = argv
    try:
        module_main()
    finally:
        sys.argv = original


def test_cli_train_and_evaluate(tmp_path, capsys):
    from src.classifier.main import main

    train_path = tmp_path / "train.jsonl"
    _write_jsonl(
        train_path,
        [
            {"text": f"kart kampanyası {i}", "label": "card"} for i in range(4)
        ]
        + [
            {"text": f"konut finansmanı {i}", "label": "housing_finance"}
            for i in range(4)
        ],
    )
    output = tmp_path / "model.joblib"

    _run_cli(
        main,
        [
            "main.py",
            "train",
            str(train_path),
            str(output),
            "--seed",
            "7",
        ],
    )
    train_result = json.loads(capsys.readouterr().out)
    assert train_result["seed"] == 7
    assert output.exists()

    eval_path = tmp_path / "eval.jsonl"
    _write_jsonl(
        eval_path,
        [
            {"text": "yeni kart kampanyası", "label": "card", "split": "validation"},
            {
                "text": "konut finansmanı başvurusu",
                "label": "housing_finance",
                "split": "validation",
            },
        ],
    )
    _run_cli(
        main,
        ["main.py", "evaluate", str(output), str(eval_path), "--split", "validation"],
    )
    eval_result = json.loads(capsys.readouterr().out)
    assert eval_result["examples"] == 2
