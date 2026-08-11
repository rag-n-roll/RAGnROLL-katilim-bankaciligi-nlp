import json

import pytest

from src.annotation.store import (
    ConcurrentUpdateError,
    approve_annotation,
    dataset_progress,
    load_records,
    reject_annotation,
    save_records,
    submit_annotation,
)


def sample_records():
    return [
        {
            "id": "campaign-1",
            "text": "Yeni müşterilere özel kampanya",
            "label": "new_customer",
            "split": None,
            "human_verified": False,
        }
    ]


def test_two_person_annotation_and_approval():
    records = sample_records()
    submit_annotation(
        records,
        "campaign-1",
        annotator="Dilan",
        label="new_customer",
        split="test",
    )
    approved = approve_annotation(records, "campaign-1", reviewer="Kutay")

    assert approved["human_verified"] is True
    assert approved["review_status"] == "approved"
    assert [event["action"] for event in approved["annotation_history"]] == [
        "annotated",
        "approved",
    ]


def test_annotator_cannot_review_own_record():
    records = sample_records()
    submit_annotation(
        records,
        "campaign-1",
        annotator="Dilan",
        label="new_customer",
        split="train",
    )

    with pytest.raises(ValueError, match="different"):
        approve_annotation(records, "campaign-1", reviewer="dilan")


def test_needs_review_cannot_be_approved():
    records = sample_records()
    submit_annotation(
        records,
        "campaign-1",
        annotator="Dilan",
        label="needs_review",
        split="validation",
    )

    with pytest.raises(ValueError, match="must be resolved"):
        approve_annotation(records, "campaign-1", reviewer="Elif")


def test_rejection_requires_note_and_marks_changes_requested():
    records = sample_records()
    submit_annotation(
        records,
        "campaign-1",
        annotator="Dilan",
        label="new_customer",
        split="train",
    )
    rejected = reject_annotation(
        records, "campaign-1", reviewer="Gizem", note="Kart kampanyası olabilir"
    )

    assert rejected["review_status"] == "changes_requested"
    assert rejected["human_verified"] is False


def test_atomic_save_detects_concurrent_update(tmp_path):
    path = tmp_path / "annotations.jsonl"
    path.write_text(json.dumps(sample_records()[0]) + "\n", encoding="utf-8")
    records, digest = load_records(path)
    path.write_text(json.dumps({"id": "changed"}) + "\n", encoding="utf-8")

    with pytest.raises(ConcurrentUpdateError):
        save_records(path, records, expected_digest=digest)


def test_dataset_progress():
    records = sample_records()
    submit_annotation(
        records,
        "campaign-1",
        annotator="Dilan",
        label="new_customer",
        split="train",
    )
    approve_annotation(records, "campaign-1", reviewer="Kutay")

    progress = dataset_progress(records)
    assert progress["verified"] == 1
    assert progress["verified_splits"] == {"train": 1}
