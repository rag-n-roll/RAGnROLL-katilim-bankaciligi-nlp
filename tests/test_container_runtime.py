"""Container bootstrap ve ağsız indeks smoke sözleşmeleri."""

from __future__ import annotations

import json
from math import isclose

from scripts.container_entrypoint import bootstrap_runtime
from scripts.ingest_chroma import (
    SmokeEmbeddingProvider,
    load_runtime_env,
    required_evren_exit_code,
)
from src.scraper.models import Campaign


def _seed_payload() -> dict:
    return {
        "records": [
            Campaign(
                id="seed-campaign",
                bank_slug="ornek",
                bank_name="Örnek Katılım",
                title="Container başlangıç kampanyası",
                content="100.000 TL'ye kadar 12 ay vadeli finansman kampanyası.",
                source_url="https://ornek.example/seed-campaign",
            ).to_dict()
        ]
    }


def test_bootstrap_runtime_seeds_empty_volume_and_preserves_existing_snapshot(tmp_path):
    seed = tmp_path / "bootstrap" / "campaigns.json"
    seed.parent.mkdir()
    seed.write_text(json.dumps(_seed_payload(), ensure_ascii=False), encoding="utf-8")
    runtime_root = tmp_path / "runtime"
    database = runtime_root / "ragnroll.sqlite3"

    first = bootstrap_runtime(
        database=database,
        runtime_root=runtime_root,
        seed_dataset=seed,
    )
    snapshot = runtime_root / "data" / "processed" / "campaigns.json"
    snapshot.write_text('{"operator":"owned"}', encoding="utf-8")
    second = bootstrap_runtime(
        database=database,
        runtime_root=runtime_root,
        seed_dataset=seed,
    )

    assert first["seeded_records"] == first["record_count"] == 1
    assert second["seeded_records"] == 0
    assert second["record_count"] == 1
    assert snapshot.read_text(encoding="utf-8") == '{"operator":"owned"}'
    assert (runtime_root / "data" / "raw").is_dir()
    assert (runtime_root / "outputs").is_dir()
    assert first["recovered_from_last_good"] is False
    assert (runtime_root / "last-good" / "ragnroll.sqlite3").is_file()


def test_bootstrap_runtime_recovers_corrupt_database_from_last_good(tmp_path):
    seed = tmp_path / "bootstrap" / "campaigns.json"
    seed.parent.mkdir()
    seed.write_text(json.dumps(_seed_payload(), ensure_ascii=False), encoding="utf-8")
    runtime_root = tmp_path / "runtime"
    database = runtime_root / "ragnroll.sqlite3"

    bootstrap_runtime(
        database=database,
        runtime_root=runtime_root,
        seed_dataset=seed,
    )
    database.write_bytes(b"bozuk-sqlite")

    recovered = bootstrap_runtime(
        database=database,
        runtime_root=runtime_root,
        seed_dataset=seed,
    )

    assert recovered["record_count"] == 1
    assert recovered["seeded_records"] == 0
    assert recovered["recovered_from_last_good"] is True


def test_smoke_embedding_is_deterministic_normalized_and_local():
    provider = SmokeEmbeddingProvider()

    first = provider.embed_documents(["Konut finansmanı"])[0]
    second = provider.embed_query("Konut finansmanı")

    assert provider.model_name == "ragnroll-smoke-hash-v1"
    assert first == second
    assert len(first) == 32
    assert isclose(sum(value * value for value in first), 1.0)


def test_require_evren_fails_when_remote_index_is_not_ready():
    assert required_evren_exit_code(required=True, status="ready") == 0
    assert required_evren_exit_code(required=True, status="disabled") == 2
    assert required_evren_exit_code(required=True, status="failed") == 2
    assert required_evren_exit_code(required=False, status="disabled") == 0


def test_ingestion_cli_loads_dotenv_without_overriding_process_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "RAGNROLL_TEST_FROM_DOTENV=dosyadan\n"
        "RAGNROLL_TEST_PRESERVED=dosyadan\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("RAGNROLL_TEST_FROM_DOTENV", raising=False)
    monkeypatch.setenv("RAGNROLL_TEST_PRESERVED", "surecten")

    load_runtime_env(env_file)

    assert __import__("os").environ["RAGNROLL_TEST_FROM_DOTENV"] == "dosyadan"
    assert __import__("os").environ["RAGNROLL_TEST_PRESERVED"] == "surecten"
