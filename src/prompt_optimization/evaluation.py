"""Deterministic proxy scoring for references projected from training labels."""

from __future__ import annotations

import re
from collections import Counter
from statistics import fmean
from typing import Any, Iterable, Mapping


FALLBACK_ANSWER = "Bu bilgi sağlanan dokümanlarda bulunmamaktadır."
PROVENANCE_SLICES = ("human", "auto", "synthetic")


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
    pattern = r"(?<!\w)(?:%?\d[\d.,/-]*|[A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9_-]{3,})(?!\w)"
    return {token.casefold() for token in re.findall(pattern, text)}


def score_answer(
    *,
    answer: str,
    gold_answer: str,
    required_facts: list[str],
    evidence: str,
) -> tuple[float, str]:
    """Score label agreement; this is not an independent human-gold metric."""
    answer = str(answer or "").strip()
    if gold_answer.strip() == FALLBACK_ANSWER:
        score = float(answer == FALLBACK_ANSWER)
        feedback = (
            "Eksik bilgi yanıtı tam doğru."
            if score
            else "Bağlamda olmayan bilgi için sabit güvenli yanıtı kullan."
        )
        return score, feedback

    normalized_answer = " ".join(_normalize(answer))
    covered = [
        fact
        for fact in required_facts
        if " ".join(_normalize(fact)) in normalized_answer
    ]
    coverage = len(covered) / len(required_facts) if required_facts else 1.0
    f1 = _token_f1(gold_answer, answer)
    supported = _numbers_and_codes(evidence + " " + gold_answer)
    invented = _numbers_and_codes(answer) - supported
    hallucination_penalty = min(0.35, 0.08 * len(invented))
    length_penalty = 0.08 if len(answer) > max(900, len(gold_answer) * 2) else 0.0
    score = max(
        0.0,
        min(1.0, 0.68 * coverage + 0.32 * f1 - hallucination_penalty - length_penalty),
    )
    missing = [fact for fact in required_facts if fact not in covered][:5]
    feedback_parts = [f"Zorunlu bilgi kapsama oranı %{coverage * 100:.0f}."]
    if missing:
        feedback_parts.append("Eksik bilgiler: " + ", ".join(missing) + ".")
    if invented:
        feedback_parts.append(
            "Bağlamda desteklenmeyen sayı/kodlar: "
            + ", ".join(sorted(invented))
            + "."
        )
    if length_penalty:
        feedback_parts.append("Yanıt gereğinden uzun; kısa ve doğrudan yaz.")
    return score, " ".join(feedback_parts)


def _slice(scores: list[float]) -> dict[str, int | float | None]:
    return {"n": len(scores), "score": fmean(scores) if scores else None}


def summarize_proxy_scores(
    scored_examples: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Report derived-label scores separately by reference provenance."""
    grouped: dict[str, list[float]] = {name: [] for name in PROVENANCE_SLICES}
    overall: list[float] = []
    for item in scored_examples:
        if item.get("reference_kind") != "derived_label_projection":
            raise ValueError("Proxy reports accept only derived_label_projection references")
        provenance = str(item.get("reference_provenance") or "")
        if provenance not in grouped:
            raise ValueError(f"Unknown reference provenance: {provenance!r}")
        score = float(item["score"])
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"Proxy score must be in [0, 1], got {score}")
        grouped[provenance].append(score)
        overall.append(score)
    return {
        "metric_kind": "proxy",
        "reference_kind": "derived_label_projection",
        "slices": {
            "overall": _slice(overall),
            **{name: _slice(grouped[name]) for name in PROVENANCE_SLICES},
        },
        "independent_gold": {"status": "not_provided", "score": None},
    }
