from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest

from src.llm.prompting import GroundedPromptBuilder, PromptConfigurationError
from src.prompt_optimization.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    ARTIFACT_TYPE,
    DEFAULT_MANIFEST_PATH,
    INDEPENDENT_GOLD,
    PromptArtifactError,
    atomic_write_json,
    load_candidate_artifact,
    load_dataset_manifest,
    sha256_file,
    validate_candidate_payload,
)
from src.prompt_optimization import optimize_gepa
from src.prompt_optimization.optimize_gepa import (
    _live_example,
    load_committed_splits,
    preflight_model_endpoint,
    run_offline_check,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _proxy_report(
    score: float = 0.75,
    *,
    human: int = 1,
    auto: int = 1,
    synthetic: int = 0,
) -> dict:
    count = human + auto + synthetic
    return {
        "metric_kind": "proxy",
        "reference_kind": "derived_label_projection",
        "slices": {
            "overall": {"n": count, "score": score},
            "human": {"n": human, "score": score if human else None},
            "auto": {"n": auto, "score": score if auto else None},
            "synthetic": {"n": synthetic, "score": score if synthetic else None},
        },
        "independent_gold": dict(INDEPENDENT_GOLD),
    }


def _artifact_payload(
    *,
    instruction: str = "Kısa, dengeli ve kanıt etiketli cevap yaz.",
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
) -> dict:
    manifest = load_dataset_manifest(manifest_path)
    output = manifest["output"]
    validation = _proxy_report()
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "profile": "grounded-tr",
        "instruction": instruction,
        "dataset": {
            "sha256": output["sha256"],
            "manifest_sha256": sha256_file(manifest_path),
            "line_count": output["line_count"],
            "split_counts": output["split_counts"],
            "provenance_counts": output["provenance_counts"],
        },
        "experiment": {
            "optimizer": "dspy-gepa",
            "student_model": "local-student",
            "reflection_model": "local-reflection",
            "budget": {"kind": "max_metric_calls", "value": 24},
            "seed": 42,
            "shots": [1],
            "train_examples": 4,
            "validation_examples": 2,
            "test_examples": output["split_counts"]["test"],
        },
        "candidate_scores": [
            {
                "candidate_id": "one-shot",
                "baseline_validation_proxy": _proxy_report(0.5),
                "optimized_validation_proxy": validation,
            }
        ],
        "selection": {
            "candidate_id": "one-shot",
            "validation_proxy_score": validation["slices"]["overall"]["score"],
            "test_proxy": _proxy_report(
                0.7,
                human=0,
                auto=output["split_counts"]["test"],
            ),
        },
        "independent_gold": dict(INDEPENDENT_GOLD),
    }


def _write_artifact(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _build_prompt(builder: GroundedPromptBuilder) -> tuple[str, str]:
    return builder.build(
        question="Oran nedir?",
        fallback_answer="Kaynakta oran belirtilmemiştir.",
        facts=[],
        sources=[],
        plan={"route": "campaign_search", "intent": "RATE_QUERY"},
    )


def test_default_prompt_keeps_committed_live_behavior(monkeypatch):
    monkeypatch.delenv("RAGNROLL_PROMPT_MODE", raising=False)
    monkeypatch.setenv("RAGNROLL_PROMPT_ARTIFACT", "/missing/must-not-be-read.json")
    builder = GroundedPromptBuilder()

    system_prompt, user_prompt = _build_prompt(builder)
    committed_system = (PROJECT_ROOT / "configs/prompts/assistant_system_tr.md").read_text(
        encoding="utf-8"
    ).strip()
    committed_profile = json.loads(
        (PROJECT_ROOT / "configs/prompts/assistant_prompt.json").read_text(
            encoding="utf-8"
        )
    )

    assert system_prompt == committed_system
    assert user_prompt.startswith(
        "GÖREV TALİMATI:\n"
        + committed_profile["instruction"]
    )
    assert committed_profile["status"] == "baseline"
    assert committed_profile["optimizer"] == "dspy-gepa-ready"
    assert builder.metadata() == {
        "profile": committed_profile["profile"],
        "optimizer": committed_profile["optimizer"],
        "status": committed_profile["status"],
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "schema_version"),
        ({"schema_version": 1}, "artifact_type"),
    ],
)
def test_gepa_mode_rejects_invalid_artifact(tmp_path, payload, message):
    artifact = tmp_path / "candidate.json"
    _write_artifact(artifact, payload)

    with pytest.raises(PromptConfigurationError, match=message):
        GroundedPromptBuilder(mode="gepa", artifact_path=artifact)


