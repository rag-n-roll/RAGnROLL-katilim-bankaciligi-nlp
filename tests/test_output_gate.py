"""OutputGate tests: deterministic checks and semantic judging integration."""

import json
from src.llm.judging import SemanticJudge
from src.policy.output_gate import OutputGate, OutputVerdict


class FakeJudge:
    """Stub judge returning a pre-configured verdict."""

    def __init__(self, *, valid: bool, reason_code: str):
        self._verdict = OutputVerdict(valid=valid, reason_code=reason_code)

    def evaluate(
        self,
        *,
        question: str,
        answer: str,
        sources: list[dict],
        context: dict | None = None,
    ) -> OutputVerdict:
        del context
        return self._verdict


class FakeJudgeLLM:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.calls: list[tuple[str, str]] = []
        self.accepted: list[dict] = []

    def stream_chat(self, *, system_prompt: str, user_prompt: str):
        self.calls.append((system_prompt, user_prompt))
        for resp in self.responses:
            yield resp

    def stream_chat_candidates(self, *, system_prompt: str, user_prompt: str):
        self.calls.append((system_prompt, user_prompt))
        for index, resp in enumerate(self.responses):
            yield [resp], {"index": index}

    def accept_candidate(self, metadata: dict):
        self.accepted.append(metadata)


def test_output_gate_rejects_repeated_normalized_bullets():
    answer = "- Masrafsız kart seçeneği [K1]\n- Masrafsız kart seçeneği [K1]"
    verdict = OutputGate().validate(answer, sources=[{"evidence": {"text": "Masrafsız kart"}}])
    assert verdict.valid is False
    assert verdict.reason_code == "repeated_content"


def test_output_gate_rejects_semantically_irrelevant_answer():
    judge = FakeJudge(valid=False, reason_code="question_not_answered")
    verdict = OutputGate(judge=judge).validate(
        "Kart kampanyaları listesi [K1]",
        question="İstanbul'da hava nasıl?",
        sources=[{"evidence": {"text": "Kart kampanyası"}}],
    )
    assert verdict.valid is False
    assert verdict.reason_code == "question_not_answered"


def test_output_gate_passes_clean_answer_without_judge():
    answer = "- Masrafsız kart seçeneği [K1]\n- Aidat yok [K2]"
    verdict = OutputGate().validate(
        answer,
        sources=[
            {"evidence": {"text": "Masrafsız kart"}},
            {"evidence": {"text": "Aidat yok"}},
        ],
    )
    assert verdict.valid is True
    assert verdict.reason_code == "deterministic_checks_passed"


def test_output_gate_citation_markers_stripped_before_normalization():
    """[K#] markers and punctuation are normalized; lines differing only by marker don't repeat."""
    answer = "- Konut finansmanı oranı [K1]\n- Konut finansmanı oranı [K2]"
    verdict = OutputGate().validate(answer, sources=[{"evidence": {"text": "oran"}}])
    assert verdict.valid is False
    assert verdict.reason_code == "repeated_content"


def test_output_gate_judge_approval_overrides_deterministic():
    judge = FakeJudge(valid=True, reason_code="approved")
    verdict = OutputGate(judge=judge).validate(
        "Tek madde yanıtı [K1]",
        question="En düşük kâr payı nedir?",
        sources=[{"evidence": {"text": "Tek madde"}}],
    )
    assert verdict.valid is True
    assert verdict.reason_code == "approved"


def test_output_gate_deterministic_rejection_runs_before_judge():
    """Repeated content is caught before the judge is even consulted."""
    judge = FakeJudge(valid=True, reason_code="approved")
    answer = "- Aynı satır [K1]\n- Aynı satır [K1]"
    verdict = OutputGate(judge=judge).validate(
        answer, sources=[{"evidence": {"text": "x"}}]
    )
    assert verdict.valid is False
    assert verdict.reason_code == "repeated_content"


def test_semantic_judge_unavailable_when_no_llm():
    judge = SemanticJudge(llm=None)
    verdict = judge.evaluate(
        question="Soru",
        answer="Cevap",
        sources=[],
    )
    assert verdict.valid is False
    assert verdict.reason_code == "judge_unavailable"


def test_semantic_judge_parses_valid_json_verdict():
    llm = FakeJudgeLLM([json.dumps({"valid": False, "reason_code": "unsupported_claim"})])
    judge = SemanticJudge(llm=llm)
    verdict = judge.evaluate(
        question="Soru",
        answer="Konut finansmanı açıklaması.",
        sources=[],
    )
    assert verdict.valid is False
    assert verdict.reason_code == "unsupported_claim"


