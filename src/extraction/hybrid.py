"""Combine deterministic PRD extraction with an optional local spaCy NER model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.extraction.campaign_fields import extract_prd_fields


ENTITY_TO_FIELD = {
    "PROFIT_RATE": "profit_share_rate",
    "MATURITY": "term_months",
    "FINANCING_AMOUNT": "financing_amount",
    "CAMPAIGN_BENEFIT": "campaign_benefit",
    "END_DATE": "campaign_end_date",
    "BANK": "bank",
    "PRODUCT": "product",
    "CONDITION": "campaign_condition",
    "APPLICATION_CHANNEL": "application_channel",
}


class HybridExtractor:
    """Rules provide normalized values; NER adds contextual spans and missing text fields."""

    def __init__(self, model_path: str | Path | None = None) -> None:
        self.nlp = None
        if model_path is not None:
            import spacy

            self.nlp = spacy.load(model_path)

    def extract(
        self,
        text: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        result = extract_prd_fields(text, start_date=start_date, end_date=end_date)
        model_entities: list[dict[str, Any]] = []
        if self.nlp is not None:
            for entity in self.nlp(text).ents:
                item = {
                    "label": entity.label_,
                    "text": entity.text,
                    "start": entity.start_char,
                    "end": entity.end_char,
                }
                model_entities.append(item)
                field = ENTITY_TO_FIELD.get(entity.label_)
                if field and result.get(field) is None:
                    result[field] = entity.text
                    result.setdefault("evidence", {})[field] = entity.text
        result["model_entities"] = model_entities
        result["extraction_method"] = "rules-v1+spacy-ner" if self.nlp else "rules-v1"
        return result
