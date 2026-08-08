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


def test_html_tag_residue_in_content_is_an_error():
    campaign = valid_campaign()
    campaign.content = f"<p>{campaign.content}</p>"

    issues = validate_campaign(campaign)

    assert issues == [
        {
            "severity": "error",
            "field": "content",
            "message": "Kampanya metninde HTML etiketi kalmis",
        },
        {
            "severity": "warning",
            "field": "date_range",
            "message": "Tarih araligi eksik veya ayiklanamadi",
        },
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
