import pytest

from src.scraper.models import Campaign, normalize_source_url


def campaign(source_url: str) -> Campaign:
    return Campaign(
        bank_slug="ornek",
        bank_name="Örnek Katılım",
        title="Kampanya",
        content="Kampanya koşullarını açıklayan yeterince uzun içerik.",
        source_url=source_url,
    )


def test_normalize_source_url_removes_tracking_and_preserves_functional_query_order():
    value = (
        " HTTPS://BANK.EXAMPLE/kampanya?utm_source=bulten&campaign=42&"
        "gclid=tracking&sort=recent&fbclid=another#kosullar "
    )

    assert normalize_source_url(value) == "https://bank.example/kampanya?campaign=42&sort=recent"


def test_campaigns_with_tracking_variants_share_source_url_and_id():
    first = campaign("https://bank.example/kampanya?campaign=42&utm_medium=email")
    second = campaign(" HTTPS://BANK.EXAMPLE/kampanya?campaign=42&gclid=tracking#kosullar ")

    assert first.source_url == second.source_url == "https://bank.example/kampanya?campaign=42"
    assert first.id == second.id


def test_campaign_rejects_non_string_required_text_field():
    with pytest.raises(TypeError, match="title string olmali"):
        Campaign(
            bank_slug="ornek",
            bank_name="Örnek Katılım",
            title=123,  # type: ignore[arg-type]
            content="Kampanya koşullarını açıklayan yeterince uzun içerik.",
            source_url="https://bank.example/kampanya",
        )


def test_normalize_source_url_rejects_non_string_value():
    with pytest.raises(TypeError, match="source_url string olmali"):
        normalize_source_url(123)  # type: ignore[arg-type]
