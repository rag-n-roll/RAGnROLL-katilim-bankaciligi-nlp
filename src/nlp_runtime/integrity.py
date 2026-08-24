"""Model dosyalarını güvenilmeyen deserialize işleminden önce doğrular."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib import metadata
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = PROJECT_ROOT / "models" / "final_training" / "runtime_manifest.json"
MANIFEST_CONTRACT = "ragnroll-nlp-runtime-2026.08"
RUNTIME_CONTRACT = "ragnroll-nlp-advisory-2026.08"
REQUIRED_DEPENDENCIES = {
    "joblib": "1.5.3",
    "scikit-learn": "1.9.0",
    "spacy": "3.8.15",
}
REQUIRED_ARTIFACT_HASHES = {
    "classifier": "327f7fdeece6798c83bbc8096d54ad9e7de7c911f5579717b11ba9c1782399e7",
    "ner": "7a39078461b2e574a9eb673a23fab565ae8eb0a0e8c03a686346967ef48be8cf",
}
REQUIRED_ARTIFACT_PATHS = {
    "classifier": "models/final_training/campaign_classifier.joblib",
    "ner": "models/final_training/augmented_weighted_30e",
}
REQUIRED_TRAINING_DATASETS = {
    "classifier": {
        "path": "data/model_training_data/classifier_dataset_final.jsonl",
        "sha256": "ff02d4a3efb9b984583ef44d0ddff2b1c0e242d4163068082e52dc52f5a90bfe",
    },
    "ner": {
        "path": "data/model_training_data/ner_dataset_final.jsonl",
        "sha256": "be7badce9d1a8f8d5587ac0fa836148457f7ee31041aa754774331f555475049",
    },
}
REQUIRED_TRAINING_PROVENANCE = {
    "manifest": {
        "path": "data/model_training_data/training_dataset_manifest.json",
        "sha256": "6babed7782fa03bb374dd96818a4e7c2a4b22364b3ac34fcebbc50e0fdb2f0cd",
        "contract": "training-dataset-lineage",
    },
    "automatic_references": "proxy_only",
    "independent_gold": "not_provided",
}
REQUIRED_RUNTIME_PROVENANCE = {
    "classifier_sha256": REQUIRED_ARTIFACT_HASHES["classifier"],
    "ner_tree_sha256": REQUIRED_ARTIFACT_HASHES["ner"],
    "classifier_dataset_sha256": REQUIRED_TRAINING_DATASETS["classifier"]["sha256"],
    "ner_dataset_sha256": REQUIRED_TRAINING_DATASETS["ner"]["sha256"],
    "training_manifest_sha256": REQUIRED_TRAINING_PROVENANCE["manifest"]["sha256"],
    "automatic_references": "proxy_only",
    "independent_gold": "not_provided",
    "runtime_contract": RUNTIME_CONTRACT,
}


class RuntimeManifestError(RuntimeError):
    """Manifest eksik veya geçersiz olduğunda yükseltilir."""


class ArtifactIntegrityError(RuntimeError):
    """Bir model artefaktının özeti manifest ile uyuşmadığında yükseltilir."""


class DependencyVersionError(RuntimeError):
    """Deserialize için gereken tam paket sürümü kurulu olmadığında yükseltilir."""


@dataclass(frozen=True)
class VerifiedArtifacts:
    classifier: Path
    ner: Path
    classifier_sha256: str
    ner_sha256: str
    classifier_dataset: Path
    ner_dataset: Path
    classifier_dataset_sha256: str
    ner_dataset_sha256: str
    training_manifest: Path
    training_manifest_sha256: str


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(path: Path) -> str:
    """Hash sorted relative POSIX paths and each file digest deterministically."""

    digest = sha256()
    files = sorted(
        (candidate for candidate in path.rglob("*") if candidate.is_file()),
        key=lambda candidate: candidate.relative_to(path).as_posix(),
    )
    if not files:
        raise ArtifactIntegrityError(f"Model dizini boş: {path}")
    for candidate in files:
        if candidate.is_symlink():
            raise ArtifactIntegrityError(f"Model ağacı sembolik bağ içeremez: {candidate}")
        relative = candidate.relative_to(path).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(file_sha256(candidate).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _object(value: Any, *, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeManifestError(f"Manifest alanı nesne olmalıdır: {name}")
    return value


def load_manifest(path: str | Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    manifest_path = Path(path)
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeManifestError(f"Model manifesti okunamadı: {manifest_path}") from exc
    manifest = _object(payload, name="root")
    if manifest.get("contract") != MANIFEST_CONTRACT:
        raise RuntimeManifestError("Model manifesti sözleşmesi geçersiz")
    return manifest


def verify_dependency_versions(manifest: dict[str, Any]) -> None:
    dependencies = _object(manifest.get("dependencies"), name="dependencies")
    if dependencies != REQUIRED_DEPENDENCIES:
        raise RuntimeManifestError("Model manifesti tam bağımlılık sürümlerini taşımıyor")
    mismatches = []
    for distribution, expected in sorted(REQUIRED_DEPENDENCIES.items()):
        try:
            actual = metadata.version(distribution)
        except metadata.PackageNotFoundError:
            actual = "not-installed"
        if actual != expected:
            mismatches.append(f"{distribution}={actual} (beklenen {expected})")
    if mismatches:
        raise DependencyVersionError("Uyumsuz model bağımlılıkları: " + ", ".join(mismatches))


def _project_path(configured: Any, *, name: str, expected: str) -> Path:
    if not isinstance(configured, str) or not configured:
        raise RuntimeManifestError(f"Manifest yolu eksik: {name}")
    if configured != expected:
        raise RuntimeManifestError(f"Manifest yolu çıpası geçersiz: {name}")
    candidate = PROJECT_ROOT / configured
    if candidate.is_symlink():
        raise ArtifactIntegrityError(f"Doğrulanan yol sembolik bağ olamaz: {name}")
    path = candidate.resolve()
    try:
        path.relative_to(PROJECT_ROOT.resolve())
    except ValueError as exc:
        raise RuntimeManifestError(f"Doğrulanan yol proje dışında olamaz: {name}") from exc
    return path


def _verified_file(path: Path, *, expected: str, name: str) -> None:
    if not path.is_file():
        raise ArtifactIntegrityError(f"Doğrulanan dosya bulunamadı: {name}")
    actual = file_sha256(path)
    if actual != expected:
        raise ArtifactIntegrityError(
            f"Dosya bütünlüğü doğrulanamadı: {name}; {actual} != {expected}"
        )


def verify_training_provenance(
    manifest: dict[str, Any],
) -> tuple[Path, Path, Path]:
    """Beyan edilen eğitim girdisi digestlerini runtime manifestine bağlar."""

    artifacts = _object(manifest.get("artifacts"), name="artifacts")
    dataset_paths: dict[str, Path] = {}
    for model_name in ("classifier", "ner"):
        artifact = _object(artifacts.get(model_name), name=model_name)
        dataset = _object(
            artifact.get("training_dataset"),
            name=f"{model_name}.training_dataset",
        )
        expected = REQUIRED_TRAINING_DATASETS[model_name]
        if dataset != expected:
            raise RuntimeManifestError(
                f"Eğitim veri çıpası geçersiz: {model_name}"
            )
        dataset_path = _project_path(
            dataset.get("path"),
            name=f"{model_name}.training_dataset",
            expected=expected["path"],
        )
        _verified_file(
            dataset_path,
            expected=expected["sha256"],
            name=f"{model_name}.training_dataset",
        )
        dataset_paths[model_name] = dataset_path

    provenance = _object(
        manifest.get("training_provenance"), name="training_provenance"
    )
    if provenance != REQUIRED_TRAINING_PROVENANCE:
        raise RuntimeManifestError("Eğitim provenance çıpası geçersiz")
    manifest_entry = _object(provenance.get("manifest"), name="training manifest")
    training_manifest_path = _project_path(
        manifest_entry.get("path"),
        name="training manifest",
        expected=REQUIRED_TRAINING_PROVENANCE["manifest"]["path"],
    )
    _verified_file(
        training_manifest_path,
        expected=REQUIRED_TRAINING_PROVENANCE["manifest"]["sha256"],
        name="training manifest",
    )
    try:
        training_manifest = json.loads(training_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactIntegrityError("Eğitim veri manifesti okunamadı") from exc
    training_manifest = _object(training_manifest, name="training manifest içeriği")
    if training_manifest.get("contract") != manifest_entry.get("contract"):
        raise ArtifactIntegrityError("Eğitim veri manifesti sözleşmesi eşleşmiyor")
    files = _object(training_manifest.get("files"), name="training manifest files")
    for model_name, expected in REQUIRED_TRAINING_DATASETS.items():
        linked = _object(files.get(expected["path"]), name=f"{model_name} dataset link")
        if linked.get("sha256") != expected["sha256"]:
            raise ArtifactIntegrityError(
                f"Eğitim veri manifesti SHA256 bağı eşleşmiyor: {model_name}"
            )
    metric_contract = _object(
        training_manifest.get("metric_contract"), name="metric_contract"
    )
    independent_gold = _object(
        training_manifest.get("independent_gold"), name="independent_gold"
    )
    if metric_contract.get("automatic_references") != "proxy_only":
        raise ArtifactIntegrityError("Otomatik referans beyanı proxy_only olmalıdır")
    if independent_gold.get("status") != "not_provided":
        raise ArtifactIntegrityError("Bağımsız gold beyanı not_provided olmalıdır")
    return (
        dataset_paths["classifier"],
        dataset_paths["ner"],
        training_manifest_path,
    )


def verify_artifacts(manifest: dict[str, Any]) -> VerifiedArtifacts:
    artifacts = _object(manifest.get("artifacts"), name="artifacts")
    classifier_entry = _object(artifacts.get("classifier"), name="classifier")
    ner_entry = _object(artifacts.get("ner"), name="ner")
    classifier_dataset, ner_dataset, training_manifest = verify_training_provenance(
        manifest
    )
    classifier = _project_path(
        classifier_entry.get("path"),
        name="classifier",
        expected=REQUIRED_ARTIFACT_PATHS["classifier"],
    )
    ner = _project_path(
        ner_entry.get("path"),
        name="ner",
        expected=REQUIRED_ARTIFACT_PATHS["ner"],
    )
    if ner_entry.get("tree_hash") != (
        "sorted relative POSIX path + NUL + file SHA256 hex + LF"
    ):
        raise RuntimeManifestError("NER ağaç hash algoritması geçersiz")
    checks = (
        ("classifier", classifier, file_sha256, classifier_entry.get("sha256")),
        ("ner", ner, tree_sha256, ner_entry.get("sha256")),
    )
    for name, path, hash_function, expected in checks:
        if not path.exists():
            raise ArtifactIntegrityError(f"Model artefaktı bulunamadı: {path}")
        if expected != REQUIRED_ARTIFACT_HASHES[name]:
            raise RuntimeManifestError(f"Manifest SHA256 çıpası geçersiz: {name}")
        actual = hash_function(path)
        if actual != expected:
            raise ArtifactIntegrityError(
                f"Model bütünlüğü doğrulanamadı: {name}; {actual} != {expected}"
            )
    return VerifiedArtifacts(
        classifier=classifier,
        ner=ner,
        classifier_sha256=REQUIRED_ARTIFACT_HASHES["classifier"],
        ner_sha256=REQUIRED_ARTIFACT_HASHES["ner"],
        classifier_dataset=classifier_dataset,
        ner_dataset=ner_dataset,
        classifier_dataset_sha256=REQUIRED_TRAINING_DATASETS["classifier"]["sha256"],
        ner_dataset_sha256=REQUIRED_TRAINING_DATASETS["ner"]["sha256"],
        training_manifest=training_manifest,
        training_manifest_sha256=REQUIRED_TRAINING_PROVENANCE["manifest"]["sha256"],
    )


def verify_runtime(path: str | Path = DEFAULT_MANIFEST) -> VerifiedArtifacts:
    manifest = load_manifest(path)
    verify_dependency_versions(manifest)
    return verify_artifacts(manifest)
