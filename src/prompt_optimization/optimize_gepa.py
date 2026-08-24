"""934 orneklik proxy veriyle canli prompt talimati icin GEPA deneyi yurutur."""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import random
from typing import Any, Callable, Mapping

from src.prompt_optimization.artifact import (
    ARTIFACT_SCHEMA_VERSION,
    ARTIFACT_TYPE,
    DEFAULT_DATASET_PATH,
    DEFAULT_MANIFEST_PATH,
    INDEPENDENT_GOLD,
    atomic_write_json,
    load_candidate_artifact,
    load_dataset_manifest,
    sha256_file,
    validate_candidate_payload,
)
from src.prompt_optimization.dataset import (
    read_jsonl,
    validate_committed_dataset,
    validate_examples,
)
from src.prompt_optimization.dspy_program import create_grounded_answer_program
from src.prompt_optimization.evaluation import score_answer, summarize_proxy_scores


EXPECTED_OPTIONAL_VERSIONS = {"dspy": "3.3.1", "gepa": "0.1.4"}
INPUT_FIELDS = ("question", "evidence", "fallback")
SPLITS = ("train", "validation", "test")


class PromptOptimizationError(RuntimeError):
    """Deney sozlesmesi veya yerel model onkosulu saglanamadi."""


def load_optional_stack() -> tuple[Any, dict[str, str]]:
    """Opsiyonel yiginin surumlerini ve import edilebilirligini gec dogrular."""
    versions: dict[str, str] = {}
    for package, expected in EXPECTED_OPTIONAL_VERSIONS.items():
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError as exc:
            raise PromptOptimizationError(
                f"Opsiyonel prompt bagimliligi kurulu degil: {package}=={expected}"
            ) from exc
        if installed != expected:
            raise PromptOptimizationError(
                f"Opsiyonel prompt bagimliligi {package}=={expected} olmali; "
                f"kurulu surum {installed}"
            )
        versions[package] = installed
    try:
        # DSPy 3.3.1'in lazy NumPy yukleyicisiyle uyum icin NumPy once yuklenir.
        import numpy  # noqa: F401
        import dspy
        import gepa  # noqa: F401
    except Exception as exc:
        raise PromptOptimizationError(
            "Opsiyonel DSPy/GEPA yigini import edilemedi"
        ) from exc
    return dspy, versions


