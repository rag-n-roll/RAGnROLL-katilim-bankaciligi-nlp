from urllib.parse import urljoin

from ..base import BaseBankScraper, ScraperConfig


class TurkiyeFinansScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="turkiye-finans",
        bank_name="Türkiye Finans Katılım Bankası A.Ş.",
        base_url="https://www.turkiyefinans.com.tr",
        allowed_campaign_hosts=(
            "www.turkiyefinansala.com",
            "turkiyefinansala.com",
            "www.happycard.com.tr",
            "happycard.com.tr",
        ),
        listing_urls=(
            (
                "https://www.turkiyefinans.com.tr/tr-tr/kampanyalar/Sayfalar/"
                "dijital-bankacilik-kampanyalari.aspx"
            ),
            (
                "https://www.turkiyefinans.com.tr/tr-tr/kampanyalar/Sayfalar/"
                "kart-kampanyalari.aspx"
            ),
            (
                "https://www.turkiyefinans.com.tr/tr-tr/kampanyalar/Sayfalar/"
                "finansman-kampanyalari.aspx"
            ),
            (
                "https://www.turkiyefinans.com.tr/tr-tr/kampanyalar/Sayfalar/"
                "yatirim-kampanyalari.aspx"
            ),
            "https://www.turkiyefinansala.com/tr-tr/kampanyalar/Sayfalar/default.aspx",
            "https://www.happycard.com.tr/kampanyalar/Sayfalar/default.aspx",
        ),
        detail_pattern=r"(?:/tr-tr/kampanyalar/sayfalar/|/kampanyalar/sayfalar/)[^/?#]+\.aspx$",
        listing_link_selectors=(
            ".campaign-list .campaign a[href]",
            ".landing-item a[href]",
            ".campaign-item a[href]",
        ),
        discover_from_base_url=True,
        content_selectors=(
            ".subpage-content.page .ms-rtestate-field",
            ".subpage-content .ms-rtestate-field",
            ".campaign-detail .ms-rtestate-field",
            ".campaign-detail",
        ),
        title_selectors=(
            ".subpage-content.page .header h1",
            ".subpage-content .header h1",
            ".campaign-detail h2",
            ".campaign-detail h1",
            "h1",
        ),
    )

    def _discover_paginated_urls(self, seen: set[str]) -> list[str]:
        urls: list[str] = []

        # 1. Âlâ Bankacılık AJAX endpoint
        try:
            ala_endpoint = (
                "https://www.turkiyefinansala.com/tr-tr/_layouts/15/"
                "AlaBankacilik/Kampanyalar/Ajax.aspx/GetAllCampaigns"
            )
            response = self.client.session.post(
                ala_endpoint,
                headers={"Content-Type": "application/json; charset=utf-8"},
                json={},
                timeout=self.client.timeout_seconds,
            )
            if response.status_code == 200:
                data = response.json()
                items = data.get("d", {}).get("Data") or []
                for item in items:
                    url_path = str(item.get("Url") or "").strip()
                    if url_path:
                        full_url = urljoin("https://www.turkiyefinansala.com", url_path)
                        if full_url not in seen and full_url not in urls:
                            urls.append(full_url)
        except Exception:
            pass

        # 2. Happy Card category AJAX endpoint
        for category in ("all", "done"):
            try:
                happy_endpoint = (
                    "https://www.happycard.com.tr/kampanyalar/_layouts/15/"
                    f"HappyCard/GetCampaignsFilterCategory.aspx?category={category}"
                )
                response = self.client.session.get(
                    happy_endpoint,
                    headers={"accept": "application/json;odata=verbose"},
                    timeout=self.client.timeout_seconds,
                )
                if response.status_code == 200:
                    items = response.json()
                    if isinstance(items, list):
                        for item in items:
                            url_path = str(item.get("CampaignDetailUrl") or "").strip()
                            if url_path:
                                full_url = urljoin("https://www.happycard.com.tr", url_path)
                                if full_url not in seen and full_url not in urls:
                                    urls.append(full_url)
            except Exception:
                pass

        return urls
