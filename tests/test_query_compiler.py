import pytest

from src.query import DomainQueryCompiler
from src.query.compiler import _answer_confidence


def test_answer_confidence_weights_verified_candidate_evidence():
    score, components = _answer_confidence(typed=2, evidenced=1, candidates=2)

    assert score == 0.715
    assert components == {
        "typed_field": 1.0,
        "evidence_coverage": 0.5,
        "candidate_coverage": 0.4,
    }


def test_answer_confidence_is_zero_without_candidates():
    assert _answer_confidence(typed=3, evidenced=3, candidates=0) == (
        0.0,
        {
            "typed_field": 0.0,
            "evidence_coverage": 0.0,
            "candidate_coverage": 0.0,
        },
    )


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


def test_compiler_routes_ne_anlama_gelir_to_definition():
    plan = DomainQueryCompiler().compile("Karz-ı Hasen ne anlama gelir?")

    assert plan.route == "HYBRID_RAG"
    assert plan.intent == "definition"


def test_compiler_recognizes_profit_pool_informational_question():
    plan = DomainQueryCompiler().compile("Katılım bankacılığındaki kâr payı havuzu nasıl işler?")
    assert plan.intent == "definition"
    assert plan.route == "HYBRID_RAG"
    assert "Fon Havuzu" in plan.canonical_query
    assert any(item.get("term_id") == "TRM0452" for item in plan.terminology_rewrites)


def test_compiler_routes_selem_definition_to_grounded_rag():
    plan = DomainQueryCompiler().compile("Selem ne anlama gelir?")

    assert plan.intent == "definition"
    assert plan.route == "HYBRID_RAG"


@pytest.mark.parametrize(
    "query",
    (
        "Katılım bankacılığı nedir?",
        "Konut finansmanında katılım bankacılığı ilkeleri nelerdir?",
    ),
)
def test_compiler_recognizes_foundational_participation_banking_questions(query):
    plan = DomainQueryCompiler().compile(query)

    assert plan.intent == "definition"
    assert plan.route == "HYBRID_RAG"
    assert plan.confidence_components["trusted_domain"] is True
    assert any(
        item.get("term_id") == "TRM0463"
        for item in plan.terminology_rewrites
    )


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


def test_generic_financing_request_is_in_domain_without_inventing_a_type():
    plan = DomainQueryCompiler().compile(
        "200.000 TL masrafsız finansman almak istiyorum"
    )

    assert plan.intent == "product_search"
    assert plan.route == "HYBRID_RAG"
    assert plan.slots["product_type"] == "financing"
    assert plan.slots.get("financing_type") is None


def test_specific_financing_type_wins_over_generic_financing_term():
    plan = DomainQueryCompiler().compile("İhtiyaç finansmanı istiyorum")

    assert plan.slots["financing_type"] == "consumer"


def test_specific_card_term_wins_over_generic_credit_alias():
    plan = DomainQueryCompiler().compile("Kredi kartı seçenekleri nelerdir?")

    assert plan.slots["product_type"] == "card"
    assert plan.slots.get("financing_type") is None


def test_metric_bound_comparison_keeps_structured_sql():
    plan = DomainQueryCompiler().compile(
        "Konut finansmanında en düşük kâr payı hangisi?"
    )

    assert plan.route == "STRUCTURED_SQL"
    assert plan.slots["metric"] == "PROFIT_RATE"
    assert plan.slots["aggregation"] == "MIN"


def test_aidatsiz_product_query_is_typed_as_fee_metric():
    plan = DomainQueryCompiler().compile("Aidatsız kart seçenekleri nelerdir?")

    assert plan.intent == "product_search"
    assert plan.route == "HYBRID_RAG"
    assert plan.slots["metric"] == "FEE"


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


@pytest.mark.parametrize(
    "query",
    (
        "Bir yılda kaç ay vardır?",
        "Kampanya sayfası nedir?",
        "Bu restoranın oran kaç menüsü var?",
        "Kartal'da hava nasıl?",
    ),
)
def test_financial_substrings_do_not_make_out_of_domain_queries_structured(query):
    plan = DomainQueryCompiler().compile(query)

    assert plan.intent == "unknown"
    assert plan.route == "SAFE_REDIRECT"
    assert plan.confidence == 0.0


