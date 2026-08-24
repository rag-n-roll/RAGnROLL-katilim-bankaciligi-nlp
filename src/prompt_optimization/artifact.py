"""GEPA prompt adaylarini uretimden bagimsiz ve fail-closed dogrular."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = (
    PROJECT_ROOT / "data" / "model_training_data" / "dspy_prompt_examples.jsonl"
)
DEFAULT_MANIFEST_PATH = (
    PROJECT_ROOT
    / "data"
    / "model_training_data"
    / "dspy_prompt_examples.manifest.json"
)
ARTIFACT_TYPE = "ragnroll-grounded-prompt-candidate"
ARTIFACT_SCHEMA_VERSION = 1
INDEPENDENT_GOLD = {"status": "not_provided", "score": None}
PROVENANCE_SLICES = ("overall", "human", "auto", "synthetic")
COMMITTED_DATASET_CONTRACT = {
    "dataset_sha256": "418a644bedcdf0cae7a33d2175e8c40861e420e7bd1439e17f89a6c6eb989dc9",
    "manifest_sha256": "988d61ed7aa36efadbacd2252750b930feb715d0fad52b2aff233d8e1a3c2d76",
    "line_count": 934,
    "split_counts": {"test": 132, "train": 659, "validation": 143},
    "provenance_counts": {"auto": 874, "human": 60},
}


class PromptArtifactError(ValueError):
    """Prompt adayi veya bagli veri sozlesmesi gecersizdir."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PromptArtifactError(f"{label} bulunamadi: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PromptArtifactError(f"{label} okunamadi veya gecerli JSON degil: {path}") from exc
    if not isinstance(payload, dict):
        raise PromptArtifactError(f"{label} bir JSON nesnesi olmalidir: {path}")
    return payload


def load_dataset_manifest(path: str | Path = DEFAULT_MANIFEST_PATH) -> dict[str, Any]:
    """Committed prompt manifestinin runtime icin gerekli alanlarini dogrular."""
    manifest_path = Path(path)
    manifest = _read_object(manifest_path, label="Prompt veri manifesti")
    if sha256_file(manifest_path) != COMMITTED_DATASET_CONTRACT["manifest_sha256"]:
        raise PromptArtifactError(
            "Prompt veri manifesti committed immutable anchor ile eslesmiyor"
        )
    output = manifest.get("output")
    if manifest.get("schema_version") != 1 or not isinstance(output, dict):
        raise PromptArtifactError("Prompt veri manifesti semasi desteklenmiyor")
    digest = output.get("sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        raise PromptArtifactError("Prompt veri manifestinde gecerli output SHA-256 yok")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise PromptArtifactError(
            "Prompt veri manifestinde gecerli output SHA-256 yok"
        ) from exc
    for field in ("split_counts", "provenance_counts"):
        counts = output.get(field)
        if not isinstance(counts, dict) or not all(
            isinstance(key, str)
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value >= 0
            for key, value in counts.items()
        ):
            raise PromptArtifactError(f"Prompt veri manifestinde {field} gecersiz")
    if not isinstance(output.get("line_count"), int) or output["line_count"] <= 0:
        raise PromptArtifactError("Prompt veri manifestinde line_count gecersiz")
    if sum(output["split_counts"].values()) != output["line_count"]:
        raise PromptArtifactError("Prompt veri manifesti split sayimlari tutarsiz")
    if set(output["split_counts"]) != {"train", "validation", "test"}:
        raise PromptArtifactError("Prompt veri manifesti split anahtarlari gecersiz")
    if sum(output["provenance_counts"].values()) != output["line_count"]:
        raise PromptArtifactError("Prompt veri manifesti provenance sayimlari tutarsiz")
    if not set(output["provenance_counts"]) <= {"human", "auto", "synthetic"}:
        raise PromptArtifactError("Prompt veri manifesti provenance anahtarlari gecersiz")
    if manifest.get("independent_gold") != INDEPENDENT_GOLD:
        raise PromptArtifactError("Prompt veri manifesti independent_gold sozlesmesini tasimiyor")
    metric = manifest.get("metric_contract")
    if (
        not isinstance(metric, dict)
        or metric.get("automatic_references") != "proxy_only"
        or metric.get("reference_kind") != "derived_label_projection"
    ):
        raise PromptArtifactError("Prompt veri manifesti proxy metrik sozlesmesini tasimiyor")
    anchored_output = {
        "dataset_sha256": output["sha256"],
        "line_count": output["line_count"],
        "split_counts": output["split_counts"],
        "provenance_counts": output["provenance_counts"],
    }
    expected_output = {
        key: value
        for key, value in COMMITTED_DATASET_CONTRACT.items()
        if key != "manifest_sha256"
    }
    if anchored_output != expected_output:
        raise PromptArtifactError(
            "Prompt dataset sozlesmesi committed immutable anchor ile eslesmiyor"
        )
    return manifest


