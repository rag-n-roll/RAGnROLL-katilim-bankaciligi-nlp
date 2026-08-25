import json
from time import sleep

import httpx
import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from src.api.main import create_app
from src.llm.client import (
    LLMSettings,
    LLMUnavailableError,
    OpenAICompatibleLLM,
    ProviderLLMChain,
)
from src.llm.decisions import EvrenDecisionService
from src.persistence import CampaignStore
from src.nlp_runtime.evren import EvrenAdvisoryAugmenter
from src.preprocessing.clean_text import preprocess_record
from src.prompt_optimization import IntentTraceRecorder, load_reviewed_intent_examples
from src.providers import CircuitBreaker, CircuitOpenError
from src.retrieval.evren import (
    EvrenEmbeddingError,
    EvrenEmbeddingProvider,
    EvrenEmbeddingSettings,
)
from src.retrieval.qdrant import (
    EvrenQdrantIndexer,
    EvrenQdrantRetriever,
    EvrenQdrantSettings,
)
from src.scraper.models import Campaign
from src.services import GroundedAssistant


def test_circuit_breaker_opens_and_allows_one_half_open_probe():
    now = [0.0]
    circuit = CircuitBreaker(
        failure_threshold=3,
        open_seconds=10,
        clock=lambda: now[0],
    )

    circuit.failure()
    circuit.failure()
    circuit.failure()

    with pytest.raises(CircuitOpenError):
        circuit.acquire()
    now[0] = 11.0
    circuit.acquire()
    with pytest.raises(CircuitOpenError):
        circuit.acquire()
    circuit.success()

    assert circuit.snapshot().state == "closed"


def _sse(content: str, *, model: str, finish_reason: str = "stop") -> str:
    return "".join(
        (
            "data: "
            + json.dumps(
                {
                    "model": model,
                    "choices": [
                        {"delta": {"content": content}, "finish_reason": None}
                    ],
                },
                ensure_ascii=False,
            )
            + "\n\n",
            "data: "
            + json.dumps(
                {
                    "model": model,
                    "choices": [
                        {"delta": {}, "finish_reason": finish_reason}
                    ],
                }
            )
            + "\n\n",
            "data: [DONE]\n\n",
        )
    )


def test_evren_llm_validates_alias_and_disables_thinking():
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "llm-fast"}]})
        return httpx.Response(200, text=_sse("Kaynaklı cevap [K1].", model="llm-fast"))

    client = OpenAICompatibleLLM(
        LLMSettings(
            base_url="https://evren.example/v1",
            api_key="secret",
            model="llm-fast",
            provider="evren",
            strict_model=True,
        ),
        transport=httpx.MockTransport(handler),
    )

    chunks = list(client.stream_chat(system_prompt="sistem", user_prompt="soru"))
    payload = json.loads(requests[-1].content)

    assert chunks == ["Kaynaklı cevap [K1]."]
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert client.generation_metadata()["served_model"] == "llm-fast"


def test_evren_llm_rejects_silent_model_substitution():
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "llm-large"}]})
        raise AssertionError("Servis listesinde olmayan model çağrılmamalı")

    client = OpenAICompatibleLLM(
        LLMSettings(
            base_url="https://evren.example/v1",
            api_key="secret",
            model="llm-fast",
            provider="evren",
            strict_model=True,
        ),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMUnavailableError):
        list(client.stream_chat(system_prompt="sistem", user_prompt="soru"))


def test_provider_chain_uses_local_after_evren_transport_failure():
    evren = OpenAICompatibleLLM(
        LLMSettings(
            base_url="https://evren.example/v1",
            api_key="secret",
            model="llm-fast",
            provider="evren",
            strict_model=False,
        ),
        transport=httpx.MockTransport(lambda request: httpx.Response(503)),
    )
    local = OpenAICompatibleLLM(
        LLMSettings(model="local-model", provider="local"),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, text=_sse("Yerel cevap [K1].", model="local-model")
            )
        ),
    )
    chain = ProviderLLMChain([evren, local])

    chunks = list(chain.stream_chat(system_prompt="sistem", user_prompt="soru"))
    metadata = chain.generation_metadata()

    assert chunks == ["Yerel cevap [K1]."]
    assert metadata["provider"] == "local"
    assert [item["outcome"] for item in metadata["fallback_chain"]] == [
        "unavailable",
        "accepted",
    ]


