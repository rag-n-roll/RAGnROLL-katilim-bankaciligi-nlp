from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..base import (
    BaseBankScraper,
    ScraperConfig,
    build_failure,
    clean_lines,
    extract_date_range,
)
from ..models import Campaign


TURKISH_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _slug(value: str) -> str:
    normalized = value.translate(TURKISH_ASCII).casefold()
    return re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", normalized))


class TomKatilimScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="tom-katilim",
        bank_name="T.O.M. Katılım Bankası A.Ş.",
        base_url="https://www.tombank.com.tr",
        listing_urls=("https://www.tombank.com.tr/kampanyalar.html",),
        detail_pattern=r"/kampanyalar\.html$",
        content_selectors=(".campaign-list",),
        title_selectors=("h4",),
    )

    def scrape(self, *, limit: int | None = None):
        url = self.config.listing_urls[0]
        try:
            soup = BeautifulSoup(self.client.get_text(url), "html.parser")
        except Exception as exc:
            return [], [build_failure(self.config.slug, "fetch", url, exc)]

        sections = soup.select(
            ".col-lg > .d-flex.flex-column-reverse.flex-lg-row."
            "align-items-start.mb-4"
        )
        if limit is not None:
            sections = sections[: max(0, limit)]
        records: list[Campaign] = []
        failures = []
        for section in sections:
            try:
                heading = section.select_one("h5")
                if heading is None:
                    raise ValueError("TOM kampanya basligi bulunamadi")
                heading_copy = BeautifulSoup(str(heading), "html.parser")
                for paragraph in heading_copy.select("p"):
                    paragraph.decompose()
                title = clean_lines(heading_copy.get_text(" ", strip=True))
                content = clean_lines(section.get_text("\n", strip=True))
                if len(title) < 5 or len(content) < 80:
                    raise ValueError("TOM kampanya bolumu yetersiz")
                start_date, end_date = extract_date_range(content)
                records.append(
                    Campaign(
                        bank_slug=self.config.slug,
                        bank_name=self.config.bank_name,
                        title=title,
                        content=content,
                        summary=content[:500],
                        start_date=start_date,
                        end_date=end_date,
                        source_url=url,
                        source_item_key=_slug(title),
                    )
                )
            except Exception as exc:
                failures.append(build_failure(self.config.slug, "parse", url, exc))
        return records, failures
