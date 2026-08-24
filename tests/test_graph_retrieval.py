from src.knowledge import TerminologyService
from src.persistence import CampaignStore
from src.retrieval import HybridRetriever, KnowledgeGraphRetriever


def test_graph_expands_only_relational_queries_with_bounded_neighbors():
    graph = KnowledgeGraphRetriever(TerminologyService())

    relational = graph.expand(
        "Konut Finansmanı hangi teminatlarla ilişkilidir?",
        intent="application_requirements",
    )
    definition = graph.expand("Konut Finansmanı nedir?", intent="definition")

    assert relational.active is True
    assert "TRM0785" in relational.term_ids
    assert relational.term_ids[0] == "TRM0785"
    assert len(relational.term_ids) <= 12
    assert definition.active is False


def test_hybrid_retrieval_fuses_graph_neighbors_without_vector_database(tmp_path):
    store = CampaignStore(tmp_path / "empty.sqlite3")
    retriever = HybridRetriever(store, TerminologyService(), chroma_enabled=False)

    results = retriever.retrieve(
        "Konut Finansmanı hangi teminatlarla ilişkilidir?",
        filters={"source_types": ["terminology"], "intent": "application_requirements"},
        limit=20,
    )

    assert results
    assert results[0]["metadata"].get("term_id") == "TRM0785"
    assert all("knowledge-graph" in item["retrieval_method"] for item in results)
    assert retriever.last_backend == "bm25+knowledge-graph"


def test_graph_keeps_both_named_terms_for_relationship_question():
    expansion = KnowledgeGraphRetriever(TerminologyService()).expand(
        "Peşinat konut finansmanı ile nasıl ilişkilidir?",
        intent="application_requirements",
    )

    assert expansion.term_ids[:2] == ("TRM0045", "TRM1110")
    assert any(
        {edge["source_id"], edge["target_id"]} == {"TRM0045", "TRM1110"}
        for edge in expansion.edges
    )


def test_graph_ranked_documents_carry_source_relation_metadata():
    graph = KnowledgeGraphRetriever(TerminologyService())
    expansion = graph.expand(
        "Peşinat konut finansmanı ile nasıl ilişkilidir?",
        intent="application_requirements",
    )
    documents = [
        {
            "id": "term:peşinat",
            "text": "Peşinat tanımı",
            "metadata": {"term_id": "TRM1110"},
        }
    ]

    ranked = graph.rank_documents(documents, expansion)

    assert ranked[0]["metadata"]["graph_relations"]
    assert any(
        {relation["source_id"], relation["target_id"]}
        == {"TRM0045", "TRM1110"}
        for relation in ranked[0]["metadata"]["graph_relations"]
    )
