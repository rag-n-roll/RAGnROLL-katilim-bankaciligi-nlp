"""EVREN llm-fast çıktısını yerel NLP advisory sözleşmesine güvenle ekler."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from typing import Any

from src.llm.client import LLMSettings, LLMUnavailableError, OpenAICompatibleLLM
from src.llm.decisions import _json_object
from src.nlp_runtime.advisory import SUGGESTION_ALLOWLIST, field_is_missing


class EvrenAdvisoryError(RuntimeError):
    """EVREN advisory çıktısının sözleşmeye alınamadığını belirtir."""


class EvrenAdvisoryAugmenter:
    """Yalnız eksik alan ve birebir kanıt aralığı için model önerisi kabul eder."""

    def __init__(self, client: OpenAICompatibleLLM | None = None) -> None:
        settings = replace(
            LLMSettings.evren_from_env(),
            model="llm-fast",
            max_tokens=1024,
            temperature=0.0,
        )
        self.client = client or OpenAICompatibleLLM(settings)

    @property
    def enabled(self) -> bool:
        return self.client.enabled

    @staticmethod
    def _validated_suggestions(
        payload: dict[str, Any], *, text: str, structured: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        if set(payload) != {"suggestions"}:
            raise EvrenAdvisoryError("EVREN advisory üst sözleşmesi geçersiz")
        suggestions = payload.get("suggestions")
        if not isinstance(suggestions, dict):
            raise EvrenAdvisoryError("EVREN advisory önerileri nesne olmalıdır")
        unexpected = set(suggestions) - SUGGESTION_ALLOWLIST
        if unexpected:
            raise EvrenAdvisoryError("EVREN advisory izin verilmeyen alan içeriyor")
        validated = {}
        for field, item in suggestions.items():
            if not field_is_missing(structured, field):
                continue
            if not isinstance(item, dict) or set(item) != {"value", "evidence"}:
                raise EvrenAdvisoryError("EVREN advisory alan sözleşmesi geçersiz")
            value = item.get("value")
            evidence = item.get("evidence")
            if value in (None, "", [], {}) or not isinstance(evidence, dict):
                raise EvrenAdvisoryError("EVREN advisory değeri veya kanıtı eksik")
            if set(evidence) != {"text", "char_start", "char_end"}:
                raise EvrenAdvisoryError("EVREN advisory kanıt sözleşmesi geçersiz")
            start = evidence.get("char_start")
            end = evidence.get("char_end")
            evidence_text = evidence.get("text")
            if (
                isinstance(start, bool)
                or not isinstance(start, int)
                or isinstance(end, bool)
                or not isinstance(end, int)
                or not isinstance(evidence_text, str)
                or start < 0
                or end <= start
                or text[start:end] != evidence_text
            ):
                raise EvrenAdvisoryError("EVREN advisory kanıt aralığı geçersiz")
            validated[field] = {
                "value": value,
                "evidence": dict(evidence),
                "method": "evren_llm_fast",
                "advisory": True,
            }
        return validated

    def augment(
        self,
        analysis: dict[str, Any],
        *,
        text: str,
        structured: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.enabled:
            return analysis
        fields = sorted(
            field for field in SUGGESTION_ALLOWLIST if field_is_missing(structured, field)
        )
        if not fields:
            return analysis
        system = (
            "Katılım bankacılığı kampanya metninden yalnız açıkça yazılmış eksik alanları "
            "öner. Hesap yapma ve çıkarım uydurma. Yalnız şu JSON'u döndür: "
            '{"suggestions":{"alan":{"value":...,"evidence":{"text":"...",'
            '"char_start":0,"char_end":1}}}}. Kanıt aralığı verilen metinde birebir olmalı. '
            "Alan allowlist: " + ", ".join(fields)
        )
        try:
            raw = "".join(
                self.client.stream_chat(system_prompt=system, user_prompt=text)
            ).strip()
        except LLMUnavailableError as exc:
            raise EvrenAdvisoryError("EVREN advisory servisi kullanılamadı") from exc
        payload = _json_object(raw)
        if payload is None:
            raise EvrenAdvisoryError("EVREN advisory JSON çıktısı geçersiz")
        remote = self._validated_suggestions(
            payload, text=text, structured=structured
        )
        result = deepcopy(analysis)
        local = result.get("suggestions")
        local = dict(local) if isinstance(local, dict) else {}
        warnings = result.setdefault("quality", {}).setdefault("warnings", [])
        accepted = 0
        for field, suggestion in remote.items():
            existing = local.get(field)
            if existing is not None:
                left = json.dumps(
                    existing.get("value"), ensure_ascii=False, sort_keys=True
                )
                right = json.dumps(
                    suggestion.get("value"), ensure_ascii=False, sort_keys=True
                )
                if left != right:
                    local.pop(field, None)
                    warnings.append(f"conflicting_evren_suggestion:{field}")
                    continue
            local[field] = suggestion
            accepted += 1
        result["suggestions"] = local
        result["quality"]["suggestion_count"] = len(local)
        result["augmentation"] = {
            "provider": "evren",
            "requested_model": "llm-fast",
            "accepted_suggestions": accepted,
            "advisory_only": True,
        }
        return result
