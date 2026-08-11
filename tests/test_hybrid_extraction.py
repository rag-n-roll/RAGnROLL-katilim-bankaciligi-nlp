from src.extraction.hybrid import HybridExtractor


def test_hybrid_extractor_works_without_model():
    result = HybridExtractor().extract("%1,89 kâr payı oranı ile 36 ay vadeli finansman")

    assert result["profit_share_rate"] == 0.0189
    assert result["duration"]["value"] == 36
    assert result["model_entities"] == []
    assert result["extraction_method"] == "rules-v1"
