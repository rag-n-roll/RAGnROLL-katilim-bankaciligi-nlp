"""Create a human-review queue for PRD campaign-type classification.

Rules only suggest labels. Records remain ``human_verified=false`` and must not
be used for final metrics until a team member confirms or corrects each label.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


CAMPAIGN_LABELS = (
    "housing_finance",
    "vehicle_finance",
    "consumer_finance",
    "general_finance",
    "card_campaign",
    "shopping_points",
    "new_customer",
    "investment_product",
    "needs_review",
)

LABEL_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("housing_finance", (r"\bkonut\b", r"gayrimenkul", r"\bev\s+finansman")),
    ("vehicle_finance", (r"\btaşıt\b", r"\baraç\b", r"otomobil", r"motosiklet")),
    ("consumer_finance", (r"\bihtiyaç\s+finansman",)),
    ("shopping_points", (r"alışveriş\s+puan", r"worldpuan", r"sağlam\s+puan", r"hediye\s+puan")),
    ("new_customer", (r"yeni\s+müşteri", r"ilk\s+kez\s+müşteri", r"hoş\s+geldin")),
    ("investment_product", (r"katılma\s+hesab", r"yatırım", r"kira\s+sertifika", r"altın\s+hesab")),
    ("card_campaign", (r"\bkart", r"taksit", r"nakit\s+iade", r"indirim")),
    ("general_finance", (r"finansman",)),
)


def suggest_label(text: str) -> tuple[str, list[str]]:
    normalized = str(text or "").casefold()
    for label, patterns in LABEL_RULES:
        evidence = [pattern for pattern in patterns if re.search(pattern, normalized)]
        if evidence:
            return label, evidence
    return "needs_review", []


def _records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return payload.get("records", payload.get("campaigns", []))
    return []


def prepare(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8"))
    prepared = []
    for index, campaign in enumerate(_records(payload)):
        text_sources = (
            campaign.get("title"),
            campaign.get("clean_text"),
            campaign.get("content"),
        )
        text = "\n".join(
            part for part in text_sources
            if isinstance(part, str) and part.strip()
        )
        label, evidence = suggest_label(text)
        prepared.append(
            {
                "id": campaign.get("id", f"campaign-{index:04d}"),
                "text": text,
                "label": label,
                "human_verified": False,
                "split": None,
                "source_url": campaign.get("source_url"),
                "bank_slug": campaign.get("bank_slug"),
                "weak_label_evidence": evidence,
            }
        )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in prepared),
        encoding="utf-8",
    )
    return {
        "records": len(prepared),
        "label_distribution": dict(Counter(record["label"] for record in prepared)),
        "human_verification_required": True,
        "output": str(output),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    print(json.dumps(prepare(args.input, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
