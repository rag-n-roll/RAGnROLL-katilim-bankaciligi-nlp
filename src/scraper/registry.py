"""Scraper kayit defteri ve haftalik oncelik gruplari."""

from .banks import (
    AdilKatilimScraper,
    AlbarakaScraper,
    DunyaKatilimScraper,
    EmlakKatilimScraper,
    HayatFinansScraper,
    KuveytTurkScraper,
    TomKatilimScraper,
    TurkiyeFinansScraper,
    VakifKatilimScraper,
    ZiraatKatilimScraper,
)

SCRAPERS = {
    "adil-katilim": AdilKatilimScraper,
    "albaraka-turk": AlbarakaScraper,
    "dunya-katilim": DunyaKatilimScraper,
    "hayat-finans": HayatFinansScraper,
    "kuveyt-turk": KuveytTurkScraper,
    "tom-katilim": TomKatilimScraper,
    "emlak-katilim": EmlakKatilimScraper,
    "turkiye-finans": TurkiyeFinansScraper,
    "vakif-katilim": VakifKatilimScraper,
    "ziraat-katilim": ZiraatKatilimScraper,
}

PRIORITY_BANKS = ("kuveyt-turk", "albaraka-turk", "turkiye-finans")
ALL_BANKS = tuple(SCRAPERS)


def resolve_banks(value: str) -> tuple[str, ...]:
    if value == "priority":
        return PRIORITY_BANKS
    if value == "all":
        return ALL_BANKS
    result = tuple(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
    unknown = sorted(set(result) - set(SCRAPERS))
    if unknown:
        raise ValueError(f"Desteklenmeyen banka: {', '.join(unknown)}")
    return result
