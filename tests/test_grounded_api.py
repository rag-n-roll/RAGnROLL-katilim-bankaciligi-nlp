from fastapi.testclient import TestClient
import json
import pytest

from src.api.main import create_app
from src.llm.decisions import PlannerDecision
from src.main import app as integrated_app
from src.persistence import CampaignStore
from src.policy import Action, ComparisonCriteria
from src.preprocessing.clean_text import preprocess_record
from src.scraper.models import Campaign
from src.services import GroundedAssistant


def _campaign(identifier, bank_slug, bank_name, rate):
    return preprocess_record(
        Campaign(
            id=identifier,
            bank_slug=bank_slug,
            bank_name=bank_name,
            title="Konut finansmanı",
            content=(
                f"500.000 TL'ye kadar 24 ay vadeli %{rate} kâr payı ile "
                "masrafsız konut finansmanı."
            ),
            source_url=f"https://{bank_slug}.example/{identifier}",
        ).to_dict()
    )


def _client(tmp_path):
    database = tmp_path / "grounded.sqlite3"
    CampaignStore(database).upsert_rows(
        [
            _campaign("low", "albaraka-turk", "Albaraka Türk", "1,89"),
            _campaign("high", "kuveyt-turk", "Kuveyt Türk", "2,09"),
        ],
        run_status="success",
    )
    return TestClient(create_app(database_path=database))