class StaticProvider:
    enabled = True

    def __init__(self, provider, model, answer):
        self.provider = provider
        self.model = model
        self.answer = answer

    def stream_chat(self, *, system_prompt, user_prompt):
        del system_prompt, user_prompt
        yield self.answer

    def generation_metadata(self):
        return {
            "provider": self.provider,
            "requested_model": self.model,
            "served_model": self.model,
            "finish_reason": "stop",
            "circuit_state": "closed",
        }

    def status(self):
        return {"available": True, "model": self.model, "provider": self.provider}


class SequencedProvider(StaticProvider):
    def __init__(self, *answers):
        super().__init__("local", "planner-writer", "")
        self.answers = list(answers)
        self.calls = []

    def stream_chat(self, *, system_prompt, user_prompt):
        self.calls.append((system_prompt, user_prompt))
        yield self.answers.pop(0)


def test_assistant_rejects_evren_claim_and_accepts_local_candidate(tmp_path):
    store = CampaignStore(tmp_path / "assistant.sqlite3")
    row = Campaign(
        id="housing",
        bank_slug="ornek",
        bank_name="Örnek Katılım",
        title="Konut finansmanı",
        content="24 ay vadeli %1,89 kâr payı ile konut finansmanı.",
        source_url="https://ornek.example/housing",
    ).to_dict()
    store.upsert_rows([preprocess_record(row)], run_status="success")
    chain = ProviderLLMChain(
        [
            StaticProvider("evren", "llm-fast", "Oran %9,99'dur [K1]."),
            StaticProvider("local", "local-model", "Oran %1,89'dur [K1]."),
        ]
    )

    result = GroundedAssistant(
        store, llm=chain, chroma_enabled=False
    ).answer("Konut finansmanında oran kaç?")

    assert result["answer"] == "Oran %1,89'dur [K1]."
    assert result["generation"]["provider"] == "local"
    assert [
        item["outcome"] for item in result["generation"]["fallback_chain"]
    ] == ["output_rejected", "accepted"]


def test_router_and_guard_accept_only_typed_allowlisted_json():
    decisions = EvrenDecisionService(
        router=StaticProvider("evren", "router", '{"route":"HYBRID_RAG"}'),
        guard=StaticProvider("evren", "guard", '{"safe":true}'),
    )

    assert decisions.route("Murabaha nedir?") == "HYBRID_RAG"
    assert decisions.is_safe("Murabaha nedir?") is True

    invalid = EvrenDecisionService(
        router=StaticProvider("evren", "router", '{"route":"SHELL"}'),
        guard=StaticProvider("evren", "guard", '{"safe":"yes"}'),
    )
    assert invalid.route("komut") is None
    assert invalid.is_safe("komut") is None