def test_semantic_judge_accepts_a_json_code_fence_without_extra_text():
    llm = FakeJudgeLLM(
        ['```json\n{"valid": true, "reason_code": "passed"}\n```']
    )

    verdict = SemanticJudge(llm=llm).evaluate(
        question="Murabaha nedir?",
        answer="Murabaha vadeli satış akdidir.",
        sources=[{"evidence": {"text": "Murabaha vadeli satış akdidir."}}],
    )

    assert verdict.valid is True
    assert verdict.reason_code == "passed"


def test_semantic_judge_handles_llm_malformed_json_gracefully():
    llm = FakeJudgeLLM(["not valid json"])
    judge = SemanticJudge(llm=llm)
    verdict = judge.evaluate(
        question="Soru",
        answer="Cevap",
        sources=[],
    )
    assert verdict.valid is False
    assert verdict.reason_code == "judge_invalid_output"


def test_semantic_judge_rejects_wrong_json_types_and_unknown_reason_codes():
    llm = FakeJudgeLLM(
        [
            json.dumps({"valid": "false", "reason_code": "passed"}),
            json.dumps({"valid": True, "reason_code": "anything_goes"}),
        ]
    )

    verdict = SemanticJudge(llm=llm).evaluate(
        question="Soru",
        answer="Cevap",
        sources=[],
    )

    assert verdict.valid is False
    assert verdict.reason_code == "judge_invalid_output"


def test_semantic_judge_rejects_unqualified_superlative_without_calling_llm():
    llm = FakeJudgeLLM(
        [json.dumps({"valid": True, "reason_code": "passed"})]
    )

    verdict = SemanticJudge(llm=llm).evaluate(
        question="Hangi kartlar var?",
        answer="Bu kesinlikle en iyi karttır.",
        sources=[{"evidence": {"text": "Kart kampanyası"}}],
    )

    assert verdict.valid is False
    assert verdict.reason_code == "unsupported_qualitative_claim"
    assert llm.calls == []


def test_semantic_judge_rejects_unsupported_relative_recommendation():
    llm = FakeJudgeLLM(
        [json.dumps({"valid": True, "reason_code": "passed"})]
    )

    verdict = SemanticJudge(llm=llm).evaluate(
        question="Hangisi daha avantajlı?",
        answer="Bu ürün daha avantajlı ve tercih edilebilir.",
        sources=[{"evidence": {"text": "Araç finansmanı seçeneği"}}],
    )

    assert verdict.valid is False
    assert verdict.reason_code == "unsupported_qualitative_claim"
    assert llm.calls == []


def test_semantic_judge_allows_evidence_backed_comparison_context():
    llm = FakeJudgeLLM(
        [json.dumps({"valid": True, "reason_code": "passed"})]
    )
    context = {
        "plan": {
            "intent": "product_comparison",
            "slots": {
                "aggregation": "MIN",
                "metric": "PROFIT_RATE",
                "term_months": None,
                "amount": None,
                "fee_priority": None,
            },
        },
        "facts": [
            {
                "campaign_id": "housing-low",
                "metric": "PROFIT_RATE",
                "value": 0.0189,
            }
        ],
    }

    verdict = SemanticJudge(llm=llm).evaluate(
        question="En düşük kâr payı hangi seçenekte?",
        answer="Bu seçenek oran açısından diğerlerinden daha avantajlıdır.",
        sources=[{"campaign_id": "housing-low", "evidence": {"text": "%1,89"}}],
        context=context,
    )

    assert verdict.valid is True
    assert verdict.reason_code == "passed"
    assert len(llm.calls) == 1
    sent_context = json.loads(llm.calls[0][1])["context"]
    assert sent_context == context


def test_semantic_judge_rejects_absolute_advice_even_with_metric_context():
    llm = FakeJudgeLLM(
        [json.dumps({"valid": True, "reason_code": "passed"})]
    )
    context = {
        "plan": {
            "intent": "product_comparison",
            "slots": {"aggregation": "MIN", "metric": "PROFIT_RATE"},
        },
        "facts": [
            {
                "campaign_id": "housing-low",
                "metric": "PROFIT_RATE",
                "value": 0.0189,
            }
        ],
    }

    verdict = SemanticJudge(llm=llm).evaluate(
        question="En düşük kâr payı hangi seçenekte?",
        answer="Bu kesinlikle en iyi bankadır.",
        sources=[{"campaign_id": "housing-low", "evidence": {"text": "%1,89"}}],
        context=context,
    )

    assert verdict.valid is False
    assert verdict.reason_code == "unsupported_qualitative_claim"
    assert llm.calls == []
