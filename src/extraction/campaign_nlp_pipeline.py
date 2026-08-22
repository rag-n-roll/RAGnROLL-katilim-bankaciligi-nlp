"""Unified local campaign NLP pipeline: classification, hybrid NER and normalization."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.extraction.campaign_fields import extract_prd_fields
from src.ner.hybrid_inference import DEFAULT_RULE_LABELS, predict_entities
from src.normalization import normalize_duration, normalize_money, normalize_rate
from src.extraction.date_range import extract_date_range


SCHEMA_VERSION = "campaign-nlp-v1"
DEFAULT_CLASSIFIER = Path("models/final_training/campaign_classifier.joblib")
DEFAULT_NER = Path("models/final_training/augmented_weighted_30e")

# Precision observed on the unified, untouched 90-document hybrid NER test set.
ENTITY_PRECISION = {
    "ALISVERIS_PUANI": 1.0,
    "BANKA": 0.989,
    "FINANSMAN_TUTARI": 0.794,
    "HEDEF_KITLE": 0.818,
    "INDIRIM_ORANI": 0.871,
    "KAMPANYA_AVANTAJI": 1.0,
    "KAMPANYA_KOSULU": 0.789,
    "KAMPANYA_TARIHI": 0.967,
    "KAR_PAYI_ORANI": 0.8,
    "MASRAF_BILGISI": 1.0,
    "ODUL_MIKTARI": 0.783,
    "PROMOSYON_KODU": 1.0,
    "TAHSIS_UCRETI": 1.0,
    "TAKSIT_SAYISI": 0.986,
    "URUN_TURU": 0.941,
    "VADE": 0.967,
}

LABEL_KEYWORDS = {
    "card": ("kart", "bankkart"),
    "housing_finance": ("konut finansmanı", "ev finansmanı"),
    "vehicle_finance": ("taşıt finansmanı", "araç finansmanı"),
    "consumer_finance": ("ihtiyaç finansmanı", "bireysel finansman"),
    "participation_account": ("katılma hesab", "katılım hesab"),
    "investment_product": ("yatırım", "altın", "döviz", "kira sertifikası"),
    "installment": ("taksit",),
    "discount": ("indirim",),
    "cashback": ("iade", "nakit iade"),
    "reward_points": ("puan", "worldpuan", "sağlam puan"),
    "promo_code": ("kod", "kodu"),
    "cardholder": ("kartınız", "kart sahip"),
    "new_customer": ("yeni müşteri", "müşteri ol"),
    "mobile": ("mobil", "uygulama"),
    "ecommerce": ("online", "internet", "e-ticaret"),
    "physical_branch": ("şube",),
    "minimum_spend": ("en az", "minimum", "üzeri harcama"),
    "minimum_balance": ("minimum", "bakiye"),
    "maximum_spend": ("en fazla", "maksimum"),
    "specific_card": ("kart ile", "kartınızla", "kartıyla"),
    "specific_merchant": ("iş yer", "marka", "mağaza"),
    "date_limited": ("tarih", "kampanya dönemi", "geçerli"),
    "application_required": ("katıl", "başvur"),
    "free_service": ("ücretsiz", "hediye"),
    "percentage_discount": ("%", "indirim"),
    "special_profit_rate": ("kâr oran", "kâr payı"),
}


# Keep these strings as escapes so Windows console encodings cannot corrupt them.
LABEL_KEYWORDS = {
    "card": ("kart", "bankkart"),
    "housing_finance": ("konut finansman\u0131", "ev finansman\u0131"),
    "vehicle_finance": ("ta\u015f\u0131t finansman\u0131", "ara\u00e7 finansman\u0131"),
    "consumer_finance": ("ihtiya\u00e7 finansman\u0131", "bireysel finansman"),
    "participation_account": ("kat\u0131lma hesab", "kat\u0131l\u0131m hesab"),
    "investment_product": (
        "yat\u0131r\u0131m", "alt\u0131n", "d\u00f6viz", "kira sertifikas\u0131",
    ),
    "installment": ("taksit",), "discount": ("indirim",),
    "cashback": ("iade", "nakit iade"),
    "reward_points": ("puan", "worldpuan", "sa\u011flam puan"),
    "promo_code": ("kod", "kodu"),
    "cardholder": ("kart\u0131n\u0131z", "kart sahip"),
    "new_customer": ("yeni m\u00fc\u015fteri", "m\u00fc\u015fteri ol"),
    "mobile": ("mobil", "uygulama"),
    "ecommerce": ("online", "internet", "e-ticaret"),
    "physical_branch": ("\u015fube",),
    "minimum_spend": ("en az", "minimum", "\u00fczeri harcama"),
    "minimum_balance": ("minimum", "bakiye"),
    "maximum_spend": ("en fazla", "maksimum"),
    "specific_card": ("kart ile", "kart\u0131n\u0131zla", "kart\u0131yla"),
    "specific_merchant": ("i\u015f yer", "marka", "ma\u011faza"),
    "date_limited": ("tarih", "kampanya d\u00f6nemi", "ge\u00e7erli"),
    "application_required": ("kat\u0131l", "ba\u015fvur"),
    "free_service": ("\u00fccretsiz", "hediye"),
    "percentage_discount": ("%", "indirim"),
    "special_profit_rate": ("k\u00e2r oran", "k\u00e2r pay\u0131"),
}


def _softmax(values: list[float]) -> list[float]:
    if not values:
        return []
    maximum = max(values)
    exponentials = [math.exp(value - maximum) for value in values]
    total = sum(exponentials)
    return [value / total for value in exponentials]


def _sigmoid(value: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, value))))


def _decision_confidences(model: Any, text: str) -> dict[str, float]:
    import numpy as np

    classes = [str(value) for value in model.classes_]
    raw = np.asarray(model.decision_function([text]))
    if len(classes) == 2 and raw.size == 1:
        positive = _sigmoid(float(raw.reshape(-1)[0]))
        return {classes[0]: 1.0 - positive, classes[1]: positive}
    values = [float(value) for value in raw.reshape(-1)]
    probabilities = _softmax(values)
    if len(values) > 1:
        order = sorted(range(len(values)), key=values.__getitem__, reverse=True)
        winner, runner_up = order[0], order[1]
        winner_confidence = _sigmoid(2.0 * (values[winner] - values[runner_up]))
        remaining_total = sum(probabilities) - probabilities[winner]
        for index in range(len(probabilities)):
            if index != winner:
                probabilities[index] = (
                    (1.0 - winner_confidence) * probabilities[index] / remaining_total
                    if remaining_total else 0.0
                )
        probabilities[winner] = winner_confidence
    return dict(zip(classes, probabilities))


def _sentence_evidence(text: str, label: str) -> str | None:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text) if part.strip()]
    keywords = LABEL_KEYWORDS.get(label, ())
    for part in parts:
        normalized = part.casefold().replace("i̇", "i")
        normalized = part.casefold().replace("i\u0307", "i")
        if any(keyword in normalized for keyword in keywords):
            return part[:500]
    return None


def _classification(bundle: dict[str, Any], text: str) -> dict[str, Any]:
    product_model = bundle["product_model"]
    product = str(product_model.predict([text])[0])
    product_confidences = _decision_confidences(product_model, text)
    dimensions = {}
    for field, components in bundle["field_models"].items():
        model, binarizer = components["model"], components["binarizer"]
        encoded = model.predict([text])[0]
        raw = model.decision_function([text])
        scores = [float(value) for value in getattr(raw, "reshape")(-1)]
        labels = [str(value) for value in binarizer.classes_]
        selected = []
        for index, label in enumerate(labels):
            if int(encoded[index]) != 1:
                continue
            selected.append(
                {
                    "value": label,
                    "confidence": round(_sigmoid(scores[index]), 4),
                    "evidence": _sentence_evidence(text, label),
                }
            )
        dimensions[field] = selected
    return {
        "product_category": {
            "value": product,
            "confidence": round(product_confidences.get(product, 0.0), 4),
            "evidence": _sentence_evidence(text, product),
        },
        "dimensions": dimensions,
    }


def normalize_entity(label: str, value: str, *, full_text: str = "") -> dict[str, Any] | None:
    if label in {"KAR_PAYI_ORANI", "INDIRIM_ORANI"}:
        rate = normalize_rate(value)
        if rate:
            fraction = float(rate.fraction)
            return {"type": "rate", "fraction": fraction, "percent": round(fraction * 100, 6)}
    if label in {
        "FINANSMAN_TUTARI", "ODUL_MIKTARI", "ALISVERIS_PUANI",
        "KAMPANYA_KOSULU", "TAHSIS_UCRETI", "MASRAF_BILGISI",
    }:
        money = normalize_money(value)
        if money:
            result = {"type": "money", **money.to_dict()}
            if label == "ALISVERIS_PUANI":
                result["semantic_type"] = "shopping_points"
            return result
    if label == "VADE":
        duration = normalize_duration(value)
        if duration:
            return {"type": "duration", **duration.to_dict()}
    if label == "TAKSIT_SAYISI":
        match = re.search(r"\d{1,3}", value)
        if match:
            return {"type": "installment", "count": int(match.group(0))}
    if label == "KAMPANYA_TARIHI":
        start, end = extract_date_range(full_text or value)
        if start or end:
            return {
                "type": "date_range",
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
            }
    if label == "PROMOSYON_KODU":
        return {"type": "code", "value": value.strip()}
    return None


def _entities(nlp: Any, text: str) -> list[dict[str, Any]]:
    entities = []
    for entity in predict_entities(nlp, text, DEFAULT_RULE_LABELS):
        label = str(entity["label"])
        entities.append(
            {
                **entity,
                "confidence": ENTITY_PRECISION.get(label, 0.8),
                "source": "deterministic_rule" if label in DEFAULT_RULE_LABELS else "spacy_ner",
                "normalized": normalize_entity(label, entity["text"], full_text=text),
                "evidence": entity["text"],
            }
        )
    return entities


def _overall_confidence(classification: dict[str, Any], entities: list[dict[str, Any]]) -> float:
    scores = [float(classification["product_category"]["confidence"])]
    scores.extend(
        float(item["confidence"])
        for values in classification["dimensions"].values()
        for item in values
    )
    scores.extend(float(entity["confidence"]) for entity in entities)
    return round(sum(scores) / len(scores), 4) if scores else 0.0


class CampaignNLPPipeline:
    def __init__(
        self,
        classifier_bundle: dict[str, Any],
        nlp: Any,
        *,
        classifier_path: str,
        ner_path: str,
    ) -> None:
        self.classifier_bundle = classifier_bundle
        self.nlp = nlp
        self.classifier_path = classifier_path
        self.ner_path = ner_path

    @classmethod
    def load(
        cls,
        classifier_path: str | Path = DEFAULT_CLASSIFIER,
        ner_path: str | Path = DEFAULT_NER,
    ) -> "CampaignNLPPipeline":
        import joblib
        import spacy

        return cls(
            joblib.load(classifier_path),
            spacy.load(ner_path),
            classifier_path=str(classifier_path),
            ner_path=str(ner_path),
        )

    def analyze(
        self,
        text: str,
        *,
        record_id: str | None = None,
        title: str | None = None,
        source_url: str | None = None,
    ) -> dict[str, Any]:
        source = str(text or "").strip()
        if not source:
            raise ValueError("Campaign text must not be empty")
        classification = _classification(self.classifier_bundle, source)
        entities = _entities(self.nlp, source)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entity in entities:
            grouped[entity["label"]].append(entity)
        start_date, end_date = extract_date_range(source)
        structured = extract_prd_fields(
            source,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
        )
        warnings = []
        if not entities:
            warnings.append("no_entities_detected")
        if classification["product_category"]["confidence"] < 0.55:
            warnings.append("low_product_confidence")
        low_entities = [entity["label"] for entity in entities if entity["confidence"] < 0.7]
        if low_entities:
            warnings.append("low_confidence_entities:" + ",".join(sorted(set(low_entities))))
        return {
            "schema_version": SCHEMA_VERSION,
            "record": {
                "id": record_id,
                "title": title,
                "source_url": source_url,
                "text_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            },
            "classification": classification,
            "entities": entities,
            "entities_by_label": dict(grouped),
            "structured": structured,
            "quality": {
                "overall_confidence": _overall_confidence(classification, entities),
                "warnings": warnings,
                "entity_count": len(entities),
            },
            "provenance": {
                "classifier": self.classifier_path,
                "ner": self.ner_path,
                "ner_strategy": "spacy_ner+deterministic_financial_rules",
                "classification_confidence_method": "uncalibrated_linear_margin_transform",
                "entity_confidence_method": "heldout_label_precision",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--classifier", default=str(DEFAULT_CLASSIFIER))
    parser.add_argument("--ner", default=str(DEFAULT_NER))
    args = parser.parse_args()
    if bool(args.text) == bool(args.input):
        parser.error("Use exactly one of --text or --input")
    text = args.text if args.text is not None else args.input.read_text(encoding="utf-8")
    result = CampaignNLPPipeline.load(args.classifier, args.ner).analyze(text)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
