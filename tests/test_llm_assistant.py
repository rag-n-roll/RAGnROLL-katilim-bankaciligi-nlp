import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.main import create_app
from src.llm.client import LLMSettings, LLMUnavailableError, OpenAICompatibleLLM
from src.persistence import CampaignStore
from src.preprocessing.clean_text import preprocess_record
from src.scraper.models import Campaign
from src.services import GroundedAssistant


class FakeLLM:
    enabled = True
    model = "test-gemma"

    def __init__(self, chunks=None, error=None):
        self.chunks = list(chunks or [])
        self.error = error
        self.calls = []

    def stream_chat(self, *, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        for chunk in self.chunks:
            yield chunk
        if self.error:
            raise self.error

    def status(self):
        return {"available": True, "model": self.model}


class StructuredStore:
    def __init__(self, path, rows):
        self.path = path
        self.rows = rows

    def bank_summary(self):
        return []

    def query_campaigns(self, *, limit, offset=0, **filters):
        del filters
        return self.rows[offset : offset + limit], len(self.rows)


def _structured_row(identifier, field_name, value, evidence):
    return {
        "id": identifier,
        "bank_slug": "ornek-katilim",
        "bank_name": "Örnek Katılım",
        "title": identifier,
        "content": evidence,
        "source_url": f"https://ornek.example/{identifier}",
        "structured": {
            field_name: value,
            "fields": {
                field_name: {
                    "evidence": {
                        "text": evidence,
                        "char_start": 0,
                        "char_end": len(evidence),
                    }
                }
            },
        },
    }


def _store(tmp_path):
    store = CampaignStore(tmp_path / "llm.sqlite3")
    record = Campaign(
        id="housing",
        bank_slug="ornek-katilim",
        bank_name="Örnek Katılım",
        title="Konut finansmanı",
        content="24 ay vadeli %1,89 kâr payı ile konut finansmanı.",
        source_url="https://ornek.example/konut",
    ).to_dict()
    store.upsert_rows([preprocess_record(record)], run_status="success")
    return store


def test_openai_compatible_client_parses_streaming_sse():
    body = "".join(
        (
            'data: {"choices":[{"delta":{"content":"Merhaba "}}]}\n\n',
            'data: {"choices":[{"delta":{"content":"dünya"}}]}\n\n',
            "data: [DONE]\n\n",
        )
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    client = OpenAICompatibleLLM(
        LLMSettings(model="test-model"), transport=transport
    )

    chunks = list(client.stream_chat(system_prompt="sistem", user_prompt="soru"))

    assert chunks == ["Merhaba ", "dünya"]


def test_openai_compatible_client_hides_provider_error_details():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(503, text="secret provider trace")
    )
    client = OpenAICompatibleLLM(LLMSettings(), transport=transport)

    with pytest.raises(LLMUnavailableError, match="yanıt vermedi") as error:
        list(client.stream_chat(system_prompt="sistem", user_prompt="soru"))

    assert "secret" not in str(error.value)


def test_openai_compatible_status_requires_configured_model_to_be_served():
    served = httpx.MockTransport(
        lambda request: httpx.Response(
            200, json={"data": [{"id": "configured-model"}, {"id": "other-model"}]}
        )
    )
    missing = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"id": "other-model"}]})
    )

    available = OpenAICompatibleLLM(
        LLMSettings(model="configured-model"), transport=served
    ).status()
    unavailable = OpenAICompatibleLLM(
        LLMSettings(model="configured-model"), transport=missing
    ).status()

    assert available == {
        "available": True,
        "model": "configured-model",
        "served_models": ["configured-model", "other-model"],
    }
    assert unavailable == {
        "available": False,
        "model": "configured-model",
        "served_models": ["other-model"],
        "reason": "model_not_served",
    }


def test_assistant_uses_llm_only_as_grounded_answer_writer(tmp_path):
    llm = FakeLLM(["Örnek Katılım kaydında oran %1,89'dur ", "[K1]."])
    assistant = GroundedAssistant(
        _store(tmp_path), llm=llm, chroma_enabled=False
    )

    result = assistant.answer("Konut finansmanında oran kaç?")

    assert result["generation"]["mode"] == "llm"
    assert result["answer"].endswith("[K1].")
    assert result["facts"][0]["campaign_id"] == "housing"
    assert "KANIT PAKETİ" in llm.calls[0][1]
    assert "kanıta dayalı" in llm.calls[0][0]


