"""OutputGate tests: deterministic checks and semantic judging integration."""

import json
from src.llm.judging import SemanticJudge
from src.policy.output_gate import OutputGate, OutputVerdict


class FakeJudge:
    """Stub judge returning a pre-configured verdict."""

    def __init__(self, *, valid: bool, reason_code: str):
        self._verdict = OutputVerdict(valid=valid, reason_code=reason_code)

    def evaluate(self, *, question: str, answer: str, sources: list[dict]) -> OutputVerdict:
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
    assert verdict.valid is True
    assert verdict.reason_code == "judge_unavailable"


def test_semantic_judge_parses_valid_json_verdict():
    llm = FakeJudgeLLM([json.dumps({"valid": False, "reason_code": "unsupported_claim"})])
    judge = SemanticJudge(llm=llm)
    verdict = judge.evaluate(
        question="Soru",
        answer="En avantajlı konut kredisi!",
        sources=[],
    )
    assert verdict.valid is False
    assert verdict.reason_code == "unsupported_claim"


def test_semantic_judge_handles_llm_malformed_json_gracefully():
    llm = FakeJudgeLLM(["not valid json"])
    judge = SemanticJudge(llm=llm)
    verdict = judge.evaluate(
        question="Soru",
        answer="Cevap",
        sources=[],
    )
    assert verdict.valid is True
    assert verdict.reason_code == "judge_fallback"
