from ..base import BaseBankScraper, ScraperConfig


class AdilKatilimScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="adil-katilim",
        bank_name="Adil Katılım Bankası A.Ş.",
        base_url="https://www.adilkatilim.com.tr",
        listing_urls=(
            "https://www.adilkatilim.com.tr/katilim-bankaciligi/urun-ve-hizmetler",
        ),
        detail_pattern=r"/katilim-bankaciligi/urun-ve-hizmetler$",
        content_selectors=(".accordion-container",),
        title_selectors=(".accordion-title",),
        record_kind="product",
    )

    def discover_urls(self) -> list[str]:
        return list(self.config.listing_urls)

    def parse_detail(self, url: str, html: str):
        record = super().parse_detail(url, html)
        record.title = "Katılım Bankacılığı Ürün ve Hizmetleri"
        return record
