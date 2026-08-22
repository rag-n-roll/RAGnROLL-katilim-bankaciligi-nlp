"""Kanıta bağlı Türkçe cevap istemini GEPA ile iyileştiren DSPy programı."""

from __future__ import annotations

# DSPy'nin isteğe bağlı bağımlılık yükleyicisinin Python 3.14 altında NumPy'yi
# kısmi başlatmasını önlemek için NumPy önce yüklenir.
import numpy  # noqa: F401
import dspy


class GroundedTurkishAnswer(dspy.Signature):
    """Kanıt dışına çıkmadan profesyonel Türkçe cevap üret."""

    question: str = dspy.InputField(desc="Kullanıcının Türkçe sorusu")
    evidence: str = dspy.InputField(desc="Etiketli ve güvenilir kanıt paketi")
    fallback: str = dspy.InputField(desc="Doğrulanmış deterministik cevap")
    answer: str = dspy.OutputField(
        desc="Somut iddiaları [K#] ile desteklenmiş nihai Türkçe cevap"
    )


class GroundedAnswerProgram(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.writer = dspy.Predict(GroundedTurkishAnswer)

    def forward(self, question: str, evidence: str, fallback: str):
        return self.writer(question=question, evidence=evidence, fallback=fallback)


def grounded_answer_metric(
    example,
    prediction,
    trace=None,
    pred_name=None,
    pred_trace=None,
):
    """GEPA'ya doğruluk, kaynak ve Türkçe üslup hakkında metinsel geri bildirim verir."""

    del trace, pred_name, pred_trace
    answer = str(getattr(prediction, "answer", "") or "").strip()
    lowered = answer.casefold()
    required = [str(value).casefold() for value in example.required_terms]
    forbidden = [str(value).casefold() for value in example.forbidden_terms]
    checks = {
        "required_terms": all(term in lowered for term in required),
        "forbidden_terms": not any(term in lowered for term in forbidden),
        "citation": "[k" in lowered,
        "turkish": any(character in lowered for character in "çğıöşü"),
        "bounded": 40 <= len(answer) <= 1200,
    }
    score = sum(checks.values()) / len(checks)
    failed = [name for name, passed in checks.items() if not passed]
    feedback = (
        "Cevap bütün kanıt, kaynak ve Türkçe üslup kontrollerini geçti."
        if not failed
        else "Şu kontroller başarısız: " + ", ".join(failed)
    )
    return dspy.Prediction(score=score, feedback=feedback)
