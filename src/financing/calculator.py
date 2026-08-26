"""Kaynaklı oranları aynı giriş koşulları için karşılaştırılabilir hale getirir."""

from __future__ import annotations

from datetime import date, datetime, timezone
from math import isfinite
from typing import Any, Iterable


CALCULATOR_SOURCES = {
    "adil-katilim": (
        "https://www.adilkatilim.com.tr/assets/pdfs/"
        "Adil%20Kat%C4%B1l%C4%B1m_%C3%9Ccret%20bilgilendirme%20formu.pdf"
    ),
    "albaraka-turk": "https://basvur.albaraka.com.tr/jet-finansman",
    "dunya-katilim": "https://dunyakatilim.com.tr/kendim-icin/finansmanlar/ihtiyac-finansmani",
    "emlak-katilim": "https://www.emlakkatilim.com.tr/tr",
    "hayat-finans": "https://hayatfinans.com.tr/krediler/bana-bunu-al",
    "kuveyt-turk": "https://www.kuveytturk.com.tr/hesaplama-araclari/finansman-hesaplama",
    "tom-katilim": "https://www.tombank.com.tr/hesaplama-araclari.html",
    "turkiye-finans": "https://www.turkiyefinans.com.tr/tr-tr/hesaplama-araclari/sayfalar/finansman-odeme-plani.aspx",
    "vakif-katilim": "https://www.vakifkatilim.com.tr/tr/yardimci-sayfalar/hesaplama-araclari/finansman-hesaplama",
    "ziraat-katilim": "https://www.ziraatkatilim.com.tr/bireysel/finansman-urunleri/ihtiyac-finansmani",
}

UNAVAILABLE_MESSAGES = {
    "adil-katilim": (
        "Adil Katılım'ın 03.04.2026 tarihli resmî ücret formunda ticari "
        "finansman tahsis ücreti azami %0,20, kullandırım ücreti azami "
        "%1,10 (BSMV hariç) yayımlanıyor; aylık kâr payı oranı veya "
        "hesaplayıcı yayımlanmadığı için taksit hesaplanamıyor."
    )
}


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _structured(record: dict[str, Any]) -> dict[str, Any]:
    value = record.get("structured")
    return value if isinstance(value, dict) else {}


def _money_amount(value: Any) -> float | None:
    if not isinstance(value, dict):
        return None
    return _number(value.get("amount"))


def _is_active(record: dict[str, Any], today: date) -> bool:
    value = record.get("end_date") or _structured(record).get("campaign_end_date")
    if not value:
        return True
    try:
        return date.fromisoformat(str(value)[:10]) >= today
    except ValueError:
        return True


def _matches(
    record: dict[str, Any],
    *,
    financing_type: str,
    amount: float,
    term_months: int,
    today: date,
) -> bool:
    structured = _structured(record)
    if structured.get("product_type") != "financing":
        return False
    record_type = structured.get("financing_type")
    if record_type and record_type != financing_type:
        return False
    if not _is_active(record, today):
        return False
    max_amount = _money_amount(structured.get("max_amount"))
    min_amount = _money_amount(structured.get("min_amount"))
    max_term = _number(structured.get("term_months"))
    if max_amount is not None and amount > max_amount:
        return False
    if min_amount is not None and amount < min_amount:
        return False
    if max_term is not None and term_months > max_term:
        return False
    return _number(structured.get("profit_share_rate")) is not None


def _freshness_key(record: dict[str, Any]) -> str:
    return str(record.get("scraped_at") or record.get("updated_at") or "")


def _installment(amount: float, monthly_rate_percent: float, months: int) -> float:
    rate = monthly_rate_percent / 100
    if rate == 0:
        return round(amount / months, 2)
    factor = (1 + rate) ** months
    return round(amount * rate * factor / (factor - 1), 2)


def _annual_rate(monthly_rate_percent: float) -> float:
    return round(((1 + monthly_rate_percent / 100) ** 12 - 1) * 100, 2)


def build_financing_quotes(
    *,
    records: Iterable[dict[str, Any]],
    banks: Iterable[dict[str, Any]],
    financing_type: str,
    amount: float,
    term_months: int,
    official_quotes: dict[str, dict[str, Any]] | None = None,
    eligible_bank_slugs: set[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """On bankanın tümünü koruyarak uygun kaynaklı oranlardan teklif üretir."""
    generated_at = now or datetime.now(timezone.utc)
    today = generated_at.date()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        grouped.setdefault(str(record.get("bank_slug") or ""), []).append(record)

    quotes: list[dict[str, Any]] = []
    official_quotes = official_quotes or {}
    for bank in banks:
        slug = str(bank.get("slug") or "")
        if eligible_bank_slugs is not None and slug not in eligible_bank_slugs:
            continue
        if slug in official_quotes:
            quotes.append(official_quotes[slug])
            continue
        if eligible_bank_slugs is not None:
            # Kampanya seçildiğinde genel oran kaydına düşmek yanlış ürünü gösterir.
            continue
        candidates = [
            record
            for record in grouped.get(slug, [])
            if _matches(
                record,
                financing_type=financing_type,
                amount=amount,
                term_months=term_months,
                today=today,
            )
        ]
        candidates.sort(key=_freshness_key, reverse=True)
        source_url = CALCULATOR_SOURCES.get(slug) or bank.get("website")
        if not candidates:
            quotes.append(
                {
                    "bank_slug": slug,
                    "bank_name": bank.get("name") or slug,
                    "status": "unsupported",
                    "source_url": source_url,
                    "message": UNAVAILABLE_MESSAGES.get(
                        slug, "Bu tutar ve vade için doğrulanmış güncel oran bulunamadı."
                    ),
                }
            )
            continue

        record = candidates[0]
        structured = _structured(record)
        monthly_rate = float(structured["profit_share_rate"])
        installment = _installment(amount, monthly_rate, term_months)
        total = round(installment * term_months, 2)
        quotes.append(
            {
                "bank_slug": slug,
                "bank_name": bank.get("name") or record.get("bank_name") or slug,
                "product_name": record.get("title") or "Finansman",
                "status": "available",
                "monthly_profit_rate": monthly_rate,
                "monthly_installment": installment,
                "total_repayment": total,
                "annual_cost_rate": _annual_rate(monthly_rate),
                "fees_total": None,
                "source_url": record.get("source_url") or source_url,
                "retrieved_at": record.get("scraped_at") or record.get("updated_at"),
                "calculation_origin": "derived_from_sourced_rate",
                "message": "Taksit, kaynaklı aylık oran üzerinden tahmini hesaplanmıştır.",
            }
        )

    quotes.sort(
        key=lambda item: (
            item["status"] != "available",
            item.get("monthly_installment", float("inf")),
            item["bank_name"],
        )
    )
    available = sum(item["status"] == "available" for item in quotes)
    return {
        "generated_at": generated_at.isoformat(),
        "currency": "TRY",
        "quotes": quotes,
        "coverage": {
            "catalog_bank_count": len(quotes),
            "available": available,
            "unsupported": len(quotes) - available,
        },
        "disclaimer": (
            "Sonuçlar bilgilendirme amaçlı tahmini değerlerdir; kesin banka teklifi değildir. "
            "Vergi, fon, sigorta ve tahsis ücretleri yalnızca resmî kaynakta yayımlandığı ölçüde dahil edilir."
        ),
    }


