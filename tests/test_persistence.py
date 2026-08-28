import json
import sqlite3
from decimal import Decimal

import pytest

from src.persistence import CampaignStore
from src.preprocessing.clean_text import preprocess_record
from src.scraper.models import Campaign


def record() -> dict:
    campaign = Campaign(
        bank_slug="ornek",
        bank_name="Örnek Katılım",
        title="Yeni müşterilere finansman fırsatı",
        content=(
            "Yeni müşterilere 100.000 TL'ye kadar, 3 ay vadeli masrafsız "
            "finansman fırsatı sunulur."
        ),
        source_url="https://ornek.example/kampanya/1",
    )
    return preprocess_record(campaign.to_dict())


def test_initialize_creates_required_schema_idempotently(tmp_path):
    store = CampaignStore(tmp_path / "campaigns.sqlite3")

    store.initialize()
    store.initialize()

    with sqlite3.connect(store.path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {"schema_meta", "scrape_runs", "banks", "products", "campaigns"} <= tables


def test_initialize_does_not_touch_unchanged_database(tmp_path):
    store = CampaignStore(tmp_path / "campaigns.sqlite3")
    store.initialize()
    modified_at = store.path.stat().st_mtime_ns

    store.initialize()

    assert store.path.stat().st_mtime_ns == modified_at


def test_upsert_preserves_single_campaign_and_nullable_product_link(tmp_path):
    store = CampaignStore(tmp_path / "campaigns.sqlite3")
    row = record()

    store.upsert_rows([row], run_status="success")
    store.upsert_rows([row], run_status="success")

    with sqlite3.connect(store.path) as connection:
        campaign_count = connection.execute(
            "SELECT COUNT(*) FROM campaigns"
        ).fetchone()[0]
        product_id, scraped_at = connection.execute(
            "SELECT product_id, scraped_at FROM campaigns"
        ).fetchone()
        bank_count = connection.execute("SELECT COUNT(*) FROM banks").fetchone()[0]
    assert (campaign_count, bank_count, product_id) == (1, 1, None)
    assert scraped_at == row["scraped_at"]


def test_store_uses_decimal_half_up_for_minor_units(tmp_path):
    store = CampaignStore(tmp_path / "campaigns.sqlite3")

    assert store._minor({"amount": Decimal("1.005"), "currency": "TRY"}) == (101, "TRY")


def test_initialize_rejects_unsupported_legacy_campaign_table(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE campaigns (id TEXT PRIMARY KEY)")

    with pytest.raises(ValueError, match="desteklenmeyen campaigns şeması"):
        CampaignStore(path).initialize()


def test_list_campaigns_returns_product_and_campaign_candidates(tmp_path):
    store = CampaignStore(tmp_path / "campaigns.sqlite3")
    product = record()
    product["record_kind"] = "product"
    campaign = record()
    campaign["id"] = "separate-campaign"

    store.upsert_rows([product, campaign], run_status="success")

    assert {row["record_kind"] for row in store.list_campaigns()} == {
        "product",
        "campaign",
    }


def test_import_legacy_dataset_reextracts_fields_and_exports_raw_and_processed(
    tmp_path,
):
    store = CampaignStore(tmp_path / "campaigns.sqlite3")
    legacy = record()
    legacy.pop("record_kind")
    legacy.pop("structured")
    legacy.pop("clean_text")
    legacy.pop("tokens")
    legacy.pop("token_count")

    assert store.import_dataset({"records": [legacy]}) == 1
    assert store.import_dataset({"records": [legacy]}) == 1
    raw, processed = store.export_datasets()

    assert raw["record_count"] == processed["record_count"] == 1
    assert raw["records"][0]["record_kind"] == "campaign"
    assert "structured" not in raw["records"][0]
    assert processed["records"][0]["structured"]["max_amount"] == {
        "amount": 100000.0,
        "currency": "TRY",
    }
    json.dumps(processed, ensure_ascii=False)


def test_replace_import_prunes_missing_active_records_but_keeps_lineage(tmp_path):
    store = CampaignStore(tmp_path / "replace.sqlite3")
    first = record()
    second = record()
    second["id"] = "second"
    store.upsert_rows([first, second], run_status="success")

    assert store.import_dataset({"records": [first]}, replace=True) == 1

    assert [row["id"] for row in store.list_campaigns()] == [first["id"]]
    assert store.record_versions("second")


def test_query_campaigns_filters_and_pages_in_sql(tmp_path):
    store = CampaignStore(tmp_path / "campaigns.sqlite3")
    first = record()
    second = record()
    second["id"] = "second"
    second["title"] = "Taşıt finansmanı"
    store.upsert_rows([first, second], run_status="success")

    rows, total = store.query_campaigns(
        bank_slug="ornek", search="Taşıt", limit=1, offset=0
    )

    assert total == 1
    assert rows[0]["id"] == "second"
    assert store.get_campaign("second")["title"] == "Taşıt finansmanı"
    assert store.get_campaign("missing") is None


def test_dashboard_summary_uses_database_aggregates(tmp_path):
    store = CampaignStore(tmp_path / "campaigns.sqlite3")
    store.upsert_rows([record()], run_status="success")

    summary = store.dashboard_summary()
    banks = store.bank_summary()

    assert summary["record_count"] == 1
    assert summary["campaign_count"] == 1
    assert summary["bank_count"] == 1
    assert banks[0]["campaign_count"] == 1
    assert store.latest_scrape_run()["record_count"] == 1
