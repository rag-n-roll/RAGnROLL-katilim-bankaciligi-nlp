from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.training.create_unified_splits import (
    create_unified_splits,
    validate_unified_split_files,
)
from src.training.dataset_contract import (
    DEFAULT_MANIFEST_PATH,
    build_training_manifest,
    canonical_source_url,
    record_provenance,
    source_family_id,
    validate_source_family_splits,
    validate_training_manifest,
)


DATA_ROOT = Path("data/model_training_data")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _real(record_id: str, source_url: str | None, split: str) -> dict:
    return {"id": record_id, "source_url": source_url, "split": split}


def test_source_family_normalizes_tracking_fragment_and_host_case():
    first = _real(
        "first",
        " HTTPS://BANK.EXAMPLE/kampanya?campaign=42&utm_source=email#details ",
        "train",
    )
    second = _real(
        "second",
        "https://bank.example/kampanya?campaign=42&gclid=tracking",
        "train",
    )

    assert canonical_source_url(first) == "https://bank.example/kampanya?campaign=42"
    assert source_family_id(first) == source_family_id(second)


def test_source_family_preserves_functional_query_values():
    first = _real("first", "https://bank.example/kampanya?campaign=42", "train")
    second = _real("second", "https://bank.example/kampanya?campaign=43", "test")

    assert source_family_id(first) != source_family_id(second)


def test_source_family_normalizes_trailing_slash_and_query_order():
    first = _real(
        "first",
        "https://bank.example/kampanya/?sort=recent&campaign=42",
        "train",
    )
    second = _real(
        "second",
        "https://bank.example/kampanya?campaign=42&sort=recent",
        "train",
    )

    assert canonical_source_url(first) == (
        "https://bank.example/kampanya?campaign=42&sort=recent"
    )
    assert source_family_id(first) == source_family_id(second)


def test_real_record_without_source_url_fails_closed():
    with pytest.raises(ValueError, match="has no source_url"):
        source_family_id(_real("missing", None, "train"))


def test_controlled_template_is_never_counted_as_human():
    row = {
        "id": "synthetic-classifier-a",
        "source_url": None,
        "split": "train",
        "human_verified": True,
        "label_status": "synthetic_verified_template",
        "metadata": {
            "synthetic": True,
            "source_id": "campaign-a",
            "generation_method": "label_preserving_controlled_template",
        },
    }

    assert record_provenance(row) == "synthetic"


def test_family_validator_rejects_different_ids_from_one_url_across_splits():
    rows = [
        _real("campaign-a", "https://bank.example/campaign", "train"),
        _real(
            "campaign-b",
            "https://BANK.example/campaign?utm_medium=email#terms",
            "validation",
        ),
    ]

    with pytest.raises(ValueError, match="Source family crosses splits"):
        validate_source_family_splits({"classifier": rows})


def test_unified_split_aligns_tasks_by_family_and_keeps_synthetic_in_train(tmp_path):
    classifier = tmp_path / "classifier.jsonl"
    ner = tmp_path / "ner.jsonl"
    classifier_output = tmp_path / "classifier-final.jsonl"
    ner_output = tmp_path / "ner-final.jsonl"
    manifest = tmp_path / "manifest.json"
    family_url = "https://bank.example/campaign"
    _write_jsonl(
        classifier,
        [
            _real("campaign-a", family_url, "train"),
            _real("campaign-b", family_url + "?utm_source=email#terms", "train"),
            {
                "id": "synthetic-classifier-a",
                "source_url": None,
                "split": "test",
                "metadata": {"synthetic": True, "source_id": "campaign-a"},
            },
        ],
    )
    _write_jsonl(
        ner,
        [
            _real("ner-page", family_url, "validation"),
            {
                "id": "synthetic-ner-a",
                "source_id": "synthetic-ner-source-a",
                "source_url": None,
                "split": "test",
                "metadata": {"synthetic": True},
            },
        ],
    )

    report = create_unified_splits(
        classifier, ner, classifier_output, ner_output, manifest
    )
    classifier_rows = [json.loads(line) for line in classifier_output.read_text().splitlines()]
    ner_rows = [json.loads(line) for line in ner_output.read_text().splitlines()]

    assert report["source_family_cross_split"] == 0
    assert report["synthetic_non_train"] == 0
    assert {row["split"] for row in classifier_rows} == {"train"}
    assert {row["split"] for row in ner_rows} == {"train"}


def test_unified_split_rejects_synthetic_derived_from_held_out_classifier(tmp_path):
    classifier = tmp_path / "classifier.jsonl"
    ner = tmp_path / "ner.jsonl"
    _write_jsonl(
        classifier,
        [
            _real("campaign-test", "https://bank.example/held-out", "test"),
            {
                "id": "synthetic-classifier-test",
                "source_url": None,
                "split": "train",
                "metadata": {"synthetic": True, "source_id": "campaign-test"},
            },
        ],
    )
    _write_jsonl(ner, [_real("ner-a", "https://bank.example/a", "train")])

    with pytest.raises(ValueError, match="derives from held-out"):
        create_unified_splits(
            classifier,
            ner,
            tmp_path / "classifier-out.jsonl",
            tmp_path / "ner-out.jsonl",
            tmp_path / "manifest.json",
        )


def test_committed_final_datasets_are_family_safe_and_synthetic_train_only():
    report = validate_unified_split_files(
        DATA_ROOT / "classifier_dataset_final.jsonl",
        DATA_ROOT / "ner_dataset_final.jsonl",
    )

    assert report["source_family_cross_split"] == 0
    assert report["synthetic_non_train"] == 0
    assert report["source_families"] == 471


def test_training_manifest_matches_files_and_is_deterministic():
    first = build_training_manifest()
    second = build_training_manifest()

    assert first == second
    assert validate_training_manifest(DEFAULT_MANIFEST_PATH) == first
    assert first["independent_gold"] == {
        "status": "not_provided",
        "score": None,
        "reason": "No independently authored and reviewed holdout is committed.",
    }
    classifier = first["files"][
        "data/model_training_data/classifier_dataset_final.jsonl"
    ]
    assert classifier["record_kind_counts"] == {"real": 472, "synthetic": 170}
    assert classifier["provenance_counts"] == {
        "human": 57,
        "auto": 408,
        "synthetic": 170,
        "excluded": 7,
    }


def test_training_manifest_detects_file_digest_change(tmp_path):
    project = tmp_path / "project"
    for relative, _ in (
        ("data/model_training_data/classifier_campaigns_review.jsonl", "classification"),
        ("data/model_training_data/ner_dataset_approved.jsonl", "ner"),
        ("data/model_training_data/classifier_dataset_final.jsonl", "classification"),
        ("data/model_training_data/ner_dataset_final.jsonl", "ner"),
        (
            "data/model_training_data/target_audience_llm_large.jsonl",
            "target_audience_extraction",
        ),
        (
            "data/enrichment/context_entities_llm_large.jsonl",
            "context_entity_extraction",
        ),
    ):
        destination = project / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(Path(relative).read_bytes())
    schema = project / "data/model_training_data/campaign_nlp_output_schema.json"
    schema.write_bytes((DATA_ROOT / "campaign_nlp_output_schema.json").read_bytes())
    manifest_path = project / "manifest.json"
    manifest_path.write_text(
        json.dumps(build_training_manifest(project), ensure_ascii=False),
        encoding="utf-8",
    )
    classifier_path = project / "data/model_training_data/classifier_dataset_final.jsonl"
    classifier_path.write_bytes(classifier_path.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="does not match"):
        validate_training_manifest(manifest_path, project_root=project)
