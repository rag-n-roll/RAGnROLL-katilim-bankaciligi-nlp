import json
import sqlite3

from src.data_quality import (
    cluster_near_duplicates,
    content_hash,
    hamming_distance,
    simhash,
)
from src.persistence import CampaignStore
from src.preprocessing.clean_text import preprocess_record
from src.scraper.models import Campaign


def _row(identifier="one", content="100.000 TL finansman fırsatı"):
    return preprocess_record(
        Campaign(
            id=identifier,
            bank_slug="ornek",
            bank_name="Örnek Katılım",
            title="Finansman",
            content=content,
            source_url=f"https://ornek.example/{identifier}",
        ).to_dict()
    )


def test_exact_hash_is_stable_across_whitespace_and_unicode_composition():
    assert content_hash("Konut  Finansmanı") == content_hash("Konut finansmanı")
    assert content_hash("Konut Finansmanı") != content_hash("Taşıt Finansmanı")


def test_simhash_is_deterministic_and_rejects_invalid_fingerprints():
    text = "Yeni müşterilere masrafsız konut finansmanı fırsatı"
    assert simhash(text) == simhash(text)
    assert hamming_distance("geçersiz", simhash(text)) == 64


def test_near_duplicates_are_clustered_only_within_same_bank():
    first = _row("one", "Yeni müşterilere 100.000 TL konut finansmanı fırsatı")
    second = _row("two", "Yeni müşterilere 100.000 TL konut finansmanı fırsatı!")
    third = {**second, "id": "three", "bank_slug": "diger"}

    clustered = cluster_near_duplicates([first, second, third])

    assert clustered[0]["duplicate_cluster_id"] == clustered[1]["duplicate_cluster_id"]
    assert clustered[2]["duplicate_cluster_id"] != clustered[0]["duplicate_cluster_id"]


def test_store_tracks_repeated_observation_and_changed_source_versions(tmp_path):
    store = CampaignStore(tmp_path / "lineage.sqlite3")
    first = _row()
    store.upsert_rows([first], run_status="success")
    store.upsert_rows([first], run_status="success")

    versions = store.record_versions("one")
    assert len(versions) == 1
    assert versions[0]["occurrence_count"] == 2
    assert versions[0]["is_current"] is True

    changed = _row(content="150.000 TL finansman fırsatı")
    store.upsert_rows([changed], run_status="success")
    versions = store.record_versions("one")

    assert [item["source_version"] for item in versions] == [1, 2]
    assert versions[0]["is_current"] is False
    assert versions[0]["valid_to"] is not None
    assert versions[0]["superseded_by"] == "one:2"
    assert versions[1]["is_current"] is True


def test_store_recomputes_untrusted_lineage_fingerprints(tmp_path):
    store = CampaignStore(tmp_path / "untrusted-lineage.sqlite3")
    row = _row()
    row["content_hash"] = "stale"
    row["duplicate_fingerprint"] = "stale"

    store.upsert_rows([row], run_status="success")
    stored = store.get_campaign("one")

    assert stored["content_hash"] == content_hash(stored["title"], stored["content"])
    assert stored["content_hash"] != "stale"
    assert stored["duplicate_fingerprint"] == simhash(stored["content"])


def test_data_quality_summary_counts_fields_and_clusters(tmp_path):
    store = CampaignStore(tmp_path / "quality.sqlite3")
    store.upsert_rows([_row()], run_status="success")

    summary = store.data_quality_summary()

    assert summary["record_count"] == 1
    assert summary["duplicate_cluster_count"] == 0
    assert summary["field_statuses"]["EXPLICIT"] >= 1
    assert 0 <= summary["evidence_coverage"] <= 1


def test_data_quality_summary_counts_only_clusters_with_multiple_records(tmp_path):
    store = CampaignStore(tmp_path / "duplicate-quality.sqlite3")
    store.upsert_rows(
        [
            _row("one", "Yeni müşterilere 100.000 TL finansman fırsatı"),
            _row("two", "Yeni müşterilere 100.000 TL finansman fırsatı!"),
            _row("three", "Tamamen farklı bir eğitim kampanyası"),
        ],
        run_status="success",
    )

    assert store.data_quality_summary()["duplicate_cluster_count"] == 1


