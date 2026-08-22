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


def test_llm_answer_gets_bounded_turkish_orthography_polish(tmp_path):
    llm = FakeLLM(["Konut finansmanı bir satış akdıdır [K1]."])

    result = GroundedAssistant(
        _store(tmp_path), llm=llm, chroma_enabled=False
    ).answer("Konut finansmanında oran kaç?")

    assert "satış akdidir" in result["answer"]
    assert "akdıdır" not in result["answer"]
    assert result["generation"]["mode"] == "llm"


def test_streaming_endpoint_emits_metadata_tokens_and_completion(tmp_path):
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


def test_llm_status_contract_uses_configured_assistant(tmp_path):
    store = _store(tmp_path)
    app = create_app(database_path=store.path, chroma_enabled=False)
    app.state.grounded_assistant = GroundedAssistant(
        store, llm=FakeLLM(), chroma_enabled=False
    )

    with TestClient(app) as client:
        payload = client.get("/api/v1/llm/status").json()

    assert payload == {"available": True, "model": "test-gemma"}
