import pytest

from src.scraper.models import Campaign, normalize_source_url


def campaign(source_url: str, **overrides: object) -> Campaign:
    values: dict[str, object] = {
        "bank_slug": "ornek",
        "bank_name": "Örnek Katılım",
        "title": "Kampanya",
        "content": "Kampanya koşullarını açıklayan yeterince uzun içerik.",
        "source_url": source_url,
    }
    values.update(overrides)
    return Campaign(**values)  # type: ignore[arg-type]


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


def test_campaign_defaults_to_campaign_record_kind():
    value = campaign("https://bank.example/kampanya")

    assert value.record_kind == "campaign"
    assert value.source_item_key is None


def test_same_page_items_have_distinct_ids():
    first = campaign("https://bank.example/kampanyalar", source_item_key="restoran")
    second = campaign("https://bank.example/kampanyalar", source_item_key="okul")

    assert first.id != second.id


def test_record_kind_rejects_unknown_value():
    with pytest.raises(ValueError, match="record_kind"):
        campaign("https://bank.example/x", record_kind="news")


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


def test_normalize_source_url_preserves_accepted_raw_query_parts():
    value = (
        "https://bank.example/kampanya?flag&message=a%20b&signature=x%2By%2Fz&"
        "utm_source=email#f"
    )

    assert normalize_source_url(value) == (
        "https://bank.example/kampanya?flag&message=a%20b&signature=x%2By%2Fz"
    )


def test_campaigns_keep_distinct_invalid_percent_encoded_functional_values():
    first = campaign("https://bank.example/kampanya?campaign=%FF")
    second = campaign("https://bank.example/kampanya?campaign=%FE")

    assert first.source_url == "https://bank.example/kampanya?campaign=%FF"
    assert second.source_url == "https://bank.example/kampanya?campaign=%FE"
    assert first.id != second.id


@pytest.mark.parametrize(("field", "value"), [("summary", 1), ("category", []), ("image_url", {})])
def test_campaign_rejects_non_string_optional_text_field(field: str, value: object):
    with pytest.raises(TypeError, match=rf"{field} string veya None olmali"):
        campaign("https://bank.example/kampanya", **{field: value})


@pytest.mark.parametrize("field", ["summary", "category", "image_url"])
def test_campaign_converts_whitespace_only_optional_text_to_none(field: str):
    record = campaign("https://bank.example/kampanya", **{field: " \t "})

    assert getattr(record, field) is None
