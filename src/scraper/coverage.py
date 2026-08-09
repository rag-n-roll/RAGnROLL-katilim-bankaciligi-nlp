"""BDDK katalogu ile yerel scraper registry kapsamını karşılaştırır."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def build_coverage_report(
    catalog_banks: Sequence[Mapping[str, Any]],
    scrapers: Mapping[str, object],
) -> dict[str, Any]:
    catalog = {str(bank["slug"]) for bank in catalog_banks}
    registered = set(scrapers)
    supported = sorted(catalog & registered)
    unsupported = sorted(catalog - registered)
    stale = sorted(registered - catalog)
    return {
        "catalog_count": len(catalog),
        "supported_count": len(supported),
        "supported": supported,
        "unsupported": unsupported,
        "stale": stale,
        "complete": not unsupported and not stale,
    }
