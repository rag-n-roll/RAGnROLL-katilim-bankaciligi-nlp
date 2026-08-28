from src.campaign_catalog import (
    CURATED_EXCLUDED_CAMPAIGNS,
    CURATED_INVESTMENT_CAMPAIGNS,
    filter_curated_campaigns,
)
from src.preprocessing.clean_text import preprocess_record


def _record(bank_slug: str, title: str, content: str = "") -> dict:
    return {
        "id": f"{bank_slug}-{title[:8]}",
        "bank_slug": bank_slug,
        "bank_name": bank_slug,
        "title": title,
        "content": content or title,
        "source_url": f"https://example.test/{bank_slug}",
    }


def test_curated_catalog_keeps_investments_and_removes_excluded():
    records = [
        _record(bank, title)
        for bank, title in (
            *CURATED_EXCLUDED_CAMPAIGNS,
            *CURATED_INVESTMENT_CAMPAIGNS,
        )
    ]

    kept = filter_curated_campaigns(records)

    assert len(CURATED_EXCLUDED_CAMPAIGNS) == 22
    assert len(CURATED_INVESTMENT_CAMPAIGNS) == 2
    assert {(row["bank_slug"], row["title"]) for row in kept} == set(
        CURATED_INVESTMENT_CAMPAIGNS
    )


def test_investment_overrides_are_extracted_from_specific_evidence():
    fx = _record(
        "kuveyt-turk",
        "Kuveyt Türk Mobil’den Müşterimiz Olun Özel Kur Fırsatını Kaçırmayın!",
    )
    daily_account = _record(
        "turkiye-finans",
        "Günlük Hesap’la İhtiyaç Anında Vadeni Bozma!",
    )

    assert preprocess_record(fx)["structured"]["product_type"] == "investment"
    assert (
        preprocess_record(daily_account)["structured"]["product_type"]
        == "investment"
    )