def test_initialize_backfills_legacy_campaign_and_product_lineage_idempotently(
    tmp_path,
):
    path = tmp_path / "legacy-lineage.sqlite3"
    timestamp = "2026-08-01T00:00:00+00:00"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE banks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                website TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE products (
                id TEXT PRIMARY KEY,
                bank_id INTEGER NOT NULL REFERENCES banks(id),
                name TEXT NOT NULL,
                product_type TEXT,
                financing_type TEXT,
                currency TEXT,
                source_url TEXT NOT NULL,
                raw_json TEXT NOT NULL,
                structured_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE campaigns (
                id TEXT PRIMARY KEY,
                bank_id INTEGER NOT NULL REFERENCES banks(id),
                product_id TEXT REFERENCES products(id),
                title TEXT NOT NULL,
                source_url TEXT NOT NULL,
                financing_type TEXT,
                profit_share_rate REAL,
                discount_rate REAL,
                reward_amount_minor INTEGER,
                max_amount_minor INTEGER,
                duration_value INTEGER,
                duration_unit TEXT,
                duration_days INTEGER,
                eligibility TEXT,
                fee_information TEXT,
                raw_json TEXT NOT NULL,
                processed_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO banks(slug, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("legacy-bank", "Legacy Bank", timestamp, timestamp),
        )
        campaigns = []
        for index in range(470):
            identifier = f"campaign-{index:03d}"
            raw = {
                "id": identifier,
                "bank_slug": "legacy-bank",
                "bank_name": "Legacy Bank",
                "title": f"Kampanya {index}",
                "content": f"Kampanya {index} için özgün içerik",
                "source_url": f"https://legacy.example/{identifier}",
                "legacy_raw_marker": index,
            }
            processed = {**raw, "legacy_processed_marker": index}
            campaigns.append(
                (
                    identifier,
                    1,
                    raw["title"],
                    raw["source_url"],
                    json.dumps(raw, ensure_ascii=False),
                    json.dumps(processed, ensure_ascii=False),
                    timestamp,
                    timestamp,
                )
            )
        connection.executemany(
            "INSERT INTO campaigns(id, bank_id, title, source_url, raw_json, "
            "processed_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            campaigns,
        )
        product_raw = {
            "id": "product-001",
            "record_kind": "product",
            "bank_slug": "legacy-bank",
            "bank_name": "Legacy Bank",
            "title": "Legacy Ürün",
            "content": "Legacy ürün içeriği",
            "source_url": "https://legacy.example/product-001",
            "legacy_product_marker": True,
        }
        connection.execute(
            "INSERT INTO products(id, bank_id, name, source_url, raw_json, "
            "structured_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "product-001",
                1,
                "Legacy Ürün",
                product_raw["source_url"],
                json.dumps(product_raw, ensure_ascii=False),
                "{}",
                timestamp,
                timestamp,
            ),
        )

    store = CampaignStore(path)
    store.initialize()
    with sqlite3.connect(path) as connection:
        version_count = connection.execute(
            "SELECT COUNT(*) FROM record_versions WHERE is_current = 1"
        ).fetchone()[0]
        missing_lineage = connection.execute(
            "SELECT COUNT(*) FROM campaigns WHERE content_hash IS NULL "
            "OR duplicate_fingerprint IS NULL OR duplicate_cluster_id IS NULL "
            "OR source_version IS NULL OR valid_from IS NULL"
        ).fetchone()[0]
        campaign_raw, campaign_processed = connection.execute(
            "SELECT raw_json, processed_json FROM campaigns WHERE id = ?",
            ("campaign-000",),
        ).fetchone()
        product_json = connection.execute(
            "SELECT raw_json FROM products WHERE id = ?", ("product-001",)
        ).fetchone()[0]
        snapshot = connection.iterdump()
        first_dump = "\n".join(snapshot)

    assert version_count == 471
    assert missing_lineage == 0
    assert json.loads(campaign_raw)["legacy_raw_marker"] == 0
    assert json.loads(campaign_processed)["legacy_processed_marker"] == 0
    assert json.loads(product_json)["legacy_product_marker"] is True
    raw_export, processed_export = store.export_datasets()
    assert raw_export["record_count"] == 471
    assert processed_export["record_count"] == 471

    store.initialize()
    with sqlite3.connect(path) as connection:
        second_dump = "\n".join(connection.iterdump())
    assert second_dump == first_dump
