"""Intent, slot ve terminoloji çözümlemeli deterministik sorgu derleyici."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Iterable

from src.knowledge import TerminologyService
from src.preprocessing.clean_text import turkish_lower


PROJECT_ROOT = Path(__file__).resolve().parents[2]

NOMINAL_PLURAL = r"(?:lar|ler)?"
NOMINAL_POSSESSIVE = r"(?:ım|im|um|üm|ımız|imiz|umuz|ümüz|ı|i|u|ü|sı|si|su|sü)?"
NOMINAL_CASE = (
    r"(?:a|e|da|de|ta|te|dan|den|tan|ten|ın|in|un|ün|"
    r"nı|ni|nu|nü|nın|nin|nun|nün|ndan|nden|la|le|yla|yle|"
    r"ıyla|iyle|uyla|üyle)?"
)
NOMINAL_SUFFIX_PATTERN = NOMINAL_PLURAL + NOMINAL_POSSESSIVE + NOMINAL_CASE
QUESTION_SUFFIXES = ("", "tır", "tir", "tur", "tür")
GENERIC_ONTOLOGY_ENTITIES = {
    "CAMPAIGN",
    "CONDITION",
    "DOCUMENT",
    "END_DATE",
    "START_DATE",
}

BANK_ALIASES = {
    "adil katılım": "adil-katilim",
    "albaraka": "albaraka-turk",
    "albaraka türk": "albaraka-turk",
    "dünya katılım": "dunya-katilim",
    "hayat finans": "hayat-finans",
    "kuveyt türk": "kuveyt-turk",
    "tom bank": "tom-katilim",
    "t.o.m.": "tom-katilim",
    "emlak katılım": "emlak-katilim",
    "türkiye finans": "turkiye-finans",
    "vakıf katılım": "vakif-katilim",
    "ziraat katılım": "ziraat-katilim",
}


def _answer_confidence(
    *, typed: int, evidenced: int, candidates: int
) -> tuple[float, dict[str, float]]:
    """Score answer verifiability independently from route selection."""

    if candidates <= 0:
        return 0.0, {
            "typed_field": 0.0,
            "evidence_coverage": 0.0,
            "candidate_coverage": 0.0,
        }
    typed_score = min(1.0, typed / candidates)
    evidence_score = min(1.0, evidenced / candidates)
    candidate_score = min(1.0, candidates / 5)
    score = round(
        0.45 * typed_score + 0.45 * evidence_score + 0.10 * candidate_score,
        4,
    )
    return score, {
        "typed_field": typed_score,
        "evidence_coverage": evidence_score,
        "candidate_coverage": candidate_score,
    }


@dataclass(frozen=True, slots=True)
class QueryPlan:
    original_query: str
    canonical_query: str
    intent: str
    route: str
    slots: dict[str, Any]
    filters: dict[str, Any]
    terminology_rewrites: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    confidence_components: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DomainQueryCompiler:
    """Serbest Türkçe sorguyu şema doğrulanabilir bir yürütme planına çevirir."""

    def __init__(self, terminology: TerminologyService | None = None) -> None:
        self.terminology = terminology or TerminologyService()
        rules = json.loads(
            (PROJECT_ROOT / "configs" / "query_rules.json").read_text(encoding="utf-8")
        )
        self.product_terms = rules["product_terms"]
        self.product_search_patterns = tuple(rules["product_search_patterns"])
        self.structured_intents = set(rules["structured_intents"])
        self.blocked_intents = set(rules["blocked_transaction_intents"])

    @staticmethod
    def _normalized(value: str) -> str:
        return " ".join(turkish_lower(value).split())

    @classmethod
    def _contains_phrase(cls, value: str, phrase: str) -> bool:
        normalized = cls._normalized(value)
        target = cls._normalized(phrase)
        return bool(re.search(rf"(?<!\w){re.escape(target)}(?!\w)", normalized))

    @classmethod
    def _contains_suffixed_phrase(
        cls, value: str, phrase: str, suffixes: Iterable[str]
    ) -> bool:
        normalized = cls._normalized(value)
        target = cls._normalized(phrase)
        suffix_pattern = "|".join(
            re.escape(suffix) for suffix in sorted(set(suffixes), key=len, reverse=True)
        )
        return bool(
            re.search(
                rf"(?<!\w){re.escape(target)}(?:{suffix_pattern})(?!\w)",
                normalized,
            )
        )

    @classmethod
    def _contains_nominal_phrase(cls, value: str, phrase: str) -> bool:
        normalized = cls._normalized(value)
        target = cls._normalized(phrase)
        return bool(
            re.search(
                rf"(?<!\w){re.escape(target)}{NOMINAL_SUFFIX_PATTERN}(?!\w)",
                normalized,
            )
        )

    def _intent(
        self,
        query: str,
        bank_count: int,
        *,
        has_product: bool = False,
        terminology_matches: Iterable[dict[str, Any]] = (),
        metric: str | None = None,
    ) -> tuple[str, float]:
        normalized = self._normalized(query)
        matches = list(terminology_matches)
        entities = {str(item.get("entity") or "") for item in matches}
        has_domain_terminology = any(
            str(item.get("entity") or "") not in GENERIC_ONTOLOGY_ENTITIES
            for item in matches
        )
        has_domain = (
            has_product
            or bool(bank_count)
            or has_domain_terminology
            or metric == "REWARD_AMOUNT"
        )
        if any(
            term in normalized
            for term in ("şikâyet", "şikayet", "itiraz")
        ):
            return "complaint_support", 0.99
        if self._contains_nominal_phrase(normalized, "katılım banka") and any(
            term in normalized
            for term in (
                "kaç",
                "sayısı",
                "sayisi",
                "say",
                "sayar",
                "liste",
                "listele",
            )
        ):
            return "bank_list", 0.99
        if self._contains_nominal_phrase(normalized, "kampanya") and any(
            self._contains_phrase(normalized, term)
            for term in ("kaç", "sayısı", "sayisi", "say", "sayar", "adet")
        ):
            return "campaign_count", 0.99
        if (bank_count > 1 or has_domain) and any(
            self._contains_phrase(normalized, term)
            for term in (
                "karşılaştır",
                "kıyasla",
                "hangisi daha",
                "hangi ürün daha avantajlı",
                "arasındaki fark",
                "en düşük",
                "en yüksek",
                "en uygun",
                "en avantajlı",
                "hangisi",
            )
        ):
            return "product_comparison", 0.99
        definition_requested = any(
            self._contains_phrase(normalized, term)
            for term in (
                "nedir",
                "ne demek",
                "ne anlama geliyor",
                "açıklar mısın",
                "ilkeleri nelerdir",
                "esasları nelerdir",
            )
        )
        if definition_requested:
            return ("definition", 0.98) if has_domain else ("unknown", 0.0)
        if has_domain and metric == "PROFIT_RATE" and (
            any(
                self._contains_phrase(normalized, term)
                for term in ("kâr payı oranı kaç", "kar payı oranı kaç")
            )
            or self._contains_suffixed_phrase(
                normalized, "oran kaç", QUESTION_SUFFIXES
            )
        ):
            return "rate_query", 0.98
        if has_domain and metric == "MATURITY" and any(
            self._contains_phrase(normalized, term) for term in ("vade kaç", "kaç ay")
        ):
            return "maturity_query", 0.96
        if "nasıl yaparım" in normalized or "nasıl yapılır" in normalized:
            return "transaction_howto", 0.96
        if entities & {"INCOTERM", "TRADE_FINANCE_TERM", "TRADE_FINANCE_PRODUCT"}:
            return "trade_finance_query", 0.94
        if "AGRICULTURE_TERM" in entities:
            return "agriculture_finance_query", 0.94
        if has_domain and any(
            term in normalized
            for term in ("ilişkilidir", "ilişkili", "bağlantılı", "arasındaki ilişki")
        ):
            return "relationship_query", 0.97
        if has_domain and any(
            term in normalized
            for term in (
                "hangi belge",
                "hangi teminat",
                "hangi koşul",
                "hangi şart",
                "neleri gerektir",
                "evrak",
                "belge",
            )
        ):
            return "application_requirements", 0.97
        matched_product_patterns = [
            pattern
            for pattern in self.product_search_patterns
            if self._contains_phrase(normalized, pattern)
        ]
        if matched_product_patterns and (
            has_domain
            or any(
                "finansman" in self._normalized(pattern)
                for pattern in matched_product_patterns
            )
        ):
            return "product_search", 0.55
        priorities = (
            "application_requirements",
            "trade_finance_query",
            "agriculture_finance_query",
            "investment_query",
            "rate_query",
            "maturity_query",
            "campaign_query",
            "transaction_howto",
            "definition",
        )
        scored: list[tuple[int, int, str]] = []
        domain_required = {
            "application_requirements",
            "rate_query",
            "maturity_query",
            "transaction_howto",
            "definition",
        }
        for priority, intent in enumerate(priorities):
            if intent in domain_required and not has_domain:
                continue
            patterns = self.terminology.intent_schema[intent].get("patterns", [])
            score = sum(
                (
                    self._contains_nominal_phrase(normalized, pattern)
                    if pattern in {"kampanya", "fırsat"}
                    else self._contains_phrase(normalized, pattern)
                )
                for pattern in patterns
            )
            if score:
                scored.append((score, -priority, intent))
        if scored:
            score, _, intent = max(scored)
            return intent, min(0.98, 0.78 + score * 0.08)
        if has_domain:
            return "product_search", 0.55
        return "unknown", 0.0

    @staticmethod
    def route_for(
        intent: str,
        slots: dict[str, Any],
        *,
        trusted_domain: bool,
    ) -> str:
        metric = slots.get("metric")
        aggregation = slots.get("aggregation")
        if intent in {"complaint_support", "transaction_howto", "unknown"}:
            return "SAFE_REDIRECT"
        if intent == "bank_list" and trusted_domain:
            return "STRUCTURED_SQL"
        if (
            intent == "campaign_count"
            and aggregation == "COUNT"
            and trusted_domain
        ):
            return "STRUCTURED_SQL"
        if intent == "rate_query" and metric == "PROFIT_RATE" and trusted_domain:
            return "STRUCTURED_SQL"
        if intent == "maturity_query" and metric == "MATURITY" and trusted_domain:
            return "STRUCTURED_SQL"
        if (
            intent == "product_comparison"
            and metric
            and aggregation in {"MIN", "MAX"}
            and trusted_domain
        ):
            return "STRUCTURED_SQL"
        return "HYBRID_RAG"

    def _banks(
        self, query: str, known_banks: Iterable[dict[str, str]] | None
    ) -> list[str]:
        normalized = self._normalized(query)
        aliases = dict(BANK_ALIASES)
        for bank in known_banks or ():
            slug = str(bank.get("slug") or "").strip()
            name = str(bank.get("name") or "").strip()
            if slug and name:
                short_name = re.sub(
                    r"\s+(?:katılım\s+bankası|bankası)\s+a\.ş\.?$",
                    "",
                    self._normalized(name),
                )
                aliases[short_name] = slug
        matches = [
            (normalized.find(alias), -len(alias), slug)
            for alias, slug in aliases.items()
            if self._contains_phrase(normalized, alias)
        ]
        return list(dict.fromkeys(slug for _, _, slug in sorted(matches)))

    def _product_slots(self, query: str) -> dict[str, Any]:
        normalized = self._normalized(query)
        selected: tuple[int, dict[str, Any]] | None = None
        for term, values in self.product_terms.items():
            if not self._contains_nominal_phrase(normalized, term):
                continue
            candidate = (len(term), dict(values))
            if selected is None or candidate[0] > selected[0]:
                selected = candidate
        return selected[1] if selected else {}

    @staticmethod
    def _metric(query: str) -> tuple[str | None, str | None]:
        normalized = turkish_lower(query)
        if (
            DomainQueryCompiler._contains_phrase(normalized, "kâr payı")
            or DomainQueryCompiler._contains_phrase(normalized, "kar payı")
            or DomainQueryCompiler._contains_phrase(normalized, "oran")
        ):
            aggregation = (
                "MIN"
                if "düşük" in normalized
                else "MAX" if "yüksek" in normalized else None
            )
            return "PROFIT_RATE", aggregation
        if "vade" in normalized or "kaç ay" in normalized:
            return "MATURITY", "MAX" if "uzun" in normalized else None
        if "masraf" in normalized or "ücret" in normalized or "aidat" in normalized:
            return "FEE", "MIN" if "düşük" in normalized or "az" in normalized else None
        if "ödül" in normalized or "puan" in normalized:
            return "REWARD_AMOUNT", "MAX" if "yüksek" in normalized else None
        return None, None

    @staticmethod
    def confidence_evidence(
        slots: dict[str, Any],
        filters: dict[str, Any],
        terminology_matches: Iterable[dict[str, Any]],
        *,
        source: str,
        trusted_domain_sources: Iterable[str] = (),
    ) -> dict[str, Any]:
        trusted_sources = sorted(set(trusted_domain_sources))
        return {
            "source": source,
            "trusted_domain": bool(trusted_sources),
            "trusted_domain_sources": trusted_sources,
            "product": {
                key: slots[key]
                for key in ("product_type", "financing_type")
                if slots.get(key) is not None
            },
            "terminology": list(terminology_matches),
            "filters": dict(filters),
        }

    def _trusted_domain_sources(
        self,
        query: str,
        slots: dict[str, Any],
        terminology_matches: Iterable[dict[str, Any]],
    ) -> list[str]:
        sources: list[str] = []
        if slots.get("product_type") or slots.get("financing_type"):
            sources.append("product_term")
        if slots.get("banks"):
            sources.append("bank_alias")
        if any(
            str(item.get("entity") or "") not in GENERIC_ONTOLOGY_ENTITIES
            for item in terminology_matches
        ):
            sources.append("domain_terminology")
        if self._contains_nominal_phrase(query, "katılım banka"):
            sources.append("participation_bank_phrase")
        if self._contains_nominal_phrase(query, "kampanya"):
            sources.append("campaign_phrase")
        if slots.get("metric") == "REWARD_AMOUNT":
            sources.append("reward_metric_phrase")
        return sorted(set(sources))

    def compile(
        self,
        query: str,
        *,
        known_banks: Iterable[dict[str, str]] | None = None,
    ) -> QueryPlan:
        original = str(query or "").strip()
        if not original:
            raise ValueError("Sorgu boş olamaz")
        canonical, rewrites = self.terminology.rewrite_query(original)
        banks = self._banks(canonical, known_banks)
        slots = self._product_slots(canonical)
        has_product = bool(slots)
        terminology_matches = self.terminology.find_terms(canonical, limit=12)
        metric, aggregation = self._metric(canonical)
        intent, confidence = self._intent(
            canonical,
            len(banks),
            has_product=has_product,
            terminology_matches=terminology_matches,
            metric=metric,
        )
        if intent == "campaign_count":
            aggregation = "COUNT"
        slots.update({"banks": banks, "metric": metric, "aggregation": aggregation})
        filters = {
            key: value
            for key, value in {
                "bank_slugs": banks,
                "product_type": slots.get("product_type"),
                "financing_type": slots.get("financing_type"),
                "active_only": True,
            }.items()
            if value not in (None, [], "")
        }
        trusted_domain_sources = self._trusted_domain_sources(
            canonical, slots, terminology_matches
        )
        warnings: list[str] = []
        route = self.route_for(
            intent, slots, trusted_domain=bool(trusted_domain_sources)
        )
        if intent in self.blocked_intents:
            warnings.append("Sistem müşteri işlemi veya şikâyet kaydı gerçekleştirmez")
        if intent == "product_comparison" and len(banks) < 2:
            warnings.append("Karşılaştırma için banka filtresi belirtilmedi")
        rewrites.extend(terminology_matches[:5])
        unique_rewrites = list(
            {
                (
                    item.get("surface"),
                    item.get("canonical"),
                    item.get("term_id"),
                ): item
                for item in rewrites
            }.values()
        )
        confidence_components = self.confidence_evidence(
            slots,
            filters,
            unique_rewrites,
            source="deterministic",
            trusted_domain_sources=trusted_domain_sources,
        )
        return QueryPlan(
            original_query=original,
            canonical_query=canonical,
            intent=intent,
            route=route,
            slots=slots,
            filters=filters,
            terminology_rewrites=unique_rewrites,
            confidence=confidence,
            confidence_components=confidence_components,
            warnings=warnings,
        )
