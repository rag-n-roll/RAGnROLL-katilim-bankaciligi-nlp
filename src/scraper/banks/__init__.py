"""Desteklenen banka scraper siniflari."""

from .albaraka import AlbarakaScraper
from .adil_katilim import AdilKatilimScraper
from .dunya_katilim import DunyaKatilimScraper
from .emlak_katilim import EmlakKatilimScraper
from .hayat_finans import HayatFinansScraper
from .kuveyt_turk import KuveytTurkScraper
from .turkiye_finans import TurkiyeFinansScraper
from .tom_katilim import TomKatilimScraper
from .vakif_katilim import VakifKatilimScraper
from .ziraat_katilim import ZiraatKatilimScraper

__all__ = [
    "AlbarakaScraper",
    "AdilKatilimScraper",
    "DunyaKatilimScraper",
    "EmlakKatilimScraper",
    "HayatFinansScraper",
    "KuveytTurkScraper",
    "TurkiyeFinansScraper",
    "TomKatilimScraper",
    "VakifKatilimScraper",
    "ZiraatKatilimScraper",
]
