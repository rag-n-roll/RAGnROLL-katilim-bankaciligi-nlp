import json

import pytest

from src.training.create_unified_splits import (
    create_unified_splits,
    validate_unified_split_files,
)


def _row(id, source_url, split, **extra):
    return {"id": id, "text": f"metin {id}", "source_url": source_url, "split": split, **extra}


def _synthetic_row(id, source_id, split="train", **extra):
    return {
        "id": id,
        "text": f"şablon {id}",
        "split": split,
        "metadata": {"synthetic": True, "source_id": source_id},
        **extra,
    }


def _write(path, rows):
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _ner_file(tmp_path):
    ner = tmp_path / "n.jsonl"
    _write(ner, [_row("n1", "https://a.example/x", "train")])
    return ner


def test_rejects_invalid_split(tmp_path):
    classifier = tmp_path / "c.jsonl"
    _write(classifier, [_row("1", "https://a.example/x", "holdout")])
    ner = _ner_file(tmp_path)

    with pytest.raises(ValueError, match="invalid split"):
        create_unified_splits(classifier, ner, tmp_path / "co", tmp_path / "no", tmp_path / "m")


def test_rejects_family_split_conflict(tmp_path):
    url = "https://a.example/same-page"
    classifier = tmp_path / "c.jsonl"
    _write(
        classifier,
        [_row("1", url, "train"), _row("2", url + "#farkli", "test")],
    )
    ner = _ner_file(tmp_path)

    with pytest.raises(ValueError, match="occurs in train and test"):
        create_unified_splits(classifier, ner, tmp_path / "co", tmp_path / "no", tmp_path / "m")


def test_rejects_synthetic_row_without_source_id(tmp_path):
    classifier = tmp_path / "c.jsonl"
    _write(classifier, [{"text": "şablon", "split": "train", "metadata": {"synthetic": True}}])
    ner = _ner_file(tmp_path)

    with pytest.raises(ValueError, match="has no source_id"):
        create_unified_splits(classifier, ner, tmp_path / "co", tmp_path / "no", tmp_path / "m")


def test_realigned_synthetic_rows_are_counted_and_forced_to_train(tmp_path):
    classifier = tmp_path / "c.jsonl"
    rows = [
        _row("1", "https://a.example/x", "train"),
        _synthetic_row("s1", "1", split="validation"),
    ]
    _write(classifier, rows)
    ner = tmp_path / "n.jsonl"
    _write(ner, [_synthetic_row("ns1", "1", split="validation")])

    report = create_unified_splits(
        classifier, ner, tmp_path / "co.jsonl", tmp_path / "no.jsonl", tmp_path / "m.json"
    )

    assert report["realigned_classifier_records"] == 1
    assert report["realigned_ner_records"] == 1
    out_rows = [
        json.loads(line)
        for line in (tmp_path / "co.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all(row["split"] == "train" for row in out_rows)


def test_ner_family_missing_from_classifier_falls_back_to_hash_split(tmp_path):
    classifier = tmp_path / "c.jsonl"
    _write(classifier, [_row("1", "https://a.example/x", "train")])
    ner = tmp_path / "n.jsonl"
    _write(ner, [_row("n1", "https://b.example/y", "train")])

    report = create_unified_splits(
        classifier, ner, tmp_path / "co.jsonl", tmp_path / "no.jsonl", tmp_path / "m.json"
    )

    assert report["ner_families_missing_from_classifier"] == 1
    assert report["classifier_splits"] == {"train": 1}
    assert set(report["ner_splits"]) <= {"train", "validation", "test"}
    assert report["policy"].startswith("canonical_source_family")


def test_validate_round_trips_written_files(tmp_path):
    classifier = tmp_path / "c.jsonl"
    _write(classifier, [_row("1", "https://a.example/x", "train")])
    ner = tmp_path / "n.jsonl"
    _write(ner, [_row("n1", "https://a.example/x", "train")])

    create_unified_splits(
        classifier, ner, tmp_path / "co.jsonl", tmp_path / "no.jsonl", tmp_path / "m.json"
    )
    invariant = validate_unified_split_files(
        tmp_path / "co.jsonl", tmp_path / "no.jsonl"
    )

    assert invariant["synthetic_records"] == 0


def _run_cli(argv):
    import sys

    from src.training.create_unified_splits import main

    original = sys.argv
    sys.argv = argv
    try:
        return main()
    finally:
        sys.argv = original


def test_cli_create_and_validate(tmp_path, capsys):
    classifier = tmp_path / "c.jsonl"
    _write(classifier, [_row("1", "https://a.example/x", "train")])
    ner = tmp_path / "n.jsonl"
    _write(ner, [_row("n1", "https://a.example/x", "validation")])
    manifest = tmp_path / "manifest.json"

    _run_cli([
        "splits.py", "create",
        "--classifier-input", str(classifier),
        "--ner-input", str(ner),
        "--classifier-output", str(tmp_path / "co.jsonl"),
        "--ner-output", str(tmp_path / "no.jsonl"),
        "--manifest-output", str(manifest),
    ])
    created = json.loads(capsys.readouterr().out)
    assert manifest.exists()
    assert created["realigned_ner_records"] == 1

    _run_cli([
        "splits.py", "validate",
        "--classifier", str(tmp_path / "co.jsonl"),
        "--ner", str(tmp_path / "no.jsonl"),
    ])
    validated = json.loads(capsys.readouterr().out)
    for key, value in validated.items():
        assert created[key] == value
