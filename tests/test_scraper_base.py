from datetime import date

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
