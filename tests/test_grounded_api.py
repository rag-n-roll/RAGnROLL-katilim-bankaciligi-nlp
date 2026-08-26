from fastapi.testclient import TestClient
import json
import pytest

from src.api.main import create_app
from src.llm.decisions import PlannerDecision
from src.llm.judging import SemanticJudge
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


def test_production_assistant_wires_an_independent_semantic_judge(tmp_path):
    assistant = GroundedAssistant(
        CampaignStore(tmp_path / "judge.sqlite3"),
        chroma_enabled=False,
    )

    assert isinstance(assistant.output_gate.judge, SemanticJudge)
    assert assistant.output_gate.judge.llm is not assistant.llm


@pytest.mark.parametrize("action", (Action.REFUSE, Action.REDIRECT, Action.CLARIFY))
def test_api_ignores_false_model_terminal_action_for_trusted_definition(tmp_path, action):
    database = tmp_path / f"terminal-{action.value}.sqlite3"
    store = CampaignStore(database)
    decision = PlannerDecision(
        action=action,
        in_domain=True,
        intent="campaign_query",
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

    class DisabledWriter:
        enabled = False
        model = "disabled-writer"

        def stream_chat(self, **kwargs):
            del kwargs
            raise AssertionError("disabled writer must not run")

        def status(self):
            return {"available": False, "model": self.model}

    app = create_app(database_path=database, chroma_enabled=False)
    app.state.grounded_assistant = GroundedAssistant(
        store,
        llm=DisabledWriter(),
        decisions=Decisions(),
        chroma_enabled=False,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": "Murabaha nedir?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "ANSWER"
    assert payload["plan"]["intent"] == "definition"
    assert payload["plan"]["route"] == "HYBRID_RAG"
    assert payload["sources"][0]["term_id"] == "TRM0462"
    assert payload["conversation_state"] is None


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
    assert any(value in answer["answer"] for value in ("%1.89", "%1,89"))


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
    assert all(
        "Ana kategori:" not in source["evidence"]["text"]
        and "Entity:" not in source["evidence"]["text"]
        for source in payload["sources"]
    )


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


def test_known_bank_query_is_not_refused_when_runtime_database_is_empty(tmp_path):
    database = tmp_path / "empty.sqlite3"
    CampaignStore(database).initialize()

    with TestClient(create_app(database_path=database, chroma_enabled=False)) as client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "Kuveyt Türk kampanyalarında hangi avantajlar var?"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["slots"]["banks"] == ["kuveyt-turk"]
    assert payload["action"] == "ANSWER"
    assert payload["generation"]["fallback_reason"] == "evidence_not_found"


def test_product_search_does_not_mix_terminology_into_campaign_results(tmp_path):
    database = tmp_path / "card-search.sqlite3"
    CampaignStore(database).upsert_rows(
        [
            preprocess_record(
                Campaign(
                    id="fee-free-card",
                    bank_slug="kuveyt-turk",
                    bank_name="Kuveyt Türk",
                    title="Masrafsız kart kampanyası",
                    content="Kart işlemlerinde masrafsız kullanım avantajı.",
                    source_url="https://kuveyt-turk.example/fee-free-card",
                ).to_dict()
            ),
            preprocess_record(
                Campaign(
                    id="ordinary-card-reward",
                    bank_slug="kuveyt-turk",
                    bank_name="Kuveyt Türk",
                    title="Kart harcamasına puan kampanyası",
                    content="Kart harcamalarına 500 TL puan avantajı.",
                    source_url="https://kuveyt-turk.example/card-reward",
                ).to_dict()
            ),
        ],
        run_status="success",
    )
    with TestClient(create_app(database_path=database, chroma_enabled=False)) as client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "Masrafsız kart ve hesap seçenekleri nelerdir?"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["intent"] == "product_search"
    assert payload["sources"]
    assert [source["campaign_id"] for source in payload["sources"]] == [
        "fee-free-card"
    ]
    assert all(source.get("campaign_id") for source in payload["sources"])
    assert all(source.get("term_id") is None for source in payload["sources"])


def test_aidatsiz_card_search_excludes_free_transfer_campaigns(tmp_path):
    database = tmp_path / "annual-fee.sqlite3"
    CampaignStore(database).upsert_rows(
        [
            preprocess_record(
                Campaign(
                    id="annual-fee-free-card",
                    bank_slug="kuveyt-turk",
                    bank_name="Kuveyt Türk",
                    title="Aidatsız finans kart",
                    content="Bu kartta yıllık kart aidatı yoktur.",
                    source_url="https://kuveyt-turk.example/aidatsiz-kart",
                ).to_dict()
            ),
            preprocess_record(
                Campaign(
                    id="free-transfer-only",
                    bank_slug="kuveyt-turk",
                    bank_name="Kuveyt Türk",
                    title="Kart müşterilerine ücretsiz EFT",
                    content="Kart sahiplerine ücretsiz havale ve EFT avantajı sunulur.",
                    source_url="https://kuveyt-turk.example/ucretsiz-eft",
                ).to_dict()
            ),
        ],
        run_status="success",
    )

    with TestClient(create_app(database_path=database, chroma_enabled=False)) as client:
        payload = client.post(
            "/api/v1/chat", json={"message": "Aidatsız kart seçenekleri nelerdir?"}
        ).json()

    assert payload["plan"]["slots"]["metric"] == "FEE"
    assert [source["campaign_id"] for source in payload["sources"]] == [
        "annual-fee-free-card"
    ]


def test_participation_principles_question_uses_exact_principles_term(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "message": "Konut finansmanında katılım bankacılığı ilkeleri nelerdir?"
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["plan"]["intent"] == "definition"
    assert payload["sources"]
    assert payload["sources"][0].get("term_id") == "TRM0463"
    assert any(
        source.get("document_id") and source.get("page_start")
        for source in payload["sources"]
    )
    assert "faizsiz finans prensipleri" in payload["answer"].casefold()


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


def test_stream_executes_complete_criteria_in_initial_message(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.services.assistant.fetch_official_quotes",
        lambda **_: {
            "albaraka-turk": {
                "bank_slug": "albaraka-turk",
                "bank_name": "Albaraka Türk",
                "product_name": "İhtiyaç Finansmanı",
                "status": "available",
                "monthly_profit_rate": 4.0,
                "monthly_installment": 5_733.32,
                "total_repayment": 68_799.23,
                "annual_cost_rate": 83.87,
                "fees_total": 0.0,
                "source_url": "https://basvur.albaraka.com.tr/jet-finansman",
                "retrieved_at": "2026-08-26T18:00:00+00:00",
                "calculation_origin": "official_calculator_live",
                "message": "Canlı resmî hesaplayıcı sonucu.",
            }
        },
    )

    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "message": (
                    "50.000 TL tutarda 12 ay vadeli ihtiyaç finansmanını "
                    "masraf önceliğiyle tarafsız karşılaştır."
                )
            },
        )

    assert response.status_code == 200
    assert '"action": "ANSWER"' in response.text
    assert '"executed_tool": "financing_quote"' in response.text
    assert '"term_months": 12' in response.text
    assert '"amount": 50000.0' in response.text
    assert '"fee_priority": true' in response.text
    assert '"action": "CLARIFY"' not in response.text


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


def test_chat_stream_emits_sequential_and_non_empty_event_ids(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "Murabaha nedir?"},
        )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    events = []
    for block in response.text.strip().split("\n\n"):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        event_type = "message"
        event_id = None
        data = None
        for line in lines:
            if line.startswith("id:"):
                event_id = line[3:].strip()
            elif line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if event_type != "heartbeat" and data is not None:
            events.append({"event": event_type, "id": event_id, "data": data})

    assert len(events) >= 2
    for idx, event in enumerate(events, start=1):
        assert event["id"] is not None and len(event["id"]) > 0
        assert event["data"]["event_id"] == event["id"]
        assert event["data"]["sequence"] == idx
        assert event["id"].endswith(f":{idx}")


