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

    def _intent(self, query: str, bank_count: int) -> tuple[str, float]:
        normalized = self._normalized(query)
        if any(term in normalized for term in ("şikâyet", "şikayet", "itiraz")):
            return "complaint_support", 0.99
        if "katılım banka" in normalized and any(
            term in normalized
            for term in ("kaç", "sayısı", "sayisi", "say", "liste")
        ):
            return "bank_list", 0.99
        if "kampanya" in normalized and any(
            term in normalized
            for term in ("kaç", "sayısı", "sayisi", "say", "adet")
        ):
            return "campaign_count", 0.99
        if bank_count > 1 or any(
            term in normalized
            for term in (
                "karşılaştır",
                "hangisi daha",
                "hangi ürün daha avantajlı",
                "arasındaki fark",
                "en düşük",
                "en yüksek",
            )
        ):
            return "product_comparison", 0.99
        if any(
            term in normalized
            for term in ("nedir", "ne demek", "ne anlama geliyor", "açıklar mısın")
        ):
            return "definition", 0.98
        if any(
            term in normalized
            for term in ("kâr payı oranı kaç", "kar payı oranı kaç", "oran kaç")
        ):
            return "rate_query", 0.98
        if "vade kaç" in normalized or "kaç ay" in normalized:
            return "maturity_query", 0.96
        if "nasıl yaparım" in normalized or "nasıl yapılır" in normalized:
            return "transaction_howto", 0.96
        entities = {
            str(item.get("entity") or "")
            for item in self.terminology.find_terms(query, limit=12)
        }
        if entities & {"INCOTERM", "TRADE_FINANCE_TERM", "TRADE_FINANCE_PRODUCT"}:
            return "trade_finance_query", 0.94
        if "AGRICULTURE_TERM" in entities:
            return "agriculture_finance_query", 0.94
        if any(
            term in normalized
            for term in ("ilişkilidir", "ilişkili", "bağlantılı", "arasındaki ilişki")
        ):
            return "relationship_query", 0.97
        if any(
            term in normalized
            for term in (
                "hangi belge",
                "hangi teminat",
                "hangi koşul",
                "hangi şart",
                "neleri gerektir",
            )
        ):
            return "application_requirements", 0.97
        if any(
            self._normalized(pattern) in normalized
            for pattern in self.product_search_patterns
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
        for priority, intent in enumerate(priorities):
            patterns = self.terminology.intent_schema[intent].get("patterns", [])
            score = sum(self._normalized(pattern) in normalized for pattern in patterns)
            if score:
                scored.append((score, -priority, intent))
        if scored:
            score, _, intent = max(scored)
            return intent, min(0.98, 0.78 + score * 0.08)
        if bank_count or self.terminology.find_terms(query, limit=1):
            return "product_search", 0.55
        return "unknown", 0.0

    @staticmethod
    def _route_for(
        intent: str, metric: str | None, aggregation: str | None
    ) -> str:
        if intent in {"complaint_support", "transaction_howto", "unknown"}:
            return "SAFE_REDIRECT"
        if intent in {"bank_list", "campaign_count", "rate_query", "maturity_query"}:
            return "STRUCTURED_SQL"
        if (
            intent == "product_comparison"
            and metric
            and aggregation in {"MIN", "MAX"}
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
            if alias in normalized
        ]
        return list(dict.fromkeys(slug for _, _, slug in sorted(matches)))

    def _product_slots(self, query: str) -> dict[str, Any]:
        normalized = self._normalized(query)
        selected: tuple[int, dict[str, Any]] | None = None
        for term, values in self.product_terms.items():
            if self._normalized(term) not in normalized:
                continue
            candidate = (len(term), dict(values))
            if selected is None or candidate[0] > selected[0]:
                selected = candidate
        return selected[1] if selected else {}

    @staticmethod
    def _metric(query: str) -> tuple[str | None, str | None]:
        normalized = turkish_lower(query)
        if (
            "kâr payı" in normalized
            or "kar payı" in normalized
            or "oran" in normalized
        ):
            aggregation = (
                "MIN"
                if "düşük" in normalized
                else "MAX" if "yüksek" in normalized else None
            )
            return "PROFIT_RATE", aggregation
        if "vade" in normalized or "kaç ay" in normalized:
            return "MATURITY", "MAX" if "uzun" in normalized else None
        if "masraf" in normalized or "ücret" in normalized:
            return "FEE", "MIN" if "düşük" in normalized or "az" in normalized else None
        if "ödül" in normalized or "puan" in normalized:
            return "REWARD_AMOUNT", "MAX" if "yüksek" in normalized else None
        return None, None

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
        intent, confidence = self._intent(canonical, len(banks))
        slots = self._product_slots(canonical)
        metric, aggregation = self._metric(canonical)
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
        warnings: list[str] = []
        route = self._route_for(intent, metric, aggregation)
        if intent in self.blocked_intents:
            warnings.append("Sistem müşteri işlemi veya şikâyet kaydı gerçekleştirmez")
        if intent == "product_comparison" and len(banks) < 2:
            warnings.append("Karşılaştırma için banka filtresi belirtilmedi")
        rewrites.extend(self.terminology.find_terms(canonical, limit=5))
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
        confidence_components = {
            "product": {
                key: slots[key]
                for key in ("product_type", "financing_type")
                if slots.get(key) is not None
            },
            "terminology": unique_rewrites,
            "filters": dict(filters),
        }
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
