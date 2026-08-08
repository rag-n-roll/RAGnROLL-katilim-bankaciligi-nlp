from datetime import date, datetime
import logging

import requests

from src.scraper.base import BaseBankScraper, ScraperConfig, extract_date_range


class ExampleScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="ornek",
        bank_name="Örnek Katılım A.Ş.",
        base_url="https://bank.example",
        listing_urls=("https://bank.example/kampanyalar",),
        detail_pattern=r"/kampanyalar/[^/]+$",
        content_selectors=("article",),
    )


class MultiListingScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="coklu-ornek",
        bank_name="Çoklu Örnek Katılım A.Ş.",
        base_url="https://bank.example",
        listing_urls=(
            "https://bank.example/kampanyalar/ilk",
            "https://bank.example/kampanyalar/bozuk",
            "https://bank.example/kampanyalar/son",
        ),
        detail_pattern=r"/kampanyalar/[^/]+$",
        content_selectors=("article",),
    )


class StubClient:
    def __init__(self, responses: dict[str, str | Exception]) -> None:
        self.responses = responses

    def get_text(self, url: str) -> str:
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


DETAIL_URL = "https://bank.example/kampanyalar/firsat"
OTHER_DETAIL_URL = "https://bank.example/kampanyalar/diger-firsat"
OVERRIDE_DETAIL_URL = "https://bank.example/kampanyalar/gecersiz-kaynak"
LISTING_HTML = f'<a href="{DETAIL_URL}">Fırsat</a>'


class OverrideDiscoveryScraper(ExampleScraper):
    def __init__(self, client: StubClient) -> None:
        super().__init__(client)
        self.discovery_calls = 0

    def discover_urls(self) -> list[str]:
        self.discovery_calls += 1
        return [OVERRIDE_DETAIL_URL]


class FailingOverrideDiscoveryScraper(ExampleScraper):
    def discover_urls(self) -> list[str]:
        raise requests.Timeout("slow")


def test_scrape_reports_timeout_during_discovery_as_structured_failure():
    scraper = ExampleScraper(
        StubClient({"https://bank.example/kampanyalar": requests.Timeout("slow")})
    )

    records, failures = scraper.scrape()

    assert records == []
    assert len(failures) == 1
    failure = failures[0]
    assert failure["bank_slug"] == "ornek"
    assert failure["stage"] == "discovery"
    assert failure["url"] == "https://bank.example/kampanyalar"
    assert failure["error_type"] == "Timeout"
    assert failure["error"] == "slow"
    assert failure["http_status"] is None
    timestamp = datetime.fromisoformat(str(failure["timestamp"]))
    assert timestamp.tzinfo is not None
    assert timestamp.utcoffset().total_seconds() == 0


def test_scrape_honors_discover_urls_override_once():
    scraper = OverrideDiscoveryScraper(
        StubClient({OVERRIDE_DETAIL_URL: "<article><h1>Özel</h1><p>İçerik</p></article>"})
    )

    records, failures = scraper.scrape()

    assert scraper.discovery_calls == 1
    assert [record.source_url for record in records] == [OVERRIDE_DETAIL_URL]
    assert failures == []


def test_scrape_reports_failure_from_discover_urls_override():
    scraper = FailingOverrideDiscoveryScraper(StubClient({}))

    records, failures = scraper.scrape()

    assert records == []
    assert len(failures) == 1
    assert failures[0]["stage"] == "discovery"
    assert failures[0]["url"] == "https://bank.example/kampanyalar"
    assert failures[0]["error_type"] == "Timeout"


def test_scrape_reports_connection_error_during_detail_fetch():
    scraper = ExampleScraper(
        StubClient(
            {
                "https://bank.example/kampanyalar": LISTING_HTML,
                DETAIL_URL: requests.ConnectionError("offline"),
            }
        )
    )

    records, failures = scraper.scrape()

    assert records == []
    assert failures[0]["stage"] == "fetch"
    assert failures[0]["url"] == DETAIL_URL
    assert failures[0]["error_type"] == "ConnectionError"


