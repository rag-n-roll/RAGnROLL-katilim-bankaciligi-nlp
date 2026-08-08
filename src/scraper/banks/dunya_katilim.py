from ..base import BaseBankScraper, ScraperConfig


class DunyaKatilimScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="dunya-katilim",
        bank_name="Dünya Katılım Bankası A.Ş.",
        base_url="https://dunyakatilim.com.tr",
        listing_urls=("https://dunyakatilim.com.tr/kampanyalar",),
        detail_pattern=r"/kampanyalar/[^/?#]+$",
        listing_link_selectors=(".notification-popup a[href]",),
        content_selectors=(".campaign-detail-content-text",),
        title_selectors=("h1.campaign-detail-header-left-title", "h1"),
    )
