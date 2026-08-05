from ..base import BaseBankScraper, ScraperConfig


class TurkiyeFinansScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="turkiye-finans",
        bank_name="Türkiye Finans Katılım Bankası A.Ş.",
        base_url="https://www.turkiyefinans.com.tr",
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
        ),
        detail_pattern=r"/tr-tr/kampanyalar/sayfalar/[^/?#]+\.aspx$",
        listing_link_selectors=(".campaign-list .campaign a[href]",),
        content_selectors=(".subpage-content.page .ms-rtestate-field",),
        title_selectors=(".subpage-content.page .header h1", "h1"),
    )