def test_fee_free_card_campaigns_are_unique_and_citation_free(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "Masrafsız kart kampanyaları nelerdir?"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert "[K" not in payload["answer"]
        assert "[K" not in payload["answer_display"]
        assert payload["answer"] == payload["answer_display"]
        campaign_ids = [s.get("campaign_id") for s in payload["sources"] if s.get("campaign_id")]
        assert len(campaign_ids) == len(set(campaign_ids))


def test_weather_question_refuses_without_tool_calls(tmp_path):
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


def test_suitable_vehicle_financing_requires_criteria(tmp_path):
    with _client(tmp_path) as client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "En uygun taşıt finansmanı hangisi?"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["action"] == "CLARIFY"
    assert "term_months" in payload["missing_criteria"]
    assert "amount" in payload["missing_criteria"]
    assert "fee_priority" in payload["missing_criteria"]
    assert payload["facts"] == []
    assert payload["sources"] == []
    assert "vade" in payload["answer_display"].casefold()


def test_follow_up_criteria_produces_neutral_comparison(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "src.services.assistant.fetch_official_quotes",
        lambda **_: {
            "kuveyt-turk": {
                "bank_slug": "kuveyt-turk",
                "bank_name": "Kuveyt Türk",
                "product_name": "Konut Finansmanı",
                "status": "available",
                "monthly_profit_rate": 3.19,
                "monthly_installment": 23_555.77,
                "total_repayment": 848_007.72,
                "annual_cost_rate": 45.8,
                "fees_total": 500.0,
                "source_url": (
                    "https://www.kuveytturk.com.tr/hesaplama-araclari/"
                    "finansman-hesaplama"
                ),
                "retrieved_at": "2026-08-26T18:00:00+00:00",
                "calculation_origin": "official_calculator_live",
                "message": "Canlı resmî hesaplayıcı sonucu.",
            }
        },
    )
    with _client(tmp_path) as client:
        first = client.post(
            "/api/v1/chat",
            json={"message": "En uygun konut finansmanı hangisi?"},
        )
        first_payload = first.json()
        second = client.post(
            "/api/v1/chat",
            json={
                "message": "36 ay, 500.000 TL; masraf öncelikli.",
                "conversation_state": first_payload["conversation_state"],
            },
        )
    assert second.status_code == 200
    payload = second.json()
    assert payload["action"] == "ANSWER"
    assert payload["missing_criteria"] == []
    assert payload["sources"]
    assert all(
        str(source.get("campaign_id") or "").startswith("financing:")
        for source in payload["sources"]
    )
    assert "masraf önceliğine göre tarafsız sıralandı" in payload[
        "answer_display"
    ].casefold()
    assert "500.000,00 tl" in payload["answer_display"].casefold()
    assert "[K" not in payload["answer_display"]
