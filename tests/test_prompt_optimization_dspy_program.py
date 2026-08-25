from src.prompt_optimization.dspy_program import (
    create_grounded_answer_program,
    create_intent_planner_program,
)


class _FakeField:
    def __init__(self, desc=""):
        self.desc = desc


class _FakeSignature:
    pass


class _FakePrediction:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakePredict:
    def __init__(self, signature):
        self.signature = signature
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return _FakePrediction(answer="yanıt")


class _FakeModule:
    def __init__(self):
        pass


def _fake_dspy():
    class FakeDspy:
        InputField = _FakeField
        OutputField = _FakeField
        Signature = _FakeSignature
        Predict = _FakePredict
        Module = _FakeModule

    return FakeDspy()


def test_grounded_answer_program_forwards_all_inputs():
    dspy = _fake_dspy()

    program = create_grounded_answer_program(dspy)
    result = program.forward(
        question="Murabaha nedir?", evidence="[K1] tanım", fallback="Varsayılan yanıt"
    )

    assert isinstance(program, dspy.Module)
    assert program.writer.calls == [
        {
            "question": "Murabaha nedir?",
            "evidence": "[K1] tanım",
            "fallback": "Varsayılan yanıt",
        }
    ]
    assert result.answer == "yanıt"


def test_intent_planner_program_forwards_all_inputs():
    dspy = _fake_dspy()

    program = create_intent_planner_program(dspy)
    result = program.forward(
        raw_input="kampanyalar",
        canonical_query="normalize sorgu",
        deterministic_hint="taslak",
        bank_catalog="ziraat-katilim",
    )

    assert isinstance(program, dspy.Module)
    assert program.planner.calls == [
        {
            "raw_input": "kampanyalar",
            "canonical_query": "normalize sorgu",
            "deterministic_hint": "taslak",
            "bank_catalog": "ziraat-katilim",
        }
    ]
    assert result.answer == "yanıt"


def test_signatures_declare_expected_fields():
    captured = []

    class RecordingPredict(_FakePredict):
        def __init__(self, signature):
            super().__init__(signature)
            captured.append(signature)

    class FakeDspy:
        InputField = _FakeField
        OutputField = _FakeField
        Signature = _FakeSignature
        Predict = RecordingPredict
        Module = _FakeModule

    create_grounded_answer_program(FakeDspy())
    create_intent_planner_program(FakeDspy())

    grounded_fields = {k for k in vars(captured[0]) if not k.startswith("__")}
    planner_fields = {k for k in vars(captured[1]) if not k.startswith("__")}

    assert set(grounded_fields) == {"question", "evidence", "fallback", "answer"}
    assert set(planner_fields) == {
        "raw_input",
        "canonical_query",
        "deterministic_hint",
        "bank_catalog",
        "intent_plan",
    }
