from __future__ import annotations

import json
import re
from typing import Any

from src.policy.output_gate import OutputVerdict


ALLOWED_REASON_CODES = frozenset(
    {"passed", "question_not_answered", "unsupported_claim", "biased_claim"}
)
_ABSOLUTE_ADVICE_RE = re.compile(
    r"\b(?:en iyi|en uygun|en avantajlı\w*|tercih edilebilir|"
    r"kesinlikle önerilir)\b",
    re.IGNORECASE,
)
_RELATIVE_COMPARISON_RE = re.compile(
    r"\b(?:daha avantajlı\w*|öne çıkıyor\w*)\b", re.IGNORECASE
)
_METRIC_PATTERNS = {
    "PROFIT_RATE": re.compile(r"\b(?:k[âa]r pay[ıi]|oran)\w*\b", re.IGNORECASE),
    "MATURITY": re.compile(r"\b(?:vade|vadeli|ay)\b", re.IGNORECASE),
    "FEE": re.compile(r"\b(?:masraf|ücret|aidat|maliyet)\w*\b", re.IGNORECASE),
    "REWARD_AMOUNT": re.compile(
        r"\b(?:ödül|puan|iade|kazanç)\w*\b", re.IGNORECASE
    ),
}


def _parsed_verdict(raw: str) -> OutputVerdict | None:
    text = str(raw or "").strip()
    fenced = re.fullmatch(r"```json\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, dict) or set(parsed) != {"valid", "reason_code"}:
        return None
    valid = parsed.get("valid")
    reason_code = parsed.get("reason_code")
    if not isinstance(valid, bool):
        return None
    if not isinstance(reason_code, str) or reason_code not in ALLOWED_REASON_CODES:
        return None
    if valid and reason_code != "passed":
        return None
    if not valid and reason_code == "passed":
        return None
    return OutputVerdict(valid=valid, reason_code=reason_code)


class SemanticJudge:
    def __init__(self, llm: Any = None) -> None:
        self.llm = llm

    def evaluate(
        self,
        *,
        question: str,
        answer: str,
        sources: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
    ) -> OutputVerdict:
        if self.llm is None or not getattr(self.llm, "enabled", True):
            return OutputVerdict(False, "judge_unavailable")
        try:
            if _ABSOLUTE_ADVICE_RE.search(answer):
                return OutputVerdict(False, "unsupported_qualitative_claim")
            relative_claim = _RELATIVE_COMPARISON_RE.search(answer)
            safe_context = context if isinstance(context, dict) else {}
            plan = safe_context.get("plan")
            plan = plan if isinstance(plan, dict) else {}
            slots = plan.get("slots")
            slots = slots if isinstance(slots, dict) else {}
            facts = safe_context.get("facts")
            facts = facts if isinstance(facts, list) else []
            plan_metric = str(slots.get("metric") or "")
            measurable_facts = [
                fact
                for fact in facts
                if isinstance(fact, dict)
                and str(fact.get("campaign_id") or "").strip()
                and fact.get("value") is not None
                and fact.get("metric") == plan_metric
            ]
            objective_comparison = slots.get("aggregation") in {"MIN", "MAX"}
            complete_preferences = all(
                slots.get(key) is not None
                for key in ("term_months", "amount", "fee_priority")
            )
            comparison_authorized = (
                plan.get("intent") == "product_comparison"
                and bool(sources)
                and bool(measurable_facts)
                and (objective_comparison or complete_preferences)
                and plan_metric in _METRIC_PATTERNS
                and bool(_METRIC_PATTERNS[plan_metric].search(answer))
            )
            if relative_claim and not comparison_authorized:
                return OutputVerdict(False, "unsupported_qualitative_claim")

            system_prompt = (
                "Verilen Türkçe katılım bankacılığı soru, cevap ve kanıt paketini "
                "değerlendiren anlamsal denetçisin. Cevabın soruya doğrudan yanıt verip "
                "vermediğini, kanıt paketinde bulunmayan nitel veya taraflı iddialar "
                "içerip içermediğini denetle. "
                'Yalnız JSON formatında şu şemayı üret: {"valid": boolean, "reason_code": '
                '"passed"|"question_not_answered"|"unsupported_claim"|"biased_claim"}'
            )
            user_prompt = json.dumps(
                {
                    "question": question,
                    "answer": answer,
                    "sources": sources,
                    "context": safe_context,
                },
                ensure_ascii=False,
            )

            candidate_factory = getattr(self.llm, "stream_chat_candidates", None)
            if callable(candidate_factory):
                for chunks, metadata in candidate_factory(
                    system_prompt=system_prompt, user_prompt=user_prompt
                ):
                    raw = "".join(chunks).strip()
                    verdict = _parsed_verdict(raw)
                    if verdict is not None:
                        accept = getattr(self.llm, "accept_candidate", None)
                        if callable(accept) and metadata is not None:
                            accept(metadata)
                        return verdict
                return OutputVerdict(False, "judge_invalid_output")

            stream_chat = getattr(self.llm, "stream_chat", None)
            if callable(stream_chat):
                raw = "".join(
                    stream_chat(system_prompt=system_prompt, user_prompt=user_prompt)
                ).strip()
                verdict = _parsed_verdict(raw)
                if verdict is not None:
                    return verdict
                return OutputVerdict(False, "judge_invalid_output")

            return OutputVerdict(False, "judge_unavailable")
        except Exception:
            return OutputVerdict(False, "judge_unavailable")
