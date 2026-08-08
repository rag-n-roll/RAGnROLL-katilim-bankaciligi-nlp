import pytest

from src.scraper.models import Campaign
from src.scraper.validation import (
    build_quality_report,
    deduplicate_campaigns,
    validate_campaign,
)


def valid_campaign() -> Campaign:
    return Campaign(
        bank_slug="ornek",
        bank_name="Örnek Katılım",
        title="Geçerli Kampanya",
        content=(
            "Müşterilerimize özel kampanyanın bütün koşullarını anlatan yeterince "
            "uzun bir içerik metnidir. Detaylar burada."
        ),
        summary="Kısa özet",
        source_url="https://ornek.example/kampanya/1",
    )


def test_missing_dates_are_warning_not_error():
    issues = validate_campaign(valid_campaign())
    assert [issue["severity"] for issue in issues] == ["warning"]


def test_duplicate_url_is_reported():
    first = valid_campaign()
    second = valid_campaign()
    report = build_quality_report([first, second])
    assert report["error_count"] >= 2
    assert report["valid_record_count"] == 0
    assert report["quality_score"] == 0.0


def test_empty_bank_identity_fields_are_errors_on_their_own_fields():
    campaign = valid_campaign()
    campaign.bank_slug = ""
    campaign.bank_name = ""

    issues = validate_campaign(campaign)

    assert {(issue["field"], issue["severity"]) for issue in issues} >= {
        ("bank_slug", "error"),
        ("bank_name", "error"),
    }


@pytest.mark.parametrize(
    "residue",
    [
        "<p>metin</p>",
        "Kampanya kosullari</p>",
        "Ilk satir<br>ikinci satir",
        "Gorsel <img src='x'> ile sunuluyor",
        "<!-- residue -->",
    ],
)
def test_html_tag_residue_in_content_is_an_error(residue):
    campaign = valid_campaign()
    campaign.content = f"{residue} {campaign.content}"

    issues = validate_campaign(campaign)

    assert [issue for issue in issues if issue["severity"] == "error"] == [
        {
            "severity": "error",
            "field": "content",
            "message": "Kampanya metninde HTML etiketi kalmis",
        }
    ]


def test_content_comparisons_are_not_treated_as_html_tags():
    campaign = valid_campaign()
    campaign.content = "Kampanya kosulu 3 < 5 oldugunda da " + campaign.content

    assert validate_campaign(campaign) == [
        {
            "severity": "warning",
            "field": "date_range",
            "message": "Tarih araligi eksik veya ayiklanamadi",
        }
    ]


def test_angle_bracket_prose_is_not_treated_as_html_tags():
    campaign = valid_campaign()
    campaign.content = (
        "Iletisim icin <info@bank.example> adresine yazin, "
        "<https://bank.example/path> baglantisini acin ve <limit> degerini kontrol edin; "
        "2 < 5 karsilastirmasi da gecerlidir. "
        + campaign.content
    )

    issues = validate_campaign(campaign)

    assert not any(
        issue["field"] == "content"
        and issue["message"] == "Kampanya metninde HTML etiketi kalmis"
        for issue in issues
    )


def test_deduplicate_campaigns_removes_tracking_and_fragment_variants():
    first = valid_campaign()
    first.id = "first-record"
    duplicate = valid_campaign()
    duplicate.id = "duplicate-record"
    duplicate.bank_slug = "ORNEK"
    duplicate.source_url = "https://ornek.example/kampanya/1?utm_source=newsletter#details"
    distinct = valid_campaign()
    distinct.id = "distinct-record"
    distinct.source_url = "https://ornek.example/kampanya/2"

    unique_records, duplicate_rows = deduplicate_campaigns([first, duplicate, distinct])

    assert unique_records == [first, distinct]
    assert duplicate_rows == [
        {
            "record_id": "duplicate-record",
            "duplicate_of": "first-record",
            "bank_slug": "ORNEK",
            "source_url": "https://ornek.example/kampanya/1?utm_source=newsletter#details",
        }
    ]


def test_quality_report_exposes_removed_duplicates():
    first = valid_campaign()
    first.id = "first-record"
    duplicate = valid_campaign()
    duplicate.id = "duplicate-record"
    unique_records, duplicates = deduplicate_campaigns([first, duplicate])

    report = build_quality_report(unique_records, duplicates=duplicates)

    assert report["duplicate_count"] == 1
    assert report["duplicates"] == [
        {
            "record_id": "duplicate-record",
            "duplicate_of": "first-record",
            "bank_slug": "ornek",
            "source_url": "https://ornek.example/kampanya/1",
        }
    ]


def test_quality_report_preserves_structured_fetch_failure_metadata():
    failure = {
        "bank_slug": "ornek",
        "stage": "fetch",
        "url": "https://ornek.example/kampanya/1",
        "error_type": "HTTPError",
        "error": "Service unavailable",
        "timestamp": "2026-08-08T12:00:00+00:00",
        "http_status": 503,
    }

    report = build_quality_report([valid_campaign()], failures=[failure])

    assert report["fetch_failure_count"] == 1
    assert report["fetch_failures"] == [failure]
