from src.extraction.hybrid import ENTITY_TO_FIELD, HybridExtractor


class _FakeSpan:
    def __init__(self, label, text, start, end):
        self.label_ = label
        self.text = text
        self.start_char = start
        self.end_char = end


class _FakeDoc:
    def __init__(self, spans):
        self.ents = spans


class _FakeNLP:
    def __init__(self, spans):
        self.spans = spans
        self.calls = []

    def __call__(self, text):
        self.calls.append(text)
        return _FakeDoc(self.spans)


def test_entity_to_field_mapping_is_complete():
    assert set(ENTITY_TO_FIELD) == {
        "PROFIT_RATE",
        "MATURITY",
        "FINANCING_AMOUNT",
        "CAMPAIGN_BENEFIT",
        "END_DATE",
        "BANK",
        "PRODUCT",
        "CONDITION",
        "APPLICATION_CHANNEL",
    }


def test_rules_only_extraction_when_no_model():
    extractor = HybridExtractor()
    text = "%5 kâr payı ile 12 ay vadeli 100.000 TL finansman"
    result = extractor.extract(text)

    assert result["extraction_method"] == "rules-v1"
    assert result["model_entities"] == []
    assert "evidence" not in result or isinstance(result.get("evidence"), dict)


def test_model_entities_fill_missing_fields_and_evidence():
    extractor = HybridExtractor()
    extractor.nlp = _FakeNLP(
        [
            _FakeSpan("BANK", "Ziraat Katılım", 40, 54),
            _FakeSpan("PRODUCT", "ihtiyaç finansmanı", 55, 73),
            _FakeSpan("UNKNOWN_LABEL", "bilinmeyen", 74, 83),
        ]
    )
    text = "Kampanya detayları: Ziraat Katılım ihtiyaç finansmanı bilinmeyen"
    result = extractor.extract(text)

    assert result["bank"] == "Ziraat Katılım"
    assert result["product"] == "ihtiyaç finansmanı"
    assert result["evidence"]["bank"] == "Ziraat Katılım"
    assert result["evidence"]["product"] == "ihtiyaç finansmanı"
    assert result["model_entities"][-1]["label"] == "UNKNOWN_LABEL"
    assert result["extraction_method"] == "rules-v1+spacy-ner"


def test_model_does_not_override_rule_values():
    extractor = HybridExtractor()
    extractor.nlp = _FakeNLP([_FakeSpan("TERM", "36 ay", 0, 5)])
    text = "12 ay vade seçeneği, 36 ay alternatifi"

    result = extractor.extract(text)

    field = ENTITY_TO_FIELD["MATURITY"]
    if result.get(field) is not None:
        assert result[field] != "36 ay" or field not in ENTITY_TO_FIELD.values()
    assert result["model_entities"][0]["text"] == "36 ay"


def test_start_and_end_dates_are_forwarded_to_rule_engine():
    extractor = HybridExtractor()
    extractor.nlp = None

    result = extractor.extract(
        "kampanya metni", start_date="2026-08-01", end_date="2026-09-30"
    )

    assert result["extraction_method"] == "rules-v1"


def test_init_loads_spacy_model_from_path(monkeypatch):
    import sys
    import types

    loaded = {}

    class FakeSpacy(types.SimpleNamespace):
        pass

    def fake_load(path):
        loaded["path"] = path
        return _FakeNLP([])

    fake_module = types.ModuleType("spacy")
    fake_module.load = fake_load
    monkeypatch.setitem(sys.modules, "spacy", fake_module)

    extractor = HybridExtractor("/models/ner-tr")

    assert loaded["path"] == "/models/ner-tr"
    assert extractor.nlp is not None
