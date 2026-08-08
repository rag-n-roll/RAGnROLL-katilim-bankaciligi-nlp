from pathlib import Path

from src.scraper.banks import (
    AdilKatilimScraper,
    DunyaKatilimScraper,
    HayatFinansScraper,
    TomKatilimScraper,
)
from src.scraper.registry import SCRAPERS
from src.scraper.validation import validate_campaign


FIXTURES = Path(__file__).parent / "fixtures" / "banks"


class FixtureClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses

    def get_text(self, url: str) -> str:
        if url not in self.responses:
            raise AssertionError(f"Unexpected fixture URL: {url}")
        return self.responses[url]


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_registry_covers_all_normative_bddk_slugs():
    assert set(SCRAPERS) == {
        "adil-katilim",
        "albaraka-turk",
        "dunya-katilim",
        "hayat-finans",
        "kuveyt-turk",
        "tom-katilim",
        "emlak-katilim",
        "turkiye-finans",
        "vakif-katilim",
        "ziraat-katilim",
    }


def test_dunya_katilim_scrapes_campaign_detail():
    detail_url = "https://dunyakatilim.com.tr/kampanyalar/network"
    client = FixtureClient(
        {
            DunyaKatilimScraper.config.listing_urls[0]: fixture("dunya_katilim_listing.html"),
            detail_url: fixture("dunya_katilim_detail.html"),
        }
    )

    records, failures = DunyaKatilimScraper(client=client).scrape(limit=1)

    assert failures == []
    assert len(records) == 1
    assert records[0].record_kind == "campaign"
    assert records[0].source_url == detail_url
    assert not [issue for issue in validate_campaign(records[0]) if issue["severity"] == "error"]


def test_hayat_finans_scrapes_campaign_detail():
    detail_url = "https://hayatfinans.com.tr/kampanyalar/islem-yaptikca-kazan"
    client = FixtureClient(
        {
            HayatFinansScraper.config.listing_urls[0]: fixture("hayat_finans_listing.html"),
            detail_url: fixture("hayat_finans_detail.html"),
        }
    )

    records, failures = HayatFinansScraper(client=client).scrape(limit=1)

    assert failures == []
    assert len(records) == 1
    assert records[0].record_kind == "campaign"
    assert records[0].source_url == detail_url
    assert not [issue for issue in validate_campaign(records[0]) if issue["severity"] == "error"]


def test_adil_katilim_collects_official_product_text():
    url = AdilKatilimScraper.config.listing_urls[0]
    client = FixtureClient({url: fixture("adil_katilim_product.html")})

    records, failures = AdilKatilimScraper(client=client).scrape(limit=1)

    assert failures == []
    assert len(records) == 1
    assert records[0].record_kind == "product"
    assert records[0].title == "Katılım Bankacılığı Ürün ve Hizmetleri"
    assert "Bireysel Finansman" in records[0].content


def test_tom_compound_page_returns_one_record_per_campaign_section():
    url = TomKatilimScraper.config.listing_urls[0]
    client = FixtureClient({url: fixture("tom_katilim_campaigns.html")})

    records, failures = TomKatilimScraper(client=client).scrape()

    assert failures == []
    assert [record.source_item_key for record in records] == [
        "restoran-harcamalarinda-10-iade-kazan",
        "ozel-okul-odemelerinde-10-taksit",
    ]
    assert len({record.id for record in records}) == 2
    assert all(record.source_url == url for record in records)
