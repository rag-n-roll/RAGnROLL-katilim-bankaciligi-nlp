"""Türkçe cevap yazım talimatını DSPy GEPA ile çevrimdışı iyileştirir."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path

import numpy  # noqa: F401
import dspy

from src.prompting import GroundedAnswerProgram, grounded_answer_metric


def load_examples(path: Path) -> list[dspy.Example]:
    examples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        examples.append(
            dspy.Example(**item).with_inputs("question", "evidence", "fallback")
        )
    if len(examples) < 6:
        raise ValueError("GEPA için en az 6 değerlendirme örneği gereklidir")
    return examples


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/model_training_data/assistant_prompt_examples.jsonl"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("configs/prompts/assistant_prompt.json")
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/v1")
    parser.add_argument("--model", default="gemma4:e4b-mlx")
    parser.add_argument(
        "--log-dir",
        type=Path,
        help="Aynı veri ve bütçeyle yarım kalan GEPA çalışmasını sürdürme dizini.",
    )
    budget = parser.add_mutually_exclusive_group()
    budget.add_argument("--auto", choices=("light", "medium", "heavy"))
    budget.add_argument(
        "--max-metric-calls",
        type=int,
        help="Yerel denemeyi öngörülebilir tutan GEPA değerlendirme bütçesi.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.auto is None and args.max_metric_calls is None:
        args.max_metric_calls = 24
    if args.max_metric_calls is not None and args.max_metric_calls < 6:
        parser.error("--max-metric-calls en az 6 olmalıdır")
    budget_name = args.auto or f"{args.max_metric_calls}-metric-calls"
    run_key = sha256(
        args.dataset.read_bytes()
        + f"{args.model}|{budget_name}".encode("utf-8")
    ).hexdigest()[:12]
    log_dir = args.log_dir or Path("runtime/gepa") / run_key

    examples = load_examples(args.dataset)
    if args.dry_run:
        print(json.dumps({"examples": len(examples), "status": "ready"}, indent=2))
        return 0

    lm = dspy.LM(
        f"openai/{args.model}",
        api_base=args.base_url,
        api_key=os.getenv("RAGNROLL_LLM_API_KEY", "EMPTY"),
        temperature=0.2,
        max_tokens=900,
        cache=False,
    )
    dspy.configure(lm=lm)
    split = max(4, int(len(examples) * 0.75))
    trainset, valset = examples[:split], examples[split:]
    optimizer = dspy.GEPA(
        metric=grounded_answer_metric,
        reflection_lm=lm,
        auto=args.auto,
        max_metric_calls=args.max_metric_calls,
        num_threads=1,
        log_dir=str(log_dir),
        track_stats=True,
        seed=32,
    )
    optimized = optimizer.compile(
        GroundedAnswerProgram(), trainset=trainset, valset=valset
    )
    predictors = list(optimized.named_predictors())
    if not predictors:
        raise RuntimeError("GEPA optimize edilmiş predictor döndürmedi")
    instruction = str(predictors[0][1].signature.instructions).strip()
    payload = {
        "profile": "grounded-tr",
        "instruction": instruction,
        "optimizer": "dspy-gepa",
        "status": "optimized",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "examples": len(examples),
        "budget": budget_name,
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
