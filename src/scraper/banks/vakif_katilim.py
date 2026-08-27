import re

from ..base import BaseBankScraper, ScraperConfig


class VakifKatilimScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="vakif-katilim",
        bank_name="Vakıf Katılım Bankası A.Ş.",
        base_url="https://www.vakifkatilim.com.tr",
        listing_urls=(
            "https://www.vakifkatilim.com.tr/tr/kendim-icin/kampanyalar/mevcut-kampanyalar",
            "https://www.vakifkatilim.com.tr/tr/kendim-icin/kampanyalar",
        ),
        detail_pattern=r"/tr/(?:kendim-icin|isim-icin)/kampanyalar/detay/[^/?#]+$",
        listing_link_selectors=("a.notification-unread[href]", "a[href*='/kampanyalar/detay/']"),
        discover_from_base_url=True,
        content_selectors=(".hero-content", ".anchor-menu-section", ".content-section"),
        title_selectors=(".hero-content h1", "h1.node-title", "h1"),
    )

    def _discover_paginated_urls(self, seen: set[str]) -> list[str]:
        urls: list[str] = []
        endpoint = "https://www.vakifkatilim.com.tr/plugins/GetCampaignList"
        lang_id = "bf2689d9-071e-4a20-9450-b1dbdd39778f"

        # 1. AJAX API discovery for active campaigns across
        # individual (1) and business (2) categories
        for page_type in (1, 2):
            section = "kendim-icin" if page_type == 1 else "isim-icin"
            page = 1
            while True:
                try:
                    response = self.client.session.get(
                        endpoint,
                        params={
                            "languageId": lang_id,
                            "pageType": page_type,
                            "page": page,
                            "pageItemSize": 50,
                            "sectorId": "",
                            "isPast": "false",
                        },
                        timeout=self.client.timeout_seconds,
                    )
                    if response.status_code != 200:
                        break
                    data = response.json()
                    items = data.get("items") or []
                    if not items:
                        break
                    for item in items:
                        link = str(item.get("link") or "").strip().strip("/")
                        if link:
                            full_url = (
                                f"https://www.vakifkatilim.com.tr/tr/{section}/"
                                f"kampanyalar/detay/{link}"
                            )
                            if full_url not in seen and full_url not in urls:
                                urls.append(full_url)
                    if len(items) < 50:
                        break
                    page += 1
                    if page > 20:
                        break
                except Exception:
                    break

        # 2. Sitemap discovery fallback for any additional campaign detail pages
        try:
            sitemap_resp = self.client.session.get(
                "https://www.vakifkatilim.com.tr/sitemap-tr.xml",
                timeout=self.client.timeout_seconds,
            )
            if sitemap_resp.status_code == 200:
                sitemap_matches = re.findall(
                    r"<loc>(https://www\.vakifkatilim\.com\.tr/tr/"
                    r"(?:kendim-icin|isim-icin)/kampanyalar/detay/[^<]+)</loc>",
                    sitemap_resp.text,
                )
                for match_url in sitemap_matches:
                    if match_url not in seen and match_url not in urls:
                        urls.append(match_url)
        except Exception:
            pass

        return urls
