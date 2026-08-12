import json
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..base import BaseBankScraper, ScraperConfig


class DunyaKatilimScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="dunya-katilim",
        bank_name="Dünya Katılım Bankası A.Ş.",
        base_url="https://dunyakatilim.com.tr",
        listing_urls=("https://dunyakatilim.com.tr/kampanyalar",),
        detail_pattern=r"/kampanyalar/[^/?#]+$",
        listing_link_selectors=(".notification-popup a[href]",),
        discover_from_base_url=True,
        content_selectors=(".campaign-detail-content-text",),
        title_selectors=("h1.campaign-detail-header-left-title", "h1"),
    )

    def _discover_paginated_urls(self, seen: set[str]) -> list[str]:
        listing_url = self.config.listing_urls[0]
        html = self._listing_documents.get(listing_url, "")
        if not BeautifulSoup(html, "html.parser").select_one("#moreCampaigns"):
            return []

        urls: list[str] = []
        endpoint = urljoin(listing_url, "/GetCampaigns")
        for campaign_type in (1, 2):
            page = 1
            while True:
                response = self.client.get(
                    endpoint,
                    params={
                        "campaignType": campaign_type,
                        "siteId": 1,
                        "query": "",
                        "categoryId": 0,
                        "totalPage": page,
                        "showHistory": "false",
                    },
                )
                payload = json.loads(response.text)
                view = str(payload.get("view") or "")
                found = self._extract_detail_urls(
                    view, listing_url, seen, selectors=("a[href]",)
                )
                urls.extend(found)
                if payload.get("allRead") or not view:
                    break
                if not found:
                    raise ValueError("Dunya Katilim pagination ilerlemedi")
                page += 1
                if page > 100:
                    raise ValueError("Dunya Katilim pagination sayfa sinirini asti")
        return urls
