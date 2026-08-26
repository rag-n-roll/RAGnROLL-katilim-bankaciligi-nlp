"""Yerel terminoloji artefaktları için hafif ve önbellekli erişim katmanı."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from src.preprocessing.clean_text import turkish_lower


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalized(value: str) -> str:
    return " ".join(turkish_lower(value).split())


@lru_cache(maxsize=1)
def _resources() -> tuple[
    dict[str, list[dict[str, Any]]],
    dict[str, Any],
    dict[str, str],
    dict[str, dict[str, Any]],
    dict[str, list[str]],
]:
    reverse_path = PROJECT_ROOT / "data" / "ontology" / "reverse_alias_index.json"
    intent_path = PROJECT_ROOT / "data" / "ontology" / "intent_schema.json"
    rules_path = PROJECT_ROOT / "configs" / "query_rules.json"
    aliases_path = PROJECT_ROOT / "data" / "ontology" / "alias_dictionary.json"
    term_intent_path = PROJECT_ROOT / "data" / "ontology" / "term_intent_map.json"
    reverse = _read_json(reverse_path)
    intents = _read_json(intent_path)
    rules = _read_json(rules_path)
    canonical_terms = {
        _normalized(name): value for name, value in _read_json(aliases_path).items()
    }
    configured = {
        _normalized(alias): str(canonical)
        for alias, canonical in rules.get("aliases", {}).items()
    }
    term_intents: dict[str, list[str]] = {}
    if term_intent_path.exists():
        for item in _read_json(term_intent_path):
            tid = item.get("term_id")
            if tid:
                term_intents[tid] = list(item.get("intents", []))
    return reverse, intents, configured, canonical_terms, term_intents


class TerminologyService:
    """Alias çözümleme ve sorgu yeniden yazımını dış servissiz yapar."""

    def __init__(self) -> None:
        reverse, intents, configured, canonical_terms, term_intents = _resources()
        self.reverse_alias_index = reverse
        self.intent_schema = intents
        self.configured_aliases = configured
        self.canonical_terms = canonical_terms
        self.term_intent_map = term_intents

    def resolve(self, surface: str) -> dict[str, Any] | None:
        normalized = _normalized(surface)
        configured = self.configured_aliases.get(normalized)
        if configured:
            return {
                "surface": surface,
                "canonical": configured,
                "term_id": None,
                "entity": None,
                "intents": [],
                "source": "query_rules",
            }
        candidates = self.reverse_alias_index.get(normalized)
        if candidates:
            selected = candidates[0]
            return {
                "surface": surface,
                "canonical": selected.get("canonical", surface),
                "term_id": selected.get("term_id"),
                "entity": selected.get("entity"),
                "intents": self.term_intent_map.get(selected.get("term_id"), []),
                "source": "ontology",
            }
        selected = self.canonical_terms.get(normalized)
        if selected is None:
            return None
        return {
            "surface": surface,
            "canonical": selected.get("canonical", surface),
            "term_id": selected.get("term_id"),
            "entity": selected.get("entity"),
            "intents": self.term_intent_map.get(selected.get("term_id"), []),
            "source": "ontology",
        }

    def rewrite_query(self, text: str) -> tuple[str, list[dict[str, Any]]]:
        rewritten = str(text or "").strip()
        matches: list[dict[str, Any]] = []
        aliases = sorted(self.configured_aliases, key=len, reverse=True)
        for alias in aliases:
            pattern = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)
            match = pattern.search(_normalized(rewritten))
            if not match:
                continue
            canonical = self.configured_aliases[alias]
            rewritten = pattern.sub(canonical, rewritten)
            matches.append(
                {
                    "surface": alias,
                    "canonical": canonical,
                    "term_id": None,
                    "entity": None,
                    "intents": [],
                    "source": "query_rules",
                }
            )
        return rewritten, matches

    def find_terms(self, text: str, *, limit: int = 10) -> list[dict[str, Any]]:
        normalized = _normalized(text)
        results: list[dict[str, Any]] = []
        for alias, candidates in sorted(
            self.reverse_alias_index.items(), key=lambda item: len(item[0]), reverse=True
        ):
            if len(results) >= limit:
                break
            normalized_alias = _normalized(alias)
            if len(normalized_alias) < 3 or not re.search(
                rf"(?<!\w){re.escape(normalized_alias)}(?!\w)", normalized
            ):
                continue
            selected = candidates[0]
            results.append(
                {
                    "surface": alias,
                    "canonical": selected.get("canonical", alias),
                    "term_id": selected.get("term_id"),
                    "entity": selected.get("entity"),
                    "intents": self.term_intent_map.get(selected.get("term_id"), []),
                    "source": "ontology",
                }
            )
        for canonical, item in sorted(
            self.canonical_terms.items(), key=lambda value: len(value[0]), reverse=True
        ):
            if len(results) >= limit:
                break
            if len(canonical) < 3 or not re.search(
                rf"(?<!\w){re.escape(canonical)}(?!\w)", normalized
            ):
                continue
            if any(result.get("term_id") == item.get("term_id") for result in results):
                continue
            results.append(
                {
                    "surface": canonical,
                    "canonical": item.get("canonical", canonical),
                    "term_id": item.get("term_id"),
                    "entity": item.get("entity"),
                    "intents": self.term_intent_map.get(item.get("term_id"), []),
                    "source": "ontology",
                }
            )
        return results
