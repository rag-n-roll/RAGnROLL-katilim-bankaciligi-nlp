"""Model çıktısını yalnız kanıtlı ve otorite olmayan önerilere dönüştürür."""

from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any

from src.extraction.campaign_fields import extract_prd_fields
from src.nlp_runtime.integrity import RUNTIME_CONTRACT
from src.normalization import normalize_duration, normalize_money, normalize_rate


SUGGESTION_ALLOWLIST = frozenset(
    {
        "application_channel",
        "campaign_benefit",
        "discount_rate",
        "fee_information",
        "financing_amount",
        "financing_type",
        "installment_count",
        "min_amount",
        "product_type",
        "profit_share_rate",
        "reward_amount",
        "target_audience",
        "term_months",
    }
)
SENSITIVE_LABELS = frozenset(
    {"application_required", "new_customer", "physical_branch"}
)
PRODUCT_TYPE_MAP = {
    "agriculture_finance": "financing",
    "card": "card",
    "consumer_finance": "financing",
    "housing_finance": "financing",
    "insurance": "insurance",
    "investment_product": "investment",
    "other_finance": "financing",
    "participation_account": "investment",
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


def _pattern(value: str) -> re.Pattern[str]:
    return re.compile(value, re.IGNORECASE | re.UNICODE)


LABEL_PATTERNS = {
    "additional_installment": _pattern(r"\bek\s+taksit\b"),
    "application_required": _pattern(
        r"\b(?:ba[şs]vur(?:u|usu|mak|arak|un|unuz)?|"
        r"kampanyaya\s+kat[ıi]l(?:ım|im|mak|ın|in)?|kat[ıi]l\s+butonu)\b"
    ),
    "atm": _pattern(r"\b(?:ATM|bankamatik)\b"),
    "call_center": _pattern(r"\b(?:çağrı\s+merkezi|müşteri\s+hizmetleri)\b"),
    "card": _pattern(r"\b(?:kart|bankkart|kredi\s+kartı)\b"),
    "card_pos": _pattern(r"\bPOS\b"),
    "cardholder": _pattern(r"\bkart\s+sahip(?:leri|lerine)?\b"),
    "cashback": _pattern(r"\b(?:nakit\s+)?iade\b"),
    "commercial_sme": _pattern(r"\b(?:ticari|KOBİ|esnaf)\b"),
    "consumer_finance": _pattern(r"\b(?:ihtiyaç|bireysel)\s+finansman[ıi]?\b"),
    "date_limited": _pattern(
        r"\b\d{1,2}\s+[A-Za-zÇĞİÖŞÜçğıöşü]+\s+20\d{2}\b"
    ),
    "digital_customer": _pattern(r"\bdijital\s+müşteri(?:ler|lere)?\b"),
    "discount": _pattern(r"\bindirim\b"),
    "ecommerce": _pattern(r"\b(?:e-ticaret|internetten|online)\b"),
    "farmer": _pattern(r"\b(?:çiftçi|üretici)(?:ler|lere)?\b"),
    "fee_exemption": _pattern(r"\b(?:ücret|masraf)\s+muafiyet[iı]?\b"),
    "free_service": _pattern(r"\b(?:ücretsiz|bedelsiz|hediye)\b"),
    "gift_voucher": _pattern(r"\b(?:hediye\s+çeki|kupon)\b"),
    "housing_finance": _pattern(r"\b(?:konut|ev)\s+finansman[ıi]?\b"),
    "installment": _pattern(r"\btaksit\b"),
    "internet_branch": _pattern(r"\binternet\s+şubesi\b"),
    "investment_product": _pattern(r"\b(?:yatırım|altın|döviz|kira\s+sertifikası)\b"),
    "minimum_balance": _pattern(r"\b(?:asgari|minimum|en\s+az)\s+bakiye\b"),
    "minimum_spend": _pattern(
        r"\b(?:en\s+az|min(?:imum)?|\d[\d.,]*\s*(?:TL|TRY|₺)\s+ve\s+üzeri)"
        r"[^.!?]{0,40}\b(?:harcama|alışveriş)\b"
    ),
    "mobile": _pattern(
        r"\b(?:mobil\s+uygulama(?:dan|den|ya|ye|sı|si)?|mobil\s+(?:şube|sube))\b"
    ),
    "new_customer": _pattern(
        r"\b(?:yeni\s+(?:bireysel\s+)?m[üu][şs]teri(?:ler|lere|si|miz)?|"
        r"ilk\s+kez\s+m[üu][şs]teri(?:ler|lere)?)\b"
    ),
    "participation_account": _pattern(r"\bkatıl(?:ım|ma)\s+hesab[ıi]\b"),
    "percentage_discount": _pattern(r"%\s*\d[\d.,]*\s+indirim\b"),
    "physical_branch": _pattern(
        r"\b(?:fiziksel\s+)?(?:şube|sube)"
        r"(?:si|sine|sinde|de|den|ye|ler|lerde)?\b"
    ),
    "promo_code": _pattern(r"\b(?:promosyon|kampanya)\s+kod[uyla]*\b"),
    "reward_points": _pattern(r"\b(?:puan|worldpuan|sağlam\s+puan)\b"),
    "salary_customer": _pattern(r"\bmaaş\s+müşteri(?:leri|lerine)?\b"),
    "special_profit_rate": _pattern(r"\b(?:özel|avantajlı)\s+k[aâ]r\s+pay[ıi]\b"),
    "specific_card": _pattern(r"\b[\wçğıöşü]+\s+kart(?:ınız|ıyla|ı\s+ile)\b"),
    "specific_merchant": _pattern(r"\b(?:iş\s*yeri|mağaza|marka)(?:nde|lerde)?\b"),
    "vehicle_finance": _pattern(r"\b(?:taşıt|araç)\s+finansman[ıi]?\b"),
    "youth_student": _pattern(r"\b(?:genç|öğrenci)(?:ler|lere)?\b"),
    "zero_profit_rate": _pattern(r"\b(?:sıfır|0)\s+k[aâ]r\s+pay[ıi]\b"),
}


NER_FIELD_MAP = {
    "FINANSMAN_TUTARI": "financing_amount",
    "INDIRIM_ORANI": "discount_rate",
    "KAMPANYA_AVANTAJI": "campaign_benefit",
    "KAR_PAYI_ORANI": "profit_share_rate",
    "MASRAF_BILGISI": "fee_information",
    "TAHSIS_UCRETI": "fee_information",
    "TAKSIT_SAYISI": "installment_count",
    "VADE": "term_months",
}
MONEY_SURFACE = r"\d[\d.,]*\s*(?:TL|TRY|₺)"
MINIMUM_SPEND_PATTERNS = (
    _pattern(
        rf"(?P<money>{MONEY_SURFACE})\s+(?:ve\s+)?(?:üzeri|üstü)"
        r"[^.!?]{0,35}\b(?:harcama|alışveriş)(?:ya|ye|da|de|sı|si|lar)?\b"
    ),
    _pattern(
        rf"\b(?:en\s+az|minimum)\s+(?P<money>{MONEY_SURFACE})"
        r"[^.!?]{0,35}\b(?:harcama|alışveriş)(?:ya|ye|da|de|sı|si|lar)?\b"
    ),
)


def _evidence(match: re.Match[str] | None) -> dict[str, Any] | None:
    if match is None:
        return None
    return {
        "text": match.group(0),
        "char_start": match.start(),
        "char_end": match.end(),
    }


def label_evidence(text: str, label: str) -> dict[str, Any] | None:
    pattern = LABEL_PATTERNS.get(label)
    match = pattern.search(text) if pattern is not None else None
    while label == "physical_branch" and match is not None:
        prefix = text[max(0, match.start() - 12) : match.start()].casefold()
        if re.search(r"(?:internet|mobil|e-)\s*$", prefix):
            match = pattern.search(text, match.end())
            continue
        break
    return _evidence(match)


def _flat_numbers(value: Any) -> list[float]:
    reshape = getattr(value, "reshape", None)
    flattened = reshape(-1) if callable(reshape) else value
    return [float(item) for item in flattened]


def classification(classifier: dict[str, Any], text: str) -> dict[str, Any]:
    product_model = classifier["product_model"]
    product = str(product_model.predict([text])[0])
    product_classes = [str(value) for value in product_model.classes_]
    product_scores = _flat_numbers(product_model.decision_function([text]))
    score_by_product = dict(zip(product_classes, product_scores))
    product_evidence = label_evidence(text, product)
    dimensions: dict[str, list[dict[str, Any]]] = {}
    suppressed = []
    for dimension, components in sorted(classifier["field_models"].items()):
        model = components["model"]
        binarizer = components["binarizer"]
        encoded = [int(value) for value in model.predict([text])[0]]
        scores = _flat_numbers(model.decision_function([text]))
        selected = []
        for index, raw_label in enumerate(binarizer.classes_):
            label = str(raw_label)
            if encoded[index] != 1:
                continue
            evidence = label_evidence(text, label)
            if label in SENSITIVE_LABELS and evidence is None:
                suppressed.append(f"{dimension}:{label}")
                continue
            selected.append(
                {
                    "value": label,
                    "decision_score": round(scores[index], 6),
                    "evidence": evidence,
                }
            )
        dimensions[str(dimension)] = sorted(selected, key=lambda item: item["value"])
    return {
        "product_category": {
            "value": product,
            "decision_score": round(score_by_product.get(product, 0.0), 6),
            "evidence": product_evidence,
        },
        "dimensions": dimensions,
        "score_contract": "uncalibrated_decision_margin",
        "suppressed_without_evidence": sorted(suppressed),
    }


def normalize_entity(label: str, text: str) -> Any:
    if label in {"INDIRIM_ORANI", "KAR_PAYI_ORANI"}:
        value = normalize_rate(text)
        return round(float(value.fraction), 6) if value else None
    if label == "FINANSMAN_TUTARI":
        value = normalize_money(text)
        return value.to_dict() if value else None
    if label == "VADE":
        value = normalize_duration(text)
        if value is None:
            return None
        if value.unit == "month":
            return int(value.value)
        if value.unit == "year":
            return int(value.value) * 12
        return None
    if label == "TAKSIT_SAYISI":
        match = re.search(r"\d{1,3}", text)
        return int(match.group(0)) if match else None
    return None


def entities(ner: Any, text: str) -> list[dict[str, Any]]:
    result = []
    for entity in ner(text).ents:
        label = str(entity.label_)
        result.append(
            {
                "start": int(entity.start_char),
                "end": int(entity.end_char),
                "text": str(entity.text),
                "label": label,
                "normalized": normalize_entity(label, str(entity.text)),
                "source": "spacy_ner",
            }
        )
    return sorted(result, key=lambda item: (item["start"], item["end"], item["label"]))


def _present(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def field_is_missing(structured: dict[str, Any], field: str) -> bool:
    if _present(structured.get(field)):
        return False
    fields = structured.get("fields")
    contract = fields.get(field) if isinstance(fields, dict) else None
    if not isinstance(contract, dict):
        return True
    if _present(contract.get("value")):
        return False
    return str(contract.get("status") or "NOT_STATED") in {
        "NOT_STATED",
        "EXTRACTION_FAILED",
    }


def _suggestion(
    *,
    value: Any,
    evidence: dict[str, Any] | None,
    method: str,
    decision_score: float | None = None,
) -> dict[str, Any] | None:
    if not _present(value) or evidence is None:
        return None
    result = {
        "value": value,
        "evidence": evidence,
        "method": method,
        "advisory": True,
    }
    if decision_score is not None:
        result["decision_score"] = round(float(decision_score), 6)
    return result


def _entity_has_field_context(
    text: str, entity: dict[str, Any], field: str
) -> bool:
    start = max(0, int(entity["start"]) - 50)
    end = min(len(text), int(entity["end"]) + 50)
    context = text[start:end].casefold()
    required = {
        "discount_rate": r"\b(?:indirim|iade)\b",
        "financing_amount": r"\b(?:finansman|kredi|fonlama)\b",
        "installment_count": r"\btaksit\b",
        "profit_share_rate": r"\bk[aâ]r\s+pay[ıi]\b",
        "term_months": r"\bvade(?:li)?\b",
    }
    pattern = required.get(field)
    if pattern is None:
        return True
    if not re.search(pattern, context):
        return False
    if field == "financing_amount":
        trailing = text[int(entity["end"]) : min(len(text), int(entity["end"]) + 35)]
        if re.search(r"\b(?:ödül|odul|iade|puan|bonus)\b", trailing, re.IGNORECASE):
            return False
    return True


def _extracted_suggestions(text: str) -> dict[str, dict[str, Any]]:
    extracted = extract_prd_fields(text)
    evidence = extracted.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    suggestions: dict[str, dict[str, Any]] = {}
    for field in sorted(SUGGESTION_ALLOWLIST):
        raw = evidence.get(field)
        if not isinstance(raw, str) or not raw:
            continue
        start = text.find(raw)
        if start < 0:
            continue
        item = _suggestion(
            value=extracted.get(field),
            evidence={"text": raw, "char_start": start, "char_end": start + len(raw)},
            method="deterministic_rule",
        )
        if item is not None:
            suggestions[field] = item
    for pattern in MINIMUM_SPEND_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        normalized = normalize_money(match.group("money"))
        if normalized is None:
            continue
        money_start, money_end = match.span("money")
        suggestions["min_amount"] = {
            "value": normalized.to_dict(),
            "evidence": {
                "text": text[money_start:money_end],
                "char_start": money_start,
                "char_end": money_end,
            },
            "method": "deterministic_rule",
            "advisory": True,
        }
        break
    return suggestions


def suggestions(
    text: str,
    structured: dict[str, Any],
    classified: dict[str, Any],
    detected_entities: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    candidates: dict[str, list[dict[str, Any]]] = {
        field: [candidate]
        for field, candidate in _extracted_suggestions(text).items()
    }

    def add(field: str, candidate: dict[str, Any] | None) -> None:
        if candidate is not None:
            candidates.setdefault(field, []).append(candidate)

    product = classified["product_category"]
    category = str(product["value"])
    add(
        "product_type",
        _suggestion(
            value=PRODUCT_TYPE_MAP.get(category),
            evidence=product.get("evidence"),
            method="classifier_mapping",
            decision_score=product.get("decision_score"),
        ),
    )
    add(
        "financing_type",
        _suggestion(
            value=FINANCING_TYPE_MAP.get(category),
            evidence=product.get("evidence"),
            method="classifier_mapping",
            decision_score=product.get("decision_score"),
        ),
    )
    target_labels = classified["dimensions"].get("target_segments", [])
    new_customer = next(
        (item for item in target_labels if item["value"] == "new_customer"), None
    )
    if new_customer is not None:
        add(
            "target_audience",
            _suggestion(
                value="new_customer",
                evidence=new_customer.get("evidence"),
                method="classifier_sensitive_regex",
                decision_score=new_customer.get("decision_score"),
            ),
        )
    channel_labels = classified["dimensions"].get("channels", [])
    for channel in channel_labels:
        if not channel.get("evidence"):
            continue
        add(
            "application_channel",
            _suggestion(
                value=channel["value"],
                evidence=channel["evidence"],
                method=(
                    "classifier_sensitive_regex"
                    if channel["value"] == "physical_branch"
                    else "classifier_evidence"
                ),
                decision_score=channel["decision_score"],
            ),
        )
    for entity in detected_entities:
        field = NER_FIELD_MAP.get(entity["label"])
        if field is None or not _entity_has_field_context(text, entity, field):
            continue
        value = entity.get("normalized")
        if value is None and field in {"campaign_benefit", "fee_information"}:
            value = entity["text"]
        add(
            field,
            _suggestion(
                value=value,
                evidence={
                    "text": entity["text"],
                    "char_start": entity["start"],
                    "char_end": entity["end"],
                },
                method="spacy_ner",
            ),
        )
    resolved: dict[str, dict[str, Any]] = {}
    warnings = []
    method_order = {
        "deterministic_rule": 0,
        "classifier_sensitive_regex": 1,
        "classifier_evidence": 2,
        "classifier_mapping": 3,
        "spacy_ner": 4,
    }
    for field, field_candidates in sorted(candidates.items()):
        if field not in SUGGESTION_ALLOWLIST or not field_is_missing(structured, field):
            continue
        values = {
            json.dumps(
                candidate.get("value"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            for candidate in field_candidates
            if candidate is not None
        }
        if len(values) > 1:
            warnings.append(f"conflicting_suggestions:{field}")
            continue
        resolved[field] = min(
            field_candidates,
            key=lambda candidate: (
                method_order.get(str(candidate.get("method")), 99),
                repr(candidate),
            ),
        )
    return resolved, warnings


def analyze(
    classifier: dict[str, Any],
    ner: Any,
    text: str,
    *,
    structured: dict[str, Any] | None = None,
    record_id: str | None = None,
    content_hash: str | None = None,
    source_version: int | None = None,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = str(text or "").strip()
    if not source:
        raise ValueError("Kampanya metni boş olamaz")
    authoritative = structured if isinstance(structured, dict) else {}
    classified = classification(classifier, source)
    suppressed = classified.pop("suppressed_without_evidence")
    detected_entities = entities(ner, source)
    proposed, warnings = suggestions(
        source, authoritative, classified, detected_entities
    )
    if classified["product_category"].get("evidence") is None:
        warnings.append("product_category_without_explicit_evidence")
    if not detected_entities:
        warnings.append("no_model_entities")
    return {
        "contract": RUNTIME_CONTRACT,
        "record": {
            "id": record_id,
            "source_content_hash": content_hash,
            "source_version": source_version,
            "text_sha256": sha256(source.encode("utf-8")).hexdigest(),
        },
        "classification": classified,
        "entities": detected_entities,
        "suggestions": proposed,
        "quality": {
            "entity_count": len(detected_entities),
            "suggestion_count": len(proposed),
            "warnings": warnings,
            "suppressed_without_evidence": suppressed,
        },
        "provenance": provenance
        or {
            "classifier": "verified_joblib",
            "ner": "verified_spacy",
            "runtime_contract": RUNTIME_CONTRACT,
        },
    }
