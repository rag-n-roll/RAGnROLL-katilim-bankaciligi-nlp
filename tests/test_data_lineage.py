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
    assert summary["duplicate_cluster_count"] == 1
    assert summary["field_statuses"]["EXPLICIT"] >= 1
    assert 0 <= summary["evidence_coverage"] <= 1
