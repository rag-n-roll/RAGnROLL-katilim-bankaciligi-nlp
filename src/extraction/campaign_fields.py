"""PRD alanları için yerel ve deterministik kural tabanlı çıkarım."""

from __future__ import annotations

import re
from typing import Any

from src.extraction.contracts import build_field_contracts
from src.normalization import normalize_duration, normalize_money, normalize_rate

NUMBER = r"\d[\d.,]*"
PROFIT_PATTERNS = (
    re.compile(rf"%\s*({NUMBER})\s*k[aâ]r\s+pay[ıi](?:\s+oran[ıi])?", re.IGNORECASE),
    re.compile(rf"k[aâ]r\s+pay[ıi](?:\s+oran[ıi])?\s*%\s*({NUMBER})", re.IGNORECASE),
    re.compile(rf"({NUMBER})\s*%\s*k[aâ]r\s+pay[ıi](?:\s+oran[ıi])?", re.IGNORECASE),
    re.compile(
        rf"%\s*({NUMBER})\s*(?:k[aâ]r\s+pay[ıi]\s+)?oran(?:[ıi]|ından|li|lı)?",
        re.IGNORECASE,
    ),
    re.compile(rf"oran(?:ı|i)?\s*%\s*({NUMBER})", re.IGNORECASE),
    re.compile(rf"%\s*({NUMBER})\s+oran", re.IGNORECASE),
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
    r"(?<!\d)(\d{1,3})\s*(?:aya\s+varan\s+|ay\s+)?taksit", re.IGNORECASE
)
MONEY_PATTERN = re.compile(
    rf"(?:[₺$€£]\s*{NUMBER}|{NUMBER}(?:\s+milyon)?\s*(?:TL|₺|TRY|USD|\$|EUR|€|GBP|£))",
    re.IGNORECASE,
)
MONEY_REWARD_PATTERN = re.compile(
    rf"({MONEY_PATTERN.pattern})(?=[^.!?]{{0,60}}(?:ödül|odul|iade|puan|bonus|bankkart\s+lira|parafpara|worldpuan|altın\s+puan|altin\s+puan|hediye\s+bakiye|hediye))",
    re.IGNORECASE,
)
MAX_AMOUNT_PATTERN = re.compile(
    rf"({MONEY_PATTERN.pattern})(?:['’]?ye|\s+tutar[aı])?\s+kadar", re.IGNORECASE
)
MIN_AMOUNT_PATTERN = re.compile(
    rf"en\s+az\s+({MONEY_PATTERN.pattern})(?:\s+ile)?", re.IGNORECASE
)
APPLICATION_CHANNEL_PATTERN = re.compile(
    r"\b(mobil uygulama|mobil bankacılık|mobil bankacilik|mobilden|internet şubesi|internet subesi|"
    r"internet şube|internet sube|görüntülü görüşme|goruntulu gorusme|şube|sube|çağrı merkezi|cagri merkezi)\b",
    re.IGNORECASE,
)
CONDITION_PATTERN = re.compile(
    r"((?:en\s+az\s+[^!?]{1,80}?|[^.!?]{1,80}?))\s+"
    r"(?:şart(?:ı|ını)?|koşul(?:u|uyla)?)",
    re.IGNORECASE,
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


def _all_profit_matches(text: str) -> list[re.Match[str]]:
    matches = [match for pattern in PROFIT_PATTERNS for match in pattern.finditer(text)]
    return sorted(matches, key=lambda match: (match.start(), match.end()))


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
            "ücretsiz",
            "ucretsiz",
            "muafiyet",
            "hediye",
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

    profit_matches = _all_profit_matches(source)
    profit_match = profit_matches[0] if profit_matches else None
    profit_share_rate = None
    conflicts: dict[str, list[Any]] = {}
    if profit_match:
        profit_share_rate = _percentage(profit_match.group(1))
        evidence["profit_share_rate"] = profit_match.group(0)
        distinct_rates = sorted(
            {_percentage(match.group(1)) for match in profit_matches}
        )
        if len(distinct_rates) > 1:
            conflicts["profit_share_rate"] = distinct_rates
            profit_share_rate = None

    term_match = TERM_PATTERN.search(source)
    duration_match = term_match or DURATION_PATTERN.search(source)
    installment_match = INSTALLMENT_PATTERN.search(source)
    discount_match = DISCOUNT_PATTERN.search(source)
    reward_matches = list(MONEY_REWARD_PATTERN.finditer(source))
    # Aynı cümlede finansman tutarı da varsa ödül ifadesine en yakın tutarı seç.
    reward_match = reward_matches[-1] if reward_matches else None
    max_amount_match = MAX_AMOUNT_PATTERN.search(source)
    min_amount_match = MIN_AMOUNT_PATTERN.search(source)
    application_channel_match = APPLICATION_CHANNEL_PATTERN.search(source)
    condition_match = CONDITION_PATTERN.search(source)
    condition = (
        condition_match.group(1).strip(" ,;:-") if condition_match else None
    )
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
        evidence["financing_amount"] = max_amount_match.group(0)
    if min_amount_match:
        evidence["min_amount"] = min_amount_match.group(0)
    if application_channel_match:
        evidence["application_channel"] = application_channel_match.group(0)
    if condition_match:
        evidence["condition"] = condition

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
    sentences = [s.strip() for s in re.split(r"(?<=[.!?\n])\s+", source) if s.strip()]
    exclusion_markers = (
        "dahil değil",
        "dahil degil",
        "geçerli değil",
        "gecerli degil",
        "hariç",
        "haric",
        "kapsam dışı",
        "kapsam disi",
    )
    target_defs = [
        (
            "new_customer",
            ("yeni müşteri", "yeni musteri", "ilk kez müşteri", "ilk kez musteri"),
            r"yeni müşteri(?:lere|miz)?|yeni musteri(?:lere|miz)?|ilk kez müşteri(?:lere)?|ilk kez musteri(?:lere)?",
        ),
        (
            "retiree",
            ("emekli", "emeklilere", "emekliler"),
            r"emekli(?:lere|ler|miz|ye)?",
        ),
        (
            "public_sector",
            ("kamu çalışanı", "kamu calisani", "kamu personeli"),
            r"kamu\s+(?:çalışan|calisan|personel)\w*",
        ),
        (
            "commercial",
            ("esnaf", "kobi", "ticari"),
            r"\b(?:esnaf|kobi|ticari)\b",
        ),
        (
            "student",
            ("öğrenci", "ogrenci", "genç", "genc", "üniversite"),
            r"\b(?:öğrenci|ogrenci|genç|genc|üniversite)\b",
        ),
    ]
    for sentence in sentences:
        norm_s = _normalized(sentence)
        if any(m in norm_s for m in exclusion_markers):
            continue
        for label, keywords, pattern in target_defs:
            if any(k in norm_s for k in keywords):
                match = re.search(pattern, sentence, re.IGNORECASE)
                if match:
                    target_audience = label
                    evidence["target_audience"] = match.group(0)
                    break
        if target_audience:
            break
    product_type = _product_type(normalized)
    if product_type:
        product_evidence_patterns = {
            "financing": r"(?:[^\s.]+\s+)?finansman(?:[ıi])?\b",
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
    campaign_benefit = _benefit(source)
    if campaign_benefit:
        evidence["campaign_benefit"] = campaign_benefit

    values = {
        "product_type": product_type,
        "financing_type": financing_type,
        "profit_share_rate": profit_share_rate,
        "financing_amount": max_amount,
        "term_months": int(term_match.group(1)) if term_match else None,
        "duration": duration.to_dict() if duration else None,
        "installment_count": (
            int(installment_match.group(1)) if installment_match else None
        ),
        "campaign_benefit": campaign_benefit,
        "reward_amount": reward_amount,
        "min_amount": min_amount,
        "max_amount": max_amount,
        "discount_rate": _percentage(discount_value) if discount_value else None,
        "target_audience": target_audience,
        "campaign_start_date": start_date,
        "campaign_end_date": end_date,
        "fee_information": fee_information,
        "application_channel": (
            application_channel_match.group(0) if application_channel_match else None
        ),
        "condition": condition,
        "evidence": evidence,
        "extraction_method": "rules-v1",
    }
    values["fields"] = build_field_contracts(
        source,
        values,
        evidence,
        method="rules-v1",
        conflicts=conflicts,
    )
    return values
