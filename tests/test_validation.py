from src.scraper.models import Campaign
from src.scraper.validation import build_quality_report, validate_campaign


def valid_campaign() -> Campaign:
    return Campaign(
        bank_slug="ornek",
        bank_name="Örnek Katılım",
        title="Geçerli Kampanya",
        content="Müşterilerimize özel kampanyanın bütün koşullarını anlatan yeterince uzun bir içerik metnidir. Detaylar burada.",
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
