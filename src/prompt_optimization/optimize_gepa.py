"""Optimize and compare one-shot/few-shot system prompts with DSPy GEPA."""

from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("DSPY_CACHEDIR", str(PROJECT_ROOT / ".codex_tmp" / "dspy_cache"))
Path(os.environ["DSPY_CACHEDIR"]).mkdir(parents=True, exist_ok=True)

import dspy

from src.prompt_optimization.dataset import DEFAULT_OUTPUT_PATH
from src.prompt_optimization.dspy_program import CampaignAnswerProgram
from src.prompt_optimization.metrics import gepa_metric


DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "models" / "dspy_gepa"
INPUT_FIELDS = ("question", "campaign_text", "classification_json", "entities_json")


def _load_examples(path: Path) -> dict[str, list[Any]]:
    splits: dict[str, list[Any]] = {"train": [], "validation": [], "test": []}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        example = dspy.Example(**item).with_inputs(*INPUT_FIELDS)
        splits[item["split"]].append(example)
    return splits


def _limit(items: list[Any], maximum: int, seed: int) -> list[Any]:
    if maximum <= 0 or len(items) <= maximum:
        return items
    sample = list(items)
    random.Random(seed).shuffle(sample)
    return sample[:maximum]


def _evaluate(program: Any, examples: list[Any], threads: int) -> float:
    evaluator = dspy.Evaluate(
        devset=examples,
        metric=lambda gold, pred, trace=None: float(gepa_metric(gold, pred, trace).score),
        num_threads=threads,
        display_progress=True,
        display_table=False,
    )
    result = evaluator(program)
    return float(result.score if hasattr(result, "score") else result)


def _export_prompt(program: Any, variant: str, scores: dict[str, float], path: Path) -> None:
    predictor = program.respond
    demos = []
    for demo in getattr(predictor, "demos", []) or []:
        demos.append({field: getattr(demo, field, "") for field in (*INPUT_FIELDS, "answer")})
    payload = {
        "schema_version": 1,
        "selected_variant": variant,
        "system_prompt": predictor.signature.instructions,
        "demonstrations": demos,
        "scores": scores,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--student-model", default="ollama_chat/gemma4:e4b")
    parser.add_argument("--reflection-model", default="ollama_chat/gemma4:e4b")
    parser.add_argument("--api-base", default="http://localhost:11434")
    parser.add_argument("--shots", type=int, nargs="+", default=[1, 4])
    parser.add_argument("--auto", choices=("light", "medium", "heavy"), default="light")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--max-train", type=int, default=0, help="0 uses every training example")
    parser.add_argument("--max-validation", type=int, default=0, help="0 uses every validation example")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    splits = _load_examples(args.dataset)
    train = _limit(splits["train"], args.max_train, args.seed)
    validation = _limit(splits["validation"], args.max_validation, args.seed + 1)
    if not train or not validation or not splits["test"]:
        raise ValueError("Dataset must contain non-empty train, validation and test splits.")

    student_lm = dspy.LM(args.student_model, api_base=args.api_base, api_key="ollama", temperature=0.1)
    reflection_lm = dspy.LM(args.reflection_model, api_base=args.api_base, api_key="ollama", temperature=0.7)
    dspy.configure(lm=student_lm)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    candidates: list[tuple[str, Any, dict[str, float]]] = []
    for shots in args.shots:
        variant = "one_shot" if shots == 1 else f"few_shot_{shots}"
        seeded = dspy.LabeledFewShot(k=shots).compile(
            student=CampaignAnswerProgram(),
            trainset=train,
        )
        baseline_validation = _evaluate(seeded, validation, args.threads)
        optimizer = dspy.GEPA(
            metric=gepa_metric,
            reflection_lm=reflection_lm,
            auto=args.auto,
            num_threads=args.threads,
            seed=args.seed,
        )
        optimized = optimizer.compile(seeded, trainset=train, valset=validation)
        optimized_validation = _evaluate(optimized, validation, args.threads)
        scores = {
            "baseline_validation": baseline_validation,
            "optimized_validation": optimized_validation,
        }
        optimized.save(str(args.output_dir / f"{variant}.json"), save_program=False)
        candidates.append((variant, optimized, scores))

    selected_variant, selected, selected_scores = max(
        candidates,
        key=lambda item: item[2]["optimized_validation"],
    )
    selected_scores["test"] = _evaluate(selected, splits["test"], args.threads)
    _export_prompt(
        selected,
        selected_variant,
        selected_scores,
        args.output_dir / "selected_prompt.json",
    )
    (args.output_dir / "experiment_report.json").write_text(
        json.dumps(
            {
                "selected_variant": selected_variant,
                "train_examples": len(train),
                "validation_examples": len(validation),
                "test_examples": len(splits["test"]),
                "candidates": [
                    {"variant": variant, **scores} for variant, _, scores in candidates
                ],
                "selected_test_score": selected_scores["test"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Selected {selected_variant}; test score={selected_scores['test']:.2f}")


if __name__ == "__main__":
    main()