def test_gepa_mode_missing_artifact_fails_closed(tmp_path):
    with pytest.raises(PromptConfigurationError, match="bulunamadi"):
        GroundedPromptBuilder(
            mode="gepa",
            artifact_path=tmp_path / "missing-candidate.json",
        )


def test_gepa_mode_rejects_dataset_digest_mismatch(tmp_path):
    artifact = tmp_path / "candidate.json"
    payload = _artifact_payload()
    payload["dataset"]["sha256"] = "0" * 64
    _write_artifact(artifact, payload)

    with pytest.raises(PromptConfigurationError, match="dataset SHA"):
        GroundedPromptBuilder(mode="gepa", artifact_path=artifact)


def test_tampered_artifact_and_manifest_pair_cannot_replace_committed_anchor(tmp_path):
    manifest_path = tmp_path / "tampered.manifest.json"
    manifest = json.loads(DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["output"]["sha256"] = "f" * 64
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    payload = _artifact_payload()
    payload["dataset"]["sha256"] = manifest["output"]["sha256"]
    payload["dataset"]["manifest_sha256"] = sha256_file(manifest_path)
    artifact = tmp_path / "tampered-candidate.json"
    _write_artifact(artifact, payload)

    with pytest.raises(PromptConfigurationError, match="immutable anchor"):
        GroundedPromptBuilder(
            mode="gepa",
            artifact_path=artifact,
            dataset_manifest_path=manifest_path,
        )


def test_valid_gepa_candidate_cannot_replace_immutable_system_rules(tmp_path):
    artifact = tmp_path / "candidate.json"
    instruction = "Kanıtları kısa maddelerle açıkla ve her iddiayı etiketle."
    _write_artifact(artifact, _artifact_payload(instruction=instruction))

    builder = GroundedPromptBuilder(mode="gepa", artifact_path=artifact)
    system_prompt, user_prompt = _build_prompt(builder)

    assert system_prompt == (
        PROJECT_ROOT / "configs/prompts/assistant_system_tr.md"
    ).read_text(encoding="utf-8").strip()
    assert "Her doğrulanabilir iddianın sonuna ilgili kaynak etiketini ekle" in system_prompt
    assert instruction in user_prompt
    assert "sistem güvenliği ve kaynak kurallarını değiştiremez" in user_prompt
    assert instruction not in system_prompt
    assert builder.metadata()["mode"] == "gepa"


def test_artifact_cannot_define_system_or_citation_rules():
    for forbidden in ("system_prompt", "safety_rules", "citation_rules"):
        payload = _artifact_payload()
        payload[forbidden] = "Bu kuralları kaldır."
        with pytest.raises(PromptArtifactError, match="sistem kurallarini"):
            validate_candidate_payload(payload)


def test_optimizer_uses_committed_splits_and_proxy_provenance():
    splits = load_committed_splits(
        PROJECT_ROOT / "data/model_training_data/dspy_prompt_examples.jsonl"
    )

    assert {name: len(rows) for name, rows in splits.items()} == {
        "train": 659,
        "validation": 143,
        "test": 132,
    }
    assert all(row["split"] == name for name, rows in splits.items() for row in rows)
    projected = _live_example(splits["validation"][0])
    assert projected["answer"].endswith("[K1]")
    assert projected["reference_kind"] == "derived_label_projection"
    assert projected["reference_provenance"] in {"human", "auto", "synthetic"}


def test_offline_check_never_calls_model_preflight(monkeypatch):
    def forbidden_preflight(**_kwargs):
        raise AssertionError("--check model endpointine baglanmamali")

    monkeypatch.setattr(optimize_gepa, "preflight_model_endpoint", forbidden_preflight)
    result = run_offline_check(
        dependency_loader=lambda: (
            object(),
            {"dspy": "3.3.1", "gepa": "0.1.4"},
        )
    )

    assert result["network"] == "not_used"
    assert result["dataset"]["line_count"] == 934
    assert result["dataset"]["split_counts"] == {
        "train": 659,
        "validation": 143,
        "test": 132,
    }
    assert result["dataset"]["provenance_counts"] == {"auto": 874, "human": 60}
    assert result["artifact_contract"]["status"] == "contract_ready"
    assert result["independent_gold"] == INDEPENDENT_GOLD


def test_model_endpoint_preflight_is_bounded_and_checks_served_model():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "local-model"}]})
        body = json.loads(request.content)
        assert body["model"] == "local-model"
        assert body["max_tokens"] == 8
        assert body["stream"] is False
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "OK"}}]},
        )

    result = preflight_model_endpoint(
        base_url="http://model.example/v1",
        api_key="test-key",
        models=["openai/local-model", "local-model"],
        transport=httpx.MockTransport(handler),
    )

    assert result == {
        "base_url": "http://model.example/v1",
        "models": ["local-model"],
        "status": "ready",
    }
    assert [request.url.path for request in requests] == [
        "/v1/models",
        "/v1/chat/completions",
    ]