def test_structured_intent_call_drives_count_and_writes_reviewable_dspy_trace(
    tmp_path,
):
    plan = json.dumps(
        {
            "safe": True,
            "intent": "campaign_count",
            "route": "STRUCTURED_SQL",
            "confidence": 0.97,
            "normalized_query": "Albaraka Türk kampanya toplamı",
            "slots": {
                "banks": ["albaraka-turk"],
                "metric": None,
                "aggregation": "COUNT",
                "product_type": None,
                "financing_type": None,
            },
        },
        ensure_ascii=False,
    )
    llm = SequencedProvider(plan)
    store = CampaignStore(tmp_path / "intent-count.sqlite3")
    store.upsert_rows(
        [
            Campaign(
                id=f"campaign-{index}",
                bank_slug="albaraka-turk",
                bank_name="Albaraka Türk",
                title=f"Fırsat {index}",
                content="Kampanya avantajı.",
                source_url=f"https://albaraka.example/{index}",
            ).to_dict()
            for index in range(3)
        ],
        run_status="success",
    )
    trace_path = tmp_path / "intent-traces.jsonl"
    assistant = GroundedAssistant(
        store,
        llm=llm,
        decisions=EvrenDecisionService(planner=llm),
        intent_trace=IntentTraceRecorder(trace_path),
        chroma_enabled=False,
    )

    result = assistant.answer("Albaraka portföyünde toplam kaç fırsat yer alıyor?")

    assert result["answer"] == "Albaraka Türk için doğrulanmış 3 kampanya bulundu."
    assert result["plan"]["intent"] == "campaign_count"
    assert result["plan"]["canonical_query"] == "Albaraka Türk kampanya toplamı"
    assert len(llm.calls) == 1
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["review_status"] == "pending"
    assert trace["reviewed_plan"] is None
    assert trace["llm_decision"]["intent"] == "campaign_count"

    trace["review_status"] = "approved"
    trace["reviewed_plan"] = trace["llm_decision"]
    trace_path.write_text(
        json.dumps(trace, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    examples = load_reviewed_intent_examples(trace_path)
    assert len(examples) == 1
    assert json.loads(examples[0]["intent_plan"])["intent"] == "campaign_count"


def test_same_llm_is_called_once_for_plan_and_once_for_grounded_answer(tmp_path):
    plan = json.dumps(
        {
            "safe": True,
            "intent": "campaign_query",
            "route": "HYBRID_RAG",
            "confidence": 0.94,
            "normalized_query": "Albaraka Türk öğrenci kampanyası avantajı",
            "slots": {
                "banks": ["albaraka-turk"],
                "metric": None,
                "aggregation": None,
                "product_type": None,
                "financing_type": None,
            },
        },
        ensure_ascii=False,
    )
    llm = SequencedProvider(
        plan,
        "Albaraka Türk öğrencilere ücretsiz internet avantajı sunuyor [K1].",
    )
    store = CampaignStore(tmp_path / "two-stage.sqlite3")
    store.upsert_rows(
        [
            Campaign(
                id="student",
                bank_slug="albaraka-turk",
                bank_name="Albaraka Türk",
                title="Öğrenci internet kampanyası",
                content="Öğrencilere ücretsiz internet avantajı sunulur.",
                source_url="https://albaraka.example/student",
            ).to_dict()
        ],
        run_status="success",
    )
    assistant = GroundedAssistant(
        store,
        llm=llm,
        decisions=EvrenDecisionService(planner=llm),
        chroma_enabled=False,
    )

    result = assistant.answer("Albaraka gençlere ne sunuyor?")

    assert result["generation"]["mode"] == "llm"
    assert result["answer"].endswith("[K1].")
    assert len(llm.calls) == 2
    assert '"raw_input":"Albaraka gençlere ne sunuyor?"' in llm.calls[0][1]
    assert "KANIT PAKETİ" in llm.calls[1][1]


def test_invalid_structured_plan_falls_back_without_repeating_planner_call(tmp_path):
    llm = SequencedProvider('{"intent":"unknown"}')
    store = CampaignStore(tmp_path / "invalid-plan.sqlite3")
    assistant = GroundedAssistant(
        store,
        llm=llm,
        decisions=EvrenDecisionService(planner=llm),
        chroma_enabled=False,
    )

    plan = assistant.compile("Kampanyaları göster")

    assert plan.intent == "campaign_query"
    assert len(llm.calls) == 1


class UnsafeDecisions:
    @staticmethod
    def is_safe(message):
        del message
        return False

    @staticmethod
    def route(message):
        del message
        return None

    @staticmethod
    def status():
        return {"enabled": True}


def test_guard_can_tighten_but_not_loosen_local_policy(tmp_path):
    store = CampaignStore(tmp_path / "guard.sqlite3")
    result = GroundedAssistant(
        store,
        llm=StaticProvider("local", "local", "kullanılmamalı"),
        decisions=UnsafeDecisions(),
        chroma_enabled=False,
    ).answer("Kampanyalar hakkında bilgi ver")

    assert result["plan"]["route"] == "SAFE_REDIRECT"
    assert result["generation"]["fallback_reason"] == "safe_redirect"


def _local_analysis():
    return {
        "suggestions": {},
        "quality": {"suggestion_count": 0, "warnings": []},
        "provenance": {"runtime_contract": "local"},
    }


def test_evren_advisory_accepts_only_exact_evidence_for_missing_field():
    text = "Öğrencilere 750 TL ödül sunulur."
    start = text.index("750 TL")
    client = StaticProvider(
        "evren",
        "llm-fast",
        json.dumps(
            {
                "suggestions": {
                    "reward_amount": {
                        "value": {"amount": 750, "currency": "TRY"},
                        "evidence": {
                            "text": "750 TL",
                            "char_start": start,
                            "char_end": start + len("750 TL"),
                        },
                    }
                }
            },
            ensure_ascii=False,
        ),
    )

    result = EvrenAdvisoryAugmenter(client).augment(
        _local_analysis(), text=text, structured={}
    )

    assert result["suggestions"]["reward_amount"]["method"] == "evren_grounded_llm"
    assert result["augmentation"]["advisory_only"] is True


def test_evren_advisory_defaults_to_large_model(monkeypatch):
    monkeypatch.delenv("EVREN_NLP_MODEL", raising=False)
    monkeypatch.setenv("EVREN_API_KEY", "secret")

    augmenter = EvrenAdvisoryAugmenter()

    assert augmenter.client.model == "llm-large"


def test_evren_advisory_reanchors_unique_evidence_and_conflicts_fail_closed():
    text = "Öğrencilere 750 TL ödül sunulur."
    invalid = StaticProvider(
        "evren",
        "llm-fast",
        json.dumps(
            {
                "suggestions": {
                    "reward_amount": {
                        "value": 750,
                        "evidence": {
                            "text": "750 TL",
                            "char_start": 0,
                            "char_end": 6,
                        },
                    }
                }
            }
        ),
    )
    reanchored = EvrenAdvisoryAugmenter(invalid).augment(
        _local_analysis(), text=text, structured={}
    )
    assert reanchored["suggestions"]["reward_amount"]["evidence"] == {
        "text": "750 TL",
        "char_start": text.index("750 TL"),
        "char_end": text.index("750 TL") + len("750 TL"),
    }

    start = text.index("750 TL")
    conflict_client = StaticProvider(
        "evren",
        "llm-fast",
        json.dumps(
            {
                "suggestions": {
                    "reward_amount": {
                        "value": 750,
                        "evidence": {
                            "text": "750 TL",
                            "char_start": start,
                            "char_end": start + 6,
                        },
                    }
                }
            }
        ),
    )
    analysis = _local_analysis()
    analysis["suggestions"]["reward_amount"] = {
        "value": 500,
        "evidence": {"text": "750 TL", "char_start": start, "char_end": start + 6},
        "advisory": True,
    }
    result = EvrenAdvisoryAugmenter(conflict_client).augment(
        analysis, text=text, structured={}
    )
    assert "reward_amount" not in result["suggestions"]
    assert "conflicting_evren_suggestion:reward_amount" in result["quality"]["warnings"]


def test_evren_advisory_skips_missing_or_ambiguous_evidence():
    for text, evidence_text in [
        ("Ödül sunulur.", "750 TL"),
        ("750 TL ödül, ardından 750 TL indirim.", "750 TL"),
    ]:
        invalid = StaticProvider(
            "evren",
            "llm-large",
            json.dumps(
                {
                    "suggestions": {
                        "reward_amount": {
                            "value": 750,
                            "evidence": {
                                "text": evidence_text,
                                "char_start": 0,
                                "char_end": 1,
                            },
                        }
                    }
                }
            ),
        )
        result = EvrenAdvisoryAugmenter(invalid).augment(
            _local_analysis(), text=text, structured={}
        )
        assert "reward_amount" not in result["suggestions"]


def _embedding_transport(*, dimensions=1024, served_model="bge-m3-embed"):
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "bge-m3-embed"}]})
        payload = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": served_model,
                "data": [
                    {"index": index, "embedding": [float(index + 1)] * dimensions}
                    for index, _ in enumerate(payload["input"])
                ],
            },
        )

    return httpx.MockTransport(handler)


