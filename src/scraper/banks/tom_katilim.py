import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..base import BaseBankScraper, ScraperConfig


class TomKatilimScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="tom-katilim",
        bank_name="T.O.M. Katılım Bankası A.Ş.",
        base_url="https://www.tombank.com.tr",
        listing_urls=("https://www.tombank.com.tr/kampanyalar.html",),
        detail_pattern=r"/kampanyalar/[^/?#]+$",
        listing_link_selectors=("a[href*='/kampanyalar/']",),
        allowed_campaign_hosts=(
            "hadiyanindakibanka.com",
            "www.hadiyanindakibanka.com",
            "tombankhadi.com",
            "www.tombankhadi.com",
        ),
        discover_from_base_url=True,
        content_selectors=("main", ".campaign-detail", ".campaign-detail-content"),
        title_selectors=("main h1", "h1"),
    )

    def _discover_paginated_urls(self, seen: set[str]) -> list[str]:
        urls: list[str] = []
        endpoint = "https://tombankhadi.com/Campaign/Search"
        page_idx = 0

        while page_idx < 30:
            try:
                response = self.client.session.post(
                    endpoint,
                    data={"index": page_idx},
                    timeout=self.client.timeout_seconds,
                )
                if response.status_code != 200:
                    break
                soup_page = BeautifulSoup(response.text, "html.parser")
                links_page = soup_page.find_all("a", href=re.compile(r"/kampanyalar/[^/?#]+$"))
                if not links_page:
                    break
                for a in links_page:
                    href = a.get("href")
                    if href:
                        full_url = urljoin("https://tombankhadi.com", href)
                        if full_url not in seen and full_url not in urls:
                            urls.append(full_url)
                show_more = soup_page.select_one(".show-more")
                if not show_more:
                    break
                page_idx += 1
            except Exception:
                break

        return urls
