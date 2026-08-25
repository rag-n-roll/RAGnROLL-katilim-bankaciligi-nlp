import json

import pytest

from src.prompt_optimization import artifact as artifact_module
from src.prompt_optimization.artifact import (
    COMMITTED_DATASET_CONTRACT,
    INDEPENDENT_GOLD,
    PromptArtifactError,
    atomic_write_json,
    load_candidate_artifact,
    load_dataset_manifest,
    validate_candidate_payload,
    validate_proxy_report,
)
from tests.test_prompt_optimization import _artifact_payload, _proxy_report


def test_validate_proxy_report_accepts_consistent_report():
    report = _proxy_report(0.8)
    assert validate_proxy_report(report, field="x") == report


def test_validate_proxy_report_rejects_inconsistent_reports():
    base = _proxy_report(0.5)
    cases = [
        "yok",
        {},
        {**base, "metric_kind": "human"},
        {**base, "reference_kind": "other"},
        {**base, "independent_gold": {"status": "provided"}},
        {**base, "slices": {}},
        {
            **base,
            "slices": {
                **base["slices"],
                "overall": {"n": 2},
            },
        },
        {**base, "slices": {**base["slices"], "auto": {"n": -1, "score": None}}},
        {
            **base,
            "slices": {
                **base["slices"],
                "synthetic": {"n": 0, "score": 0.4},
            },
        },
        {
            **base,
            "slices": {
                **base["slices"],
                "auto": {"n": 1, "score": 1.5},
            },
        },
        {**base, "slices": {**base["slices"], "overall": {"n": 0, "score": None}}},
    ]
    for value in cases:
        with pytest.raises(PromptArtifactError):
            validate_proxy_report(value, field="x")

    inconsistent_n = _proxy_report(human=1, auto=1)
    inconsistent_n["slices"]["overall"]["n"] = 5
    with pytest.raises(PromptArtifactError, match="sayimlari tutarsiz"):
        validate_proxy_report(inconsistent_n, field="x")

    inconsistent_score = _proxy_report(score=0.9, human=1, auto=1)
    inconsistent_score["slices"]["auto"]["score"] = 0.1
    with pytest.raises(PromptArtifactError, match="skoru dilimlerle tutarsiz"):
        validate_proxy_report(inconsistent_score, field="x")


@pytest.fixture()
def anchored_sha(monkeypatch):
    monkeypatch.setattr(
        artifact_module,
        "sha256_file",
        lambda path: COMMITTED_DATASET_CONTRACT["manifest_sha256"],
    )


def _manifest(**overrides):
    manifest = {
        "schema_version": 1,
        "output": {
            "sha256": "a" * 64,
            "line_count": 934,
            "split_counts": {"test": 132, "train": 659, "validation": 143},
            "provenance_counts": {"auto": 874, "human": 60},
        },
        "independent_gold": dict(INDEPENDENT_GOLD),
        "metric_contract": {
            "automatic_references": "proxy_only",
            "reference_kind": "derived_label_projection",
        },
    }
    for dotted_key, value in overrides.items():
        if "." in dotted_key:
            section, field = dotted_key.split(".", 1)
            manifest[section][field] = value
        else:
            manifest[dotted_key] = value
    return manifest


def test_load_dataset_manifest_rejects_unreadable_or_invalid_files(tmp_path):
    missing = tmp_path / "missing.json"
    with pytest.raises(PromptArtifactError, match="bulunamadi"):
        load_dataset_manifest(missing)

    broken = tmp_path / "broken.json"
    broken.write_text("{kesik", encoding="utf-8")
    with pytest.raises(PromptArtifactError, match="okunamadi"):
        load_dataset_manifest(broken)

    listing = tmp_path / "listing.json"
    listing.write_text("[]", encoding="utf-8")
    with pytest.raises(PromptArtifactError, match="JSON nesnesi"):
        load_dataset_manifest(listing)


