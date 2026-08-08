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
    def __init__(
        self, listing_urls: tuple[str, ...], listing: str, detail: str
    ) -> None:
        self.listing_urls = set(listing_urls)
        self.listing = listing
        self.detail = detail
        self.requests: list[str] = []

    def get_text(self, url: str) -> str:
        self.requests.append(url)
        return self.listing if url in self.listing_urls else self.detail


@pytest.mark.parametrize(
    ("scraper_class", "fixture_prefix", "expected_url"),
    [
        (
            KuveytTurkScraper,
            "kuveyt_turk",
            (
                "https://www.kuveytturk.com.tr/kampanyalar/kendim-icin/"
                "kart-kampanyalari/ornek-firsat"
            ),
        ),
        (
            AlbarakaScraper,
            "albaraka",
            "https://www.albaraka.com.tr/tr/kampanyalar/detay/ornek-firsat",
        ),
        (
            TurkiyeFinansScraper,
            "turkiye_finans",
            (
                "https://www.turkiyefinans.com.tr/tr-tr/kampanyalar/"
                "Sayfalar/ornek-firsat.aspx"
            ),
        ),
    ],
)
def test_priority_bank_fixture_pipeline(
    scraper_class, fixture_prefix: str, expected_url: str
) -> None:
    listing_path = FIXTURES / f"{fixture_prefix}_listing.html"
    detail_path = FIXTURES / f"{fixture_prefix}_detail.html"
    listing = listing_path.read_text(encoding="utf-8")
    detail = detail_path.read_text(encoding="utf-8")
    client = FixtureClient(scraper_class.config.listing_urls, listing, detail)

    records, failures = scraper_class(client=client).scrape(limit=1)

    assert failures == []
    assert len(records) == 1
    assert client.requests.count(expected_url) == 1

    record = records[0]
    assert record.bank_slug == scraper_class.config.slug
    assert record.bank_name == scraper_class.config.bank_name
    assert record.source_url == expected_url
    assert record.source_url.startswith("https://")
    assert record.title
    assert record.summary
    assert record.content
    assert record.start_date == date(2026, 8, 1)
    assert record.end_date == date(2026, 8, 31)
    assert not re.search(r"<[^>]+>", record.content)
    error_issues = [
        issue
        for issue in validate_campaign(record)
        if issue["severity"] == "error"
    ]
    assert not error_issues
