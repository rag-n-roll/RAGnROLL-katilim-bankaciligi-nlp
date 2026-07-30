from ..base import BaseBankScraper, ScraperConfig


class AlbarakaScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="albaraka-turk",
        bank_name="Albaraka Türk Katılım Bankası A.Ş.",
        base_url="https://www.albaraka.com.tr",
        listing_urls=("https://www.albaraka.com.tr/tr/kampanyalar",),
        detail_pattern=r"/tr/kampanyalar/detay/[^/?#]+$",
        listing_link_selectors=(".kampanyalar-card a[href]",),
        content_selectors=(".searchContent.custom-table",),
        title_selectors=("h1.searchTitle", "h1"),
    )