def test_campaign_count_uses_exact_structured_total_without_raw_rag_fallback(tmp_path):
    llm = FakeLLM(["Bu yanıt kullanılmamalı."])
    store = CampaignStore(tmp_path / "counts.sqlite3")
    store.upsert_rows(
        [
            Campaign(
                id=f"campaign-{index}",
                bank_slug="albaraka-turk",
                bank_name="Albaraka Türk",
                title=f"Kampanya {index}",
                content="Doğrulanmış kampanya içeriği.",
                source_url=f"https://albaraka.example/{index}",
            ).to_dict()
            for index in range(3)
        ],
        run_status="success",
    )
    assistant = GroundedAssistant(store, llm=llm, chroma_enabled=False)

    result = assistant.answer("Albaraka Türk kampanyalarını say")

    assert result["plan"]["route"] == "STRUCTURED_SQL"
    assert result["plan"]["intent"] == "campaign_count"
    assert result["answer"] == "Albaraka Türk için doğrulanmış 3 kampanya bulundu."
    assert result["facts"] == [
        {
            "metric": "CAMPAIGN_COUNT",
            "value": 3,
            "bank_slugs": ["albaraka-turk"],
        }
    ]
    assert result["generation"]["fallback_reason"] == "deterministic_count"
    assert len(result["sources"]) == 3
    assert llm.calls == []


def test_llm_slot_merge_replaces_deterministic_confidence_evidence(tmp_path):
    assistant = GroundedAssistant(_store(tmp_path), chroma_enabled=False)
    deterministic = assistant.compiler.compile("Konut finansmanı seçenekleri")

    selected = assistant._merge_llm_plan(
        deterministic,
        {
            "intent": "product_search",
            "route": "HYBRID_RAG",
            "confidence": 0.91,
            "normalized_query": "Taşıt finansmanı seçenekleri",
            "slots": {
                "banks": [],
                "metric": None,
                "aggregation": None,
                "product_type": "financing",
                "financing_type": "vehicle",
            },
        },
    )

    assert selected.slots["financing_type"] == "vehicle"
    assert selected.filters["financing_type"] == "vehicle"
    assert selected.confidence == 0.91
    assert selected.confidence_components["source"] == "llm_plan"
    assert selected.confidence_components["product"] == {
        "product_type": "financing",
        "financing_type": "vehicle",
    }
    assert selected.confidence_components["filters"] == selected.filters
    assert selected.confidence_components["terminology"] == []
    assert selected.terminology_rewrites == []


@pytest.mark.parametrize(
    "query",
    (
        "Konut finansmanında oran seçenekleri nelerdir?",
        "Kart seçeneklerinde ücret nedir?",
    ),
)
def test_legacy_structured_suggestion_cannot_bypass_compiler_route_policy(
    tmp_path, query
):
    class LegacyStructuredDecision:
        @staticmethod
        def is_safe(message):
            del message
            return True

        @staticmethod
        def route(message):
            del message
            return "STRUCTURED_SQL"

    assistant = GroundedAssistant(
        _store(tmp_path),
        decisions=LegacyStructuredDecision(),
        chroma_enabled=False,
    )

    plan = assistant.compile(query)

    assert plan.route == "HYBRID_RAG"


def test_structured_extrema_scans_beyond_first_hundred_rows(tmp_path):
    records = [
        Campaign(
            id=f"rate-{index:03d}",
            bank_slug="ornek-katilim",
            bank_name="Örnek Katılım",
            title=f"Standart oran {index:03d}",
            content="%1,00 kâr payı ile finansman.",
            source_url=f"https://ornek.example/rate-{index:03d}",
        ).to_dict()
        for index in range(100)
    ]
    records.append(
        Campaign(
            id="zzz-global-max",
            bank_slug="ornek-katilim",
            bank_name="Örnek Katılım",
            title="Global maksimum",
            content="%99,00 kâr payı ile finansman.",
            source_url="https://ornek.example/zzz-global-max",
        ).to_dict()
    )
    store = CampaignStore(tmp_path / "structured.sqlite3")
    store.upsert_rows(records, run_status="success")
    assistant = GroundedAssistant(store, llm=FakeLLM(), chroma_enabled=False)

    result = assistant._grounded_result(
        "En yüksek kâr payı oranı hangisi?", limit=5
    )

    assert result["facts"][0]["campaign_id"] == "zzz-global-max"


