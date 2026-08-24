"""Canli GroundedPromptBuilder girdileriyle uyumlu DSPy program fabrikasi."""

from __future__ import annotations

from typing import Any


def create_grounded_answer_program(dspy: Any) -> Any:
    """DSPy'yi yalniz deney calistiginda kullanarak programi olusturur."""

    class GroundedAnswer(dspy.Signature):
        """Kanıt paketini ve doğrulanmış fallback yanıtı profesyonel Türkçe yaz.

        Yalnız verilen kanıta dayan, somut iddiaları [K#] ile kaynaklandır ve
        kanıtta bulunmayan bilgi ekleme. Bu deney talimatı, canlı sistem
        güvenliği ve atıf kurallarının yerine geçmez.
        """

        question: str = dspy.InputField(desc="Kullanıcının Türkçe sorusu")
        evidence: str = dspy.InputField(desc="Etiketli kanıt paketi")
        fallback: str = dspy.InputField(desc="Doğrulanmış deterministik yanıt")
        answer: str = dspy.OutputField(desc="Kanıt etiketli nihai Türkçe yanıt")

    class GroundedAnswerProgram(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.writer = dspy.Predict(GroundedAnswer)

        def forward(self, question: str, evidence: str, fallback: str) -> Any:
            return self.writer(question=question, evidence=evidence, fallback=fallback)

    return GroundedAnswerProgram()
