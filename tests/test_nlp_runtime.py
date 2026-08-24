from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from src.nlp_runtime import (
    ArtifactIntegrityError,
    CampaignNlpRuntime,
    DependencyVersionError,
    RuntimeManifestError,
)
from src.nlp_runtime.advisory import analyze, classification, label_evidence
from src.nlp_runtime.integrity import (
    DEFAULT_MANIFEST,
    REQUIRED_RUNTIME_PROVENANCE,
    REQUIRED_TRAINING_DATASETS,
    REQUIRED_TRAINING_PROVENANCE,
    file_sha256,
    load_manifest,
    tree_sha256,
    verify_artifacts,
    verify_dependency_versions,
    verify_training_provenance,
)


def test_shipped_artifacts_match_the_runtime_manifest():
    manifest = load_manifest(DEFAULT_MANIFEST)

    artifacts = verify_artifacts(manifest)

    assert artifacts.classifier.name == "campaign_classifier.joblib"
    assert tree_sha256(artifacts.ner) == manifest["artifacts"]["ner"]["sha256"]
    assert file_sha256(artifacts.classifier_dataset) == (
        REQUIRED_TRAINING_DATASETS["classifier"]["sha256"]
    )
    assert file_sha256(artifacts.ner_dataset) == (
        REQUIRED_TRAINING_DATASETS["ner"]["sha256"]
    )
    assert file_sha256(artifacts.training_manifest) == (
        REQUIRED_TRAINING_PROVENANCE["manifest"]["sha256"]
    )


def test_dependency_versions_are_exact_and_fail_closed(monkeypatch):
    manifest = load_manifest(DEFAULT_MANIFEST)
    installed = dict(manifest["dependencies"])

    monkeypatch.setattr(
        "src.nlp_runtime.integrity.metadata.version", lambda name: installed[name]
    )
    verify_dependency_versions(manifest)

    installed["spacy"] = "3.8.14"
    with pytest.raises(DependencyVersionError, match="spacy=3.8.14"):
        verify_dependency_versions(manifest)

    changed_manifest = deepcopy(manifest)
    changed_manifest["dependencies"]["spacy"] = "3.8.14"
    with pytest.raises(RuntimeManifestError, match="tam bağımlılık"):
        verify_dependency_versions(changed_manifest)


def test_manifest_cannot_move_the_pinned_artifact_hashes():
    manifest = load_manifest(DEFAULT_MANIFEST)
    manifest["artifacts"]["classifier"]["sha256"] = "0" * 64

    with pytest.raises(RuntimeManifestError, match="SHA256 çıpası"):
        verify_artifacts(manifest)


