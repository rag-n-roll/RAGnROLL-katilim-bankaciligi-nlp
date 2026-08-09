"""PRD alanları için yerel ve deterministik kural tabanlı çıkarım."""

from __future__ import annotations

import re
from typing import Any

from src.normalization import normalize_duration, normalize_money, normalize_rate

NUMBER = r"\d[\d.,]*"
PROFIT_PATTERNS = (
    re.compile(rf"%\s*({NUMBER})\s*k[aâ]r\s+pay[ıi](?:\s+oran[ıi])?", re.IGNORECASE),
    re.compile(rf"k[aâ]r\s+pay[ıi](?:\s+oran[ıi])?\s*%\s*({NUMBER})", re.IGNORECASE),
)
DISCOUNT_PATTERN = re.compile(
    rf"(?:%\s*({NUMBER})|({NUMBER})\s*%)\s*(?:indirim|iade)",
    re.IGNORECASE,
)
TERM_PATTERN = re.compile(r"(?<!\d)(\d{1,3})\s*ay\s*(?:vade|vadeli)", re.IGNORECASE)
DURATION_PATTERN = re.compile(
    r"(?<!\d)\d{1,4}\s*(?:gün|gun|ay|yıl|yil)(?:\s*(?:vade|vadeli))?",
    re.IGNORECASE,
)
INSTALLMENT_PATTERN = re.compile(
    r"(?<!\d)(\d{1,3})\s*(?:aya\s+varan\s+)?taksit", re.IGNORECASE
)
MONEY_PATTERN = re.compile(
    rf"(?:[₺$€£]\s*{NUMBER}|{NUMBER}(?:\s+milyon)?\s*(?:TL|₺|TRY|USD|\$|EUR|€|GBP|£))",
    re.IGNORECASE,
)
MONEY_REWARD_PATTERN = re.compile(
    rf"({MONEY_PATTERN.pattern})(?=[^.!?]{{0,45}}(?:ödül|odul|iade|puan|bonus))",
    re.IGNORECASE,
)
MAX_AMOUNT_PATTERN = re.compile(
    rf"({MONEY_PATTERN.pattern})(?:['’]?ye)?\s+kadar", re.IGNORECASE
)
MIN_AMOUNT_PATTERN = re.compile(
    rf"en\s+az\s+({MONEY_PATTERN.pattern})(?:\s+ile)?", re.IGNORECASE
)


def _normalized(value: str) -> str:
    return value.casefold().replace("i̇", "i")


def _number(value: str) -> float:
    normalized = normalize_money(f"{value} TL")
    return float(normalized.amount) if normalized else 0.0


def _percentage(value: str) -> float:
    normalized = normalize_rate(f"%{value}")
    return round(float(normalized.fraction), 6) if normalized else 0.0


def _product_type(text: str) -> str | None:
    if "finansman" in text:
        return "financing"
    if any(word in text for word in ("kart", "bonus")):
        return "card"
    investment_words = (
        "yatırım",
        "yatirim",
        "katılma hesab",
        "katilma hesab",
        "altın",
        "altin",
    )
    if any(word in text for word in investment_words):
        return "investment"
    if any(
        word in text
        for word in ("alışveriş puan", "alisveris puan", "worldpuan", "parafpara")
    ):
        return "shopping_points"
    new_customer_words = (
        "yeni müşteri",
        "yeni musteri",
        "ilk kez müşteri",
        "ilk kez musteri",
    )
    if any(word in text for word in new_customer_words):
        return "new_customer"
    return None


def _financing_type(text: str) -> str | None:
    if "konut" in text:
        return "housing"
    if any(word in text for word in ("taşıt", "tasit", "araç", "arac")):
        return "vehicle"
    if "ihtiyaç" in text or "ihtiyac" in text:
        return "consumer"
    return None


def _first_match(
    patterns: tuple[re.Pattern[str], ...], text: str
) -> re.Match[str] | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match
    return None


def _benefit(text: str) -> str | None:
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        normalized = _normalized(sentence)
        benefit_words = (
            "avantaj",
            "indirim",
            "ödül",
            "odul",
            "iade",
            "masrafsız",
            "masrafsiz",
        )
        if any(word in normalized for word in benefit_words):
            return sentence[:500]
    return None


