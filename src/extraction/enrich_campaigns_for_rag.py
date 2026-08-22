"""Enrich campaign JSON with final classifier and hybrid NER output for RAG."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.extraction.campaign_nlp_pipeline import CampaignNLPPipeline


PRODUCT_TYPE_MAP = {
    "card": "card",
    "investment_product": "investment",
    "participation_account": "investment",
    "insurance": "insurance",
    "agriculture_finance": "financing",
    "consumer_finance": "financing",
    "housing_finance": "financing",
    "other_finance": "financing",
    "shopping_finance": "financing",
    "sustainable_finance": "financing",
    "vehicle_finance": "financing",
}

FINANCING_TYPE_MAP = {
    "agriculture_finance": "agriculture",
    "consumer_finance": "consumer",
    "housing_finance": "housing",
    "shopping_finance": "shopping",
    "sustainable_finance": "sustainable",
    "vehicle_finance": "vehicle",
}

ENTITY_FIELD_MAP = {
    "KAR_PAYI_ORANI": "profit_share_rate",
    "FINANSMAN_TUTARI": "financing_amount",
    "VADE": "term_months",
    "TAKSIT_SAYISI": "installment_count",
    "KAMPANYA_AVANTAJI": "campaign_benefit",
    "ODUL_MIKTARI": "reward_amount",
    "ALISVERIS_PUANI": "reward_amount",
    "INDIRIM_ORANI": "discount_rate",
    "HEDEF_KITLE": "target_audience",
    "MASRAF_BILGISI": "fee_information",
    "TAHSIS_UCRETI": "fee_information",
    "KAMPANYA_KOSULU": "condition",
}


def _records(payload: Any) -> tuple[list[dict[str, Any]], bool]:
    if isinstance(payload, list):
        return payload, True
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return payload["records"], False
    raise ValueError("Campaign input must be a JSON list or an object with records")


def _contract(
    value: Any,
    *,
    raw: str | None,
    confidence: float,
    method: str,
    start: int | None = None,
    end: int | None = None,
) -> dict[str, Any]:
    unit = None
    if isinstance(value, dict):
        unit = value.get("currency") or value.get("unit") or value.get("type")
    return {
        "raw": raw,
        "value": value,
        "unit": unit,
        "status": "EXPLICIT" if raw else "IMPLICIT",
        "confidence": round(float(confidence), 4),
        "evidence": (
            {"text": raw, "char_start": start, "char_end": end}
            if raw
            else None
        ),
        "method": method,
        "conflicting_values": [],
    }


def _rag_field_contracts(
    analysis: dict[str, Any],
    structured: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    fields = dict(structured.get("fields") or {})
    product = analysis["classification"]["product_category"]
    fields.setdefault(
        "product_type",
        _contract(
            structured.get("product_type"),
            raw=product.get("evidence"),
            confidence=product.get("confidence", 0.0),
            method="classifier+mapping",
        ),
    )
    if structured.get("financing_type"):
        fields.setdefault(
            "financing_type",
            _contract(
                structured["financing_type"],
                raw=product.get("evidence"),
                confidence=product.get("confidence", 0.0),
                method="classifier+mapping",
            ),
        )
    for entity in analysis["entities"]:
        field = ENTITY_FIELD_MAP.get(str(entity["label"]))
        if not field or field in fields:
            continue
        normalized = entity.get("normalized")
        value = normalized if normalized is not None else entity["text"]
        fields[field] = _contract(
            value,
            raw=entity["text"],
            confidence=entity.get("confidence", 0.0),
            method=str(entity.get("source") or "hybrid_ner"),
            start=int(entity["start"]),
            end=int(entity["end"]),
        )
    dimensions = analysis["classification"]["dimensions"]
    if "target_audience" not in fields and dimensions.get("target_segments"):
        values = [item["value"] for item in dimensions["target_segments"]]
        confidence = min(float(item["confidence"]) for item in dimensions["target_segments"])
        fields["target_audience"] = _contract(
            values, raw=None, confidence=confidence, method="classifier"
        )
    if dimensions.get("channels"):
        values = [item["value"] for item in dimensions["channels"]]
        confidence = min(float(item["confidence"]) for item in dimensions["channels"])
        fields.setdefault(
            "application_channel",
            _contract(values, raw=None, confidence=confidence, method="classifier"),
        )
    return fields


def enrich(
    input_path: str | Path,
    output_path: str | Path,
    *,
    classifier: str | Path,
    ner: str | Path,
) -> dict[str, Any]:
    source = Path(input_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    records, list_payload = _records(payload)
    pipeline = CampaignNLPPipeline.load(classifier, ner)
    enriched = 0
    skipped = 0
    for record in records:
        text = str(
            record.get("clean_text")
            or record.get("content")
            or record.get("text")
            or ""
        ).strip()
        if not text:
            skipped += 1
            continue
        analysis = pipeline.analyze(
            text,
            record_id=str(record.get("id") or "") or None,
            title=str(record.get("title") or "") or None,
            source_url=str(record.get("source_url") or "") or None,
        )
        classification = analysis["classification"]
        category = classification["product_category"]["value"]
        structured = dict(record.get("structured") or {})
        structured.update(analysis["structured"])
        structured["product_category"] = category
        structured["product_type"] = (
            structured.get("product_type") or PRODUCT_TYPE_MAP.get(category)
        )
        structured["financing_type"] = (
            structured.get("financing_type") or FINANCING_TYPE_MAP.get(category)
        )
        structured["classification_dimensions"] = classification["dimensions"]
        structured["entities"] = analysis["entities"]
        structured["nlp_quality"] = analysis["quality"]
        structured["nlp_provenance"] = analysis["provenance"]
        structured["fields"] = _rag_field_contracts(analysis, structured)
        record["structured"] = structured
        enriched += 1

    output_payload: Any = records if list_payload else {**payload, "records": records}
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(output_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "input": str(source),
        "output": str(output),
        "records": len(records),
        "enriched": enriched,
        "skipped_without_text": skipped,
        "classifier": str(classifier),
        "ner": str(ner),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--classifier", default="models/final_training/campaign_classifier.joblib")
    parser.add_argument("--ner", default="models/final_training/augmented_weighted_30e")
    args = parser.parse_args()
    report = enrich(
        args.input,
        args.output,
        classifier=args.classifier,
        ner=args.ner,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
