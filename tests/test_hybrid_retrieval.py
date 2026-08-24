import pytest

from src.knowledge import TerminologyService
from src.persistence import CampaignStore
from src.preprocessing.clean_text import preprocess_record
from src.retrieval import HybridRetriever
from src.scraper.models import Campaign


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


@pytest.mark.parametrize("limit", (0, 21))
def test_retrieval_rejects_unbounded_limit(tmp_path, limit):
    with pytest.raises(ValueError, match="1 ile 20"):
        HybridRetriever(_store(tmp_path)).retrieve("finansman", limit=limit)
