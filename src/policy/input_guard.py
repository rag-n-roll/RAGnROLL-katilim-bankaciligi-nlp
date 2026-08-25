import re

from src.policy.contracts import Action, PolicyDecision

_IBAN_RE = re.compile(r"\bTR\d{24}\b", re.IGNORECASE)
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){15,19}(?!\d)")
_TCKN_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")
_SECRET_RE = re.compile(
    r"\b(?:sistem promptu|system prompt|gizli anahtar|api key)\b",
    re.IGNORECASE,
)
_TRANSACTION_RE = re.compile(
    r"\b(?:havale|eft|para transferi|şikâyet kaydı|başvuru yap)\b",
    re.IGNORECASE,
)


class InputGuard:
    def inspect(self, message: str) -> PolicyDecision | None:
        if _IBAN_RE.search(message) or _CARD_RE.search(message) or _TCKN_RE.search(message):
            return PolicyDecision(
                action=Action.REDIRECT,
                in_domain=True,
                intent="sensitive_data",
                confidence=1.0,
                reason_code="sensitive_financial_identifier",
                safe_message="Güvenliğiniz için hesap veya kart bilgisi paylaşmayın.",
            )
        if _SECRET_RE.search(message):
            return PolicyDecision(
                action=Action.REFUSE,
                in_domain=False,
                intent="internal_information",
                confidence=1.0,
                reason_code="internal_information_request",
                safe_message="Bu iç bilgiyi paylaşamam; katılım bankacılığı sorularında yardımcı olabilirim.",
            )
        if _TRANSACTION_RE.search(message):
            return PolicyDecision(
                action=Action.REDIRECT,
                in_domain=True,
                intent="transaction_execution",
                confidence=1.0,
                reason_code="transaction_execution",
                safe_message="Bu işlemi gerçekleştiremiyorum; lütfen bankanızın resmî kanalını kullanın.",
            )
        return None
