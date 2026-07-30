"""Scraper kayit defteri ve haftalik oncelik gruplari."""

from .banks import (
    AlbarakaScraper,
    EmlakKatilimScraper,
    KuveytTurkScraper,
    TurkiyeFinansScraper,
    VakifKatilimScraper,
    ZiraatKatilimScraper,
)

SCRAPERS = {
    "kuveyt-turk": KuveytTurkScraper,
    "albaraka-turk": AlbarakaScraper,
    "turkiye-finans": TurkiyeFinansScraper,
    "ziraat-katilim": ZiraatKatilimScraper,
    "vakif-katilim": VakifKatilimScraper,
    "emlak-katilim": EmlakKatilimScraper,
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