@pytest.mark.usefixtures("anchored_sha")
def test_manifest_branches_are_covered_individually(tmp_path):
    def write(manifest):
        path = tmp_path / "m.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    bad = _manifest()
    del bad["output"]
    with pytest.raises(PromptArtifactError, match="semasi"):
        load_dataset_manifest(write(bad))

    bad = _manifest(**{"output.sha256": "kisa"})
    with pytest.raises(PromptArtifactError, match="SHA-256"):
        load_dataset_manifest(write(bad))

    bad = _manifest(**{"output.split_counts": "yok"})
    with pytest.raises(PromptArtifactError, match="split_counts gecersiz"):
        load_dataset_manifest(write(bad))

    bad = _manifest(**{"output.line_count": 0})
    with pytest.raises(PromptArtifactError, match="line_count gecersiz"):
        load_dataset_manifest(write(bad))

    bad = _manifest(**{"output.line_count": 10})
    with pytest.raises(PromptArtifactError, match="split sayimlari tutarsiz"):
        load_dataset_manifest(write(bad))

    bad = _manifest(
        **{"output.split_counts": {"test": 132, "train": 659, "validation": 143, "dev": 0}}
    )
    with pytest.raises(PromptArtifactError, match="split anahtarlari"):
        load_dataset_manifest(write(bad))

    bad = _manifest(**{"output.provenance_counts": {"auto": 800, "human": 60}})
    with pytest.raises(PromptArtifactError, match="provenance sayimlari tutarsiz"):
        load_dataset_manifest(write(bad))

    bad = _manifest(**{"output.provenance_counts": {"auto": 874, "human": 60, "gold": 0}})
    with pytest.raises(PromptArtifactError, match="provenance anahtarlari"):
        load_dataset_manifest(write(bad))

    bad = _manifest()
    bad["independent_gold"] = {"status": "provided"}
    with pytest.raises(PromptArtifactError, match="independent_gold"):
        load_dataset_manifest(write(bad))

    bad = _manifest()
    bad["metric_contract"] = {"automatic_references": "full"}
    with pytest.raises(PromptArtifactError, match="proxy metrik"):
        load_dataset_manifest(write(bad))

    good = _manifest(
        **{
            "output.sha256": COMMITTED_DATASET_CONTRACT["dataset_sha256"],
        }
    )
    loaded = load_dataset_manifest(write(good))
    assert loaded["output"]["sha256"] == COMMITTED_DATASET_CONTRACT["dataset_sha256"]


def test_validate_candidate_payload_rejects_top_level_violations(tmp_path):
    payload = _artifact_payload()

    with pytest.raises(PromptArtifactError, match="JSON nesnesi"):
        validate_candidate_payload(["dizi"])

    with pytest.raises(PromptArtifactError, match="schema_version"):
        validate_candidate_payload({**payload, "schema_version": 99})

    with pytest.raises(PromptArtifactError, match="artifact_type"):
        validate_candidate_payload({**payload, "artifact_type": "baska"})

    with pytest.raises(PromptArtifactError, match="degismez sistem kurallari"):
        validate_candidate_payload({**payload, "system_prompt": "override"})

    with pytest.raises(PromptArtifactError, match="ust seviye semasi"):
        validate_candidate_payload({k: v for k, v in payload.items() if k != "selection"})

    with pytest.raises(PromptArtifactError, match="profile"):
        validate_candidate_payload({**payload, "profile": "grounded-en"})

    with pytest.raises(PromptArtifactError, match="instruction"):
        validate_candidate_payload({**payload, "instruction": "   "})


def test_validate_candidate_payload_rejects_experiment_violations():
    payload = _artifact_payload()

    def mutate(path, value):
        copy = json.loads(json.dumps(payload))
        target = copy
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        return copy

    with pytest.raises(PromptArtifactError, match="optimizer"):
        validate_candidate_payload(mutate(("experiment", "optimizer"), "manual"))

    extra = json.loads(json.dumps(payload))
    extra["experiment"]["unknown"] = True
    with pytest.raises(PromptArtifactError, match="experiment semasi"):
        validate_candidate_payload(extra)

    with pytest.raises(PromptArtifactError, match="student_model"):
        validate_candidate_payload(mutate(("experiment", "student_model"), " "))

    with pytest.raises(PromptArtifactError, match="budget"):
        validate_candidate_payload(mutate(("experiment", "budget"), {"kind": "other", "value": 1}))

    with pytest.raises(PromptArtifactError, match="auto budget"):
        validate_candidate_payload(
            mutate(("experiment", "budget"), {"kind": "auto", "value": "dev"})
        )

    with pytest.raises(PromptArtifactError, match="metric-call budget"):
        validate_candidate_payload(
            mutate(("experiment", "budget"), {"kind": "max_metric_calls", "value": 0})
        )

    with pytest.raises(PromptArtifactError, match="seed"):
        validate_candidate_payload(mutate(("experiment", "seed"), True))

    with pytest.raises(PromptArtifactError, match="shots"):
        validate_candidate_payload(mutate(("experiment", "shots"), []))

    with pytest.raises(PromptArtifactError, match="shots"):
        validate_candidate_payload(mutate(("experiment", "shots"), [1, 1]))

    with pytest.raises(PromptArtifactError, match="train_examples"):
        validate_candidate_payload(mutate(("experiment", "train_examples"), 100000))

    with pytest.raises(PromptArtifactError, match="test spliti"):
        validate_candidate_payload(mutate(("experiment", "test_examples"), 1))