def test_reward_extrema_compare_each_currency_without_implicit_fx(tmp_path):
    rows = [
        _structured_row(
            "try-low", "reward_amount", {"amount": 100, "currency": "TRY"}, "100 TL ödül"
        ),
        _structured_row(
            "try-high", "reward_amount", {"amount": 1000, "currency": "TRY"}, "1.000 TL ödül"
        ),
        _structured_row(
            "usd-only", "reward_amount", {"amount": 500, "currency": "USD"}, "500 USD ödül"
        ),
    ]
    assistant = GroundedAssistant(
        StructuredStore(tmp_path / "reward.sqlite3", rows),
        llm=FakeLLM(),
        chroma_enabled=False,
    )

    result = assistant._grounded_result("En yüksek ödül hangisi?", limit=5)

    assert {fact["campaign_id"] for fact in result["facts"]} == {
        "try-high",
        "usd-only",
    }
    assert any("kur dönüşümü" in warning for warning in result["warnings"])


def test_fee_minimum_prefers_explicit_fee_free_and_ignores_unknown(tmp_path):
    rows = [
        _structured_row("paid", "fee_information", "100 TL", "100 TL ücret"),
        _structured_row("free", "fee_information", "masrafsız", "masrafsız"),
        _structured_row(
            "unknown", "fee_information", "ücret belirtilmedi", "ücret belirtilmedi"
        ),
    ]
    assistant = GroundedAssistant(
        StructuredStore(tmp_path / "fee.sqlite3", rows),
        llm=FakeLLM(),
        chroma_enabled=False,
    )

    result = assistant._grounded_result("En düşük ücret hangisi?", limit=5)

    assert [fact["campaign_id"] for fact in result["facts"]] == ["free"]
    assert any("karşılaştırmaya alınmadı" in warning for warning in result["warnings"])


def test_extrema_return_all_ties_in_stable_identifier_order(tmp_path):
    rows = [
        _structured_row(
            "tie-b", "reward_amount", {"amount": 1000, "currency": "TRY"}, "1.000 TL ödül"
        ),
        _structured_row(
            "lower", "reward_amount", {"amount": 900, "currency": "TRY"}, "900 TL ödül"
        ),
        _structured_row(
            "tie-a", "reward_amount", {"amount": 1000, "currency": "TRY"}, "1.000 TL ödül"
        ),
    ]
    assistant = GroundedAssistant(
        StructuredStore(tmp_path / "ties.sqlite3", rows),
        llm=FakeLLM(),
        chroma_enabled=False,
    )

    result = assistant._grounded_result("En yüksek ödül hangisi?", limit=5)

    assert [fact["campaign_id"] for fact in result["facts"]] == ["tie-a", "tie-b"]


@pytest.mark.parametrize(
    "llm",
    (
        FakeLLM(["Kaynak etiketi olmayan bir cevap."]),
        FakeLLM(["Yarım cevap"], LLMUnavailableError("bağlantı kesildi")),
        FakeLLM([]),
    ),
)
def test_assistant_replaces_invalid_or_interrupted_generation_with_fallback(
    tmp_path, llm
):
    result = GroundedAssistant(
        _store(tmp_path), llm=llm, chroma_enabled=False
    ).answer("Konut finansmanında oran kaç?")

    assert result["generation"]["mode"] == "fallback"
    assert "%1.89" in result["answer"]
    assert "Yarım cevap" not in result["answer"]


@pytest.mark.parametrize(
    "unsupported",
    (
        "Örnek Katılım oranı %9,99'dur [K1].",
        "Örnek Katılım finansmanı masrafsızdır [K1].",
    ),
)
def test_assistant_buffers_and_rejects_unsupported_financial_claims(
    tmp_path, unsupported
):
    assistant = GroundedAssistant(
        _store(tmp_path), llm=FakeLLM([unsupported[:18], unsupported[18:]]), chroma_enabled=False
    )

    events = list(assistant.stream_answer("Konut finansmanında oran kaç?"))
    delivered = "".join(
        str(item["data"].get("text") or "")
        for item in events
        if item["event"] in {"delta", "replace"}
    )

    assert unsupported not in delivered
    assert "%1.89" in delivered
    assert events[-1]["data"]["fallback_reason"] == "llm_output_rejected"
    assert all(item["event"] != "replace" for item in events)


def test_numeric_claim_must_be_supported_by_the_cited_source():
    sources = [
        {"evidence": {"text": "100 TL ödül"}},
        {"evidence": {"text": "200 TL ödül"}},
    ]

    assert GroundedAssistant._valid_llm_answer(
        "Ödül 200 TL'dir [K2].", sources=sources
    )
    assert not GroundedAssistant._valid_llm_answer(
        "Ödül 200 TL'dir [K1].", sources=sources
    )


def test_ordered_list_markers_are_not_treated_as_financial_claims():
    sources = [
        {"evidence": {"text": "2.000 TL iade sunulur"}},
        {"evidence": {"text": "13.500 TL hediye sunulur"}},
    ]

    assert GroundedAssistant._valid_llm_answer(
        "1. 2.000 TL iade sunulur [K1].\n2. 13.500 TL hediye sunulur [K2].",
        sources=sources,
    )


