import pytest

from src.knowledge import TerminologyService
from src.persistence import CampaignStore
from src.preprocessing.clean_text import preprocess_record
from src.retrieval import HybridRetriever
from src.scraper.models import Campaign
from src.services.assistant import deduplicate_sources, stable_source_key


def _store(tmp_path):
    store = CampaignStore(tmp_path / "retrieval.sqlite3")
    rows = [
        preprocess_record(
            Campaign(
                id="housing",
                bank_slug="ornek",
                bank_name="Örnek Katılım",
                title="Konut finansmanı",
                content="Yeni müşterilere masrafsız konut finansmanı sunulur.",
                source_url="https://ornek.example/housing",
            ).to_dict()
        ),
        preprocess_record(
            Campaign(
                id="vehicle",
                bank_slug="diger",
                bank_name="Diğer Katılım",
                title="Taşıt finansmanı",
                content="Taşıt finansmanı kampanyası.",
                source_url="https://diger.example/vehicle",
            ).to_dict()
        ),
    ]
    store.upsert_rows(rows, run_status="success")
    return store


def test_retrieval_expands_ontology_and_ranks_murabaha_term(tmp_path):
    retriever = HybridRetriever(_store(tmp_path), TerminologyService())

    results = retriever.retrieve("Murabaha nedir?", limit=5)

    assert results
    assert any(item["metadata"].get("term_id") == "TRM0462" for item in results)
    assert all(item["retrieval_method"] == "metadata+bm25+ontology" for item in results)


def test_retrieval_applies_bank_metadata_prefilter_to_campaigns(tmp_path):
    retriever = HybridRetriever(_store(tmp_path))

    results = retriever.retrieve(
        "finansmanı", filters={"bank_slugs": ["ornek"]}, limit=20
    )
    campaign_results = [
        item for item in results if item["metadata"]["source_type"] == "campaign"
    ]

    assert campaign_results
    assert {item["metadata"]["bank_slug"] for item in campaign_results} == {"ornek"}


def test_retrieval_can_limit_definition_search_to_terminology(tmp_path):
    results = HybridRetriever(_store(tmp_path)).retrieve(
        "Murabaha nedir?", filters={"source_types": ["terminology"]}, limit=5
    )

    assert results
    assert {item["metadata"]["source_type"] for item in results} == {"terminology"}


def test_retrieval_reuses_unchanged_corpus_and_token_cache(tmp_path, monkeypatch):
    store = _store(tmp_path)
    retriever = HybridRetriever(store)
    first = retriever.retrieve("konut finansmanı", limit=5)

    def fail_if_corpus_is_loaded_again():
        raise AssertionError("değişmeyen veri seti yeniden yüklenmemeli")

    monkeypatch.setattr(store, "list_campaigns", fail_if_corpus_is_loaded_again)
    second = retriever.retrieve("konut finansmanı", limit=5)

    assert first == second
    assert retriever._token_cache


def test_retrieval_invalidates_corpus_after_database_update(tmp_path):
    store = _store(tmp_path)
    retriever = HybridRetriever(store)
    retriever.retrieve("konut finansmanı", limit=5)
    new_row = preprocess_record(
        Campaign(
            id="education",
            bank_slug="ornek",
            bank_name="Örnek Katılım",
            title="Öğrenci eğitim desteği",
            content="Öğrencilere eğitim desteği ve taksit avantajı sunulur.",
            source_url="https://ornek.example/education",
        ).to_dict()
    )

    store.upsert_rows([new_row], run_status="success")
    results = retriever.retrieve("öğrenci eğitim desteği", limit=10)

    assert any(
        item["metadata"].get("campaign_id") == "education" for item in results
    )


class StubVectorRetriever:
    embedding_model = "stub"

    def __init__(self, results):
        self.results = results
        self.calls = 0

    def retrieve(self, query, *, filters, limit):
        del query, filters, limit
        self.calls += 1
        return list(self.results)

    def ready(self):
        return bool(self.results)

    def status(self):
        return {"available": bool(self.results)}


def _vector_result(method):
    return {
        "id": "campaign:housing",
        "text": "Konut finansmanı",
        "metadata": {
            "source_type": "campaign",
            "campaign_id": "housing",
            "bank_slug": "ornek",
        },
        "score": 0.99,
        "retrieval_method": method,
    }


def test_retrieval_prefers_evren_and_does_not_call_local_vector(tmp_path):
    evren = StubVectorRetriever([_vector_result("evren")])
    local = StubVectorRetriever([_vector_result("local")])
    retriever = HybridRetriever(
        _store(tmp_path),
        evren_retriever=evren,
        vector_retriever=local,
    )

    results = retriever.retrieve("konut finansmanı", limit=5)

    assert results
    assert evren.calls == 1
    assert local.calls == 0
    assert retriever.last_backend.startswith("evren-qdrant")


