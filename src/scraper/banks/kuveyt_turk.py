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
