import json

import pytest

from src.llm.client import LLMUnavailableError
from src.llm.decisions import (
    ALLOWED_INTENTS,
    EvrenDecisionService,
    _json_object,
)


class FakePlanner:
    enabled = True

    def __init__(self, answers):
        self.answers = list(answers)
        self.rejected = []
        self.accepted = []

    def stream_chat(self, *, system_prompt, user_prompt):
        if isinstance(self.answers[0], Exception):
            raise self.answers.pop(0)
        yield self.answers.pop(0)

    def reject_candidate(self, metadata):
        self.rejected.append(metadata)

    def accept_candidate(self, metadata):
        self.accepted.append(metadata)


class DisabledPlanner:
    enabled = False


def valid_decision(**overrides):
    decision = {
        "safe": True,
        "intent": "campaign_count",
        "route": "STRUCTURED_SQL",
        "confidence": 0.9,
        "normalized_query": "Albaraka kampanya sayısı",
        "slots": {
            "banks": ["albaraka"],
            "metric": None,
            "aggregation": "COUNT",
            "product_type": None,
            "financing_type": None,
        },
    }
    decision.update(overrides)
    return json.dumps(decision, ensure_ascii=False)


@pytest.fixture()
def service():
    return EvrenDecisionService(
        prompt_path="configs/prompts/intent_prompt.json",
        router=FakePlanner([valid_decision()]),
    )


def test_json_object_parses_fenced_embedded_and_invalid_payloads():
    assert _json_object('```json\n{"safe": true}\n```') == {"safe": True}
    assert _json_object("Önce metin {\"route\": \"HYBRID_RAG\"} sonra metin") == {
        "route": "HYBRID_RAG"
    }
    assert _json_object("") is None
    assert _json_object("[1, 2, 3]") is None
    assert _json_object("tamamen geçersiz") is None


def test_analyze_returns_validated_decision(service):
    decision = service.analyze("kaç kampanya var", known_banks=[{"slug": "albaraka", "name": "Albaraka"}])

    assert decision["safe"] is True
    assert decision["intent"] == "campaign_count"
    assert decision["route"] == "STRUCTURED_SQL"
    assert decision["confidence"] == 0.9
    assert decision["normalized_query"] == "Albaraka kampanya sayısı"
    assert decision["slots"]["banks"] == ["albaraka"]


def test_analyze_normalizes_whitespace_and_dedupes_banks():
    raw = valid_decision(
        normalized_query="  fazla   boşluklu   sorgu  ",
        slots={
            "banks": ["albaraka", "albaraka", "kuveyt"],
            "metric": None,
            "aggregation": "COUNT",
        },
    )
    service = EvrenDecisionService(router=FakePlanner([raw]))

    decision = service.analyze(
        "soru",
        known_banks=[
            {"slug": "albaraka", "name": "Albaraka"},
            {"slug": "kuveyt", "name": "Kuveyt Türk"},
        ],
    )
    assert decision["normalized_query"] == "fazla boşluklu sorgu"
    assert decision["slots"]["banks"] == ["albaraka", "kuveyt"]


def _extra_field_case():
    payload = json.loads(valid_decision())
    payload["extra"] = 1
    return json.dumps(payload)


def test_analyze_rejects_schema_violations():
    cases = [
        "{}",
        _extra_field_case(),
        valid_decision(safe="evet"),
        valid_decision(intent="shell_exec"),
        valid_decision(route="SHELL"),
        valid_decision(confidence=True),
        valid_decision(confidence="yüksek"),
        valid_decision(confidence=1.5),
        valid_decision(confidence=-0.1),
        valid_decision(normalized_query="   "),
        valid_decision(normalized_query="x" * 2001),
        valid_decision(slots=["yok"]),
        valid_decision(slots={"banks": [], "unknown_slot": 1}),
        valid_decision(slots={"banks": "tek"}),
        valid_decision(slots={"banks": [42]}),
        valid_decision(slots={"metric": "FAIZ", "aggregation": "COUNT"}),
        valid_decision(slots={"banks": [], "aggregation": "SUM"}),
        valid_decision(intent="bank_list", slots={"banks": [], "aggregation": "MAX"}),
        valid_decision(intent="complaint_support"),
        valid_decision(safe=False, route="SAFE_REDIRECT", intent="definition"),
        valid_decision(intent="definition"),
        json.dumps({"safe": True, "intent": "definition"}),
    ]
    for raw in cases:
        service = EvrenDecisionService(router=FakePlanner([raw]))
        assert service.analyze("soru", known_banks=[{"slug": "albaraka", "name": "A"}]) is None, raw


