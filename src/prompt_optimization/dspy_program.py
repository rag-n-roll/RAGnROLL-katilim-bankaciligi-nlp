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


def create_intent_planner_program(dspy: Any) -> Any:
    """İncelenmiş plan izlerinden optimize edilebilen ilk-aşama programı kurar."""

    class IntentPlan(dspy.Signature):
        """Türkçe kullanıcı girdisini güvenli, şema uyumlu yürütme planına çevir.

        Kullanıcıya cevap verme. Banka sluglarını yalnız katalogdan seç; güvenlik
        kurallarını gevşetme ve bütün çıktıyı geçerli JSON nesnesi olarak üret.
        """

        raw_input: str = dspy.InputField(desc="Kullanıcının değiştirilmemiş girdisi")
        canonical_query: str = dspy.InputField(desc="Terminolojiyle normalize sorgu")
        deterministic_hint: str = dspy.InputField(desc="Güvenli yerel plan taslağı")
        bank_catalog: str = dspy.InputField(desc="İzinli banka adları ve slugları")
        intent_plan: str = dspy.OutputField(
            desc="Güvenlik, intent, route, confidence, normalized_query ve slots JSON'u"
        )

    class IntentPlannerProgram(dspy.Module):
        def __init__(self) -> None:
            super().__init__()
            self.planner = dspy.Predict(IntentPlan)

        def forward(
            self,
            raw_input: str,
            canonical_query: str,
            deterministic_hint: str,
            bank_catalog: str,
        ) -> Any:
            return self.planner(
                raw_input=raw_input,
                canonical_query=canonical_query,
                deterministic_hint=deterministic_hint,
                bank_catalog=bank_catalog,
            )

    return IntentPlannerProgram()
