"""PRD alanları için yerel ve deterministik kural tabanlı çıkarım."""

from __future__ import annotations

import re
from typing import Any


NUMBER = r"\d+(?:[.,]\d+)?"
PROFIT_PATTERNS = (
    re.compile(rf"%\s*({NUMBER})\s*k[aâ]r\s+pay[ıi](?:\s+oran[ıi])?", re.IGNORECASE),
    re.compile(rf"k[aâ]r\s+pay[ıi](?:\s+oran[ıi])?\s*%\s*({NUMBER})", re.IGNORECASE),
)
DISCOUNT_PATTERN = re.compile(rf"%\s*({NUMBER})\s*(?:indirim|iade)", re.IGNORECASE)
TERM_PATTERN = re.compile(r"(?<!\d)(\d{1,3})\s*ay\s*(?:vade|vadeli)", re.IGNORECASE)
INSTALLMENT_PATTERN = re.compile(r"(?<!\d)(\d{1,3})\s*(?:aya\s+varan\s+)?taksit", re.IGNORECASE)
MONEY_REWARD_PATTERN = re.compile(
    rf"({NUMBER})\s*(TL|₺|USD|\$|EUR|€)(?=[^.!?]{{0,45}}(?:ödül|odul|iade|puan|bonus))",
    re.IGNORECASE,
)
CURRENCY_CODES = {"tl": "TRY", "₺": "TRY", "usd": "USD", "$": "USD", "eur": "EUR", "€": "EUR"}


def _normalized(value: str) -> str:
    return value.casefold().replace("i̇", "i")


def _number(value: str) -> float:
    return float(value.replace(".", "").replace(",", "."))


def _percentage(value: str) -> float:
    return round(_number(value) / 100, 6)


def _product_type(text: str) -> str | None:
    if "finansman" in text:
        return "financing"
    if any(word in text for word in ("kart", "bonus")):
        return "card"
    if any(word in text for word in ("yatırım", "yatirim", "katılma hesab", "katilma hesab", "altın", "altin")):
        return "investment"
    if any(word in text for word in ("alışveriş puan", "alisveris puan", "worldpuan", "parafpara")):
        return "shopping_points"
    if any(word in text for word in ("yeni müşteri", "yeni musteri", "ilk kez müşteri", "ilk kez musteri")):
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


def _first_match(patterns: tuple[re.Pattern[str], ...], text: str) -> re.Match[str] | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match
    return None


def _benefit(text: str) -> str | None:
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        normalized = _normalized(sentence)
        if any(word in normalized for word in ("avantaj", "indirim", "ödül", "odul", "iade", "masrafsız", "masrafsiz")):
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
    installment_match = INSTALLMENT_PATTERN.search(source)
    discount_match = DISCOUNT_PATTERN.search(source)
    reward_match = MONEY_REWARD_PATTERN.search(source)
    if term_match:
        evidence["term_months"] = term_match.group(0)
    if installment_match:
        evidence["installment_count"] = installment_match.group(0)
    if discount_match:
        evidence["discount_rate"] = discount_match.group(0)
    if reward_match:
        evidence["reward_amount"] = reward_match.group(0)

    reward_amount = None
    if reward_match:
        reward_amount = {
            "amount": _number(reward_match.group(1)),
            "currency": CURRENCY_CODES[reward_match.group(2).casefold()],
        }

    target_audience = None
    if any(word in normalized for word in ("yeni müşteri", "yeni musteri", "ilk kez müşteri", "ilk kez musteri")):
        target_audience = "new_customer"

    fee_information = None
    if "masrafsız" in normalized or "masrafsiz" in normalized:
        fee_information = "masrafsız"
        evidence["fee_information"] = "masrafsız"

    return {
        "product_type": _product_type(normalized),
        "financing_type": _financing_type(normalized),
        "profit_share_rate": profit_share_rate,
        "term_months": int(term_match.group(1)) if term_match else None,
        "installment_count": int(installment_match.group(1)) if installment_match else None,
        "campaign_benefit": _benefit(source),
        "reward_amount": reward_amount,
        "discount_rate": _percentage(discount_match.group(1)) if discount_match else None,
        "target_audience": target_audience,
        "campaign_start_date": start_date,
        "campaign_end_date": end_date,
        "fee_information": fee_information,
        "evidence": evidence,
        "extraction_method": "rules-v1",
    }
