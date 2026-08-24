from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.prompt_optimization.dataset import (
    DEFAULT_MANIFEST_PATH,
    DEFAULT_OUTPUT_PATH,
    build_examples,
    read_jsonl,
    validate_committed_dataset,
    write_examples_and_manifest,
)
from src.prompt_optimization.evaluation import score_answer, summarize_proxy_scores


def _classifier(
    record_id: str,
    url: str | None,
    *,
    human: bool = False,
    synthetic: bool = False,
) -> dict:
    row = {
        "id": record_id,
        "text": "Kart kampanyasında 500 TL Worldpuan kazanın.",
        "source_url": url,
        "annotations": {
            "product_category": "card",
            "campaign_mechanics": ["reward_points"],
            "target_segments": ["cardholder"],
            "channels": ["mobile"],
            "benefits": ["reward_points"],
            "requirements": ["minimum_spend"],
        },
        "human_verified": human,
        "label_status": "human_approved" if human else "auto_high_confidence",
        "training_eligible": True,
    }
    if synthetic:
        row["human_verified"] = True
        row["label_status"] = "synthetic_verified_template"
        row["metadata"] = {"synthetic": True, "source_id": "source-a"}
    return row


def _ner(record_id: str, url: str, *, human: bool = False) -> dict:
    return {
        "id": record_id,
        "source_id": record_id,
        "source_url": url,
        "text": "Örnek Bank kampanyasında 500 TL kazanın.",
        "entities": [
            {"start": 0, "end": 10, "text": "Örnek Bank", "label": "BANKA"},
            {"start": 25, "end": 31, "text": "500 TL", "label": "ODUL_MIKTARI"},
        ],
        "metadata": {
            "label_status": "human_approved" if human else "auto_high_confidence",
            "human_verified": human,
        },
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_same_canonical_source_family_with_different_ids_never_crosses_splits():
    url = "https://bank.example/campaign"
    examples = build_examples(
        [
            _classifier("classifier-a", url),
            _classifier("classifier-b", url + "?utm_source=email#details"),
        ],
        [_ner("ner-c", "HTTPS://BANK.EXAMPLE/campaign?gclid=tracking")],
    )

    assert {item["campaign_id"] for item in examples} == {
        "classifier-a",
        "classifier-b",
        "ner-c",
    }
    assert len({item["source_family_id"] for item in examples}) == 1
    assert len({item["split"] for item in examples}) == 1


def test_classifier_and_ner_tasks_for_same_campaign_share_family_and_split():
    url = "https://bank.example/campaign/one"
    examples = build_examples(
        [_classifier("campaign-a", url, human=True)],
        [_ner("campaign-a", url, human=False)],
    )

    assert len(examples) == 2
    assert len({item["source_family_id"] for item in examples}) == 1
    assert len({item["split"] for item in examples}) == 1
    assert {item["reference_provenance"] for item in examples} == {"human", "auto"}
    assert {item["reference_kind"] for item in examples} == {
        "derived_label_projection"
    }


def test_mismatched_classifier_and_ner_urls_for_same_id_fail_closed():
    with pytest.raises(ValueError, match="multiple source families"):
        build_examples(
            [_classifier("campaign-a", "https://bank.example/a")],
            [_ner("campaign-a", "https://bank.example/b")],
        )


def test_missing_real_source_url_fails_closed():
    with pytest.raises(ValueError, match="has no source_url"):
        build_examples([_classifier("campaign-a", None)], [])


def test_synthetic_reference_is_never_human_and_is_train_only():
    examples = build_examples(
        [_classifier("synthetic-classifier-a", None, synthetic=True)], []
    )

    assert examples[0]["reference_provenance"] == "synthetic"
    assert examples[0]["split"] == "train"


def test_proxy_report_separates_provenance_and_keeps_empty_slice_null():
    report = summarize_proxy_scores(
        [
            {
                "score": 1.0,
                "reference_kind": "derived_label_projection",
                "reference_provenance": "human",
            },
            {
                "score": 0.5,
                "reference_kind": "derived_label_projection",
                "reference_provenance": "auto",
            },
        ]
    )

    assert report["metric_kind"] == "proxy"
    assert report["slices"]["overall"] == {"n": 2, "score": 0.75}
    assert report["slices"]["human"] == {"n": 1, "score": 1.0}
    assert report["slices"]["auto"] == {"n": 1, "score": 0.5}
    assert report["slices"]["synthetic"] == {"n": 0, "score": None}
    assert report["independent_gold"] == {"status": "not_provided", "score": None}


def test_proxy_metric_penalizes_invented_amount():
    good, _ = score_answer(
        answer="Ödül 500 TL.",
        gold_answer="Ödül 500 TL.",
        required_facts=["500 TL"],
        evidence="500 TL",
    )
    bad, feedback = score_answer(
        answer="Ödül 900 TL.",
        gold_answer="Ödül 500 TL.",
        required_facts=["500 TL"],
        evidence="500 TL",
    )

    assert good > bad
    assert "900" in feedback


def test_prompt_dataset_and_manifest_are_deterministic(tmp_path):
    classifier = tmp_path / "classifier.jsonl"
    ner = tmp_path / "ner.jsonl"
    _write_jsonl(
        classifier,
        [_classifier("campaign-a", "https://bank.example/a", human=True)],
    )
    _write_jsonl(ner, [_ner("campaign-a", "https://bank.example/a")])
    examples = build_examples(read_jsonl(classifier), read_jsonl(ner))
    first_output = tmp_path / "first.jsonl"
    first_manifest = tmp_path / "first.manifest.json"
    second_output = tmp_path / "second.jsonl"
    second_manifest = tmp_path / "second.manifest.json"

    first = write_examples_and_manifest(
        examples,
        first_output,
        first_manifest,
        classifier_path=classifier,
        ner_path=ner,
    )
    second = write_examples_and_manifest(
        examples,
        second_output,
        second_manifest,
        classifier_path=classifier,
        ner_path=ner,
    )

    assert first_output.read_bytes() == second_output.read_bytes()
    assert first == second
    assert first_manifest.read_bytes() == second_manifest.read_bytes()


def test_committed_prompt_dataset_matches_digest_manifest():
    manifest = validate_committed_dataset(DEFAULT_OUTPUT_PATH, DEFAULT_MANIFEST_PATH)

    assert manifest["output"]["line_count"] == 934
    assert manifest["output"]["task_counts"] == {
        "classification_summary": 465,
        "entity_detail": 469,
    }
    assert manifest["invariants"]["source_family_cross_split"] == 0
    assert manifest["independent_gold"] == {"status": "not_provided", "score": None}


def test_prompt_manifest_detects_changed_dataset(tmp_path):
    output = tmp_path / "examples.jsonl"
    manifest = tmp_path / "manifest.json"
    output.write_bytes(DEFAULT_OUTPUT_PATH.read_bytes())
    manifest.write_bytes(DEFAULT_MANIFEST_PATH.read_bytes())
    first = json.loads(output.read_text(encoding="utf-8").splitlines()[0])
    first["answer"] = "Değiştirildi"
    lines = output.read_text(encoding="utf-8").splitlines()
    lines[0] = json.dumps(first, ensure_ascii=False)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not match"):
        validate_committed_dataset(output, manifest)


def test_prompt_manifest_cannot_bless_output_that_differs_from_inputs(tmp_path):
    output = tmp_path / "examples.jsonl"
    manifest = tmp_path / "manifest.json"
    examples = read_jsonl(DEFAULT_OUTPUT_PATH)
    examples[0]["answer"] = "Kaynak etiketlerden türetilmeyen cevap"
    write_examples_and_manifest(
        examples,
        output,
        manifest,
        classifier_path=Path(
            "data/model_training_data/classifier_campaigns_review.jsonl"
        ),
        ner_path=Path("data/model_training_data/ner_dataset_approved.jsonl"),
    )

    with pytest.raises(ValueError, match="deterministic regeneration"):
        validate_committed_dataset(output, manifest)
