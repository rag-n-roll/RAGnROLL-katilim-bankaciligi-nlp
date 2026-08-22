"""DSPy signature for a grounded Turkish participation-banking assistant."""

from __future__ import annotations

import dspy


class CampaignAnswer(dspy.Signature):
    """Türkçe yanıt ver. Kampanya metni ile sınıflandırma ve entity kanıtlarını birlikte kullan. Sadece verilen kanıtlara dayan; bilgi yoksa tam olarak 'Bu bilgi sağlanan dokümanlarda bulunmamaktadır.' de. Birbiriyle çelişen kanıtlarda ham kampanya metnini esas al. Sayı, oran, tarih, kod ve koşulları aynen koru. Kısa, açık ve kullanıcı sorusuna doğrudan cevap ver."""

    question: str = dspy.InputField(desc="Kullanıcının Türkçe sorusu")
    campaign_text: str = dspy.InputField(desc="Getirilen gerçek kampanya metni")
    classification_json: str = dspy.InputField(desc="Sınıflandırma modelinin yapılandırılmış çıktısı")
    entities_json: str = dspy.InputField(desc="Hibrit NER modelinin yapılandırılmış çıktısı")
    answer: str = dspy.OutputField(desc="Kanıta dayalı, kısa Türkçe yanıt")


class CampaignAnswerProgram(dspy.Module):
    def __init__(self) -> None:
        super().__init__()
        self.respond = dspy.Predict(CampaignAnswer)

    def forward(
        self,
        question: str,
        campaign_text: str,
        classification_json: str,
        entities_json: str,
    ):
        return self.respond(
            question=question,
            campaign_text=campaign_text,
            classification_json=classification_json,
            entities_json=entities_json,
        )

