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
