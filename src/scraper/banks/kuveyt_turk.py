import json
import re
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from ..base import BaseBankScraper, ScraperConfig


class KuveytTurkScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="kuveyt-turk",
        bank_name="Kuveyt Türk Katılım Bankası A.Ş.",
        base_url="https://www.kuveytturk.com.tr",
        listing_urls=(
            "https://www.kuveytturk.com.tr/kampanyalar/kendim-icin/kart-kampanyalari",
            "https://www.kuveytturk.com.tr/kampanyalar/kendim-icin/musteri-ol-kampanyalari",
        ),
        detail_pattern=r"/kampanyalar/kendim-icin/[^/?#]+/[^/?#]+$",
        listing_link_selectors=(".campaign-item a[href]",),
        discover_from_base_url=True,
        content_selectors=(".subpage-content .search-content",),
        title_selectors=("h1#pageTitle", "h1"),
    )

    def _discover_paginated_urls(self, seen: set[str]) -> list[str]:
        urls: list[str] = []
        api_endpoint: str | None = None
        page_size = 9

        for listing_url in self.config.listing_urls:
            html = self._listing_documents.get(listing_url, "")
            soup = BeautifulSoup(html, "html.parser")
            if not soup.select_one(".load-more-btn"):
                continue
            category = soup.select_one(".sub-cat option[selected][data-id]")
            if category is None:
                category = soup.select_one(".campaign-tab-btn.active[data-id]")
            category_id = str(category.get("data-id") or "") if category else ""
            if not category_id:
                raise ValueError("Kuveyt Turk kampanya kategori kimligi bulunamadi")

            if api_endpoint is None:
                script = next(
                    (
                        str(tag.get("src"))
                        for tag in soup.select("script[src]")
                        if "magiclick.core.min.js" in str(tag.get("src"))
                    ),
                    "",
                )
                if not script:
                    raise ValueError("Kuveyt Turk API betigi bulunamadi")
                script_text = self.client.get_text(urljoin(listing_url, script))
                endpoint_match = re.search(r'\bck:"([^"]+)"', script_text)
                if not endpoint_match:
                    raise ValueError("Kuveyt Turk kampanya API yolu bulunamadi")
                api_endpoint = urljoin(
                    self.config.base_url + "/", endpoint_match.group(1)
                )

            query = urlencode(
                {
                    "p1": category_id,
                    "p2": "",
                    "p5": "false",
                    "p6": "",
                    "p7": "",
                    "p8": "false",
                }
            )
            endpoint = f"{api_endpoint}&{query}"
            total_count = len(soup.select(".campaign-item"))
            page = 2
            while (page - 1) * page_size < total_count or page == 2:
                response = self.client.get(
                    endpoint,
                    headers={"Page": str(page), "PageSize": str(page_size)},
                )
                items = json.loads(response.text)
                total_count = int(response.headers.get("Totalcount") or len(items))
                page_new = 0
                for item in items:
                    href = str(item.get("Url") or "").strip()
                    if not href:
                        continue
                    fragment = f'<a href="{href}">Kampanya</a>'
                    found = self._extract_detail_urls(
                        fragment, listing_url, seen, selectors=("a[href]",)
                    )
                    urls.extend(found)
                    page_new += len(found)
                if not items:
                    break
                if page_new == 0 and page * page_size < total_count:
                    raise ValueError("Kuveyt Turk pagination ilerlemedi")
                page += 1
        return urls