def test_scrape_reports_http_status_for_http_error():
    response = requests.Response()
    response.status_code = 503
    error = requests.HTTPError("service unavailable", response=response)
    scraper = ExampleScraper(
        StubClient(
            {
                "https://bank.example/kampanyalar": LISTING_HTML,
                DETAIL_URL: error,
            }
        )
    )

    _, failures = scraper.scrape()

    assert failures[0]["http_status"] == 503


def test_scrape_keeps_following_record_when_one_detail_parse_fails(monkeypatch):
    listing_html = (
        f'<a href="{DETAIL_URL}">Bozuk</a>'
        f'<a href="{OTHER_DETAIL_URL}">Geçerli</a>'
    )
    scraper = ExampleScraper(
        StubClient(
            {
                "https://bank.example/kampanyalar": listing_html,
                DETAIL_URL: "<html>bozuk</html>",
                OTHER_DETAIL_URL: "<article><h1>Geçerli</h1><p>İçerik</p></article>",
            }
        )
    )
    original_parse_detail = scraper.parse_detail

    def raise_for_first_url(url: str, html: str):
        if url == DETAIL_URL:
            raise ValueError("invalid detail")
        return original_parse_detail(url, html)

    monkeypatch.setattr(scraper, "parse_detail", raise_for_first_url)

    records, failures = scraper.scrape()

    assert [record.source_url for record in records] == [OTHER_DETAIL_URL]
    assert failures[0]["stage"] == "parse"
    assert failures[0]["url"] == DETAIL_URL


def test_scrape_preserves_successful_listings_around_discovery_failure(caplog):
    first_listing_url, failed_listing_url, last_listing_url = (
        MultiListingScraper.config.listing_urls
    )
    scraper = MultiListingScraper(
        StubClient(
            {
                first_listing_url: f'<a href="{DETAIL_URL}">İlk</a>',
                failed_listing_url: requests.Timeout("slow"),
                last_listing_url: f'<a href="{OTHER_DETAIL_URL}">Son</a>',
                DETAIL_URL: "<article><h1>İlk</h1><p>İçerik</p></article>",
                OTHER_DETAIL_URL: "<article><h1>Son</h1><p>İçerik</p></article>",
            }
        )
    )
    caplog.set_level(logging.INFO, logger="src.scraper.base")

    records, failures = scraper.scrape()

    assert [record.source_url for record in records] == [DETAIL_URL, OTHER_DETAIL_URL]
    assert len(failures) == 1
    assert failures[0]["stage"] == "discovery"
    assert failures[0]["url"] == failed_listing_url
    assert any("Campaign detail parsed" in message for message in caplog.messages)


def test_extracts_turkish_textual_date_range_with_inferred_year():
    assert extract_date_range("14 Temmuz - 31 Temmuz 2026") == (
        date(2026, 7, 14),
        date(2026, 7, 31),
    )


def test_extracts_numeric_date_range():
    assert extract_date_range("01-04-2025 - 31-07-2026") == (
        date(2025, 4, 1),
        date(2026, 7, 31),
    )


def test_extracts_compact_turkish_date_range_with_shared_month():
    assert extract_date_range("Kampanya 1-31 Ağustos 2026 tarihleri arasında geçerlidir.") == (
        date(2026, 8, 1),
        date(2026, 8, 31),
    )


def test_extracts_textual_date_range_with_clock_text_before_separator():
    assert extract_date_range(
        "10 Haziran 2026 saat 00.01 – 31 Ağustos 2026 saat 23.59 "
        "tarihleri arasında geçerlidir."
    ) == (
        date(2026, 6, 10),
        date(2026, 8, 31),
    )


def test_extracts_numeric_single_campaign_end_date():
    assert extract_date_range("Kampanya 31.12.2026 tarihine kadar geçerlidir.") == (
        None,
        date(2026, 12, 31),
    )


def test_extracts_textual_single_campaign_end_date_with_clock_text():
    assert extract_date_range(
        "İndirim kodları en geç 31 Aralık 2026 saat 23:59'a kadar kullanılabilir."
    ) == (
        None,
        date(2026, 12, 31),
    )