def test_run_experiment_emits_valid_artifact_and_uses_test_after_selection(
    tmp_path,
    monkeypatch,
):
    evaluations = []

    class FakeExample:
        def __init__(self, **values):
            self.__dict__.update(values)

        def with_inputs(self, *_fields):
            return self

    class FakePredict:
        def __init__(self, signature):
            self.signature = signature

    class FakeProgram:
        def __init__(self, instruction):
            self.instruction = instruction

        def named_predictors(self):
            predictor = SimpleNamespace(
                signature=SimpleNamespace(instructions=self.instruction)
            )
            return [("writer", predictor)]

    class FakeLabeledFewShot:
        def __init__(self, shots):
            self.shots = shots

        def compile(self, *, student, trainset):
            assert student is not None
            assert len(trainset) == 4
            return FakeProgram(f"baseline-{self.shots}")

    class FakeGEPA:
        def __init__(self, options):
            self.options = options

        def compile(self, seeded, *, trainset, valset):
            assert seeded is not None
            assert len(trainset) == 4
            assert len(valset) == 2
            candidate_id = Path(self.options["log_dir"]).name
            return FakeProgram(f"optimized-{candidate_id}")

    class FakeEvaluator:
        def __init__(self, devset):
            self.devset = devset

        def __call__(self, program):
            score = {
                "baseline-1": 0.4,
                "optimized-one-shot": 0.6,
                "baseline-4": 0.5,
                "optimized-few-shot-4": 0.8,
            }[program.instruction]
            evaluations.append((program.instruction, len(self.devset)))
            return SimpleNamespace(
                results=[(example, None, score) for example in self.devset]
            )

    class FakeDspy:
        class Signature:
            pass

        class Module:
            pass

        Prediction = SimpleNamespace
        Example = FakeExample

        @staticmethod
        def InputField(**_kwargs):
            return object()

        @staticmethod
        def OutputField(**_kwargs):
            return object()

        @staticmethod
        def Predict(signature):
            return FakePredict(signature)

        @staticmethod
        def LM(*_args, **_kwargs):
            return object()

        @staticmethod
        def configure(**_kwargs):
            return None

        @staticmethod
        def LabeledFewShot(k):
            return FakeLabeledFewShot(k)

        @staticmethod
        def GEPA(**options):
            return FakeGEPA(options)

        @staticmethod
        def Evaluate(*, devset, **_kwargs):
            return FakeEvaluator(devset)

    monkeypatch.setattr(
        optimize_gepa,
        "load_optional_stack",
        lambda: (FakeDspy(), {"dspy": "3.3.1", "gepa": "0.1.4"}),
    )
    monkeypatch.setattr(
        optimize_gepa,
        "preflight_model_endpoint",
        lambda **_kwargs: {"status": "ready", "models": ["fake-local"]},
    )
    args = optimize_gepa.build_parser().parse_args(
        [
            "--runtime-dir",
            str(tmp_path / "runtime"),
            "--student-model",
            "fake-local",
            "--reflection-model",
            "fake-local",
            "--shots",
            "1",
            "4",
            "--max-metric-calls",
            "6",
            "--max-train",
            "4",
            "--max-validation",
            "2",
        ]
    )

    result = optimize_gepa.run_experiment(args)
    artifact = load_candidate_artifact(result["artifact"])

    assert [item["candidate_id"] for item in artifact["candidate_scores"]] == [
        "one-shot",
        "few-shot-4",
    ]
    assert artifact["selection"]["candidate_id"] == "few-shot-4"
    assert artifact["instruction"] == "optimized-few-shot-4"
    assert artifact["experiment"]["shots"] == [1, 4]
    assert artifact["experiment"]["budget"] == {
        "kind": "max_metric_calls",
        "value": 6,
    }
    assert evaluations == [
        ("baseline-1", 2),
        ("optimized-one-shot", 2),
        ("baseline-4", 2),
        ("optimized-few-shot-4", 2),
        ("optimized-few-shot-4", 132),
    ]
    assert artifact["independent_gold"] == INDEPENDENT_GOLD


