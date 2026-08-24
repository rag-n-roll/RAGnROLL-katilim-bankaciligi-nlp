"""Container bootstrap ve ağsız indeks smoke sözleşmeleri."""

from __future__ import annotations

import json
from math import isclose

from scripts.container_entrypoint import bootstrap_runtime
from scripts.ingest_chroma import SmokeEmbeddingProvider
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


def test_smoke_embedding_is_deterministic_normalized_and_local():
    provider = SmokeEmbeddingProvider()

    first = provider.embed_documents(["Konut finansmanı"])[0]
    second = provider.embed_query("Konut finansmanı")

    assert provider.model_name == "ragnroll-smoke-hash-v1"
    assert first == second
    assert len(first) == 32
    assert isclose(sum(value * value for value in first), 1.0)