def test_does_not_treat_unrelated_single_date_as_campaign_end():
    assert extract_date_range(
        "Kullanılmayan ParafPara'lar 15 Ekim 2026 tarihinde geri alınacaktır."
    ) == (None, None)


def test_rejects_invalid_compact_date_range():
    assert extract_date_range("Kampanya 1-32 Ağustos 2026 tarihleri arasında geçerlidir.") == (
        None,
        None,
    )


def test_rejects_compact_date_with_long_numeric_prefix():
    assert extract_date_range("Kampanya 101-31 Ağustos 2026 tarihleri arasında geçerlidir.") == (
        None,
        None,
    )


def test_rejects_full_date_range_with_long_numeric_prefix():
    assert extract_date_range("110 Haziran 2026 - 31 Ağustos 2026") == (None, None)


def test_rejects_textual_end_date_with_long_numeric_prefix():
    assert extract_date_range("Kampanya 131 Aralık 2026 tarihine kadar geçerlidir.") == (
        None,
        None,
    )


def test_rejects_numeric_end_date_with_long_numeric_prefix():
    assert extract_date_range("Kampanya 131.12.2026 tarihine kadar geçerlidir.") == (
        None,
        None,
    )


def test_extracts_covering_range_from_multiple_campaign_periods():
    text = (
        "Kampanya 1 Temmuz 2026 saat 09.00 – 7 Temmuz 2026 saat 23.59, "
        "1 Ağustos 2026 saat 09.00 – 7 Ağustos 2026 23.59 ve "
        "1 Eylül 2026 saat 09.00 – 7 Eylül 2026 23.59 arasında geçerlidir."
    )

    assert extract_date_range(text) == (date(2026, 7, 1), date(2026, 9, 7))


def test_does_not_use_reward_expiry_as_campaign_end():
    text = "Kampanya süresizdir. Kazanılan ParafPara 15 Ekim 2026 tarihine kadar kullanılabilir."

    assert extract_date_range(text) == (None, None)


def test_parses_campaign_detail_and_removes_script():
    html = """
    <html><head><meta property="og:image" content="/image.jpg"></head><body>
      <h1>Türkçe Kampanya Başlığı</h1>
      <article><p>14 Temmuz - 31 Temmuz 2026 tarihleri arasında geçerlidir.</p>
      <p>Bu kampanya müşterilere özel uzun ve açıklayıcı bir fırsat metni sunar.</p>
      <script>izlemeKodu()</script></article>
    </body></html>
    """
    record = ExampleScraper().parse_detail("https://bank.example/kampanyalar/firsat", html)
    assert record.title == "Türkçe Kampanya Başlığı"
    assert "izlemeKodu" not in record.content
    assert record.start_date == date(2026, 7, 14)
    assert record.end_date == date(2026, 7, 31)
    assert record.image_url == "https://bank.example/image.jpg"


def test_parse_detail_prefers_campaign_content_date_over_page_chrome():
    html = """
    <html><body>
      <div class="page-chrome">Kampanya Tarihleri 1.07.2026 - 31.07.2076</div>
      <h1>Bella Maison Kampanyası</h1>
      <article><p>Kampanya 31 Temmuz 2026 tarihine kadar geçerlidir.</p></article>
    </body></html>
    """

    record = ExampleScraper().parse_detail("https://bank.example/kampanyalar/bella", html)

    assert record.start_date is None
    assert record.end_date == date(2026, 7, 31)


def test_parse_detail_falls_back_to_page_date_when_campaign_content_has_none():
    html = """
    <html><body>
      <div class="page-chrome">Kampanya Tarihleri 1.07.2026 - 31.07.2026</div>
      <h1>Tarihsiz Kampanya İçeriği</h1>
      <article><p>Bu kampanya müşterilere özel avantajlar sunar.</p></article>
    </body></html>
    """

    record = ExampleScraper().parse_detail("https://bank.example/kampanyalar/tarihsiz", html)

    assert record.start_date == date(2026, 7, 1)
    assert record.end_date == date(2026, 7, 31)