def test_product_matching_uses_word_boundaries_without_breaking_card_queries():
    collision = DomainQueryCompiler().compile("Kartal'da hava nasıl?")
    legitimate = DomainQueryCompiler().compile("Kart seçenekleri neler?")

    assert "product_type" not in collision.slots
    assert collision.confidence_components["product"] == {}
    assert legitimate.intent == "product_search"
    assert legitimate.route == "HYBRID_RAG"
    assert legitimate.slots["product_type"] == "card"


@pytest.mark.parametrize(
    ("query", "intent", "metric", "aggregation"),
    (
        ("Katılım bankalarını listele", "bank_list", None, None),
        (
            "Albaraka Türk kampanyalarını sayar mısın?",
            "campaign_count",
            None,
            "COUNT",
        ),
        (
            "Konut finansmanında oran kaçtır?",
            "rate_query",
            "PROFIT_RATE",
            None,
        ),
    ),
)
def test_inflected_measurable_queries_keep_structured_routes(
    query, intent, metric, aggregation
):
    plan = DomainQueryCompiler().compile(query)

    assert plan.intent == intent
    assert plan.route == "STRUCTURED_SQL"
    assert plan.slots["metric"] == metric
    assert plan.slots["aggregation"] == aggregation


def test_inflected_card_product_is_domain_evidence_without_matching_kartal():
    card = DomainQueryCompiler().compile("Kartım")
    collision = DomainQueryCompiler().compile("Kartal'da hava nasıl?")

    assert card.intent == "product_search"
    assert card.route == "HYBRID_RAG"
    assert card.slots["product_type"] == "card"
    assert card.confidence == 0.55
    assert collision.intent == "unknown"
    assert "product_type" not in collision.slots


@pytest.mark.parametrize(
    "query",
    (
        "Akşam yemeği için seçenekler neler?",
        "Bu işte ne kullanabilirim?",
        "Aşı başvurusu için hangi belge gerekir?",
    ),
)
def test_generic_discovery_and_requirement_cues_fail_closed(query):
    plan = DomainQueryCompiler().compile(query)

    assert plan.intent == "unknown"
    assert plan.route == "SAFE_REDIRECT"
    assert plan.confidence == 0.0


def test_chained_turkish_suffixes_preserve_measurable_bank_queries():
    campaign = DomainQueryCompiler().compile(
        "Albaraka Türk kampanyalarından kaç tanesi aktif?"
    )
    banks = DomainQueryCompiler().compile("Katılım bankalarının sayısı kaç?")

    assert campaign.intent == "campaign_count"
    assert campaign.route == "STRUCTURED_SQL"
    assert campaign.slots["banks"] == ["albaraka-turk"]
    assert campaign.slots["aggregation"] == "COUNT"
    assert banks.intent == "bank_list"
    assert banks.route == "STRUCTURED_SQL"


@pytest.mark.parametrize(
    "query",
    [
        "En yüksek faiz veren geleneksel banka hangisi?",
        "Bugün repo getirisi ne kadar?",
        "Halka arz hisselerini tavan bozmadan nasıl satarım?",
        "Dolara faiz veren en iyi özel banka hangisi?",
    ],
)
def test_compiler_refuses_conventional_finance_before_alias_rewrite(query):
    plan = DomainQueryCompiler().compile(query)
    assert plan.intent == "unknown"
    assert plan.route == "SAFE_REDIRECT"
    assert plan.confidence == 0.0


@pytest.mark.parametrize(
    "query",
    [
        "3.000.000 TL ev finansmanı oranları nedir?",
        "Ev finansmanı karşılaştırma tablosu çıkar.",
        "Konut finansmanında kâr payı oranları nasıl?",
    ],
)
def test_financing_discovery_cues_enter_comparison_clarification_flow(query):
    plan = DomainQueryCompiler().compile(query)
    assert plan.intent == "product_comparison"
    assert plan.route == "HYBRID_RAG"
