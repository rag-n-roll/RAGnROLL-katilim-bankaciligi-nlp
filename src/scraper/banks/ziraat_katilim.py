from ..base import BaseBankScraper, ScraperConfig


class ZiraatKatilimScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="ziraat-katilim",
        bank_name="Ziraat Katılım Bankası A.Ş.",
        base_url="https://www.ziraatkatilim.com.tr",
        listing_urls=("https://www.ziraatkatilim.com.tr/kart-kampanyalari",),
        detail_pattern=r"/kart-kampanyalari/[^/?#]+$",
        listing_link_selectors=(".campaign-item a[href]",),
        content_selectors=(".node-bankkart-kampanyalar",),
        title_selectors=("h1.node-title", ".main-content > h1"),
    )
