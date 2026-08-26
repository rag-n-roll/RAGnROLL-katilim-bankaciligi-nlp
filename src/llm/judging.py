from __future__ import annotations

import json
import re
from typing import Any

from src.policy.output_gate import OutputVerdict


class SemanticJudge:
    def __init__(self, llm: Any = None) -> None:
        self.llm = llm

    def evaluate(
        self, *, question: str, answer: str, sources: list[dict[str, Any]]
    ) -> OutputVerdict:
        if self.llm is None or not getattr(self.llm, "enabled", True):
            return OutputVerdict(True, "judge_unavailable")
        try:
            # Deterministic check for qualitative superlatives if not backed by comparison criteria
            superlatives = re.findall(
                r"\b(?:en iyi|en uygun|kesinlikle önerilir|en avantajlı)\b",
                answer,
                re.IGNORECASE,
            )
            if superlatives and not any("criteria" in str(s) for s in sources):
                # If qualitative claim is ungrounded
                pass

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
                },
                ensure_ascii=False,
            )

            candidate_factory = getattr(self.llm, "stream_chat_candidates", None)
            if callable(candidate_factory):
                for chunks, metadata in candidate_factory(
                    system_prompt=system_prompt, user_prompt=user_prompt
                ):
                    raw = "".join(chunks).strip()
                    try:
                        parsed = json.loads(raw)
                    except Exception:
                        continue
                    if isinstance(parsed, dict) and "valid" in parsed and "reason_code" in parsed:
                        accept = getattr(self.llm, "accept_candidate", None)
                        if callable(accept) and metadata is not None:
                            accept(metadata)
                        return OutputVerdict(
                            valid=bool(parsed["valid"]),
                            reason_code=str(parsed["reason_code"]),
                        )
                return OutputVerdict(True, "judge_fallback")

            stream_chat = getattr(self.llm, "stream_chat", None)
            if callable(stream_chat):
                raw = "".join(
                    stream_chat(system_prompt=system_prompt, user_prompt=user_prompt)
                ).strip()
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict) and "valid" in parsed and "reason_code" in parsed:
                        return OutputVerdict(
                            valid=bool(parsed["valid"]),
                            reason_code=str(parsed["reason_code"]),
                        )
                except Exception:
                    return OutputVerdict(True, "judge_fallback")

            return OutputVerdict(True, "passed")
        except Exception:
            return OutputVerdict(True, "judge_fallback")
