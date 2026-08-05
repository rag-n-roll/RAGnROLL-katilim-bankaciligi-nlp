"""Desteklenen banka scraper siniflari."""

from .albaraka import AlbarakaScraper
from .emlak_katilim import EmlakKatilimScraper
from .kuveyt_turk import KuveytTurkScraper
from .turkiye_finans import TurkiyeFinansScraper
from .vakif_katilim import VakifKatilimScraper
from .ziraat_katilim import ZiraatKatilimScraper

__all__ = [
    "AlbarakaScraper",
    "EmlakKatilimScraper",
    "KuveytTurkScraper",
    "TurkiyeFinansScraper",
    "VakifKatilimScraper",
    "ZiraatKatilimScraper",
]
