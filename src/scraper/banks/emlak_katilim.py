from ..base import BaseBankScraper, ScraperConfig


class EmlakKatilimScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="emlak-katilim",
        bank_name="Türkiye Emlak Katılım Bankası A.Ş.",
        base_url="https://www.emlakkatilim.com.tr",
        listing_urls=("https://www.emlakkatilim.com.tr/tr/bireysel/kampanyalar",),
        detail_pattern=r"/tr/bireysel/kampanyalar/kampanya/[^/?#]+$",
        listing_link_selectors=(".campaign-card a[href]",),
        discover_from_base_url=True,
        content_selectors=("article.o-page__content",),
        title_selectors=("article.o-page__content h2", ".c-subpage-header h1", "h1"),
    )
