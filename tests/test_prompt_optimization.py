from pathlib import Path

import numpy  # noqa: F401
import dspy

from scripts.optimize_assistant_prompt import load_examples
from src.prompting import grounded_answer_metric


DATASET = Path("data/model_training_data/assistant_prompt_examples.jsonl")


def test_gepa_dataset_is_large_enough_and_has_required_inputs():
    examples = load_examples(DATASET)

    assert len(examples) == 12
    assert all(example.question and example.evidence and example.fallback for example in examples)


def test_gepa_metric_returns_feedback_for_unsupported_claims():
    example = load_examples(DATASET)[0]
    result = grounded_answer_metric(
        example,
        dspy.Prediction(answer="Murabaha kesinlikle en iyi faizli kredidir."),
    )

    assert result.score < 1
    assert "başarısız" in result.feedback
