from ..base import BaseBankScraper, ScraperConfig


class HayatFinansScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="hayat-finans",
        bank_name="Hayat Finans Katılım Bankası A.Ş.",
        base_url="https://hayatfinans.com.tr",
        listing_urls=("https://hayatfinans.com.tr/kampanyalar",),
        detail_pattern=r"/kampanyalar/[^/?#]+$",
        listing_link_selectors=("section#contentCardContainer a[href]",),
        discover_from_base_url=True,
        content_selectors=("div[id^='contentModuleSection']",),
        title_selectors=("main h1", "h1"),
    )
