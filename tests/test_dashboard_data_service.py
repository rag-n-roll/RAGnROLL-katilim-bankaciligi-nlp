import sqlite3
from datetime import datetime, timezone

import pytest

from src.persistence import CampaignStore, DashboardDataService
from src.scraper.models import Campaign


def make_record(
    identifier: str,
    *,
    bank_slug: str = "ornek",
    bank_name: str = "Örnek Katılım",
    title: str = "İhtiyaç finansmanı",
    content: str = "%2,05 kâr payı oranı ile 12 ay ihtiyaç finansmanı",
    record_kind: str = "campaign",
) -> dict:
    return Campaign(
        id=identifier,
        bank_slug=bank_slug,
        bank_name=bank_name,
        title=title,
        content=content,
        source_url=f"https://{bank_slug}.example/{identifier}",
        record_kind=record_kind,
        scraped_at=datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc),
    ).to_dict()


def populated_store(tmp_path) -> CampaignStore:
    store = CampaignStore(tmp_path / "dashboard.sqlite3")
    store.upsert_rows(
        [
            make_record("finance"),
            make_record(
                "card",
                bank_slug="ikinci",
                bank_name="İkinci Katılım",
                title="Kart alışveriş kampanyası",
                content="Kart alışverişine 500 TL ödül fırsatı",
            ),
            make_record("product", record_kind="product"),
        ],
        run_status="success",
    )
    return store


def test_dashboard_snapshot_is_composed_from_sql_aggregates(tmp_path, monkeypatch):
    store = populated_store(tmp_path)

    def fail_if_full_dataset_is_loaded():
        raise AssertionError("dashboard tüm veri setini belleğe almamalı")

    monkeypatch.setattr(store, "list_campaigns", fail_if_full_dataset_is_loaded)
    snapshot = DashboardDataService(store).snapshot(recent_limit=2)

    assert snapshot["summary"] == {
        "campaign_count": 2,
        "product_count": 1,
        "bank_count": 2,
        "record_count": 3,
        "average_profit_share_rate": 0.0205,
        "last_updated_at": snapshot["summary"]["last_updated_at"],
        "campaigns_by_product_type": {"card": 1, "financing": 1},
    }
    assert len(snapshot["recent_campaigns"]) == 2
    assert snapshot["freshness"]["last_scraped_at"] == "2026-08-19T10:00:00+00:00"
    assert snapshot["freshness"]["latest_scrape_run"]["status"] == "success"


def test_dashboard_distributions_have_counts_and_normalized_shares(tmp_path):
    store = populated_store(tmp_path)

    banks = store.bank_distribution()
    product_types = store.product_type_distribution()

    assert sum(item["campaign_count"] for item in banks) == 2
    assert sum(item["record_count"] for item in banks) == 3
    assert sum(item["campaign_share"] for item in banks) == pytest.approx(1.0)
    assert sum(item["share"] for item in product_types) == pytest.approx(1.0)
    financing = next(
        item for item in product_types if item["product_type"] == "financing"
    )
    assert financing["campaign_count"] == 1
    assert financing["product_count"] == 1


def test_filter_options_match_api_contract_and_count_campaigns(tmp_path):
    store = populated_store(tmp_path)

    options = store.filter_options()

    assert {item["value"]: item for item in options["banks"]} == {
        "ikinci": {"value": "ikinci", "label": "İkinci Katılım", "count": 1},
        "ornek": {"value": "ornek", "label": "Örnek Katılım", "count": 1},
    }
    assert options["product_types"] == [
        {"value": "card", "label": "card", "count": 1},
        {"value": "financing", "label": "financing", "count": 1},
    ]
    assert options["currencies"] == [
        {"value": "TRY", "label": "TRY", "count": 1}
    ]


def test_dashboard_indexes_and_recent_campaign_limit_are_guarded(tmp_path):
    store = populated_store(tmp_path)

    with sqlite3.connect(store.path) as connection:
        campaign_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(campaigns)")
        }
        product_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(products)")
        }

    assert "campaigns_freshness_idx" in campaign_indexes
    assert "products_bank_type_idx" in product_indexes
    with pytest.raises(ValueError, match="1 ile 50"):
        store.recent_campaigns(limit=51)