def test_retrieval_falls_back_from_evren_to_local_then_bm25(tmp_path):
    evren = StubVectorRetriever([])
    local = StubVectorRetriever([_vector_result("local")])
    retriever = HybridRetriever(
        _store(tmp_path),
        evren_retriever=evren,
        vector_retriever=local,
    )

    results = retriever.retrieve("konut finansmanı", limit=5)

    assert results
    assert evren.calls == 1
    assert local.calls == 1
    assert retriever.last_backend.startswith("chroma")

    local.results = []
    fallback = retriever.retrieve("konut finansmanı", limit=5)
    assert fallback
    assert retriever.last_backend.endswith("fallback")


@pytest.mark.parametrize("limit", (0, 21))
def test_retrieval_rejects_unbounded_limit(tmp_path, limit):
    with pytest.raises(ValueError, match="1 ile 20"):
        HybridRetriever(_store(tmp_path)).retrieve("finansman", limit=limit)


def test_stable_source_identity_reads_nested_ids_and_keeps_best_score_stably():
    sources = [
        {
            "metadata": {"campaign_id": "campaign-1"},
            "title": "Başlık",
            "text": "ilk",
            "retrieval_score": 0.7,
        },
        {
            "campaign_id": "campaign-1",
            "title": "Başlık",
            "evidence": {"text": "en iyi"},
            "retrieval_score": 0.9,
        },
        {
            "campaign_id": "campaign-1",
            "title": "Başlık",
            "evidence": {"text": "eşit ama sonra"},
            "retrieval_score": 0.9,
        },
        {
            "metadata": {"term_id": "TRM0001"},
            "title": "Terim",
            "text": "tanım",
            "retrieval_score": 0.5,
        },
    ]

    assert stable_source_key(sources[0]) == "campaign_id:campaign-1"
    assert stable_source_key(sources[-1]) == "term_id:TRM0001"
    assert deduplicate_sources(sources) == [sources[1], sources[-1]]


def test_whitespace_top_level_identity_does_not_mask_nested_metadata_identity():
    first = {
        "campaign_id": "   ",
        "metadata": {"campaign_id": "campaign-1"},
        "retrieval_score": 0.4,
    }
    winner = {
        "campaign_id": "campaign-1",
        "retrieval_score": 0.8,
    }

    assert stable_source_key(first) == "campaign_id:campaign-1"
    assert deduplicate_sources([first, winner]) == [winner]


def test_dedup_collapses_same_bank_and_title_across_scraper_ids():
    older = {
        "campaign_id": "old-id",
        "bank_name": "Örnek Katılım",
        "title": "Masraflara Son!",
        "retrieval_score": 0.4,
    }
    winner = {
        "campaign_id": "new-id",
        "bank_name": "Örnek Katılım",
        "title": "  Masraflara   Son! ",
        "retrieval_score": 0.9,
    }

    assert deduplicate_sources([older, winner]) == [
        {**winner, "retrieval_score": 0.9}
    ]


def test_non_finite_or_invalid_scores_never_beat_a_finite_score():
    finite = {"campaign_id": "same", "retrieval_score": 0.5}
    invalid = {"campaign_id": "same", "retrieval_score": "not-a-number"}
    nan = {"campaign_id": "same", "retrieval_score": float("nan")}

    assert deduplicate_sources([invalid, nan, finite]) == [finite]


def test_finite_negative_score_beats_invalid_scores_without_mutating_input():
    malformed = {"campaign_id": "same", "retrieval_score": "invalid"}
    nan = {"campaign_id": "same", "retrieval_score": float("nan")}
    finite = {"campaign_id": "same", "retrieval_score": -0.5}
    sources = [malformed, nan, finite]

    result = deduplicate_sources(sources)

    assert result == [{"campaign_id": "same", "retrieval_score": -0.5}]
    assert result[0] is not finite
    assert malformed["retrieval_score"] == "invalid"
    assert nan["retrieval_score"] != nan["retrieval_score"]


@pytest.mark.parametrize("invalid_score", (float("nan"), "invalid", None))
def test_invalid_winner_score_is_emitted_as_finite_fallback(invalid_score):
    source = {"campaign_id": "only", "retrieval_score": invalid_score}

    result = deduplicate_sources([source])

    assert result == [{"campaign_id": "only", "retrieval_score": 0.0}]
    assert result[0] is not source
    assert source["retrieval_score"] is invalid_score
