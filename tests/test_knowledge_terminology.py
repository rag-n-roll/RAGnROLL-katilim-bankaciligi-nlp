from src.knowledge.terminology import TerminologyService


def test_resolve_prefers_configured_query_rules():
    service = TerminologyService()
    result = service.resolve("faiz")

    assert result["canonical"] == "kâr payı"
    assert result["source"] == "query_rules"
    assert result["surface"] == "faiz"


def test_resolve_uses_reverse_alias_ontology_index():
    service = TerminologyService()
    result = service.resolve("ehliyet")

    assert result["canonical"] == "Sürücü Belgesi"
    assert result["term_id"] == "TRM0018"
    assert result["entity"] == "DOCUMENT"
    assert result["source"] == "ontology"


def test_resolve_matches_canonical_terms_directly():
    service = TerminologyService()
    result = service.resolve("bloke")

    assert result is not None
    assert result["canonical"] == "Bloke"
    assert result["term_id"] == "TRM0001"


def test_resolve_returns_none_for_unknown_surface():
    service = TerminologyService()
    assert service.resolve("xyz bilinmeyen terim") is None


def test_rewrite_query_replaces_known_aliases():
    service = TerminologyService()

    rewritten, matches = service.rewrite_query("Ev kredisi faiz oranı kaç?")

    assert "konut finansmanı" in rewritten
    assert "kâr payı oranı" in rewritten
    surfaces = {match["surface"] for match in matches}
    assert {"ev kredisi", "faiz oranı"} <= surfaces
    assert all(match["source"] == "query_rules" for match in matches)


def test_rewrite_query_leaves_unknown_text_untouched():
    service = TerminologyService()

    rewritten, matches = service.rewrite_query("tamamen alakasız metin")

    assert rewritten == "tamamen alakasız metin"
    assert matches == []


def test_find_terms_finds_aliases_and_canonical_terms():
    service = TerminologyService()

    results = service.find_terms("ehliyet ve bloke gerekiyor", limit=10)

    assert results, "en az bir terim bulunmalı"
    term_ids = {result["term_id"] for result in results}
    assert "TRM0018" in term_ids
    assert all(result["source"] == "ontology" for result in results)


def test_find_terms_respects_limit_and_skips_short_aliases():
    service = TerminologyService()

    results = service.find_terms("ehliyet bloke ikamet", limit=2)

    assert len(results) <= 2
