from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True, slots=True)
class OutputVerdict:
    valid: bool
    reason_code: str


def _fingerprints(answer: str) -> list[str]:
    values = []
    for line in answer.splitlines():
        clean = re.sub(r"\[K\d+\]", "", line).casefold()
        clean = re.sub(r"[^\wçğıöşü]+", " ", clean).strip()
        if clean:
            values.append(clean)
    return values


class OutputGate:
    def __init__(self, *, judge: Any = None) -> None:
        self.judge = judge

    def validate(
        self, answer: str, *, sources: list[dict[str, Any]], question: str = ""
    ) -> OutputVerdict:
        fingerprints = _fingerprints(answer)
        if len(fingerprints) != len(set(fingerprints)):
            return OutputVerdict(False, "repeated_content")
        if self.judge is not None:
            return self.judge.evaluate(
                question=question, answer=answer, sources=sources
            )
        return OutputVerdict(True, "deterministic_checks_passed")
