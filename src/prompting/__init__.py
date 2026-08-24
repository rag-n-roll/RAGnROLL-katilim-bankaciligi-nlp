"""Eski DSPy prompt API'si icin import-time yan etkisiz uyumluluk katmani."""

from __future__ import annotations

from importlib import import_module
from typing import Any


__all__ = ["GroundedAnswerProgram", "grounded_answer_metric"]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    compatibility = import_module("src.prompting.dspy_program")
    value = getattr(compatibility, name)
    globals()[name] = value
    return value
