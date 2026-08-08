from datetime import date
from pathlib import Path
import re

import pytest

from src.scraper.banks import (
    AlbarakaScraper,
    KuveytTurkScraper,
    TurkiyeFinansScraper,
)
from src.scraper.validation import validate_campaign


FIXTURES = Path(__file__).parent / "fixtures" / "banks"


class FixtureClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.requests: list[str] = []

    def get_text(self, url: str) -> str:
        self.requests.append(url)
        if url not in self.responses:
            raise AssertionError(f"Unexpected fixture URL: {url}")
        return self.responses[url]


@pytest.mark.parametrize(
    (
        "scraper_class",
        "fixture_prefix",
        "expected_slug",
        "expected_bank_name",
        "expected_title",
        "expected_summary",
        "expected_content",
        "expected_url",
    ),
    [
        (
            KuveytTurkScraper,
            "kuveyt_turk",
            "kuveyt-turk",
            "Kuveyt Türk Katılım Bankası A.Ş.",
            "Kuveyt Türk Örnek Kampanyası",
            "1 Ağustos - 31 Ağustos 2026 tarihleri arasında geçerlidir.",
            (
                "1 Ağustos - 31 Ağustos 2026 tarihleri arasında geçerlidir.\n"
                "Kuveyt Türk müşterilerine özel kampanya koşullarını ve "
                "katılım "
                "ayrıntılarını açıklayan yeterince uzun içerik metnidir."
            ),
            (
                "https://www.kuveytturk.com.tr/kampanyalar/kendim-icin/"
                "kart-kampanyalari/ornek-firsat"
            ),
        ),
        (
            AlbarakaScraper,
            "albaraka",
            "albaraka-turk",
            "Albaraka Türk Katılım Bankası A.Ş.",
            "Albaraka Türk Örnek Kampanyası",
            "1 Ağustos - 31 Ağustos 2026 tarihleri arasında geçerlidir.",
            (
                "1 Ağustos - 31 Ağustos 2026 tarihleri arasında geçerlidir.\n"
                "Albaraka Türk müşterilerine özel kampanya koşullarını ve "
                "katılım "
                "ayrıntılarını açıklayan yeterince uzun içerik metnidir."
            ),
            "https://www.albaraka.com.tr/tr/kampanyalar/detay/ornek-firsat",
        ),
        (
            TurkiyeFinansScraper,
            "turkiye_finans",
            "turkiye-finans",
            "Türkiye Finans Katılım Bankası A.Ş.",
            "Türkiye Finans Örnek Kampanyası",
            "1 Ağustos - 31 Ağustos 2026 tarihleri arasında geçerlidir.",
            (
                "1 Ağustos - 31 Ağustos 2026 tarihleri arasında geçerlidir.\n"
                "Türkiye Finans müşterilerine özel kampanya koşullarını ve "
                "katılım "
                "ayrıntılarını açıklayan yeterince uzun içerik metnidir."
            ),
            (
                "https://www.turkiyefinans.com.tr/tr-tr/kampanyalar/"
                "Sayfalar/ornek-firsat.aspx"
            ),
        ),
    ],
)
def test_priority_bank_fixture_pipeline(
    scraper_class,
    fixture_prefix: str,
    expected_slug: str,
    expected_bank_name: str,
    expected_title: str,
    expected_summary: str,
    expected_content: str,
    expected_url: str,
) -> None:
    listing_path = FIXTURES / f"{fixture_prefix}_listing.html"
    detail_path = FIXTURES / f"{fixture_prefix}_detail.html"
    listing = listing_path.read_text(encoding="utf-8")
    detail = detail_path.read_text(encoding="utf-8")
    client = FixtureClient(
        {
            **{url: listing for url in scraper_class.config.listing_urls},
            expected_url: detail,
        }
    )

    records, failures = scraper_class(client=client).scrape(limit=1)

    assert failures == []
    assert len(records) == 1
    assert client.requests.count(expected_url) == 1
    expected_requests = list(scraper_class.config.listing_urls)
    expected_requests.append(expected_url)
    assert client.requests == expected_requests

    record = records[0]
    assert record.bank_slug == expected_slug
    assert record.bank_name == expected_bank_name
    assert record.title == expected_title
    assert record.summary == expected_summary
    assert record.content == expected_content
    assert record.source_url == expected_url
    assert record.source_url.startswith("https://")
    assert record.start_date == date(2026, 8, 1)
    assert record.end_date == date(2026, 8, 31)
    assert not re.search(r"<[^>]+>", record.content)
    error_issues = [
        issue
        for issue in validate_campaign(record)
        if issue["severity"] == "error"
    ]
    assert not error_issues
