import json

import pytest

from src.llm.client import LLMUnavailableError
from src.llm.decisions import ALLOWED_INTENTS, EvrenDecisionService, _json_object
from src.policy import Action, ComparisonCriteria, PolicyDecision


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
        "action": "ANSWER",
        "in_domain": True,
        "intent": "campaign_count",
        "confidence": 0.9,
        "normalized_query": "Albaraka kampanya sayısı",
        "concepts": ["campaign"],
        "missing_criteria": [],
        "tool_calls": [
            {
                "name": "structured_sql",
                "arguments": {"banks": ["albaraka"], "aggregation": "COUNT"},
            }
        ],
        "slots": {
            "banks": ["albaraka"],
            "metric": None,
            "aggregation": "COUNT",
            "product_type": None,
            "financing_type": None,
            "term_months": None,
            "amount": None,
            "fee_priority": None,
        },
        "reason_code": "model_answer",
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
    assert _json_object('```json\n{"action": "ANSWER"}\n```') == {"action": "ANSWER"}
    assert _json_object('prefix {"action": "CLARIFY"} suffix') == {"action": "CLARIFY"}
    assert _json_object("") is None
    assert _json_object("tamamen geçersiz") is None
    assert _json_object("[1, 2, 3]") is None


def test_analyze_returns_policy_decision_and_preserves_query_compatibility(service):
    decision = service.analyze(
        "kaç kampanya var", known_banks=[{"slug": "albaraka", "name": "Albaraka"}]
    )
    assert isinstance(decision, PolicyDecision)
    assert decision.action == Action.ANSWER
    assert decision.intent == "campaign_count"
    assert decision.confidence == 0.9
    assert decision.concepts == ("campaign",)
    assert decision.normalized_query == "Albaraka kampanya sayısı"
    assert decision["normalized_query"] == "Albaraka kampanya sayısı"
    assert decision["slots"]["banks"] == ["albaraka"]
    assert decision.get("route") == "STRUCTURED_SQL"
    assert decision.get("unknown", "fallback") == "fallback"
    serialized = decision.to_dict()
    assert json.loads(json.dumps(serialized))["action"] == "ANSWER"


def test_analyze_maps_comparison_slots_into_criteria():
    raw = valid_decision(
        intent="product_comparison",
        tool_calls=[
            {
                "name": "comparison",
                "arguments": {
                    "banks": ["albaraka"],
                    "term_months": 24,
                    "amount": 750000,
                    "fee_priority": True,
                },
            }
        ],
        slots={
            "banks": ["albaraka"],
            "metric": None,
            "aggregation": None,
            "product_type": "financing",
            "financing_type": "housing",
            "term_months": 24,
            "amount": 750000,
            "fee_priority": True,
        },
    )
    decision = EvrenDecisionService(router=FakePlanner([raw])).analyze(
        "karşılaştır", known_banks=[{"slug": "albaraka", "name": "A"}]
    )
    assert decision.criteria == ComparisonCriteria(
        term_months=24, amount=750000.0, fee_priority=True
    )


def _payload(**overrides):
    value = json.loads(valid_decision())
    value.update(overrides)
    return json.dumps(value, ensure_ascii=False)


@pytest.mark.parametrize(
    ("rejection_class", "raw"),
    [
        ("action", _payload(action="EXECUTE")),
        ("intent", _payload(intent="shell_exec")),
        ("tool", _payload(tool_calls=[{"name": "shell", "arguments": {}}])),
        ("criterion", _payload(missing_criteria=["interest_color"])),
        (
            "bank",
            _payload(
                slots={"banks": ["unknown-bank"]},
                tool_calls=[
                    {"name": "structured_sql", "arguments": {"banks": ["unknown-bank"]}}
                ],
            ),
        ),
        (
            "tool argument",
            _payload(
                tool_calls=[
                    {"name": "structured_sql", "arguments": {"shell": "whoami"}}
                ]
            ),
        ),
    ],
)
def test_analyze_rejects_unknown_policy_values(rejection_class, raw):
    service = EvrenDecisionService(router=FakePlanner([raw]))
    assert (
        service.analyze("soru", known_banks=[{"slug": "albaraka", "name": "A"}]) is None
    ), rejection_class


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        _payload(extra=True),
        _payload(in_domain="yes"),
        _payload(confidence=True),
        _payload(confidence=1.1),
        _payload(normalized_query=" "),
        _payload(concepts="campaign"),
        _payload(missing_criteria="amount"),
        _payload(tool_calls={}),
        _payload(slots=[]),
        _payload(reason_code=""),
    ],
)
def test_analyze_rejects_malformed_schema(raw):
    service = EvrenDecisionService(router=FakePlanner([raw]))
    assert (
        service.analyze("soru", known_banks=[{"slug": "albaraka", "name": "A"}]) is None
    )


def test_analyze_returns_none_when_planner_disabled_or_unavailable():
    assert EvrenDecisionService(planner=DisabledPlanner()).analyze("soru") is None
    assert (
        EvrenDecisionService(router=FakePlanner([LLMUnavailableError("yok")])).analyze(
            "soru"
        )
        is None
    )


class CandidatePlanner(FakePlanner):
    def __init__(self, candidates):
        super().__init__([])
        self.candidates = list(candidates)

    def stream_chat_candidates(self, *, system_prompt, user_prompt):
        for index, answer in enumerate(self.candidates):
            yield [answer], {"index": index}


def test_analyze_reports_candidate_outcomes_to_planner():
    planner = CandidatePlanner(["geçersiz çıktı", valid_decision()])
    decision = EvrenDecisionService(router=planner).analyze(
        "soru", known_banks=[{"slug": "albaraka", "name": "A"}]
    )
    assert decision is not None
    assert len(planner.rejected) == 1
    assert len(planner.accepted) == 1


def test_legacy_safety_and_route_helpers_use_policy_decision():
    safe = EvrenDecisionService(
        router=FakePlanner(
            [
                valid_decision(
                    tool_calls=[
                        {
                            "name": "structured_sql",
                            "arguments": {"banks": [], "aggregation": "COUNT"},
                        }
                    ],
                    slots={"banks": [], "aggregation": "COUNT"},
                )
            ]
        )
    )
    assert safe.is_safe("soru") is True
    redirect = EvrenDecisionService(
        router=FakePlanner(
            [
                valid_decision(
                    action="REDIRECT",
                    in_domain=True,
                    intent="transaction_howto",
                    tool_calls=[],
                    slots={"banks": []},
                    reason_code="transaction_request",
                )
            ]
        )
    )
    assert redirect.route("havale yap") == "SAFE_REDIRECT"


class StaticProvider(FakePlanner):
    def __init__(self, answer):
        super().__init__([])
        self.answer = answer

    def stream_chat(self, *, system_prompt, user_prompt):
        yield self.answer


def test_route_guard_path_still_validates_legacy_values():
    service = EvrenDecisionService(
        router=StaticProvider('{"route": "HYBRID_RAG"}'),
        guard=FakePlanner([]),
    )
    assert service.route("soru") == "HYBRID_RAG"

    invalid = EvrenDecisionService(
        router=StaticProvider('{"route": "TELNET"}'),
        guard=FakePlanner([]),
    )
    assert invalid.route("soru") is None


def test_enabled_legacy_guard_still_returns_bool_or_none():
    guarded = EvrenDecisionService(
        router=FakePlanner([]),
        guard=StaticProvider('{"safe": false}'),
    )
    assert guarded.is_safe("şikâyet") is False

    ambiguous = EvrenDecisionService(
        router=FakePlanner([]),
        guard=StaticProvider('{"safe": "belki"}'),
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
