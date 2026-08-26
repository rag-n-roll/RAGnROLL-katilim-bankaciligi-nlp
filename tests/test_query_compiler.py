import pytest

from src.query import DomainQueryCompiler


def test_compiler_routes_exact_financing_question_to_structured_query():
    plan = DomainQueryCompiler().compile(
        "Faizsiz ev finansmanında en düşük oran hangisi?"
    )

    assert plan.route == "STRUCTURED_SQL"
    assert plan.intent == "product_comparison"
    assert plan.slots["product_type"] == "financing"
    assert plan.slots["financing_type"] == "housing"
    assert plan.slots["metric"] == "PROFIT_RATE"
    assert plan.slots["aggregation"] == "MIN"
    assert "faiz" not in plan.canonical_query.casefold()


def test_compiler_keeps_each_named_bank_in_comparison_filter():
    plan = DomainQueryCompiler().compile(
        "Kuveyt Türk ile Albaraka Türk taşıt finansmanını karşılaştır"
    )

    assert plan.slots["banks"] == ["kuveyt-turk", "albaraka-turk"]
    assert plan.filters["bank_slugs"] == plan.slots["banks"]


def test_compiler_distinguishes_bank_list_from_campaign_count():
    plan = DomainQueryCompiler().compile(
        "Türkiye'deki katılım bankalarını sayar mısın?"
    )

    assert plan.intent == "bank_list"
    assert plan.route == "STRUCTURED_SQL"


def test_compiler_links_domain_definition_to_ontology():
    plan = DomainQueryCompiler().compile("Murabaha nedir?")

    assert plan.route == "HYBRID_RAG"
    assert plan.intent == "definition"
    assert any(item.get("term_id") == "TRM0462" for item in plan.terminology_rewrites)


@pytest.mark.parametrize(
    ("query", "intent"),
    (
        ("Konut finansmanı hangi teminatları gerektirir?", "application_requirements"),
        (
            "Peşinat konut finansmanı ile nasıl ilişkilidir?",
            "relationship_query",
        ),
    ),
)
def test_compiler_routes_relational_questions_to_graph_capable_rag(query, intent):
    plan = DomainQueryCompiler().compile(query)

    assert plan.route == "HYBRID_RAG"
    assert plan.intent == intent


def test_compiler_safely_redirects_complaints_and_rejects_empty_queries():
    compiler = DomainQueryCompiler()
    plan = compiler.compile("Şikâyet kaydı açmak istiyorum")

    assert plan.route == "SAFE_REDIRECT"
    assert plan.warnings
    with pytest.raises(ValueError, match="boş olamaz"):
        compiler.compile("   ")


def test_compiler_fails_closed_for_unmatched_out_of_domain_query():
    plan = DomainQueryCompiler().compile("İstanbul'da hava durumu nasıl?")

    assert plan.intent == "unknown"
    assert plan.route == "SAFE_REDIRECT"
    assert plan.confidence == 0.0


@pytest.mark.parametrize(
    "query",
    (
        "Konut finansmanı için seçenekler neler?",
        "Bana bir finansman bul",
    ),
)
def test_product_discovery_uses_hybrid_rag(query):
    plan = DomainQueryCompiler().compile(query)

    assert plan.intent == "product_search"
    assert plan.route == "HYBRID_RAG"


def test_metric_bound_comparison_keeps_structured_sql():
    plan = DomainQueryCompiler().compile(
        "Konut finansmanında en düşük kâr payı hangisi?"
    )

    assert plan.route == "STRUCTURED_SQL"
    assert plan.slots["metric"] == "PROFIT_RATE"
    assert plan.slots["aggregation"] == "MIN"


def test_product_search_keeps_confidence_evidence_separate_from_base_score():
    plan = DomainQueryCompiler().compile("Konut finansmanı için seçenekler neler?")

    assert plan.confidence == 0.55
    assert plan.confidence_components["product"] == {
        "product_type": "financing",
        "financing_type": "housing",
    }
    assert plan.confidence_components["filters"]["active_only"] is True


@pytest.mark.parametrize(
    ("query", "financing_type"),
    (("Konut", "housing"), ("Taşıt", "vehicle")),
)
def test_configured_product_only_term_is_in_domain(query, financing_type):
    plan = DomainQueryCompiler().compile(query)

    assert plan.intent == "product_search"
    assert plan.route == "HYBRID_RAG"
    assert plan.confidence == 0.55
    assert plan.confidence_components["product"] == {
        "product_type": "financing",
        "financing_type": financing_type,
    }
    assert plan.confidence_components["filters"]["financing_type"] == financing_type