def _require_text(mapping: Mapping[str, Any], field: str, *, limit: int = 20000) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise PromptArtifactError(f"Prompt artifact alanı gecersiz: {field}")
    return value.strip()


def _score(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PromptArtifactError(f"Proxy skor alani sayi olmalidir: {field}")
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise PromptArtifactError(f"Proxy skor [0, 1] araliginda olmalidir: {field}")
    return score


def validate_proxy_report(value: Any, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PromptArtifactError(f"Proxy raporu nesne olmalidir: {field}")
    if set(value) != {
        "metric_kind",
        "reference_kind",
        "slices",
        "independent_gold",
    }:
        raise PromptArtifactError(f"Proxy raporu semasi gecersiz: {field}")
    if value.get("metric_kind") != "proxy":
        raise PromptArtifactError(f"Proxy raporu metric_kind=proxy olmalidir: {field}")
    if value.get("reference_kind") != "derived_label_projection":
        raise PromptArtifactError(f"Proxy raporu reference_kind gecersiz: {field}")
    if value.get("independent_gold") != INDEPENDENT_GOLD:
        raise PromptArtifactError(f"Proxy raporu independent_gold sozlesmesini bozuyor: {field}")
    slices = value.get("slices")
    if not isinstance(slices, dict) or set(slices) != set(PROVENANCE_SLICES):
        raise PromptArtifactError(f"Proxy raporu provenance dilimleri eksik: {field}")
    for name in PROVENANCE_SLICES:
        item = slices.get(name)
        if not isinstance(item, dict) or set(item) != {"n", "score"}:
            raise PromptArtifactError(f"Proxy dilimi gecersiz: {field}.{name}")
        count = item.get("n")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise PromptArtifactError(f"Proxy dilimi adedi gecersiz: {field}.{name}")
        score = item.get("score")
        if count == 0 and score is not None:
            raise PromptArtifactError(f"Bos proxy dilimi skoru null olmalidir: {field}.{name}")
        if count > 0:
            _score(score, field=f"{field}.{name}.score")
    overall = slices["overall"]
    provenance = [slices[name] for name in PROVENANCE_SLICES if name != "overall"]
    if overall["n"] <= 0 or sum(item["n"] for item in provenance) != overall["n"]:
        raise PromptArtifactError(f"Proxy raporu provenance sayimlari tutarsiz: {field}")
    weighted_score = sum(
        item["n"] * float(item["score"] or 0.0) for item in provenance
    ) / overall["n"]
    if not math.isclose(weighted_score, float(overall["score"]), abs_tol=1e-12):
        raise PromptArtifactError(f"Proxy raporu overall skoru dilimlerle tutarsiz: {field}")
    return value


def validate_candidate_payload(
    payload: Mapping[str, Any],
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    """Artifact semasini ve committed dataset bagini dogrular."""
    if not isinstance(payload, dict):
        raise PromptArtifactError("Prompt artifact bir JSON nesnesi olmalidir")
    if payload.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise PromptArtifactError("Prompt artifact schema_version desteklenmiyor")
    if payload.get("artifact_type") != ARTIFACT_TYPE:
        raise PromptArtifactError("Prompt artifact_type desteklenmiyor")
    forbidden = {"system_prompt", "safety_rules", "citation_rules"} & set(payload)
    if forbidden:
        raise PromptArtifactError(
            "Prompt artifact degismez sistem kurallarini tanimlayamaz: "
            + ", ".join(sorted(forbidden))
        )
    expected_fields = {
        "schema_version",
        "artifact_type",
        "profile",
        "instruction",
        "dataset",
        "experiment",
        "candidate_scores",
        "selection",
        "independent_gold",
    }
    if set(payload) != expected_fields:
        raise PromptArtifactError("Prompt artifact ust seviye semasi gecersiz")
    _require_text(payload, "instruction")
    if payload.get("profile") != "grounded-tr":
        raise PromptArtifactError("Prompt artifact profile=grounded-tr olmalidir")

    manifest_file = Path(manifest_path)
    manifest = load_dataset_manifest(manifest_file)
    expected = manifest["output"]
    dataset = payload.get("dataset")
    if not isinstance(dataset, dict):
        raise PromptArtifactError("Prompt artifact dataset sozlesmesi eksik")
    expected_dataset = {
        "sha256": expected["sha256"],
        "manifest_sha256": sha256_file(manifest_file),
        "line_count": expected["line_count"],
        "split_counts": expected["split_counts"],
        "provenance_counts": expected["provenance_counts"],
    }
    if dataset != expected_dataset:
        raise PromptArtifactError(
            "Prompt artifact dataset SHA veya sayimlari manifestle eslesmiyor"
        )

    experiment = payload.get("experiment")
    if not isinstance(experiment, dict) or experiment.get("optimizer") != "dspy-gepa":
        raise PromptArtifactError("Prompt artifact experiment optimizer alani gecersiz")
    if set(experiment) != {
        "optimizer",
        "student_model",
        "reflection_model",
        "budget",
        "seed",
        "shots",
        "train_examples",
        "validation_examples",
        "test_examples",
    }:
        raise PromptArtifactError("Prompt artifact experiment semasi gecersiz")
    _require_text(experiment, "student_model", limit=500)
    _require_text(experiment, "reflection_model", limit=500)
    budget = experiment.get("budget")
    if not isinstance(budget, dict) or budget.get("kind") not in {
        "auto",
        "max_metric_calls",
    }:
        raise PromptArtifactError("Prompt artifact budget sozlesmesi gecersiz")
    budget_value = budget.get("value")
    if budget["kind"] == "auto":
        if budget_value not in {"light", "medium", "heavy"}:
            raise PromptArtifactError("Prompt artifact auto budget degeri gecersiz")
    elif (
        isinstance(budget_value, bool)
        or not isinstance(budget_value, int)
        or budget_value < 1
    ):
        raise PromptArtifactError("Prompt artifact metric-call budget degeri gecersiz")
    seed = experiment.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise PromptArtifactError("Prompt artifact seed alani gecersiz")
    shots = experiment.get("shots")
    if (
        not isinstance(shots, list)
        or not shots
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in shots
        )
        or len(set(shots)) != len(shots)
    ):
        raise PromptArtifactError("Prompt artifact shots alani gecersiz")
    for field, split in (
        ("train_examples", "train"),
        ("validation_examples", "validation"),
        ("test_examples", "test"),
    ):
        count = experiment.get(field)
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
            or count > expected["split_counts"][split]
        ):
            raise PromptArtifactError(f"Prompt artifact experiment sayimi gecersiz: {field}")
    if experiment["test_examples"] != expected["split_counts"]["test"]:
        raise PromptArtifactError("Prompt artifact test spliti tam olarak bir kez olculmelidir")

    candidates = payload.get("candidate_scores")
    if not isinstance(candidates, list) or not candidates:
        raise PromptArtifactError("Prompt artifact candidate_scores bos olamaz")
    candidate_reports: dict[str, dict[str, Any]] = {}
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise PromptArtifactError("Prompt artifact candidate score kaydi gecersiz")
        if set(candidate) != {
            "candidate_id",
            "baseline_validation_proxy",
            "optimized_validation_proxy",
        }:
            raise PromptArtifactError("Prompt artifact candidate score semasi gecersiz")
        candidate_id = _require_text(candidate, "candidate_id", limit=200)
        if candidate_id in candidate_reports:
            raise PromptArtifactError(f"Tekrarlanan prompt adayi: {candidate_id}")
        baseline = validate_proxy_report(
            candidate.get("baseline_validation_proxy"),
            field=f"candidate_scores[{index}].baseline_validation_proxy",
        )
        optimized = validate_proxy_report(
            candidate.get("optimized_validation_proxy"),
            field=f"candidate_scores[{index}].optimized_validation_proxy",
        )
        if baseline["slices"]["overall"]["n"] != experiment["validation_examples"]:
            raise PromptArtifactError("Baseline validation proxy ornek sayimi gecersiz")
        if optimized["slices"]["overall"]["n"] != experiment["validation_examples"]:
            raise PromptArtifactError("Optimized validation proxy ornek sayimi gecersiz")
        if {
            name: baseline["slices"][name]["n"] for name in PROVENANCE_SLICES
        } != {
            name: optimized["slices"][name]["n"] for name in PROVENANCE_SLICES
        }:
            raise PromptArtifactError("Aday validation provenance dilimleri degisemez")
        candidate_reports[candidate_id] = {"baseline": baseline, "optimized": optimized}
    expected_candidate_ids = {
        "one-shot" if shots_value == 1 else f"few-shot-{shots_value}"
        for shots_value in shots
    }
    if set(candidate_reports) != expected_candidate_ids:
        raise PromptArtifactError("Prompt artifact shots ve candidate_scores eslesmiyor")

    selection = payload.get("selection")
    if not isinstance(selection, dict):
        raise PromptArtifactError("Prompt artifact selection sozlesmesi eksik")
    if set(selection) != {"candidate_id", "validation_proxy_score", "test_proxy"}:
        raise PromptArtifactError("Prompt artifact selection semasi gecersiz")
    selected_id = _require_text(selection, "candidate_id", limit=200)
    if selected_id not in candidate_reports:
        raise PromptArtifactError("Secilen prompt adayi candidate_scores icinde yok")
    validation_score = _score(
        selection.get("validation_proxy_score"),
        field="selection.validation_proxy_score",
    )
    expected_score = candidate_reports[selected_id]["optimized"]["slices"]["overall"][
        "score"
    ]
    if expected_score is None or not math.isclose(validation_score, expected_score):
        raise PromptArtifactError("Secim skoru aday validation proxy skoruyla eslesmiyor")
    test_proxy = validate_proxy_report(
        selection.get("test_proxy"), field="selection.test_proxy"
    )
    if test_proxy["slices"]["overall"]["n"] != experiment["test_examples"]:
        raise PromptArtifactError("Secilen aday test proxy ornek sayimi gecersiz")
    if payload.get("independent_gold") != INDEPENDENT_GOLD:
        raise PromptArtifactError("Prompt artifact independent_gold:not_provided olmalidir")
    return dict(payload)


def load_candidate_artifact(
    path: str | Path,
    *,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
) -> dict[str, Any]:
    artifact_path = Path(path)
    payload = _read_object(artifact_path, label="GEPA prompt artifact")
    return validate_candidate_payload(payload, manifest_path=manifest_path)


def atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    """JSON ciktisini ayni dizinde fsync + replace ile atomik yazar."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(payload, output, ensure_ascii=False, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