@pytest.mark.parametrize(
    ("model_name", "field", "value"),
    [
        ("classifier", "path", "data/model_training_data/classifier_dataset.jsonl"),
        ("classifier", "sha256", "0" * 64),
        ("ner", "path", "data/model_training_data/ner_dataset.jsonl"),
        ("ner", "sha256", "f" * 64),
    ],
)
def test_manifest_cannot_move_pinned_training_dataset_anchors(
    model_name, field, value
):
    manifest = load_manifest(DEFAULT_MANIFEST)
    manifest["artifacts"][model_name]["training_dataset"][field] = value

    with pytest.raises(RuntimeManifestError, match="Eğitim veri çıpası"):
        verify_training_provenance(manifest)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("automatic_references",), "gold"),
        (("independent_gold",), "provided"),
        (("manifest", "path"), "data/model_training_data/other.json"),
        (("manifest", "sha256"), "0" * 64),
        (("manifest", "contract"), "untrusted-lineage"),
    ],
)
def test_manifest_cannot_relax_training_provenance_contract(path, value):
    manifest = load_manifest(DEFAULT_MANIFEST)
    target = manifest["training_provenance"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(RuntimeManifestError, match="provenance çıpası"):
        verify_training_provenance(manifest)


@pytest.mark.parametrize(
    ("filename", "message"),
    [
        ("classifier_dataset_final.jsonl", "classifier.training_dataset"),
        ("ner_dataset_final.jsonl", "ner.training_dataset"),
        ("training_dataset_manifest.json", "training manifest"),
    ],
)
def test_training_lineage_bytes_are_verified_before_model_load(
    monkeypatch, filename, message
):
    manifest = load_manifest(DEFAULT_MANIFEST)

    def mismatched_dataset(path):
        if path.name == filename:
            return "0" * 64
        return file_sha256(path)

    monkeypatch.setattr("src.nlp_runtime.integrity.file_sha256", mismatched_dataset)

    with pytest.raises(ArtifactIntegrityError, match=message):
        verify_artifacts(manifest)


def test_loader_does_not_import_deserializers_when_verification_fails(monkeypatch):
    imported = []

    def reject(_manifest):
        raise DependencyVersionError("sürüm uyuşmuyor")

    monkeypatch.setattr("src.nlp_runtime.runtime.verify_runtime", reject)
    monkeypatch.setattr(
        "src.nlp_runtime.runtime.importlib.import_module",
        lambda name: imported.append(name),
    )

    with pytest.raises(DependencyVersionError, match="uyuşmuyor"):
        CampaignNlpRuntime.load()

    assert imported == []


class _ProductModel:
    classes_ = np.asarray(["card", "vehicle_finance"])

    def predict(self, _texts):
        return np.asarray(["card"])

    def decision_function(self, _texts):
        return np.asarray([[0.8, -0.4]])


class _Binarizer:
    def __init__(self, labels):
        self.classes_ = np.asarray(labels)


class _FieldModel:
    def __init__(self, selected, scores):
        self.selected = np.asarray(selected)
        self.scores = np.asarray(scores)

    def predict(self, _texts):
        return np.asarray([self.selected])

    def decision_function(self, _texts):
        return np.asarray([self.scores])


class _EmptyNer:
    def __call__(self, _text):
        return type("Doc", (), {"ents": []})()


class _SingleEntityNer:
    def __init__(self, text, label):
        self.entity_text = text
        self.label = label

    def __call__(self, source):
        start = source.index(self.entity_text)
        entity = type(
            "Entity",
            (),
            {
                "start_char": start,
                "end_char": start + len(self.entity_text),
                "text": self.entity_text,
                "label_": self.label,
            },
        )()
        return type("Doc", (), {"ents": [entity]})()


def _classifier(**dimensions):
    fields = {}
    for name, labels in dimensions.items():
        fields[name] = {
            "binarizer": _Binarizer([item[0] for item in labels]),
            "model": _FieldModel(
                [item[1] for item in labels], [item[2] for item in labels]
            ),
        }
    return {"product_model": _ProductModel(), "field_models": fields}


def test_sensitive_model_labels_are_suppressed_without_specific_regex_evidence():
    bundle = _classifier(
        channels=[("physical_branch", 1, 0.9)],
        requirements=[("application_required", 1, 0.8)],
        target_segments=[("new_customer", 1, 0.7)],
    )

    result = classification(
        bundle,
        "Katılım Bankası internet subesi ve mobil sube hizmetlerini tanıttı.",
    )

    assert result["dimensions"]["channels"] == []
    assert result["dimensions"]["requirements"] == []
    assert result["dimensions"]["target_segments"] == []
    assert result["suppressed_without_evidence"] == [
        "channels:physical_branch",
        "requirements:application_required",
        "target_segments:new_customer",
    ]
    advisory = analyze(
        bundle,
        _EmptyNer(),
        "Katılım Bankası internet subesi ve mobil sube hizmetlerini tanıttı.",
        structured={},
    )
    assert advisory["quality"]["suppressed_without_evidence"] == result[
        "suppressed_without_evidence"
    ]


@pytest.mark.parametrize(
    "text",
    ["internet şubesi", "internet subesi", "mobil şube", "mobil sube", "e-şube"],
)
def test_digital_branch_phrases_are_not_physical_branch_evidence(text):
    assert label_evidence(text, "physical_branch") is None


@pytest.mark.parametrize("text", ["fiziksel şubede", "subede işlemi tamamlayın"])
def test_explicit_physical_branch_phrases_are_evidence(text):
    evidence = label_evidence(text, "physical_branch")

    assert evidence is not None
    assert text[evidence["char_start"] : evidence["char_end"]] == evidence["text"]


def test_conflicting_channels_produce_warning_without_field_suggestion():
    bundle = _classifier(
        channels=[("mobile", 1, 0.9), ("physical_branch", 1, 0.7)]
    )
    text = "Mobil uygulamadan başvurun, işlemi fiziksel şubede tamamlayın."

    result = analyze(bundle, _EmptyNer(), text, structured={})

    assert "application_channel" not in result["suggestions"]
    assert "conflicting_suggestions:application_channel" in result["quality"][
        "warnings"
    ]


def test_minimum_spend_and_reward_are_distinct_and_authority_is_untouched():
    bundle = _classifier()
    text = "5.000 TL ve üzeri harcamaya 500 TL ödül kazanılır."
    empty = analyze(bundle, _EmptyNer(), text, structured={})

    assert empty["suggestions"]["min_amount"]["value"] == {
        "amount": 5000.0,
        "currency": "TRY",
    }
    assert empty["suggestions"]["reward_amount"]["value"] == {
        "amount": 500.0,
        "currency": "TRY",
    }
    assert empty["suggestions"]["reward_amount"]["evidence"]["text"] == "500 TL"

    structured = {"reward_amount": {"amount": 500.0, "currency": "TRY"}}
    before = deepcopy(structured)
    authoritative = analyze(bundle, _EmptyNer(), text, structured=structured)

    assert structured == before
    assert "reward_amount" not in authoritative["suggestions"]
    assert authoritative["suggestions"]["min_amount"]["value"]["amount"] == 5000.0


def test_reward_context_cannot_become_a_financing_amount_suggestion():
    text = "Kampanya kapsamında 500 TL ödül kazanılır."

    result = analyze(
        _classifier(),
        _SingleEntityNer("500 TL", "FINANSMAN_TUTARI"),
        text,
        structured={},
    )

    assert "financing_amount" not in result["suggestions"]
    assert result["suggestions"]["reward_amount"]["value"]["amount"] == 500.0


def test_real_verified_artifacts_load_and_infer():
    runtime = CampaignNlpRuntime.load()

    result = runtime.analyze(
        "Yeni müşteriler 5.000 TL ve üzeri harcamaya 500 TL ödül kazanır.",
        structured={},
        record_id="real-artifact-smoke",
        content_hash="a" * 64,
        source_version=1,
    )

    assert result["record"]["id"] == "real-artifact-smoke"
    assert result["classification"]["product_category"]["value"]
    assert isinstance(result["entities"], list)
    assert result["provenance"] == REQUIRED_RUNTIME_PROVENANCE
    assert result["suggestions"]["min_amount"]["value"]["amount"] == 5000.0
    assert result["suggestions"]["reward_amount"]["value"]["amount"] == 500.0