def test_bullet_citation_covers_its_sentences_and_unsupported_bullet_is_removed():
    sources = [
        {
            "title": "%10 indirim kampanyası",
            "evidence": {"text": "Yurt dışı turlarında indirim sunulur."},
        },
        {"title": "Diğer kampanya", "evidence": {"text": "500 TL iade"}},
    ]
    answer = (
        "Avantajlar:\n"
        "* Tur fırsatı sunulur. İndirim oranı %10'dur [K1].\n"
        "* Türetilmiş 1.000 TL ödül sunulur [K2]."
    )

    assert not GroundedAssistant._valid_llm_answer(answer, sources=sources)
    assert GroundedAssistant._sanitize_llm_answer(answer, sources=sources) == (
        "Avantajlar:\n"
        "* Tur fırsatı sunulur. İndirim oranı %10'dur [K1]."
    )


def test_safe_redirect_never_calls_language_model(tmp_path):
    llm = FakeLLM(["Çağrılmamalı [K1]"])
    result = GroundedAssistant(
        _store(tmp_path), llm=llm, chroma_enabled=False
    ).answer("Şikâyet kaydı açmak istiyorum")

    assert result["generation"]["fallback_reason"] == "safe_redirect"
    assert not llm.calls
    assert result["sources"] == []


def test_definition_keeps_only_exact_terminology_source(tmp_path):
    llm = FakeLLM(["Murabaha vadeli bir satış akdidir [K1]."])
    assistant = GroundedAssistant(
        _store(tmp_path), llm=llm, chroma_enabled=False
    )

    class DefinitionRetriever:
        last_backend = "chroma+bm25"

        def retrieve(self, query, *, filters, limit):
            del query, filters, limit
            return [
                {
                    "text": "Murabaha, maliyet üzerine kâr eklenen vadeli satış akdidir.",
                    "score": 1.0,
                    "retrieval_method": "chroma+semantic+ontology",
                    "metadata": {"term_id": "TRM0462", "title": "Murabaha"},
                },
                {
                    "text": "Muhabir banka uluslararası işlemlere aracılık eder.",
                    "score": 0.2,
                    "retrieval_method": "bm25+ontology",
                    "metadata": {"term_id": "TRM0184", "title": "Muhabir Banka"},
                },
            ]

    assistant.retriever = DefinitionRetriever()

    result = assistant.answer("Murabaha nedir?")

    assert [source["term_id"] for source in result["sources"]] == ["TRM0462"]
    assert result["generation"]["mode"] == "llm"
    grounded = assistant._grounded_result("Murabaha nedir?", limit=5)
    assert grounded["answer"].endswith("satış akdidir.")
    assert "Muhabir Banka" not in grounded["answer"]


def test_chunk_evidence_keeps_bounded_source_offsets(tmp_path):
    assistant = GroundedAssistant(
        _store(tmp_path), llm=FakeLLM(), chroma_enabled=False
    )

    class ChunkRetriever:
        last_backend = "chroma+bm25"

        def retrieve(self, query, *, filters, limit):
            del query, filters, limit
            return [
                {
                    "text": (
                        "Başlık: Uzun kampanya\nBanka: Örnek Katılım\n"
                        "İçerik: İkinci bölümde öğrencilere 750 TL ödül sunulur."
                    ),
                    "score": 1.0,
                    "retrieval_method": "chroma+semantic+bm25+ontology",
                    "metadata": {
                        "campaign_id": "long",
                        "title": "Uzun kampanya",
                        "section": "content",
                        "char_start": 420,
                        "char_end": 472,
                    },
                }
            ]

    assistant.retriever = ChunkRetriever()
    result = assistant._grounded_result("Öğrenci ödülü nedir?", limit=5)
    evidence = result["sources"][0]["evidence"]

    assert evidence["text"].startswith("İkinci bölümde")
    assert evidence["char_start"] == 420
    assert evidence["char_end"] <= 472


