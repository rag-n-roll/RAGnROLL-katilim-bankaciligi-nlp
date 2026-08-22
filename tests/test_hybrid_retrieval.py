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


@pytest.mark.parametrize("limit", (0, 21))
def test_retrieval_rejects_unbounded_limit(tmp_path, limit):
    with pytest.raises(ValueError, match="1 ile 20"):
        HybridRetriever(_store(tmp_path)).retrieve("finansman", limit=limit)