@pytest.mark.parametrize("action", (Action.REFUSE, Action.REDIRECT, Action.CLARIFY))
def test_api_preserves_validated_terminal_policy_action(tmp_path, action):
    database = tmp_path / f"terminal-{action.value}.sqlite3"
    store = CampaignStore(database)
    decision = PlannerDecision(
        action=action,
        in_domain=True,
        intent="product_comparison" if action == Action.CLARIFY else "campaign_query",
        confidence=0.8,
        reason_code=f"terminal_{action.value.casefold()}",
        normalized_query="doğrulanmış karar",
        slots={"banks": []},
        missing_criteria=("amount", "fee_priority") if action == Action.CLARIFY else (),
        safe_message=f"{action.value} güvenli mesajı.",
        criteria=ComparisonCriteria(term_months=24),
    )

    class Decisions:
        def analyze(self, *args, **kwargs):
            del args, kwargs
            return decision

    class NoLLM:
        enabled = True
        model = "must-not-run"

        def stream_chat(self, **kwargs):
            del kwargs
            raise AssertionError("terminal policy must not call LLM")

        def status(self):
            return {"available": True, "model": self.model}

    app = create_app(database_path=database, chroma_enabled=False)
    app.state.grounded_assistant = GroundedAssistant(
        store,
        llm=NoLLM(),
        decisions=Decisions(),
        chroma_enabled=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": "Kampanyaları göster"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == action.value
    assert payload["sources"] == []
    if action == Action.CLARIFY:
        assert payload["missing_criteria"] == ["amount", "fee_priority"]
        assert payload["conversation_state"]["criteria"]["term_months"] == 24
    else:
        assert payload["answer"] == decision.safe_message


def test_api_normalizes_nan_retrieval_score_for_strict_json(tmp_path):
    database = tmp_path / "nan-score.sqlite3"
    store = CampaignStore(database)
    assistant = GroundedAssistant(store, chroma_enabled=False)

    class NanRetriever:
        last_backend = "test"

        def retrieve(self, query, *, filters, limit):
            del query, filters, limit
            return [
                {
                    "text": "Doğrulanmış kampanya bilgisi.",
                    "score": float("nan"),
                    "retrieval_method": "test",
                    "metadata": {
                        "campaign_id": "nan-campaign",
                        "title": "NaN skorlu kampanya",
                    },
                }
            ]

    assistant.retriever = NanRetriever()
    app = create_app(database_path=database, chroma_enabled=False)
    app.state.grounded_assistant = assistant

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat", json={"message": "Kampanyaları göster"}
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"][0]["retrieval_score"] == 0.0
    json.dumps(payload, allow_nan=False)


def test_extraction_endpoint_returns_traceable_field_contracts(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/extract",
            json={"text": "%1,89 kâr payı ile 24 ay vadeli konut finansmanı."},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_version"] == "2026.08"
    assert len(payload["request_id"]) == 32
    field = payload["extraction"]["fields"]["profit_share_rate"]
    assert field["status"] == "EXPLICIT"
    assert field["evidence"]["text"] == "%1,89 kâr payı"


def test_compile_and_chat_use_structured_first_route_with_sources(tmp_path):
    with _client(tmp_path) as client:
        compiled = client.post(
            "/api/v1/query/compile",
            json={"query": "Konut finansmanında en düşük kâr payı hangisi?"},
        )
        chat = client.post(
            "/api/v1/chat",
            json={"message": "Konut finansmanında en düşük kâr payı hangisi?"},
        )

    assert compiled.status_code == chat.status_code == 200
    assert compiled.json()["plan"]["route"] == "STRUCTURED_SQL"
    answer = chat.json()
    assert answer["plan"]["route"] == "STRUCTURED_SQL"
    assert answer["facts"][0]["campaign_id"] == "low"
    assert answer["sources"][0]["source_url"].startswith("https://")
    assert "%1.89" in answer["answer"]


def test_campaign_count_chat_returns_sql_total_instead_of_retrieved_document_text(tmp_path):
    with _client(tmp_path) as client:
        compiled = client.post(
            "/api/v1/query/compile",
            json={"query": "Albaraka Türk kampanyalarını say"},
        )
        chat = client.post(
            "/api/v1/chat",
            json={"message": "Albaraka Türk kampanyalarını say"},
        )

    assert compiled.status_code == chat.status_code == 200
    assert compiled.json()["plan"]["intent"] == "campaign_count"
    assert compiled.json()["plan"]["route"] == "STRUCTURED_SQL"
    answer = chat.json()
    assert answer["answer"] == "Albaraka Türk için doğrulanmış 1 kampanya bulundu."
    assert answer["facts"][0]["value"] == 1
    assert answer["generation"]["fallback_reason"] == "deterministic_count"


def test_bank_list_question_returns_banks_instead_of_campaign_total(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "Türkiye'deki katılım bankalarını sayar mısın?"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["intent"] == "bank_list"
    assert payload["plan"]["route"] == "STRUCTURED_SQL"
    assert payload["facts"][0]["value"] == 2
    assert "Albaraka Türk" in payload["answer"]
    assert "Kuveyt Türk" in payload["answer"]
    assert payload["generation"]["fallback_reason"] == "deterministic_bank_list"


def test_definition_chat_uses_local_terminology_corpus(tmp_path):
    with _client(tmp_path) as client:
        response = client.post("/api/v1/chat", json={"message": "Murabaha nedir?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["route"] == "HYBRID_RAG"
    assert payload["sources"]
    assert payload["sources"][0]["term_id"] == "TRM0462"
    assert all(source.get("campaign_id") is None for source in payload["sources"])


def test_transactional_request_is_redirected_without_fake_sources(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat", json={"message": "Şikâyet kaydı açmak istiyorum"}
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["route"] == "SAFE_REDIRECT"
    assert payload["action"] == "REDIRECT"
    assert payload["facts"] == []
    assert payload["sources"] == []


def test_out_of_domain_chat_is_redirected_without_irrelevant_retrieval(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat", json={"message": "İstanbul'da hava durumu nasıl?"}
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["intent"] == "unknown"
    assert payload["plan"]["route"] == "SAFE_REDIRECT"
    assert payload["action"] == "REFUSE"
    assert payload["facts"] == []
    assert payload["sources"] == []


def test_product_discovery_chat_uses_hybrid_rag(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "Konut finansmanı için seçenekler neler?"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["intent"] == "product_search"
    assert payload["plan"]["route"] == "HYBRID_RAG"
    assert payload["sources"]


def test_subjective_comparison_is_clarified_then_resumed_from_client_state(tmp_path):
    question = (
        "Albaraka Türk ile Kuveyt Türk konut finansmanlarından hangisi daha avantajlı?"
    )
    with _client(tmp_path) as client:
        first = client.post("/api/v1/chat", json={"message": question})
        first_payload = first.json()
        state = first_payload["conversation_state"]
        second = client.post(
            "/api/v1/chat",
            json={
                "message": "24 ay, 750.000 TL; masraf öncelikli.",
                "conversation_state": state,
            },
        )

    assert first.status_code == second.status_code == 200
    assert first_payload["action"] == "CLARIFY"
    assert first_payload["missing_criteria"] == [
        "term_months",
        "amount",
        "fee_priority",
    ]
    assert first_payload["facts"] == []
    assert first_payload["sources"] == []
    assert first_payload["conversation_state"]["criteria"] == {
        "term_months": None,
        "amount": None,
        "fee_priority": None,
    }
    assert "vade" in first_payload["answer_display"].casefold()
    assert first_payload["answer"] == first_payload["answer_display"]

    resumed = second.json()
    assert resumed["action"] == "ANSWER"
    assert resumed["missing_criteria"] == []
    assert resumed["conversation_state"] is None
    assert resumed["sources"]
    assert resumed["plan"]["slots"]["term_months"] == 24
    assert resumed["plan"]["slots"]["amount"] == 750_000
    assert resumed["plan"]["slots"]["fee_priority"] is True
    assert resumed["answer"] == resumed["answer_display"]


def test_initial_comparison_retains_explicit_criteria_and_only_asks_for_fee(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "message": (
                    "Konut finansmanlarından hangisi daha avantajlı? "
                    "24 ay, 750.000 TL"
                )
            },
        )

    payload = response.json()
    assert payload["action"] == "CLARIFY"
    assert payload["missing_criteria"] == ["fee_priority"]
    assert payload["conversation_state"]["criteria"] == {
        "term_months": 24,
        "amount": 750_000,
        "fee_priority": None,
    }
    display = payload["answer_display"].casefold()
    assert "masraf" in display
    assert "vade" not in display
    assert "tutar" not in display
    assert payload["answer"] == payload["answer_display"]


def test_initial_complete_comparison_executes_even_when_fee_metric_is_detected(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "message": (
                    "Konut finansmanlarından hangisi daha avantajlı? "
                    "24 ay, 750.000 TL; masraf öncelikli"
                )
            },
        )

    payload = response.json()
    assert payload["action"] == "ANSWER"
    assert payload["missing_criteria"] == []
    assert payload["plan"]["intent"] == "product_comparison"
    assert payload["plan"]["slots"]["metric"] == "FEE"
    assert payload["plan"]["slots"]["term_months"] == 24
    assert payload["plan"]["slots"]["amount"] == 750_000
    assert payload["plan"]["slots"]["fee_priority"] is True


def test_explicit_fee_comparison_still_requires_term_and_amount(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "Konut finansmanlarını karşılaştır; masraf önemli."},
        )

    payload = response.json()
    assert payload["action"] == "CLARIFY"
    assert payload["missing_criteria"] == ["term_months", "amount"]
    assert payload["facts"] == []
    assert payload["sources"] == []
    display = payload["answer_display"].casefold()
    assert "vade" in display
    assert "tutar" in display
    assert "masraf" not in display


def test_metric_comparison_verb_requires_all_personal_criteria(tmp_path):
    with _client(tmp_path) as client:
        for message in (
            "Konut finansmanlarını masraf açısından karşılaştır.",
            "Konut finansmanlarını masraf açısından kıyasla.",
        ):
            payload = client.post("/api/v1/chat", json={"message": message}).json()
            assert payload["action"] == "CLARIFY"
            assert payload["missing_criteria"] == [
                "term_months",
                "amount",
                "fee_priority",
            ]
            display = payload["answer_display"].casefold()
            assert "vade" in display
            assert "tutar" in display
            assert "masraf" in display


def test_partial_follow_ups_round_trip_remaining_criteria_without_server_state(tmp_path):
    question = (
        "Albaraka Türk ile Kuveyt Türk konut finansmanlarından hangisi daha avantajlı?"
    )
    with _client(tmp_path) as client:
        first = client.post("/api/v1/chat", json={"message": question}).json()
        partial = client.post(
            "/api/v1/chat",
            json={
                "message": "24 aylık olsun",
                "conversation_state": first["conversation_state"],
            },
        ).json()
        completed = client.post(
            "/api/v1/chat",
            json={
                "message": "750 bin TL, masraf önemli değil",
                "conversation_state": partial["conversation_state"],
            },
        ).json()

    assert partial["action"] == "CLARIFY"
    assert partial["missing_criteria"] == ["amount", "fee_priority"]
    assert partial["conversation_state"]["criteria"] == {
        "term_months": 24,
        "amount": None,
        "fee_priority": None,
    }
    assert completed["action"] == "ANSWER"
    assert completed["plan"]["slots"]["term_months"] == 24
    assert completed["plan"]["slots"]["amount"] == 750_000
    assert completed["plan"]["slots"]["fee_priority"] is False


def test_conversation_state_rejects_injected_execution_fields(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "message": "devam",
                "conversation_state": {
                    "pending_intent": "product_comparison",
                    "pending_query": "Konut finansmanlarını karşılaştır",
                    "criteria": {
                        "term_months": 24,
                        "amount": 750_000,
                        "fee_priority": True,
                    },
                    "tool_calls": [{"name": "structured_sql", "arguments": {}}],
                },
            },
        )

    assert response.status_code == 422


def test_metrics_and_record_versions_are_exposed(tmp_path):
    with _client(tmp_path) as client:
        client.post("/api/v1/query/compile", json={"query": "Murabaha nedir?"})
        versions = client.get("/api/v1/campaigns/low/versions")
        metrics = client.get("/api/v1/metrics/summary")

    assert versions.status_code == metrics.status_code == 200
    assert versions.json()["versions"][0]["is_current"] is True
    assert metrics.json()["observability"]["event_count"] == 1
    assert metrics.json()["data_quality"]["record_count"] == 2


def test_new_api_contracts_reject_blank_and_unbounded_payloads(tmp_path):
    with _client(tmp_path) as client:
        blank = client.post("/api/v1/chat", json={"message": ""})
        too_many_sources = client.post(
            "/api/v1/chat", json={"message": "Murabaha nedir?", "source_limit": 11}
        )
        long_query = client.post(
            "/api/v1/query/compile", json={"query": "a" * 2001}
        )

    assert blank.status_code == 422
    assert too_many_sources.status_code == 422
    assert long_query.status_code == 422


def test_local_dashboard_origins_pass_cors_preflight(tmp_path):
    with _client(tmp_path) as client:
        for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
            response = client.options(
                "/api/v1/health",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin

    with TestClient(integrated_app) as client:
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
