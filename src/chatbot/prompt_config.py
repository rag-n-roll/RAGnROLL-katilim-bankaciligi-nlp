"""Load a GEPA-selected system prompt while keeping a safe built-in fallback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_SYSTEM_PROMPT = """Sen Türkçe konuşan bir katılım bankacılığı asistanısın.
Kampanya metni ile sınıflandırma ve hibrit entity kanıtlarını birlikte kullan.
Sadece sağlanan bağlamdaki bilgilere dayan; bilgi yoksa tam olarak
\"Bu bilgi sağlanan dokümanlarda bulunmamaktadır.\" yanıtını ver.
Sayı, oran, tarih, kod ve koşulları aynen koru. Kısa, açık ve doğrudan cevap ver."""


def load_prompt_config(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {"system_prompt": DEFAULT_SYSTEM_PROMPT, "demonstrations": []}
    data = json.loads(source.read_text(encoding="utf-8"))
    return {
        "system_prompt": str(data.get("system_prompt") or DEFAULT_SYSTEM_PROMPT),
        "demonstrations": list(data.get("demonstrations") or []),
    }


def render_prompt(
    *,
    question: str,
    context: str,
    config: dict[str, Any],
    max_demonstrations: int = 4,
) -> str:
    sections = [str(config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT).strip()]
    demos = list(config.get("demonstrations") or [])[:max_demonstrations]
    if demos:
        rendered = []
        for demo in demos:
            evidence = "\n".join(
                part
                for part in (
                    str(demo.get("campaign_text") or "").strip(),
                    "Sınıflandırma: " + str(demo.get("classification_json") or "{}"),
                    "Entityler: " + str(demo.get("entities_json") or "{}"),
                )
                if part
            )
            rendered.append(
                f"Örnek bağlam:\n{evidence}\nÖrnek soru: {demo.get('question', '')}\n"
                f"Örnek cevap: {demo.get('answer', '')}"
            )
        sections.append("Örnekler:\n\n" + "\n\n---\n\n".join(rendered))
    sections.append(f"Bağlam:\n{context}\n\nKullanıcı sorusu:\n{question}\n\nCevap:")
    return "\n\n".join(sections)