def test_evren_embedding_validates_model_dimension_and_order():
    provider = EvrenEmbeddingProvider(
        EvrenEmbeddingSettings(
            enabled=True,
            base_url="https://evren.example/v1",
            api_key="secret",
        ),
        transport=_embedding_transport(),
    )

    vectors = provider.embed_documents(["bir", "iki"])

    assert len(vectors) == 2
    assert len(vectors[0]) == 1024
    assert vectors[0][0] == 1.0
    assert vectors[1][0] == 2.0


def test_evren_embedding_rejects_wrong_dimension():
    provider = EvrenEmbeddingProvider(
        EvrenEmbeddingSettings(
            enabled=True,
            base_url="https://evren.example/v1",
            api_key="secret",
        ),
        transport=_embedding_transport(dimensions=8),
    )

    with pytest.raises(EvrenEmbeddingError, match="geçersiz çıktı"):
        provider.embed_query("murabaha")


class FakeEvrenEmbedding:
    enabled = True
    model_name = "bge-m3-embed"

    class Settings:
        dimensions = 2

    settings = Settings()

    @staticmethod
    def embed_documents(texts):
        return [
            [1.0, 0.0] if "konut" in text.casefold() else [0.0, 1.0]
            for text in texts
        ]

    @classmethod
    def embed_query(cls, text):
        return cls.embed_documents([text])[0]


