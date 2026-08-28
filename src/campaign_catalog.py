"""Kampanya kataloğu için doğrulanmış daraltma kuralları."""

from __future__ import annotations

from typing import Any, Iterable


CampaignIdentity = tuple[str, str]


# Bu kayıtlar 24 belirsiz kampanya kümesinde ürün türü kanıtı taşımıyor ve
# kullanıcının doğrulama kararıyla aktif katalogdan çıkarılıyor. Kimlikte banka
# ve başlık birlikte tutulduğu için scraper ID'si değişse bile kural kararlı
# kalır.
CURATED_EXCLUDED_CAMPAIGNS: frozenset[CampaignIdentity] = frozenset(
    {
        ("vakif-katilim", "Taze Çiçek’te %15 İndirim!"),
        (
            "albaraka-turk",
            'Albaraka Mobil\'de Şimdi "Seçkin Fırsatlar" Zamanı!',
        ),
        ("vakif-katilim", "Muhiku’da %20 İndirim!"),
        ("albaraka-turk", "8 Taksit Fırsatıyla KASKO Zamanı!"),
        ("kuveyt-turk", "Fatura Talimatlarınıza Toplam 500 TL Hediye!"),
        ("vakif-katilim", "AVVA’da Tüm İndirimlere Ek %10 İndirim!"),
        ("vakif-katilim", "Otel Rezervasyonlarında 2.500 TL İndirim!"),
        ("hayat-finans", "Harcadıkça Kazan, Cebin Hep Dolu Kalsın!"),
        ("vakif-katilim", "Espressolab Hediye Kahve Kampanyası"),
        ("vakif-katilim", "Tiktak’ta 600 TL İndirim!"),
        ("vakif-katilim", "Nota Çiçek’te %20 İndirim!"),
        ("vakif-katilim", "Vialand’da %25 İndirim!"),
        ("vakif-katilim", "Arzum’da %15 İndirim!"),
        (
            "vakif-katilim",
            "Mobilden Fatura Talimatına 1 Aylık tabii Premium Üyelik Hediye!",
        ),
        ("albaraka-turk", "Limitsiz İMM Sigortasında Vade Farksız 3 Taksit!"),
        ("vakif-katilim", "English Home’da %15 İndirim!"),
        (
            "vakif-katilim",
            "Vakıf Katılımlı Olanlara tabii’den Premium Üyelik!",
        ),
        ("albaraka-turk", "Kahve Keyfiniz Albaraka’dan!"),
        (
            "albaraka-turk",
            "Ücretsiz İSPARK Otopark Kampanyası | Albarakalılara Özel",
        ),
        (
            "vakif-katilim",
            "Vakıf Katılımlılar Davet Et Kazan’la Kazanıyor!",
        ),
        ("albaraka-turk", "Hızlı Çiçek %20 İndirim Kampanyası"),
        ("vakif-katilim", "Etkinlik Biletlerinde 250 TL İndirim!"),
    }
)


CURATED_INVESTMENT_CAMPAIGNS: frozenset[CampaignIdentity] = frozenset(
    {
        (
            "kuveyt-turk",
            "Kuveyt Türk Mobil’den Müşterimiz Olun Özel Kur Fırsatını "
            "Kaçırmayın!",
        ),
        ("turkiye-finans", "Günlük Hesap’la İhtiyaç Anında Vadeni Bozma!"),
    }
)


def _record_value(record: Any, key: str) -> Any:
    if isinstance(record, dict):
        return record.get(key)
    return getattr(record, key, None)


def campaign_identity(record: Any) -> CampaignIdentity:
    return (
        str(_record_value(record, "bank_slug") or "").strip(),
        str(_record_value(record, "title") or "").strip(),
    )


def filter_curated_campaigns(
    records: Iterable[Any],
) -> list[Any]:
    """Remove only the explicitly excluded campaign identities.

    Products and known typed campaigns are preserved. The function returns
    and preserves the input record type for scraper models and JSON records.
    """

    return [
        record
        for record in records
        if not (
            str(_record_value(record, "record_kind") or "campaign")
            == "campaign"
            and campaign_identity(record) in CURATED_EXCLUDED_CAMPAIGNS
        )
    ]


def is_curated_investment(record: Any) -> bool:
    return campaign_identity(record) in CURATED_INVESTMENT_CAMPAIGNS