def test_campaign_fallback_never_exposes_raw_index_document_format(tmp_path):
    assistant = GroundedAssistant(
        _store(tmp_path), llm=FakeLLM(), chroma_enabled=False
    )

    class StructuredFieldRetriever:
        last_backend = "bm25"

        def retrieve(self, query, *, filters, limit):
            del query, filters, limit
            return [
                {
                    "text": (
                        "Başlık: Öğrenci Kampanyası Banka: Örnek Katılım "
                        "Yapılandırılmış alanlar: campaign_benefit: Ücretsiz internet"
                    ),
                    "score": 1.0,
                    "retrieval_method": "bm25",
                    "metadata": {
                        "campaign_id": "student",
                        "bank_name": "Örnek Katılım",
                        "title": "Öğrenci Kampanyası",
                        "section": "structured_fields",
                    },
                }
            ]

    assistant.retriever = StructuredFieldRetriever()
    result = assistant.answer("Öğrencilere hangi fırsatlar var?")

    assert result["answer"] == (
        "İlgili doğrulanmış kampanya kayıtları:\n"
        "- Örnek Katılım — Öğrenci Kampanyası [K1]"
    )
    assert "Yapılandırılmış alanlar" not in result["answer"]
    assert "campaign_benefit" not in result["answer"]


def test_graph_relationship_is_preserved_in_deterministic_fallback(tmp_path):
    assistant = GroundedAssistant(
        _store(tmp_path), llm=FakeLLM(), chroma_enabled=False
    )

    class GraphRetriever:
        last_backend = "bm25+knowledge-graph"

        def retrieve(self, query, *, filters, limit):
            del query, filters, limit
            return [
                {
                    "text": "Peşinat: Satış bedelinin önceden ödenen kısmı.",
                    "score": 1.0,
                    "retrieval_method": "metadata+bm25+ontology+knowledge-graph",
                    "metadata": {
                        "term_id": "TRM1110",
                        "title": "Peşinat",
                        "graph_relations": [
                            {
                                "source_id": "TRM1110",
                                "source_term": "Peşinat",
                                "relation": "RELATED_TO",
                                "target_id": "TRM0045",
                                "target_term": "Konut Finansmanı",
                            }
                        ],
                    },
                }
            ]

    assistant.retriever = GraphRetriever()
    result = assistant._grounded_result(
        "Peşinat konut finansmanı ile nasıl ilişkilidir?", limit=5
    )

    assert result["answer"].startswith(
        "Peşinat, Konut Finansmanı ile ilişkilidir."
    )
    assert result["sources"][0]["relations"]


def test_llm_answer_gets_bounded_turkish_orthography_polish(tmp_path):
    llm = FakeLLM(["Konut finansmanı bir satış akdıdır [K1]."])

    result = GroundedAssistant(
        _store(tmp_path), llm=llm, chroma_enabled=False
    ).answer("Konut finansmanında oran kaç?")

    assert "satış akdidir" in result["answer"]
    assert "akdıdır" not in result["answer"]
    assert result["generation"]["mode"] == "llm"


def test_llm_answer_markdown_is_normalized_for_plain_text_chat_ui():
    answer = "*   **Avantaj:** %10 indirim [K1].\n\n*Not: Koşulları doğrulayın.*"

    assert GroundedAssistant._polish_llm_answer(answer) == (
        "• Avantaj: %10 indirim [K1].\n\nNot: Koşulları doğrulayın."
    )


def test_streaming_endpoint_emits_metadata_validated_answer_and_completion(tmp_path):
    store = _store(tmp_path)
    app = create_app(database_path=store.path, chroma_enabled=False)
    app.state.grounded_assistant = GroundedAssistant(
        store,
        llm=FakeLLM(["Profesyonel ", "cevap [K1]."]),
        recorder=app.state.event_recorder,
        chroma_enabled=False,
    )

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"message": "Konut finansmanında oran kaç?"},
        ) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: meta" in body
    assert "event: delta" in body
    assert "event: done" in body
    assert "Profesyonel" in body
    assert '"mode": "llm"' in body


def test_streaming_endpoint_never_emits_rejected_chunks(tmp_path):
    store = _store(tmp_path)
    app = create_app(database_path=store.path, chroma_enabled=False)
    app.state.grounded_assistant = GroundedAssistant(
        store,
        llm=FakeLLM(["Uydurma oran %9,99 ", "olarak açıklandı [K1]."]),
        recorder=app.state.event_recorder,
        chroma_enabled=False,
    )

    with TestClient(app) as client:
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"message": "Konut finansmanında oran kaç?"},
        ) as response:
            body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "%9,99" not in body
    assert "%1.89" in body
    assert '"fallback_reason": "llm_output_rejected"' in body


def test_llm_status_contract_uses_configured_assistant(tmp_path):
    store = _store(tmp_path)
    app = create_app(database_path=store.path, chroma_enabled=False)
    app.state.grounded_assistant = GroundedAssistant(
        store, llm=FakeLLM(), chroma_enabled=False
    )

    with TestClient(app) as client:
        payload = client.get("/api/v1/llm/status").json()

    assert payload == {"available": True, "model": "test-gemma"}
