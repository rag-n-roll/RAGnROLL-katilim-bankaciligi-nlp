"""Create an ontology-aligned, multi-dimensional human-review queue."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from src.annotation.taxonomy import (
    BENEFITS,
    CAMPAIGN_MECHANICS,
    CHANNELS,
    REQUIREMENTS,
    TARGET_SEGMENTS,
)


PRODUCT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "takaful",
        (r"\btekafül\b", r"katılım\s+sigortacılı", r"katılımcı\s+risk\s+fonu"),
    ),
    (
        "insurance",
        (
            r"\bdask\b",
            r"\bkasko\b",
            r"zorunlu\s+trafik\s+sigorta",
            r"sağlık\s+sigorta",
            r"hayat\s+sigorta",
            r"konut\s+sigorta",
            r"seyahat\s+sağlık\s+sigorta",
            r"sigorta\s+işlemleri",
            r"sigorta\s+alımı",
            r"sigortanızı\s+(?:kolayca\s+)?yaptır",
        ),
    ),
    ("housing_finance", (r"\bkonut\b", r"gayrimenkul", r"\bev\s+finansman")),
    ("vehicle_finance", (r"\btaşıt\b", r"\baraç\b", r"otomobil", r"motosiklet")),
    ("education_finance", (r"eğitim\s+finansman", r"okul\s+finansman")),
    ("land_finance", (r"arsa\s+finansman",)),
    ("workplace_finance", (r"iş\s*yeri\s+finansman",)),
    ("urban_transformation_finance", (r"kentsel\s+dönüşüm",)),
    ("shopping_finance", (r"alışveriş\s+finansman",)),
    ("consumer_finance", (r"\bihtiyaç\s+finansman",)),
    ("agriculture_finance", (r"tarım", r"çiftçi", r"gübre", r"tohum", r"hayvancılık")),
    (
        "sustainable_finance",
        (r"sürdürülebilir", r"yeşil\s+finansman", r"\bges\b", r"enerji\s+verim"),
    ),
    (
        "commercial_finance",
        (r"\bkobi\b", r"ticari\s+finansman", r"işletme\s+finansman", r"tahsile\s+çek"),
    ),
    (
        "participation_account",
        (r"katılma\s+hesab", r"katılım\s+fonu", r"günlük\s+(?:kazandıran\s+)?hesap"),
    ),
    (
        "investment_product",
        (
            r"yatırım",
            r"kira\s+sertifika",
            r"altın\s+hesab",
            r"\bfon\b",
            r"döviz\s+işlem",
            r"kur\s+fırsat",
        ),
    ),
    ("digital_finance", (r"dijital\s+finansman", r"taksitlio", r"cebimpos")),
    (
        "card",
        (
            r"\bkart",
            r"worldpuan",
            r"sağlam\s+puan",
            r"taksit",
            r"hediye\s+bakiye",
            r"fatura\s+talimat",
            r"kahve\s+keyfi",
            r"seçkin\s+fırsat",
            r"premium\s+üyelik",
            r"hızlı\s+çiçek",
        ),
    ),
    ("other_finance", (r"finansman",)),
)

MULTI_RULES: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
    "campaign_mechanics": (
        ("cashback", (r"nakit\s+iade", r"cashback", r"para\s+iade", r"%\s*[\d,.]+\s*iade")),
        ("reward_points", (r"puan", r"worldpuan", r"bonus", r"hediye\s+bakiye")),
        ("discount", (r"indirim",)),
        ("installment", (r"taksit",)),
        ("referral", (r"davet\s+et", r"arkadaşını\s+getir")),
        ("loyalty_membership", (r"üyelik", r"gold", r"sadakat")),
        ("promo_code", (r"promosyon\s+kodu", r"kupon\s+kodu", r"kampanya\s+kodu")),
        ("gift_voucher", (r"hediye\s+çek", r"alışveriş\s+çek")),
        (
            "bonus_service",
            (
                r"\d+\s*(?:ay|gün|hafta|ders|gb)\s+hediye",
                r"hediye\s+(?:ders|internet|hizmet|bakım|kullanım)",
                r"ek\s+ücretsiz\s+(?:ders|hizmet|bakım|kullanım)",
            ),
        ),
        ("draw_lottery", (r"çekiliş",)),
    ),
    "target_segments": (
        ("new_customer", (r"yeni\s+müşteri", r"ilk\s+kez\s+müşteri", r"hoş\s+geldin")),
        ("existing_customer", (r"mevcut\s+müşteri",)),
        ("salary_customer", (r"maaş\s+müşteri",)),
        ("youth_student", (r"öğrenci", r"genç", r"kampüs")),
        ("commercial_sme", (r"\bkobi\b", r"ticari\s+müşteri", r"işletme")),
        ("farmer", (r"çiftçi", r"tarım", r"üretici")),
        ("cardholder", (r"kart\s+sahib", r"kartınızla", r"kartları\s+ile")),
        ("digital_customer", (r"dijital\s+müşteri",)),
    ),
    "channels": (
        ("mobile", (r"mobil\s+uygulama", r"mobilden", r"mobil\s+şube")),
        ("internet_branch", (r"internet\s+şube",)),
        ("physical_branch", (r"\bşube",)),
        ("card_pos", (r"\bpos\b", r"kartınızla")),
        ("ecommerce", (r"web\s+sites", r"e-ticaret", r"online\s+alışveriş")),
        ("atm", (r"\batm\b",)),
        ("call_center", (r"çağrı\s+merkezi", r"müşteri\s+iletişim\s+merkezi")),
    ),
    "benefits": (
        (
            "reward_points",
            (
                r"worldpuan",
                r"sağlam\s+puan",
                r"bankkart\s+lira",
                r"\bbonus\b",
                r"\bpuan\s+kazan",
                r"ödül\s+puan",
            ),
        ),
        (
            "cashback",
            (r"nakit\s+iade", r"(?:%\s*)?[\d,.]+\s*(?:oranında\s+)?iade"),
        ),
        ("discount", (r"\bindirim\b", r"indirimli")),
        (
            "percentage_discount",
            (
                r"%\s*\d+(?:[.,]\d+)?\s*(?:'?[a-zçğıöşü]+\s+)?indirim",
                r"yüzde\s+\d+(?:[.,]\d+)?\s+indirim",
            ),
        ),
        ("installment", (r"\btaksit\b", r"taksitlendirme")),
        (
            "no_extra_cost_installment",
            (r"vade\s+farksız", r"peşin\s+fiyatına\s+\d+\s*taksit"),
        ),
        ("additional_installment", (r"(?:ek|ilave)\s+(?:\d+\s+)?taksit",)),
        ("zero_profit_rate", (r"%\s*0", r"sıfır\s+kâr\s+pay")),
        ("special_profit_rate", (r"avantajlı\s+(?:kâr\s+payı|oran)", r"özel\s+oran")),
        (
            "fee_exemption",
            (r"masraf\w*\s+(?:yok|alınm)", r"ücret\s+muaf", r"tahsis\s+ücreti\s+yok"),
        ),
        ("free_insurance", (r"ücretsiz\s+sigorta",)),
        ("payment_deferral", (r"taksit\s+ertele", r"ödem\w+\s+ertele")),
        ("gift_voucher", (r"hediye\s+çek", r"alışveriş\s+çek")),
        ("free_service", (r"ücretsiz",)),
    ),
    "requirements": (
        ("minimum_spend", (r"en\s+az\s+[\d.]", r"minimum\s+harcama")),
        (
            "maximum_spend",
            (
                r"en\s+fazla\s+[\d.]",
                r"maksimum\s+harcama",
                r"[\d.]+\s*(?:tl|₺)\s*(?:veya\s+)?alt(?:ı|i)",
                r"[\d.]+\s*(?:tl|₺)\s*(?:üzerinde|üstünde)\s+(?:olan\s+)?"
                r"(?:işlem|harcama)\w*\s+geçerli\s+değil",
            ),
        ),
        (
            "minimum_balance",
            (
                r"minimum\s+[\d.]+\s*(?:tl|₺).{0,40}(?:bakiye|bulundur)",
                r"hesap(?:ta|\s+bakiyesi).{0,40}en\s+az\s+[\d.]+\s*(?:tl|₺)",
            ),
        ),
        (
            "application_required",
            (r"kampanyaya\s+katıl", r"kampanya\s+katılım", r"başvuru"),
        ),
        ("promo_code_required", (r"(?:promosyon|kupon)\s+kodu",)),
        ("automatic_payment_instruction", (r"otomatik\s+ödeme\s+talimat",)),
        ("first_transaction", (r"ilk\s+işlem", r"ilk\s+alışveriş")),
        ("limited_stock", (r"stoklarla\s+sınırlı",)),
        (
            "date_limited",
            (
                r"\d{1,2}\s+(?:ocak|şubat|mart|nisan|mayıs|haziran|temmuz|"
                r"ağustos|eylül|ekim|kasım|aralık)\s+20\d{2}",
            ),
        ),
        ("specific_merchant", (r"üye\s+işyer", r"mağazalarında", r"resmi\s+web\s+sitesinde")),
        ("specific_card", (r"belirli\s+kart", r"kartları\s+ile", r"kartınızla")),
    ),
}

ALLOWED = {
    "campaign_mechanics": set(CAMPAIGN_MECHANICS),
    "target_segments": set(TARGET_SEGMENTS),
    "channels": set(CHANNELS),
    "benefits": set(BENEFITS),
    "requirements": set(REQUIREMENTS),
}


def suggest_annotations(text: str) -> tuple[dict[str, Any], dict[str, list[str]]]:
    normalized = str(text or "").casefold()
    evidence: dict[str, list[str]] = {}
    product_category = "needs_review"
    for label, patterns in PRODUCT_RULES:
        matches = [pattern for pattern in patterns if re.search(pattern, normalized)]
        if matches:
            product_category = label
            evidence["product_category"] = matches
            break
    annotations: dict[str, Any] = {"product_category": product_category}
    for field, rules in MULTI_RULES.items():
        values = []
        field_evidence = []
        for label, patterns in rules:
            matches = [pattern for pattern in patterns if re.search(pattern, normalized)]
            if matches and label in ALLOWED[field]:
                values.append(label)
                field_evidence.extend(matches)
        annotations[field] = values
        if field_evidence:
            evidence[field] = field_evidence
    if not annotations["channels"]:
        annotations["channels"] = ["unspecified"]
    return annotations, evidence


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
            part for part in text_sources if isinstance(part, str) and part.strip()
        )
        annotations, evidence = suggest_annotations(text)
        prepared.append(
            {
                "id": campaign.get("id", f"campaign-{index:04d}"),
                "text": text,
                "annotations": annotations,
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
        "product_distribution": dict(
            Counter(record["annotations"]["product_category"] for record in prepared)
        ),
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