def load_committed_splits(dataset_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Yeni split uretmeden yalniz committed split alanlarini kullanir."""
    rows = read_jsonl(Path(dataset_path))
    validate_examples(rows)
    splits: dict[str, list[dict[str, Any]]] = {name: [] for name in SPLITS}
    for row in rows:
        example_id = str(row.get("example_id") or "")
        for field in ("question", "answer", "campaign_text"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise PromptOptimizationError(
                    f"Prompt orneginde zorunlu alan eksik: {example_id}.{field}"
                )
        if not isinstance(row.get("required_facts"), list):
            raise PromptOptimizationError(
                f"Prompt orneginde required_facts liste degil: {example_id}"
            )
        split = str(row.get("split") or "")
        if split not in splits:
            raise PromptOptimizationError(
                f"Prompt orneginde desteklenmeyen committed split: {split!r}"
            )
        splits[split].append(row)
    if any(not splits[name] for name in SPLITS):
        raise PromptOptimizationError("Train, validation ve test splitleri bos olamaz")
    return splits


def _limit_rows(rows: list[dict[str, Any]], maximum: int, seed: int) -> list[dict[str, Any]]:
    if maximum <= 0 or len(rows) <= maximum:
        return list(rows)
    sampled = list(rows)
    random.Random(seed).shuffle(sampled)
    return sampled[:maximum]


def _live_example(row: Mapping[str, Any]) -> dict[str, Any]:
    fallback = str(row.get("answer") or "").strip()
    answer = fallback if fallback.endswith("[K1]") else f"{fallback} [K1]"
    evidence = {
        "sources": [
            {
                "label": "K1",
                "campaign_id": row.get("campaign_id"),
                "source_url": row.get("source_url"),
                "evidence": row.get("campaign_text"),
                "classification_json": row.get("classification_json"),
                "entities_json": row.get("entities_json"),
            }
        ],
        "verified_fallback_answer": fallback,
    }
    return {
        "example_id": row.get("example_id"),
        "question": str(row.get("question") or ""),
        "evidence": json.dumps(
            evidence,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        "fallback": fallback,
        "answer": answer,
        "required_facts": list(row.get("required_facts") or []),
        "reference_kind": row.get("reference_kind"),
        "reference_provenance": row.get("reference_provenance"),
    }


def _dspy_examples(rows: list[dict[str, Any]], dspy: Any) -> list[Any]:
    return [dspy.Example(**_live_example(row)).with_inputs(*INPUT_FIELDS) for row in rows]


def make_gepa_metric(dspy: Any) -> Callable[..., Any]:
    """GEPA feedback donduren ve acikca proxy olan deterministik metrik."""

    def metric(
        gold: Any,
        prediction: Any,
        trace: Any = None,
        pred_name: str | None = None,
        pred_trace: Any = None,
    ) -> Any:
        del trace, pred_name, pred_trace
        answer = str(getattr(prediction, "answer", "") or "").strip()
        score, feedback = score_answer(
            answer=answer,
            gold_answer=str(getattr(gold, "answer", "") or ""),
            required_facts=list(getattr(gold, "required_facts", []) or []),
            evidence=str(getattr(gold, "evidence", "") or ""),
        )
        citation_ok = "[K1]" in answer
        combined = 0.9 * score + 0.1 * float(citation_ok)
        if not citation_ok:
            feedback = f"{feedback} Kaynak etiketi [K1] eksik."
        return dspy.Prediction(score=combined, feedback=feedback)

    return metric


def _evaluate_proxy(
    program: Any,
    examples: list[Any],
    *,
    dspy: Any,
    metric: Callable[..., Any],
    threads: int,
) -> dict[str, Any]:
    evaluator = dspy.Evaluate(
        devset=examples,
        metric=lambda gold, pred, trace=None: float(metric(gold, pred, trace).score),
        num_threads=threads,
        display_progress=False,
        display_table=False,
    )
    result = evaluator(program)
    scored = [
        {
            "score": float(score),
            "reference_kind": getattr(example, "reference_kind"),
            "reference_provenance": getattr(example, "reference_provenance"),
        }
        for example, _prediction, score in result.results
    ]
    return summarize_proxy_scores(scored)


def _endpoint_model_id(model: str) -> str:
    return model[len("openai/") :] if model.startswith("openai/") else model


def _dspy_model_id(model: str) -> str:
    return model if model.startswith("openai/") else f"openai/{model}"


def preflight_model_endpoint(
    *,
    base_url: str,
    api_key: str,
    models: list[str],
    timeout: float = 10.0,
    transport: Any = None,
) -> dict[str, Any]:
    """Model listesini ve cok kucuk bir chat yanitini optimization oncesi sinar."""
    import httpx

    endpoint = base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    requested = sorted({_endpoint_model_id(model) for model in models})
    try:
        with httpx.Client(timeout=timeout, transport=transport) as client:
            response = client.get(f"{endpoint}/models", headers=headers)
            response.raise_for_status()
            served = {
                str(item.get("id"))
                for item in response.json().get("data", [])
                if isinstance(item, dict) and item.get("id")
            }
            missing = [model for model in requested if model not in served]
            if missing:
                raise PromptOptimizationError(
                    "Model endpoint istenen modeli sunmuyor: " + ", ".join(missing)
                )
            for model in requested:
                probe = client.post(
                    f"{endpoint}/chat/completions",
                    headers=headers,
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "Yalnız OK yaz."}],
                        "temperature": 0,
                        "max_tokens": 8,
                        "stream": False,
                    },
                )
                probe.raise_for_status()
                probe_payload = probe.json()
                choices = probe_payload.get("choices") or []
                message = choices[0].get("message") if choices else None
                content = message.get("content") if isinstance(message, dict) else None
                if not isinstance(content, str) or not content.strip():
                    raise PromptOptimizationError(
                        f"Model endpoint preflight yaniti bos: {model}"
                    )
    except PromptOptimizationError:
        raise
    except (AttributeError, httpx.HTTPError, OSError, TypeError, ValueError) as exc:
        raise PromptOptimizationError("Model endpoint preflight basarisiz") from exc
    return {"base_url": endpoint, "models": requested, "status": "ready"}


def run_offline_check(
    *,
    dataset_path: str | Path = DEFAULT_DATASET_PATH,
    manifest_path: str | Path = DEFAULT_MANIFEST_PATH,
    artifact_path: str | Path | None = None,
    dependency_loader: Callable[[], tuple[Any, dict[str, str]]] = load_optional_stack,
) -> dict[str, Any]:
    """Ag kullanmadan bagimlilik, veri, manifest ve artifact contract kontrolu."""
    load_dataset_manifest(manifest_path)
    manifest = validate_committed_dataset(dataset_path, manifest_path)
    splits = load_committed_splits(dataset_path)
    _dspy, versions = dependency_loader()
    artifact_status: dict[str, Any] = {
        "status": "contract_ready",
        "artifact_type": ARTIFACT_TYPE,
        "schema_version": ARTIFACT_SCHEMA_VERSION,
    }
    if artifact_path is not None:
        artifact = load_candidate_artifact(artifact_path, manifest_path=manifest_path)
        artifact_status = {
            "status": "validated",
            "artifact_type": artifact["artifact_type"],
            "schema_version": artifact["schema_version"],
            "candidate_id": artifact["selection"]["candidate_id"],
        }
    return {
        "status": "ready",
        "network": "not_used",
        "dependencies": versions,
        "dataset": {
            "sha256": manifest["output"]["sha256"],
            "line_count": manifest["output"]["line_count"],
            "split_counts": {name: len(splits[name]) for name in SPLITS},
            "provenance_counts": manifest["output"]["provenance_counts"],
        },
        "artifact_contract": artifact_status,
        "independent_gold": dict(INDEPENDENT_GOLD),
    }


def _budget(args: argparse.Namespace) -> dict[str, Any]:
    if args.auto is not None:
        return {"kind": "auto", "value": args.auto}
    return {"kind": "max_metric_calls", "value": args.max_metric_calls}


def _run_key(args: argparse.Namespace, dataset_sha256: str) -> str:
    payload = {
        "dataset_sha256": dataset_sha256,
        "student_model": args.student_model,
        "reflection_model": args.reflection_model,
        "base_url": args.base_url.rstrip("/"),
        "budget": _budget(args),
        "seed": args.seed,
        "shots": args.shots,
        "max_train": args.max_train,
        "max_validation": args.max_validation,
    }
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(rendered).hexdigest()[:16]


def _extract_instruction(program: Any) -> str:
    predictors = list(program.named_predictors())
    if not predictors:
        raise PromptOptimizationError("GEPA optimize edilmis predictor dondurmedi")
    instruction = str(predictors[0][1].signature.instructions or "").strip()
    if not instruction:
        raise PromptOptimizationError("GEPA bos talimat dondurdu")
    return instruction


def _candidate_id(shots: int) -> str:
    return "one-shot" if shots == 1 else f"few-shot-{shots}"


def run_experiment(args: argparse.Namespace) -> dict[str, Any]:
    """Validation ile aday secer; test splitini yalniz secilen adaya uygular."""
    if args.runtime_dir is None:
        raise PromptOptimizationError("Deney icin --runtime-dir acikca verilmelidir")
    load_dataset_manifest(args.manifest)
    manifest = validate_committed_dataset(args.dataset, args.manifest)
    splits = load_committed_splits(args.dataset)
    run_key = _run_key(args, manifest["output"]["sha256"])
    output_root = Path(args.runtime_dir).resolve() / "prompt-optimization"
    run_directory = output_root / "runs" / run_key
    cache_directory = run_directory / "cache"
    log_directory = run_directory / "logs"
    cache_directory.mkdir(parents=True, exist_ok=True)
    log_directory.mkdir(parents=True, exist_ok=True)
    os.environ["DSPY_CACHEDIR"] = str(cache_directory)
    dspy, versions = load_optional_stack()
    api_key = os.getenv("RAGNROLL_LLM_API_KEY", "EMPTY")
    preflight = preflight_model_endpoint(
        base_url=args.base_url,
        api_key=api_key,
        models=[args.student_model, args.reflection_model],
        timeout=args.preflight_timeout,
    )

    train_rows = _limit_rows(splits["train"], args.max_train, args.seed)
    validation_rows = _limit_rows(
        splits["validation"], args.max_validation, args.seed + 1
    )
    train = _dspy_examples(train_rows, dspy)
    validation = _dspy_examples(validation_rows, dspy)
    metric = make_gepa_metric(dspy)

    student_lm = dspy.LM(
        _dspy_model_id(args.student_model),
        api_base=args.base_url.rstrip("/"),
        api_key=api_key,
        temperature=0.1,
        max_tokens=900,
        cache=False,
    )
    reflection_lm = dspy.LM(
        _dspy_model_id(args.reflection_model),
        api_base=args.base_url.rstrip("/"),
        api_key=api_key,
        temperature=0.7,
        max_tokens=1200,
        cache=False,
    )
    dspy.configure(lm=student_lm)

    candidates: list[dict[str, Any]] = []
    programs: dict[str, Any] = {}
    instructions: dict[str, str] = {}
    for shots in args.shots:
        candidate_id = _candidate_id(shots)
        seeded = dspy.LabeledFewShot(k=shots).compile(
            student=create_grounded_answer_program(dspy),
            trainset=train,
        )
        baseline = _evaluate_proxy(
            seeded,
            validation,
            dspy=dspy,
            metric=metric,
            threads=args.threads,
        )
        gepa_options: dict[str, Any] = {
            "metric": metric,
            "reflection_lm": reflection_lm,
            "num_threads": args.threads,
            "log_dir": str(log_directory / candidate_id),
            "track_stats": True,
            "seed": args.seed,
        }
        if args.auto is not None:
            gepa_options["auto"] = args.auto
        else:
            gepa_options["max_metric_calls"] = args.max_metric_calls
        optimized = dspy.GEPA(**gepa_options).compile(
            seeded,
            trainset=train,
            valset=validation,
        )
        optimized_validation = _evaluate_proxy(
            optimized,
            validation,
            dspy=dspy,
            metric=metric,
            threads=args.threads,
        )
        programs[candidate_id] = optimized
        instructions[candidate_id] = _extract_instruction(optimized)
        candidates.append(
            {
                "candidate_id": candidate_id,
                "baseline_validation_proxy": baseline,
                "optimized_validation_proxy": optimized_validation,
            }
        )

    selected = max(
        candidates,
        key=lambda candidate: (
            candidate["optimized_validation_proxy"]["slices"]["overall"]["score"],
            candidate["candidate_id"],
        ),
    )
    selected_id = selected["candidate_id"]
    test = _dspy_examples(splits["test"], dspy)
    selected_test = _evaluate_proxy(
        programs[selected_id],
        test,
        dspy=dspy,
        metric=metric,
        threads=args.threads,
    )

    experiment = {
        "optimizer": "dspy-gepa",
        "student_model": args.student_model,
        "reflection_model": args.reflection_model,
        "budget": _budget(args),
        "seed": args.seed,
        "shots": list(args.shots),
        "train_examples": len(train_rows),
        "validation_examples": len(validation_rows),
        "test_examples": len(splits["test"]),
    }
    output = manifest["output"]
    artifact = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "profile": "grounded-tr",
        "instruction": instructions[selected_id],
        "dataset": {
            "sha256": output["sha256"],
            "manifest_sha256": sha256_file(args.manifest),
            "line_count": output["line_count"],
            "split_counts": output["split_counts"],
            "provenance_counts": output["provenance_counts"],
        },
        "experiment": experiment,
        "candidate_scores": candidates,
        "selection": {
            "candidate_id": selected_id,
            "validation_proxy_score": selected["optimized_validation_proxy"]["slices"][
                "overall"
            ]["score"],
            "test_proxy": selected_test,
        },
        "independent_gold": dict(INDEPENDENT_GOLD),
    }
    validate_candidate_payload(artifact, manifest_path=args.manifest)
    report = {
        "status": "completed",
        "metric_kind": "proxy",
        "dataset": artifact["dataset"],
        "selected_train_examples": len(train_rows),
        "selected_validation_examples": len(validation_rows),
        "test_examples": len(splits["test"]),
        "committed_split_counts": output["split_counts"],
        "committed_provenance_counts": output["provenance_counts"],
        "experiment": experiment,
        "candidate_scores": candidates,
        "selection": artifact["selection"],
        "preflight": preflight,
        "dependency_check": versions,
        "independent_gold": dict(INDEPENDENT_GOLD),
    }
    run_artifact = run_directory / "selected_prompt.json"
    run_report = run_directory / "experiment_report.json"
    stable_artifact = output_root / "selected_prompt.json"
    stable_report = output_root / "experiment_report.json"
    for path, payload in (
        (run_artifact, artifact),
        (run_report, report),
        (stable_artifact, artifact),
        (stable_report, report),
    ):
        atomic_write_json(path, payload)
    return {
        "status": "completed",
        "artifact": str(stable_artifact),
        "report": str(stable_report),
        "run_directory": str(run_directory),
        "independent_gold": dict(INDEPENDENT_GOLD),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument(
        "--artifact",
        type=Path,
        help="--check sirasinda ayrica dogrulanacak mevcut aday artifact.",
    )
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        help="Cache, log, rapor ve artifact icin acik runtime koku.",
    )
    parser.add_argument("--student-model", default="gemma4:e4b-mlx")
    parser.add_argument("--reflection-model", default="gemma4:e4b-mlx")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--preflight-timeout", type=float, default=10.0)
    parser.add_argument("--shots", type=int, nargs="+", default=[1, 4])
    budget = parser.add_mutually_exclusive_group()
    budget.add_argument("--auto", choices=("light", "medium", "heavy"))
    budget.add_argument("--max-metric-calls", type=int, default=24)
    parser.add_argument("--max-train", type=int, default=0)
    parser.add_argument("--max-validation", type=int, default=0)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    return parser


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.artifact is not None and not args.check:
        parser.error("--artifact yalniz --check ile kullanilir")
    if not args.check and args.runtime_dir is None:
        parser.error("Deney icin --runtime-dir acikca verilmelidir")
    if args.max_metric_calls is not None and args.max_metric_calls < 6:
        parser.error("--max-metric-calls en az 6 olmalidir")
    if any(shots < 1 for shots in args.shots) or len(set(args.shots)) != len(args.shots):
        parser.error("--shots pozitif ve tekrarsiz degerler icermelidir")
    if args.threads < 1 or args.max_train < 0 or args.max_validation < 0:
        parser.error("threads pozitif; veri limitleri sifir veya pozitif olmalidir")
    if args.max_train and args.max_train < max(args.shots):
        parser.error("--max-train en buyuk --shots degerinden kucuk olamaz")
    if args.preflight_timeout <= 0:
        parser.error("--preflight-timeout pozitif olmalidir")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _validate_args(parser, args)
    if args.check:
        payload = run_offline_check(
            dataset_path=args.dataset,
            manifest_path=args.manifest,
            artifact_path=args.artifact,
        )
    else:
        payload = run_experiment(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
