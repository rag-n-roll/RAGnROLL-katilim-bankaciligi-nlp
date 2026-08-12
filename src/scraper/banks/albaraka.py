import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..base import BaseBankScraper, ScraperConfig


class AlbarakaScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="albaraka-turk",
        bank_name="Albaraka Türk Katılım Bankası A.Ş.",
        base_url="https://www.albaraka.com.tr",
        listing_urls=("https://www.albaraka.com.tr/tr/kampanyalar",),
        detail_pattern=r"/tr/kampanyalar/detay/[^/?#]+$",
        listing_link_selectors=(".kampanyalar-card a[href]",),
        # Kategori linkleri ?slug=... robots.txt tarafindan yasakli; ana liste ve
        # izinli JSON devam endpoint'i tum kampanyalari zaten sagliyor.
        campaign_hub_link_selectors=(),
        discover_from_base_url=True,
        content_selectors=(".searchContent.custom-table",),
        title_selectors=("h1.searchTitle", "h1"),
    )

    def _discover_paginated_urls(self, seen: set[str]) -> list[str]:
        listing_url = self.config.listing_urls[0]
        html = self._listing_documents.get(listing_url, "")
        soup = BeautifulSoup(html, "html.parser")
        if not soup.select_one(".btn-outline-kampanyalar-primary"):
            return []

        lang_id = re.search(r"langId:\s*['\"]([^'\"]+)", html)
        if not lang_id:
            raise ValueError("Albaraka pagination langId bulunamadi")

        urls: list[str] = []
        page_size = 9
        page = 2
        total_count: int | None = None
        endpoint = urljoin(listing_url, "/plugins/GetCampaigns")
        while total_count is None or (page - 1) * page_size < total_count:
            response = self.client.get(
                endpoint,
                params={
                    "langId": lang_id.group(1),
                    "language": "tr",
                    "PageIndex": page,
                    "PageSize": page_size,
                    "Type": "",
                },
                headers={
                    "Accept": "application/json",
                    "Referer": listing_url,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            payload = json.loads(response.text)
            if not payload.get("Result"):
                raise ValueError("Albaraka pagination endpoint basarisiz sonuc dondurdu")
            data = payload.get("Data") or {}
            total_count = int(data.get("TotalCount") or 0)
            items = data.get("Campaigns") or []
            page_new = 0
            for item in items:
                href = str(item.get("Link") or "").strip()
                if not href:
                    continue
                fragment = f'<a href="{href}">Kampanya</a>'
                found = self._extract_detail_urls(
                    fragment, listing_url, seen, selectors=("a[href]",)
                )
                urls.extend(found)
                page_new += len(found)
            if not items or (page_new == 0 and page * page_size < total_count):
                raise ValueError("Albaraka pagination ilerlemedi")
            page += 1
        return urls