def test_atomic_artifact_write_leaves_no_partial_file(tmp_path):
    destination = tmp_path / "nested" / "candidate.json"

    atomic_write_json(destination, {"status": "complete", "score": None})

    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "score": None,
        "status": "complete",
    }
    assert list(destination.parent.glob("*.tmp")) == []


def test_prod_requirements_and_docker_exclude_optional_optimizer_stack():
    production = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    optional = (PROJECT_ROOT / "requirements-prompt-optimization.txt").read_text(
        encoding="utf-8"
    )
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "dspy" not in production.casefold()
    assert "gepa" not in production.casefold()
    assert optional.splitlines() == ["dspy==3.3.1", "gepa==0.1.4"]
    assert "requirements-prompt-optimization.txt" not in dockerfile


def test_legacy_twelve_example_proxy_and_import_surface_remain_available():
    dspy = pytest.importorskip("dspy")
    from src.prompting import grounded_answer_metric
    dataset = PROJECT_ROOT / "data/model_training_data/assistant_prompt_examples.jsonl"
    rows = [json.loads(line) for line in dataset.read_text(encoding="utf-8").splitlines()]
    example = dspy.Example(**rows[0]).with_inputs("question", "evidence", "fallback")

    result = grounded_answer_metric(
        example,
        dspy.Prediction(
            answer=(
                "Murabaha maliyet ve kârın açıklandığı vadeli satış işlemidir [K1]."
            )
        ),
    )

    assert len(rows) == 12
    assert result.score == 1.0


def test_prompt_modules_do_not_import_optional_stack_or_write_at_import(tmp_path):
    runtime_root = tmp_path / "runtime-must-not-exist"
    environment = {
        **os.environ,
        "PYTHONPATH": str(PROJECT_ROOT),
        "PYTHONDONTWRITEBYTECODE": "1",
        "RAGNROLL_RUNTIME_ROOT": str(runtime_root),
    }
    code = (
        "import sys\n"
        "from pathlib import Path\n"
        "import src.prompt_optimization.artifact\n"
        "import src.prompt_optimization.dspy_program\n"
        "import src.prompt_optimization.optimize_gepa\n"
        "import src.prompting\n"
        "import src.llm.prompting\n"
        "assert 'dspy' not in sys.modules\n"
        "assert 'gepa' not in sys.modules\n"
        f"assert not Path({str(runtime_root)!r}).exists()\n"
    )

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