def extract_prd_fields(
    text: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Metinden PRD alanlarını çıkarır; bulunmayan değerleri tahmin etmez."""
    source = str(text or "")
    normalized = _normalized(source)
    evidence: dict[str, str] = {}

    profit_match = _first_match(PROFIT_PATTERNS, source)
    profit_share_rate = None
    if profit_match:
        profit_share_rate = _percentage(profit_match.group(1))
        evidence["profit_share_rate"] = profit_match.group(0)

    term_match = TERM_PATTERN.search(source)
    duration_match = term_match or DURATION_PATTERN.search(source)
    installment_match = INSTALLMENT_PATTERN.search(source)
    discount_match = DISCOUNT_PATTERN.search(source)
    reward_match = MONEY_REWARD_PATTERN.search(source)
    max_amount_match = MAX_AMOUNT_PATTERN.search(source)
    min_amount_match = MIN_AMOUNT_PATTERN.search(source)
    duration = normalize_duration(duration_match.group(0)) if duration_match else None
    discount_value = None
    if discount_match:
        discount_value = discount_match.group(1) or discount_match.group(2)
    if term_match:
        evidence["term_months"] = term_match.group(0)
    if installment_match:
        evidence["installment_count"] = installment_match.group(0)
    if discount_match:
        evidence["discount_rate"] = discount_match.group(0)
    if reward_match:
        evidence["reward_amount"] = reward_match.group(0)
    if max_amount_match:
        evidence["max_amount"] = max_amount_match.group(0)
    if min_amount_match:
        evidence["min_amount"] = min_amount_match.group(0)

    reward_amount = None
    if reward_match:
        normalized_reward = normalize_money(reward_match.group(1))
        reward_amount = normalized_reward.to_dict() if normalized_reward else None
    max_amount = None
    if max_amount_match:
        normalized_max = normalize_money(max_amount_match.group(1))
        max_amount = normalized_max.to_dict() if normalized_max else None
    min_amount = None
    if min_amount_match:
        normalized_min = normalize_money(min_amount_match.group(1))
        min_amount = normalized_min.to_dict() if normalized_min else None

    target_audience = None
    new_customer_words = (
        "yeni müşteri",
        "yeni musteri",
        "ilk kez müşteri",
        "ilk kez musteri",
    )
    if any(word in normalized for word in new_customer_words):
        target_audience = "new_customer"
        match = re.search(
            r"yeni müşteri(?:lere)?|yeni musteri(?:lere)?|"
            r"ilk kez müşteri(?:lere)?|ilk kez musteri(?:lere)?",
            source,
            re.IGNORECASE,
        )
        if match:
            evidence["target_audience"] = match.group(0)

    product_type = _product_type(normalized)
    if product_type:
        product_evidence_patterns = {
            "financing": r"[^\s.]+\s+finansman[ıi]",
            "card": r"kart|bonus",
            "investment": (
                r"yatırım|yatirim|katılma hesabı|katilma hesabı|altın|altin"
            ),
            "shopping_points": (
                r"alışveriş puanı|alisveris puanı|alisveris puan|worldpuan|parafpara"
            ),
            "new_customer": r"yeni müşteri|yeni musteri|ilk kez müşteri|ilk kez musteri",
        }
        match = re.search(
            product_evidence_patterns[product_type], source, re.IGNORECASE
        )
        if match:
            evidence["product_type"] = match.group(0)
    financing_type = _financing_type(normalized)
    if financing_type:
        match = re.search(
            r"konut|taşıt|tasit|araç|arac|ihtiyaç|ihtiyac", source, re.IGNORECASE
        )
        if match:
            evidence["financing_type"] = match.group(0)

    fee_information = None
    if "masrafsız" in normalized or "masrafsiz" in normalized:
        fee_information = "masrafsız"
        evidence["fee_information"] = "masrafsız"

    return {
        "product_type": product_type,
        "financing_type": financing_type,
        "profit_share_rate": profit_share_rate,
        "term_months": int(term_match.group(1)) if term_match else None,
        "duration": duration.to_dict() if duration else None,
        "installment_count": (
            int(installment_match.group(1)) if installment_match else None
        ),
        "campaign_benefit": _benefit(source),
        "reward_amount": reward_amount,
        "min_amount": min_amount,
        "max_amount": max_amount,
        "discount_rate": _percentage(discount_value) if discount_value else None,
        "target_audience": target_audience,
        "campaign_start_date": start_date,
        "campaign_end_date": end_date,
        "fee_information": fee_information,
        "evidence": evidence,
        "extraction_method": "rules-v1",
    }