def test_atomic_write_json_writes_atomically_and_cleans_up(tmp_path):
    destination = tmp_path / "out" / "artifact.json"

    atomic_write_json(destination, {"isim": "aday", "sayı": 1})

    content = json.loads(destination.read_text(encoding="utf-8"))
    assert content == {"isim": "aday", "sayı": 1}
    assert list(destination.parent.glob("*.tmp")) == []


def test_load_candidate_artifact_round_trip(tmp_path):
    artifact = tmp_path / "candidate.json"
    payload = _artifact_payload()
    artifact.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest = tmp_path / "tampered-manifest.json"

    with pytest.raises((PromptArtifactError, FileNotFoundError, OSError)):
        load_candidate_artifact(artifact, manifest_path=manifest)


def test_validate_candidate_payload_rejects_candidate_and_selection_violations():
    payload = _artifact_payload()

    def mutate(dotted_path, value):
        copy = json.loads(json.dumps(payload))
        keys = dotted_path.split(".")
        target = copy
        for key in keys[:-1]:
            target = target[int(key)] if key.isdigit() else target[key]
        last = keys[-1]
        if last.isdigit():
            target[int(last)] = value
        else:
            target[last] = value
        return copy

    def delete(dotted_path):
        copy = json.loads(json.dumps(payload))
        keys = dotted_path.split(".")
        target = copy
        for key in keys[:-1]:
            target = target[int(key)] if key.isdigit() else target[key]
        del target[keys[-1]]
        return copy

    with pytest.raises(PromptArtifactError, match="candidate_scores bos"):
        validate_candidate_payload(mutate("candidate_scores", []))

    with pytest.raises(PromptArtifactError, match="candidate score kaydi"):
        validate_candidate_payload(mutate("candidate_scores", ["x"]))

    with pytest.raises(PromptArtifactError, match="candidate score semasi"):
        validate_candidate_payload(mutate("candidate_scores.0.extra", 1))

    duplicate = json.loads(json.dumps(payload))
    first = json.loads(json.dumps(duplicate["candidate_scores"][0]))
    duplicate["candidate_scores"].append(first)
    with pytest.raises(PromptArtifactError, match="Tekrarlanan prompt adayi"):
        validate_candidate_payload(duplicate)

    scaled = json.loads(json.dumps(payload))
    for key in ("baseline_validation_proxy", "optimized_validation_proxy"):
        slices = scaled["candidate_scores"][0][key]["slices"]
        for name in ("overall", "human", "auto"):
            slices[name]["n"] *= 2
    with pytest.raises(PromptArtifactError, match="Baseline validation proxy"):
        validate_candidate_payload(scaled)

    optimized_scaled = json.loads(json.dumps(payload))
    slices = optimized_scaled["candidate_scores"][0]["optimized_validation_proxy"]["slices"]
    for name in ("overall", "human", "auto"):
        slices[name]["n"] *= 2
    with pytest.raises(PromptArtifactError, match="Optimized validation proxy"):
        validate_candidate_payload(optimized_scaled)

    with pytest.raises(PromptArtifactError, match="provenance dilimleri degisemez"):
        mutated = json.loads(json.dumps(payload))
        report = mutated["candidate_scores"][0]["optimized_validation_proxy"]
        report["slices"]["human"] = {"n": 2, "score": 0.75}
        report["slices"]["auto"] = {"n": 0, "score": None}
        validate_candidate_payload(mutated)

    with pytest.raises(PromptArtifactError, match="shots ve candidate_scores eslesmiyor"):
        validate_candidate_payload(mutate("candidate_scores.0.candidate_id", "few-shot-4"))

    with pytest.raises(PromptArtifactError, match="selection sozlesmesi"):
        validate_candidate_payload(mutate("selection", None))

    with pytest.raises(PromptArtifactError, match="selection semasi"):
        validate_candidate_payload(mutate("selection.extra", 1))

    with pytest.raises(PromptArtifactError, match="Secilen prompt adayi"):
        validate_candidate_payload(mutate("selection.candidate_id", "yok-boyle"))

    with pytest.raises(PromptArtifactError, match="Secim skoru"):
        validate_candidate_payload(mutate("selection.validation_proxy_score", 0.11))

    test_scaled = json.loads(json.dumps(payload))
    slices = test_scaled["selection"]["test_proxy"]["slices"]
    for name in ("overall", "auto"):
        slices[name]["n"] *= 2
    with pytest.raises(PromptArtifactError, match="test proxy ornek sayimi"):
        validate_candidate_payload(test_scaled)

    with pytest.raises(PromptArtifactError, match="independent_gold"):
        validate_candidate_payload(mutate("independent_gold", {"status": "provided"}))


def test_full_valid_payload_passes_validation():
    payload = _artifact_payload()
    validated = validate_candidate_payload(payload)
    assert validated["profile"] == "grounded-tr"
