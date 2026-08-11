from ..base import BaseBankScraper, ScraperConfig


class VakifKatilimScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="vakif-katilim",
        bank_name="Vakıf Katılım Bankası A.Ş.",
        base_url="https://www.vakifkatilim.com.tr",
        listing_urls=(
            "https://www.vakifkatilim.com.tr/tr/kendim-icin/kampanyalar/mevcut-kampanyalar",
        ),
        detail_pattern=r"/tr/kendim-icin/kampanyalar/detay/[^/?#]+$",
        # Liste govdesi JS ile geliyor; bildirim linkleri sunucu tarafli guvenli geri donustur.
        listing_link_selectors=("a.notification-unread[href]", "a[href*='/kampanyalar/detay/']"),
        discover_from_base_url=True,
        content_selectors=(".hero-content", ".anchor-menu-section"),
        title_selectors=(".hero-content h1", "h1"),
    )
