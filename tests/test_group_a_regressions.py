import pytest

from src.query.compiler import DomainQueryCompiler


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("İstisna akdi ile kentsel dönüşüm finansmanı nasıl yapılır?", "definition"),
        ("Katılım bankalarında gecikme cezası nereye aktarılır?", "definition"),
        ("Emlak Katılım FATSİ sistemiyle altın teslimatı nasıl yapılır?", "definition"),
        (
            "Happy Card ile Total akaryakıt harcamasında ekstre indirimi ne kadar?",
            "campaign_query",
        ),
        ("Monster Notebook alışverişine 12 taksit yapan bankalar hangileridir?", "campaign_query"),
    ],
)
def test_group_a_in_domain_questions_get_informational_intents(query, intent):
    plan = DomainQueryCompiler().compile(query)

    assert plan.intent == intent
    assert plan.route == "HYBRID_RAG"


def test_group_a_gold_aliases_rewrite_to_existing_ontology_terms():
    plan = DomainQueryCompiler().compile(
        "Emlak Katılım FATSİ sistemiyle altın teslimatı nasıl yapılır?"
    )

    term_ids = {item.get("term_id") for item in plan.terminology_rewrites}
    assert {"TRM0386", "TRM1009"} <= term_ids


def test_group_a_fee_free_card_query_rewrites_existing_card_feature():
    plan = DomainQueryCompiler().compile("Aidatsız katılım kredi kartları hangileridir?")

    assert plan.intent == "product_search"
    assert plan.slots["product_type"] == "card"
    assert any(item.get("term_id") == "TRM0434" for item in plan.terminology_rewrites)


def test_campaign_cues_do_not_classify_unrelated_shopping_as_bank_content():
    plan = DomainQueryCompiler().compile("Monster Notebook satın almak istiyorum")

    assert plan.intent == "unknown"
    assert plan.route == "SAFE_REDIRECT"
