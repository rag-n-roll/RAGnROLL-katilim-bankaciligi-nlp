from __future__ import annotations

from copy import deepcopy
import sqlite3

import pytest

from scripts.enrich_nlp import enrich_database
from src.nlp_runtime.advisory import RUNTIME_CONTRACT
from src.persistence import CampaignStore, StaleNlpAnalysisError
from src.scraper.models import Campaign


def _campaign(identifier: str) -> dict:
    return Campaign(
        id=identifier,
        bank_slug="ornek",
        bank_name="Örnek Katılım",
        title=f"{identifier} kart kampanyası",
        content="1.000 TL ve üzeri harcamaya 100 TL ödül sunulur.",
        source_url=f"https://ornek.example/{identifier}",
    ).to_dict()


def _analysis(candidate: dict, *, marker: str = "first") -> dict:
    return {
        "contract": RUNTIME_CONTRACT,
        "record": {
            "id": candidate["id"],
            "source_content_hash": candidate["content_hash"],
            "source_version": candidate["source_version"],
            "text_sha256": candidate["text_sha256"],
        },
        "classification": {"marker": marker},
        "entities": [],
        "suggestions": {},
        "quality": {"warnings": []},
        "provenance": {"runtime_contract": RUNTIME_CONTRACT},
    }


def _lineage_snapshot(store: CampaignStore, record_id: str) -> tuple:
    with sqlite3.connect(store.path) as connection:
        campaign = connection.execute(
            "SELECT raw_json, content_hash, source_version, updated_at "
            "FROM campaigns WHERE id = ?",
            (record_id,),
        ).fetchone()
        version = connection.execute(
            "SELECT raw_json, content_hash, source_version, occurrence_count, "
            "last_seen_at FROM record_versions WHERE record_id = ? AND is_current = 1",
            (record_id,),
        ).fetchone()
    return campaign, version


def test_candidates_are_deterministic_and_batch_apply_preserves_lineage(tmp_path):
    store = CampaignStore(tmp_path / "nlp.sqlite3")
    store.upsert_rows([_campaign("second"), _campaign("first")], run_status="success")

    candidates = store.nlp_enrichment_candidates()
    assert [candidate["id"] for candidate in candidates] == ["first", "second"]
    assert store.nlp_enrichment_candidates(max_records=1) == candidates[:1]

    candidate = candidates[0]
    before_lineage = _lineage_snapshot(store, candidate["id"])
    before_structured = deepcopy(store.get_campaign(candidate["id"])["structured"])
    analysis = _analysis(candidate)

    assert store.apply_nlp_analyses([analysis]) == 1
    assert store.apply_nlp_analyses([analysis]) == 0

    stored = store.get_campaign(candidate["id"])
    assert stored["nlp_analysis"] == analysis
    assert stored["structured"] == before_structured
    assert _lineage_snapshot(store, candidate["id"]) == before_lineage


def test_stale_sha_rolls_back_the_entire_analysis_batch(tmp_path):
    store = CampaignStore(tmp_path / "stale.sqlite3")
    store.upsert_rows([_campaign("first"), _campaign("second")], run_status="success")
    first, second = store.nlp_enrichment_candidates()
    first_analysis = _analysis(first)
    stale_analysis = _analysis(second)
    stale_analysis["record"]["source_content_hash"] = "0" * 64

    with pytest.raises(StaleNlpAnalysisError, match="güncel değil"):
        store.apply_nlp_analyses([first_analysis, stale_analysis])

    assert "nlp_analysis" not in store.get_campaign("first")
    assert "nlp_analysis" not in store.get_campaign("second")


def test_store_rejects_suggestion_for_an_authoritative_field(tmp_path):
    store = CampaignStore(tmp_path / "authority.sqlite3")
    store.upsert_rows([_campaign("campaign")], run_status="success")
    candidate = store.nlp_enrichment_candidates()[0]
    analysis = _analysis(candidate)
    evidence_text = "kart"
    start = candidate["text"].find(evidence_text)
    analysis["suggestions"] = {
        "product_type": {
            "value": "financing",
            "evidence": {
                "text": evidence_text,
                "char_start": start,
                "char_end": start + len(evidence_text),
            },
            "method": "classifier_mapping",
            "advisory": True,
        }
    }

    with pytest.raises(ValueError, match="yalnız eksik alan"):
        store.apply_nlp_analyses([analysis])

    assert "nlp_analysis" not in store.get_campaign("campaign")


def test_cli_analyzes_every_candidate_before_the_single_write(tmp_path):
    store = CampaignStore(tmp_path / "cli.sqlite3")
    store.upsert_rows([_campaign("first"), _campaign("second")], run_status="success")
    calls = []

    class FailingRuntime:
        def analyze(self, text, **kwargs):
            calls.append(kwargs["record_id"])
            if len(calls) == 2:
                raise RuntimeError("ikinci analiz başarısız")
            candidate = {
                **kwargs,
                "id": kwargs["record_id"],
                "text_sha256": next(
                    item["text_sha256"]
                    for item in store.nlp_enrichment_candidates()
                    if item["id"] == kwargs["record_id"]
                ),
            }
            return _analysis(candidate)

    with pytest.raises(RuntimeError, match="ikinci analiz"):
        enrich_database(
            store.path,
            runtime_loader=lambda _manifest: FailingRuntime(),
        )

    assert calls == ["first", "second"]
    assert "nlp_analysis" not in store.get_campaign("first")
    assert "nlp_analysis" not in store.get_campaign("second")


def test_evren_only_enrichment_does_not_load_local_runtime(tmp_path):
    store = CampaignStore(tmp_path / "evren-only.sqlite3")
    store.upsert_rows([_campaign("campaign")], run_status="success")

    class DisabledAugmenter:
        enabled = False

    def reject_runtime_load(_manifest):
        raise AssertionError("yerel runtime yüklenmemeli")

    report = enrich_database(
        store.path,
        runtime_loader=reject_runtime_load,
        augmenter=DisabledAugmenter(),
        evren_only=True,
    )

    stored = store.get_campaign("campaign")["nlp_analysis"]
    assert report["mode"] == "evren_only"
    assert stored["provenance"]["mode"] == "evren_only"
