import re
import unicodedata

from src.policy.contracts import Action, PolicyDecision

_IBAN_RE = re.compile(r"\bTR\d{24}\b", re.IGNORECASE)
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){15,19}(?!\d)")
_TCKN_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")
_INTERNAL_INFORMATION_RE = re.compile(
    r"\b(?:"
    r"(?:sistem|system|gelistirici|developer)\s+(?:prompt\w*|talimat\w*|instruction\w*)"
    r"|(?:gizli|sakli|hidden)\s+(?:"
    r"politika\w*|polic\w*|talimat\w*|instruction\w*|prompt\w*"
    r"|anahtar\w*|kimlik bilg\w*|credential\w*|secret\w*"
    r")"
    r"|api\s+(?:key\w*|anahtar\w*)"
    r"|(?:credential|secret)\w*"
    r")\b"
)
_EXTRACTION_RE = re.compile(
    r"\b(?:goster\w*|acikla\w*|paylas\w*|yazdir\w*|ver\w*|ifsa\w*|cikar\w*"
    r"|show\w*|reveal\w*|print\w*|expose\w*|repeat\w*)\b"
)
_TRANSFER_CONCEPT_RE = re.compile(r"\b(?:havale\w*|eft\w*|para transfer\w*)\b")
_TRANSFER_ACTION_RE = re.compile(
    r"\b(?:yap\w*|gonder\w*|aktar\w*|gerceklestir\w*)\b"
)
_COMPLAINT_CONCEPT_RE = re.compile(r"\bsikayet\w*\b")
_COMPLAINT_ACTION_RE = re.compile(
    r"\b(?:olustur\w*|kaydet\w*|ac(?:mak|in(?:iz)?)?|ilet(?:mek|in(?:iz)?)?)\b"
)
_APPLICATION_CONCEPT_RE = re.compile(r"\b(?:basvuru\w*|finansman\w*)\b")
_APPLICATION_ACTION_RE = re.compile(
    r"\b(?:basvur(?:mak|mayi|uyorum|urum|alim|un(?:uz)?|acag\w*|abilir\w*)?|yap\w*)\b"
)


def _normalize(message: str) -> str:
    folded = unicodedata.normalize("NFKD", message.casefold().replace("ı", "i"))
    return "".join(character for character in folded if not unicodedata.combining(character))


def _clauses(message: str) -> tuple[str, ...]:
    normalized = _normalize(message)
    return tuple(
        clause.strip()
        for clause in re.split(
            r"[.!?;,\n]+|\b(?:ve|ama|fakat|ancak|and|but)\b",
            normalized,
        )
        if clause.strip()
    )


def _is_transaction_request(message: str) -> bool:
    intent_patterns = (
        (_TRANSFER_CONCEPT_RE, _TRANSFER_ACTION_RE),
        (_COMPLAINT_CONCEPT_RE, _COMPLAINT_ACTION_RE),
        (_APPLICATION_CONCEPT_RE, _APPLICATION_ACTION_RE),
    )
    return any(
        concept.search(clause) and action.search(clause)
        for clause in _clauses(message)
        for concept, action in intent_patterns
    )


def _is_internal_information_request(message: str) -> bool:
    return any(
        _INTERNAL_INFORMATION_RE.search(clause) and _EXTRACTION_RE.search(clause)
        for clause in _clauses(message)
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
        if _is_internal_information_request(message):
            return PolicyDecision(
                action=Action.REFUSE,
                in_domain=False,
                intent="internal_information",
                confidence=1.0,
                reason_code="internal_information_request",
                safe_message=(
                    "Bu iç bilgiyi paylaşamam; katılım bankacılığı "
                    "sorularında yardımcı olabilirim."
                ),
            )
        if _is_transaction_request(message):
            return PolicyDecision(
                action=Action.REDIRECT,
                in_domain=True,
                intent="transaction_execution",
                confidence=1.0,
                reason_code="transaction_execution",
                safe_message=(
                    "Bu işlemi gerçekleştiremiyorum; lütfen bankanızın "
                    "resmî kanalını kullanın."
                ),
            )
        return None
