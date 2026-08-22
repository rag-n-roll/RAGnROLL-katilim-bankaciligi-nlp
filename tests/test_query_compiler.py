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


def test_compiler_links_domain_definition_to_ontology():
    plan = DomainQueryCompiler().compile("Murabaha nedir?")

    assert plan.route == "HYBRID_RAG"
    assert plan.intent == "definition"
    assert any(item.get("term_id") == "TRM0462" for item in plan.terminology_rewrites)


def test_compiler_safely_redirects_complaints_and_rejects_empty_queries():
    compiler = DomainQueryCompiler()
    plan = compiler.compile("Şikâyet kaydı açmak istiyorum")

    assert plan.route == "SAFE_REDIRECT"
    assert plan.warnings
    with pytest.raises(ValueError, match="boş olamaz"):
        compiler.compile("   ")