def test_analyze_accepts_hybrid_rag_for_safe_definition_intent():
    service = EvrenDecisionService(router=FakePlanner([
        valid_decision(
            intent="definition",
            route="HYBRID_RAG",
            slots={"banks": [], "aggregation": None},
        )
    ]))
    decision = service.analyze("murabaha nedir")
    assert decision["route"] == "HYBRID_RAG"


def test_analyze_accepts_safe_redirect_for_unsafe_intent():
    service = EvrenDecisionService(router=FakePlanner([
        valid_decision(
            safe=False,
            intent="transaction_howto",
            route="SAFE_REDIRECT",
            slots={"banks": []},
        )
    ]))
    decision = service.analyze("havale yap")
    assert decision["safe"] is False
    assert decision["route"] == "SAFE_REDIRECT"


def test_analyze_returns_none_when_planner_disabled():
    service = EvrenDecisionService(planner=DisabledPlanner())
    assert service.analyze("soru") is None
    assert service.enabled is False


def test_analyze_survives_llm_unavailability():
    service = EvrenDecisionService(router=FakePlanner([LLMUnavailableError("yok")]))
    assert service.analyze("soru") is None


class CandidatePlanner(FakePlanner):
    """stream_chat_candidates sözleşmesini uygulayan çok adaylı sahte planlayıcı."""

    def __init__(self, candidates):
        super().__init__([])
        self.candidates = list(candidates)

    def stream_chat_candidates(self, *, system_prompt, user_prompt):
        for answer in self.candidates:
            yield [answer], {"index": len(self.rejected) + len(self.accepted)}


def test_analyze_reports_candidate_outcomes_to_planner():
    planner = CandidatePlanner(["geçersiz çıktı", valid_decision()])
    service = EvrenDecisionService(router=planner)

    decision = service.analyze("soru", known_banks=[{"slug": "albaraka", "name": "A"}])

    assert decision is not None
    assert len(planner.rejected) == 1
    assert len(planner.accepted) == 1


def _bankless_decision(**overrides):
    payload = json.loads(valid_decision(**overrides))
    payload["slots"]["banks"] = []
    return json.dumps(payload, ensure_ascii=False)


def test_is_safe_falls_back_to_analyze_when_guard_missing():
    service = EvrenDecisionService(router=FakePlanner([_bankless_decision()]))
    assert service.is_safe("soru") is True

    failing = EvrenDecisionService(router=FakePlanner(["bozuk"]))
    assert failing.is_safe("soru") is None


def test_route_uses_guard_path_and_validates_values():
    class StaticProvider(FakePlanner):
        def __init__(self, answer):
            super().__init__([])

        def stream_chat(self, *, system_prompt, user_prompt):
            yield self.answer

    good = StaticProvider(None)
    good.answer = '{"route": "HYBRID_RAG"}'
    service = EvrenDecisionService(
        router=good, guard=FakePlanner([]), prompt_path="configs/prompts/intent_prompt.json"
    )
    assert service.route("soru") == "HYBRID_RAG"

    bad = StaticProvider(None)
    bad.answer = '{"route": "TELNET"}'
    invalid = EvrenDecisionService(router=bad, guard=FakePlanner([]))
    assert invalid.route("soru") is None


def test_is_safe_with_enabled_guard_returns_bool_or_none():
    class AnsweringGuard(FakePlanner):
        def __init__(self, answer):
            super().__init__([])
            self.answer = answer

        def stream_chat(self, *, system_prompt, user_prompt):
            yield self.answer

    guarded = EvrenDecisionService(
        router=FakePlanner([valid_decision()]),
        guard=AnsweringGuard('{"safe": false}'),
    )
    assert guarded.is_safe("şikâyet") is False

    ambiguous = EvrenDecisionService(
        router=FakePlanner([valid_decision()]),
        guard=AnsweringGuard('{"safe": "belki"}'),
    )
    assert ambiguous.is_safe("soru") is None


def test_status_exposes_prompt_profile_and_planner_info(service):
    status = service.status()
    assert status["enabled"] is True
    assert status["mode"] == "single_call_structured_intent"
    assert set(status["prompt"]) == {"profile", "optimizer", "status"}
    assert status["planner"]["available"] is True


def test_allowlisted_intents_are_complete():
    assert "campaign_count" in ALLOWED_INTENTS
    assert "investment_query" in ALLOWED_INTENTS
