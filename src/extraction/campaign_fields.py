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
REWARD_WORDS = (
    r"ödül|odul|iade|puan|bonus|bankkart\s+lira|parafpara|"
    r"worldpuan|altın\s+puan|altin\s+puan|hediye\s+bakiye|hediye"
)
MONEY_REWARD_PATTERN = re.compile(
    rf"({MONEY_PATTERN.pattern})(?=[^.!?]{{0,60}}(?:{REWARD_WORDS}))",
    re.IGNORECASE,
)
MAX_AMOUNT_PATTERN = re.compile(
    rf"({MONEY_PATTERN.pattern})(?:['’]?ye|\s+tutar[aı])?\s+kadar", re.IGNORECASE
)
MIN_AMOUNT_PATTERN = re.compile(
    rf"en\s+az\s+({MONEY_PATTERN.pattern})(?:\s+ile)?", re.IGNORECASE
)
APPLICATION_CHANNEL_PATTERN = re.compile(
    r"\b(mobil uygulama|mobil bankacılık|mobil bankacilik|mobilden|"
    r"internet şubesi|internet subesi|internet şube|internet sube|"
    r"görüntülü görüşme|goruntulu gorusme|şube|sube|çağrı merkezi|cagri merkezi)\b",
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
    # İki doğrulanmış yatırım kaydı genel "mobil/müşteri" şablonunu taşıyor;
    # ürün türünü yalnızca yatırım bağlamını birlikte veren özgün ifadelerde
    # yükselt. Böylece genel "döviz" veya "hesap" kelimeleri tek başına
    # yanlış yatırım etiketine dönüşmez.
    if (
        "kur fırsat" in text
        and "müşterimiz olun" in text
    ) or (
        "günlük hesap" in text
        and "vadeni boz" in text
    ):
        return "investment"
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
    sentences = [s.strip() for s in re.split(r"[\n.!?;]+|\s{2,}", source) if s.strip()]
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
            (
                "yeni müşteri", "yeni musteri", "ilk kez müşteri", "ilk kez musteri",
                "müşteri olan", "musteri olan", "müşteri olun", "musteri olun",
                "türkiye finanslı", "turkiye finansli", "kuveyt türklü", "kuveyt turklu",
                "albarakalı", "albarakali", "hayat finanslı", "hayat finansli",
                "vakıf katılımlı", "vakif katilimli", "ziraat katılımlı", "ziraat katilimli",
                "hadi'li", "hadili", "kart sahibi olun", "hoş geldin", "hos geldin", "onboarding",
            ),
            (
                r"yeni\s+müşteri(?:ler[ea]?|miz)?|yeni\s+musteri(?:ler[ea]?|miz)?|"
                r"ilk\s+kez\s+müşteri(?:ler[ea]?|miz)?|ilk\s+kez\s+musteri(?:ler[ea]?|miz)?|"
                r"müşteri\s+olan(?:lar)?|musteri\s+olan(?:lar)?|"
                r"müşteri\s+olun|musteri\s+olun|"
                r"mobilden\s+[^.!?\n]{1,30}?\s*müşteri\s+ol\w*|"
                r"mobilden\s+[^.!?\n]{1,30}?\s*musteri\s+ol\w*|"
                r"(?:türkiye\s+finanslı|turkiye\s+finansli|kuveyt\s+türklü|kuveyt\s+turklu|"
                r"albarakalı|albarakali|hayat\s+finanslı|hayat\s+finansli|"
                r"vakıf\s+katılımlı|vakif\s+katilimli|ziraat\s+katılımlı|ziraat\s+katilimli|"
                r"hadi'li|hadili)\s+ol\w*|"
                r"kart\s+sahibi\s+olun|hoş\s+geldin|hos\s+geldin|onboarding"
            ),
        ),
        (
            "retiree",
            ("emekli", "emeklilere", "emekliler", "emekli maaş", "emekli maas"),
            r"emekli(?:ler[ea]?|miz|ye)?|emekli\s+maaş\w*|emekli\s+maas\w*",
        ),
        (
            "public_sector",
            (
                "kamu çalışan", "kamu calisan", "kamu personel",
                "sağlık meslek", "saglik meslek", "doktor", "öğretmen", "ogretmen",
            ),
            (
                r"kamu\s+(?:çalışan|calisan|personel)\w*|"
                r"sağlık\s+meslek|saglik\s+meslek|\bdoktor\w*|\böğretmen\w*|\bogretmen\w*"
            ),
        ),
        (
            "commercial",
            (
                "esnaf", "kobi", "ticari", "tüzel", "tuzel",
                "çiftçi", "ciftci", "tarım", "tarim", "işletme", "isletme", "pilot",
            ),
            (
                r"\b(?:esnaf|kobi|ticari|tüzel|tuzel|çiftçi|ciftci|"
                r"tarım|tarim|işletme|isletme|pilot\w*)\b"
            ),
        ),
        (
            "student",
            (
                "öğrenci", "ogrenci", "genç", "genc",
                "gençler", "gencler", "üniversite", "universite", "kampüs", "kampus",
            ),
            (
                r"\b(?:öğrenci\w*|ogrenci\w*|genç\w*|genc\w*|"
                r"üniversite\w*|universite\w*|kampüs\w*|kampus\w*)\b"
            ),
        ),
        (
            "existing_customer",
            (
                "bankkart", "paraf", "world", "sağlam kart", "saglam kart", "hadi",
                "vkart", "biz kart", "dkart", "troy", "kartınız", "kartiniz",
                "kart sahip", "debit kart", "sanal kart",
                "bireysel müşteri", "bireysel musteri",
                "mevcut müşteri", "mevcut musteri",
                "bankamız müşteri", "bankamiz musteri",
                "müşterilerimize özel", "musterilerimize ozel",
                "müşterilerine özel", "musterilerine ozel",
                "müşterimize özel", "musterimize ozel",
                "müşteri bazlı", "musteri bazli",
                "işlem yapan müşteri", "islem yapan musteri",
                "katılma hesabı", "katilma hesabi", "mevduat",
                "vadesiz hesap", "avantajlı hesap", "avantajli hesap",
            ),
            (
                r"(?:bankkart|paraf|world|sağlam\s+kart|saglam\s+kart|hadi|vkart|"
                r"biz\s+kart|dkart|troy)\s+(?:kredi\s+)?kart\w*|"
                r"kartınız(?:la)?|kartiniz(?:la)?|kart\s+sahip\w*|debit\s+kart\w*|"
                r"sanal\s+kart\w*|"
                r"(?:bireysel|tüm\s+bireysel|mevcut|bankamız|bankamiz)\s+müşteri\w*|"
                r"(?:bireysel|tüm\s+bireysel|mevcut|bankamız|bankamiz)\s+musteri\w*|"
                r"müşteri(?:lerimize|lerine|mize)\s+özel|"
                r"musteri(?:lerimize|lerine|mize)\s+ozel|"
                r"müşteri\s+bazlı|musteri\s+bazli|"
                r"işlem\s+yapan\s+müşteri\w*|islem\s+yapan\s+musteri\w*|"
                r"(?:hayat\s+finanslı|kuveyt\s+türklü|albarakalı|türkiye\s+finanslı|"
                r"ziraat\s+katılımlı|vakıf\s+katılımlı|hadi'li)\w*\s+özel|"
                r"(?:avantajlı|katılma|mevduat|vadesiz)\s+hesap\s+(?:açan\s+)?"
                r"(?:bireysel\s+)?müşteri\w*"
            ),
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
                r"yatırım|yatirim|katılma hesabı|katilma hesabı|altın|altin|"
                r"kur\s+fırsat\w*|günlük\s+hesap\w*|vadeni\s+boz\w*"
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
