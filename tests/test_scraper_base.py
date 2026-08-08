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
LISTING_HTML = f'<a href="{DETAIL_URL}">Fırsat</a>'


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