def test_qdrant_index_is_incremental_and_retrievable(tmp_path, monkeypatch):
    monkeypatch.setattr("src.retrieval.qdrant.terminology_documents", lambda: [])
    store = CampaignStore(tmp_path / "campaigns.sqlite3")
    row = Campaign(
        id="housing",
        bank_slug="ornek",
        bank_name="Örnek Katılım",
        title="Konut finansmanı",
        content="Masrafsız konut finansmanı.",
        source_url="https://ornek.example/housing",
    ).to_dict()
    store.upsert_rows([preprocess_record(row)], run_status="success")
    settings = EvrenQdrantSettings(
        enabled=True,
        url="https://evren-vektor.example",
        port=443,
        prefix="team07",
        api_key="qdr-secret",
        collection="campaigns",
    )
    retriever = EvrenQdrantRetriever(
        settings=settings,
        embedding_provider=FakeEvrenEmbedding(),
        client=QdrantClient(":memory:"),
    )
    indexer = EvrenQdrantIndexer(store, retriever=retriever)

    first = indexer.build()
    second = indexer.build()
    results = retriever.retrieve(
        "konut", filters={"bank_slugs": ["ornek"]}, limit=3
    )

    assert first["embedded"] == 1
    assert second["embedded"] == 0
    assert second["unchanged"] == 1
    assert results[0]["metadata"]["campaign_id"] == "housing"
    assert results[0]["retrieval_method"] == "evren-qdrant+bge-m3-embed"


class SlowLocalLLM(StaticProvider):
    def stream_chat(self, *, system_prompt, user_prompt):
        del system_prompt, user_prompt
        sleep(0.04)
        yield self.answer


def test_capability_matrix_and_sse_heartbeat_preserve_fallback(tmp_path, monkeypatch):
    store = CampaignStore(tmp_path / "api.sqlite3")
    row = Campaign(
        id="housing",
        bank_slug="ornek",
        bank_name="Örnek Katılım",
        title="Konut finansmanı",
        content="24 ay vadeli %1,89 kâr payı ile konut finansmanı.",
        source_url="https://ornek.example/housing",
    ).to_dict()
    store.upsert_rows([preprocess_record(row)], run_status="success")
    app = create_app(database_path=store.path, chroma_enabled=False)
    app.state.grounded_assistant = GroundedAssistant(
        store,
        llm=SlowLocalLLM("local", "local-model", "Oran %1,89'dur [K1]."),
        recorder=app.state.event_recorder,
        chroma_enabled=False,
    )
    monkeypatch.setenv("RAGNROLL_SSE_HEARTBEAT_SECONDS", "0.01")

    with TestClient(app) as client:
        status = client.get("/api/v1/capabilities/status")
        with client.stream(
            "POST",
            "/api/v1/chat/stream",
            json={"message": "Konut finansmanında oran kaç?"},
        ) as response:
            body = "".join(response.iter_text())

    assert status.status_code == 200
    assert status.json()["retrieval"]["bm25_graph"]["available"] is True
    assert "event: heartbeat" in body
    assert "Oran %1,89'dur [K1]." in body
