"""Deterministic, feedback-rich metric used by DSPy GEPA."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


FALLBACK_ANSWER = "Bu bilgi sağlanan dokümanlarda bulunmamaktadır."


def _normalize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9çğıöşü%]+", text.casefold())


def _token_f1(gold: str, prediction: str) -> float:
    gold_tokens = Counter(_normalize(gold))
    pred_tokens = Counter(_normalize(prediction))
    overlap = sum((gold_tokens & pred_tokens).values())
    if not gold_tokens or not pred_tokens:
        return float(gold_tokens == pred_tokens)
    precision = overlap / sum(pred_tokens.values())
    recall = overlap / sum(gold_tokens.values())
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _numbers_and_codes(text: str) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(r"(?<!\w)(?:%?\d[\d.,/-]*|[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9_-]{3,})(?!\w)", text)
    }


def score_answer(
    *,
    answer: str,
    gold_answer: str,
    required_facts: list[str],
    evidence: str,
) -> tuple[float, str]:
    answer = str(answer or "").strip()
    if gold_answer.strip() == FALLBACK_ANSWER:
        score = float(answer == FALLBACK_ANSWER)
        feedback = "Eksik bilgi yanıtı tam doğru." if score else "Bağlamda olmayan bilgi için sabit güvenli yanıtı kullan."
        return score, feedback

    normalized_answer = " ".join(_normalize(answer))
    covered = [fact for fact in required_facts if " ".join(_normalize(fact)) in normalized_answer]
    coverage = len(covered) / len(required_facts) if required_facts else 1.0
    f1 = _token_f1(gold_answer, answer)
    supported = _numbers_and_codes(evidence + " " + gold_answer)
    invented = _numbers_and_codes(answer) - supported
    hallucination_penalty = min(0.35, 0.08 * len(invented))
    length_penalty = 0.08 if len(answer) > max(900, len(gold_answer) * 2) else 0.0
    score = max(0.0, min(1.0, 0.68 * coverage + 0.32 * f1 - hallucination_penalty - length_penalty))

    missing = [fact for fact in required_facts if fact not in covered][:5]
    feedback_parts = [f"Zorunlu bilgi kapsama oranı %{coverage * 100:.0f}."]
    if missing:
        feedback_parts.append("Eksik bilgiler: " + ", ".join(missing) + ".")
    if invented:
        feedback_parts.append("Bağlamda desteklenmeyen sayı/kodlar: " + ", ".join(sorted(invented)) + ".")
    if length_penalty:
        feedback_parts.append("Yanıt gereğinden uzun; kısa ve doğrudan yaz.")
    return score, " ".join(feedback_parts)


def gepa_metric(gold: Any, pred: Any, trace: Any = None, pred_name: str | None = None, pred_trace: Any = None) -> Any:
    """DSPy GEPA metric; imported lazily so dataset/tests do not require DSPy."""
    del trace, pred_name, pred_trace
    answer = getattr(pred, "answer", "")
    gold_answer = str(getattr(gold, "answer", ""))
    required_facts = list(getattr(gold, "required_facts", []) or [])
    evidence = " ".join(
        str(getattr(gold, field, ""))
        for field in ("campaign_text", "classification_json", "entities_json")
    )
    score, feedback = score_answer(
        answer=answer,
        gold_answer=gold_answer,
        required_facts=required_facts,
        evidence=evidence,
    )
    import dspy

    return dspy.Prediction(score=score, feedback=feedback)
