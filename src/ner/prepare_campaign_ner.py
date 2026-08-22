"""Create high-precision NER labels from scraped participation-bank campaigns."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


LABELS = (
    "BANKA", "URUN_TURU", "KAR_PAYI_ORANI", "FINANSMAN_TUTARI", "VADE",
    "TAKSIT_SAYISI", "ODUL_MIKTARI", "ALISVERIS_PUANI", "INDIRIM_ORANI",
    "HEDEF_KITLE", "KAMPANYA_TARIHI", "KAMPANYA_KOSULU", "TAHSIS_UCRETI",
    "MASRAF_BILGISI", "KAMPANYA_AVANTAJI", "PROMOSYON_KODU",
)

MONTH = r"(?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)"
MONEY = r"(?:\d[\d.]*?(?:,\d+)?\s*(?:TL|₺|Türk Lirası))"
PATTERNS: tuple[tuple[str, re.Pattern[str], float], ...] = (
    ("KAR_PAYI_ORANI", re.compile(r"(?:%\s*\d+(?:[,.]\d+)?\s*k[âa]r\s+payı(?:\s+oranı)?|k[âa]r\s+payı(?:\s+oranı)?\s*%\s*\d+(?:[,.]\d+)?)", re.I), 0.99),  # noqa: E501
    ("INDIRIM_ORANI", re.compile(r"(?:%\s*\d+(?:[,.]\d+)?|yüzde\s+\d+(?:[,.]\d+)?)\s*(?:'?[a-zçğıöşü]+\s+)?indirim", re.I), 0.98),  # noqa: E501
    ("VADE", re.compile(r"(?<!\d)\d{1,3}\s*(?:ay|yıl)(?:a|e)?\s*(?:kadar|varan|vade(?:li|yle)?)?", re.I), 0.94),  # noqa: E501
    ("TAKSIT_SAYISI", re.compile(r"(?<!\d)\d{1,3}\s*(?:aya\s+varan\s+)?taksit", re.I), 0.98),
    ("ALISVERIS_PUANI", re.compile(rf"(?:{MONEY}\s*(?:değerinde\s+)?(?:Worldpuan|Sağlam\s*Puan|puan)|\d[\d.]*\s*(?:Worldpuan|Sağlam\s*Puan))", re.I), 0.98),  # noqa: E501
    ("KAMPANYA_TARIHI", re.compile(rf"(?:\d{{1,2}}\s*[-–]\s*\d{{1,2}}\s+{MONTH}\s+20\d{{2}}|\d{{1,2}}\s+{MONTH}\s+20\d{{2}}(?:\s*(?:[-–]|ile)\s*\d{{1,2}}\s+{MONTH}\s+20\d{{2}})?)", re.I), 0.98),  # noqa: E501
    ("HEDEF_KITLE", re.compile(r"(?:yeni|mevcut|bireysel|ticari|maaş|emekli|genç|öğrenci)\s+müşteri(?:lerimiz|ler|miz|si)?|kart\s+sahipleri", re.I), 0.93),  # noqa: E501
    ("TAHSIS_UCRETI", re.compile(r"(?:tahsis\s+ücreti(?:\s+(?:alınmamaktadır|yoktur|muafiyeti))?)", re.I), 0.98),  # noqa: E501
    ("MASRAF_BILGISI", re.compile(r"(?:(?:dosya|ekspertiz|swift)\s+(?:masrafı|ücreti)(?:[^.!?\n]{0,60})?|masrafsız\s+(?:finansman|bankacılık|hesap|para\s+transferi|döviz\s+havalesi|banka\s+ve\s+kredi\s+kartı)|(?:masraf|ücret)\s+alınma(?:z|maktadır))", re.I), 0.95),  # noqa: E501
    ("KAMPANYA_AVANTAJI", re.compile(r"(?:vade\s+farksız|ücretsiz\s+(?:hizmet|sigorta|ekspertiz)|k[âa]r\s+payı\s+avantajı|ödeme\s+erteleme)", re.I), 0.93),  # noqa: E501
    ("URUN_TURU", re.compile(r"(?:konut|taşıt|araç|ihtiyaç|alışveriş|eğitim|arsa|iş\s*yeri|tarım|ticari|KOBİ|dijital|yeşil)\s+finansmanı|katılma\s+hesabı|kira\s+sertifikası|(?:kredi|banka)\s+kartı|BES|Erken\s+BES", re.I), 0.96),  # noqa: E501
)

CONDITION_PATTERNS = (
    re.compile(rf"(?:en\s+az|min(?:imum)?\.?\s*){MONEY}(?:[^.!?]{{0,80}}(?:harcama|alışveriş|işlem))?", re.I),  # noqa: E501
    re.compile(r"kampanyaya\s+katılmak\s+için", re.I),
    re.compile(r"(?:kampanya|promosyon|kupon)\s+kodu", re.I),
    re.compile(r"otomatik\s+ödeme\s+talimatı", re.I),
)
PRODUCT_CONTEXT = re.compile(r"finansman|limit|tutar", re.I)
REWARD_CONTEXT = re.compile(r"ödül|hediye|iade|çek|kazan", re.I)

UPPER_CODE_TOKEN = (
    r"(?=[A-ZÇĞİÖŞÜ0-9_-]{2,25}\b)"
    r"(?=[A-ZÇĞİÖŞÜ0-9_-]*[A-ZÇĞİÖŞÜ])[A-ZÇĞİÖŞÜ0-9_-]+"
)
UPPER_CODE = rf"{UPPER_CODE_TOKEN}(?:\s+{UPPER_CODE_TOKEN})?"
PROMO_CODE_PATTERNS = (
    re.compile(
        rf"(?P<code>{UPPER_CODE})\s+"
        r"(?:(?i:(?:indirim|kampanya|promosyon|referans)\s+))?"
        r"(?i:kodu(?:yla|nu|nun|nı|na|dur)?)\b"
    ),
    re.compile(rf"(?P<code>{UPPER_CODE})\s*['\"”’]?\s+(?i:yazıp)\b"),
    re.compile(
        rf"(?i:(?:indirim|kampanya|promosyon|referans)\s+kodu)\s*[:=-]\s*"
        rf"(?P<code>{UPPER_CODE})"
    ),
)
PROMO_CODE_STOPWORDS = {"MCC", "QR", "TL", "SIFRE", "İSPARK"}


def split_for(source_id: str) -> str:
    value = int(hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:8], 16) % 10
    return "test" if value < 2 else "train"


def _add(
    spans: list[dict[str, Any]], occupied: set[int], text: str,
    match: re.Match[str], label: str, confidence: float,
) -> bool:
    return _add_range(spans, occupied, text, *match.span(), label, confidence)


def _add_range(
    spans: list[dict[str, Any]], occupied: set[int], text: str,
    start: int, end: int, label: str, confidence: float,
) -> bool:
    while end > start and text[end - 1] in " .,;:!?\n":
        end -= 1
    positions = set(range(start, end))
    if start == end or occupied & positions:
        return False
    occupied |= positions
    spans.append(
        {
            "start": start,
            "end": end,
            "text": text[start:end],
            "label": label,
            "confidence": confidence,
        }
    )
    return True


def annotate(text: str, bank_name: str) -> tuple[list[dict[str, Any]], list[str]]:
    spans: list[dict[str, Any]] = []
    occupied: set[int] = set()
    issues: list[str] = []
    if bank_name:
        match = re.search(re.escape(bank_name), text)
        if match:
            _add(spans, occupied, text, match, "BANKA", 1.0)
    for pattern in PROMO_CODE_PATTERNS:
        for match in pattern.finditer(text):
            code = match.group("code").strip()
            if code.upper() in PROMO_CODE_STOPWORDS:
                continue
            _add_range(
                spans, occupied, text,
                match.start("code"), match.end("code"), "PROMOSYON_KODU", 0.99,
            )
    for label, pattern, confidence in PATTERNS:
        for match in pattern.finditer(text):
            _add(spans, occupied, text, match, label, confidence)
    for pattern in CONDITION_PATTERNS:
        for match in pattern.finditer(text):
            _add(spans, occupied, text, match, "KAMPANYA_KOSULU", 0.91)
    for match in re.finditer(MONEY, text, re.I):
        window = text[max(0, match.start() - 55) : min(len(text), match.end() + 55)]
        if REWARD_CONTEXT.search(window):
            label, confidence = "ODUL_MIKTARI", 0.91
        elif PRODUCT_CONTEXT.search(window):
            label, confidence = "FINANSMAN_TUTARI", 0.90
        else:
            # In campaign pages, remaining explicit amounts overwhelmingly
            # represent minimum spend/payment/transaction conditions.
            label, confidence = "KAMPANYA_KOSULU", 0.90
        _add(spans, occupied, text, match, label, confidence)
    spans.sort(key=lambda item: item["start"])
    if len(spans) <= 1:
        issues.append("few_entities")
    return spans, issues


def prepare(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(input_path).read_text(encoding="utf-8-sig"))
    rows = payload.get("records", [])
    prepared = []
    for index, row in enumerate(rows):
        bank = str(row.get("bank_name") or "").strip()
        title = str(row.get("title") or "").strip()
        clean = str(row.get("clean_text") or row.get("content") or "").strip()
        text = "\n".join(part for part in (bank, title, clean) if part)
        entities, issues = annotate(text, bank)
        minimum = min((entity["confidence"] for entity in entities), default=0.0)
        status = "auto_high_confidence" if minimum >= 0.90 and not issues else "review_required"
        prepared.append({
            "id": str(row.get("id") or f"campaign-{index}"),
            "source_id": str(row.get("id") or f"campaign-{index}"),
            "source_url": row.get("source_url"),
            "bank_slug": row.get("bank_slug"),
            "text": text,
            "entities": entities,
            "split": split_for(str(row.get("id") or f"campaign-{index}")),
            "label_status": status,
            "training_eligible": status == "auto_high_confidence",
            "human_verified": False,
            "review_issues": issues,
            "labeling_method": "terminology-regex-v2",
        })
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in prepared),
        encoding="utf-8",
    )
    labels = Counter(entity["label"] for row in prepared for entity in row["entities"])
    return {
        "records": len(prepared),
        "splits": dict(Counter(row["split"] for row in prepared)),
        "statuses": dict(Counter(row["label_status"] for row in prepared)),
        "entities": dict(sorted(labels.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("output")
    args = parser.parse_args()
    print(json.dumps(prepare(args.input, args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
