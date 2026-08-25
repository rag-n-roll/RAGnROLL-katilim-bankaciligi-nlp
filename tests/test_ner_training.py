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


def _ner_record(text, entities, split="train", **extra):
    return {"text": text, "entities": entities, "split": split, **extra}


def test_validate_record_error_paths():
    with pytest.raises(ValueError, match="text must be a non-empty string"):
        validate_record({"text": "  ", "entities": []})
    with pytest.raises(ValueError, match="entities must be a list"):
        validate_record({"text": "Metin", "entities": "yok"})
    with pytest.raises(ValueError, match="malformed entity"):
        validate_record({"text": "Metin", "entities": [{"start": 0}]})
    with pytest.raises(ValueError, match="entity label must be non-empty"):
        validate_record(
            {"text": "Metin", "entities": [{"start": 0, "end": 5, "label": ""}]}
        )
    with pytest.raises(ValueError, match="invalid entity offsets"):
        validate_record(
            {"text": "Kısa", "entities": [{"start": 2, "end": 2, "label": "X"}]}
        )
    with pytest.raises(ValueError, match="entity text mismatch"):
        validate_record(
            {
                "text": "Murabaha nedir",
                "entities": [
                    {"start": 0, "end": 8, "label": "PRODUCT", "text": "İcara"}
                ],
            }
        )
    with pytest.raises(ValueError, match="overlapping entity"):
        validate_record(
            {
                "text": "%5 kâr payı 12 ay",
                "entities": [
                    {"start": 0, "end": 4, "label": "PROFIT_RATE"},
                    {"start": 3, "end": 6, "label": "MATURITY"},
                ],
            }
        )


def test_read_jsonl_rejects_invalid_json_and_empty_files(tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"text": "ok", "entities": []}\n{broken\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON on line 2"):
        read_jsonl(bad)

    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n \n", encoding="utf-8")
    with pytest.raises(ValueError, match="No NER records found"):
        read_jsonl(empty)


def test_select_split_reports_available_splits():
    from src.ner.train import select_split

    records = [_ner_record("a", [], split="train"), _ner_record("b", [], split="test")]
    with pytest.raises(ValueError, match="available splits"):
        select_split(records, "validation")


def test_json_default_converts_numpy_like_scalars():
    from src.ner.train import _json_default

    class FakeNumpy:
        def item(self):
            return 3

    assert _json_default(FakeNumpy()) == 3
    with pytest.raises(TypeError, match="not JSON serializable"):
        _json_default(object())


def test_train_model_trains_scores_and_saves(tmp_path):
    from src.ner.train import train_model

    dataset = tmp_path / "ner.jsonl"
    rows = [
        _ner_record(
            f"%{i} kâr payı kampanyası",
            [{"start": 0, "end": 2 + (i == 10), "label": "PROFIT_RATE"}],
            split="train",
        )
        for i in range(1, 9)
    ]
    rows += [
        _ner_record(
            "12 ay vade fırsatı",
            [{"start": 0, "end": 5, "label": "MATURITY"}],
            split="validation",
        ),
        _ner_record(
            "24 ay vadeli finansman",
            [{"start": 0, "end": 5, "label": "MATURITY"}],
            split="validation",
        ),
    ]
    dataset.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    output_dir = tmp_path / "model"

    report = train_model(dataset, output_dir, epochs=2, batch_size=4, seed=7)

    assert (output_dir / "evaluation.json").exists()
    assert report["train_documents"] == 8
    assert set(report["labels"]) == {"PROFIT_RATE"}
    assert report["metrics"]["documents"] == 2
    assert report["competition_metric_eligible"] is False
    assert float(report["last_training_loss"]) >= 0.0


def test_evaluate_dataset_report_and_cli(tmp_path, capsys):
    import sys

    from src.ner.train import evaluate_model, main, train_model

    dataset = tmp_path / "ner.jsonl"
    entities = [{"start": 0, "end": 12, "label": "CONDITION"}]
    rows = [
        _ner_record("kart aidatı yok", entities, split="train"),
        _ner_record("kart aidatı yok", entities, split="validation"),
    ]
    dataset.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )

    def run(argv):
        original = sys.argv
        sys.argv = argv
        try:
            main()
        finally:
            sys.argv = original

    run(["main.py", "validate", str(dataset)])
    summary = json.loads(capsys.readouterr().out)
    assert summary["documents"] == 2
    assert summary["splits"] == {"train": 1, "validation": 1}
    assert summary["provenance_counts"] == {"auto": 2}

    model_dir = tmp_path / "model"
    train_model(dataset, model_dir, epochs=1)

    report = evaluate_model(model_dir, dataset, split="validation")
    assert report["split"] == "validation"
    assert report["metrics"]["documents"] == 1

    run(["main.py", "evaluate", str(model_dir), str(dataset), "--split", "validation"])
    cli_report = json.loads(capsys.readouterr().out)
    assert cli_report["split"] == "validation"
