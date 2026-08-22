import json

from src.retrieval.documents import campaign_documents, terminology_documents


def _record(content: str) -> dict:
    return {
        "id": "campaign-1",
        "bank_slug": "ornek",
        "bank_name": "Örnek Katılım",
        "title": "Eğitim kampanyası",
        "content": content,
        "clean_text": content,
        "content_hash": "source-hash",
        "source_url": "https://ornek.example/campaign-1",
        "structured": {
            "product_type": "card",
            "fields": {"reward_amount": {"value": 500, "unit": "TRY"}},
        },
    }


def test_long_campaign_is_split_at_word_boundaries_with_source_offsets():
    content = " ".join(f"Cümle {index} kampanya koşulunu açıklar." for index in range(180))

    documents = campaign_documents(_record(content), max_words=100, overlap_words=10)

    content_chunks = [item for item in documents if item[2]["section"] == "content"]
    assert len(content_chunks) > 1
    assert documents[-1][2]["section"] == "structured_fields"
    for identifier, text, metadata in content_chunks:
        excerpt = content[metadata["char_start"] : metadata["char_end"]]
        assert excerpt
        assert excerpt in text
        assert identifier.startswith("campaign:campaign-1:content:")
        assert metadata["index_hash"]


def test_short_campaign_has_one_stable_overview_chunk():
    first = campaign_documents(_record("Öğrencilere 500 TL ödül sunulur."))
    second = campaign_documents(_record("Öğrencilere 500 TL ödül sunulur."))

    assert len(first) == 1
    assert first == second
    assert first[0][0] == "campaign:campaign-1:overview:000"
    assert first[0][2]["section"] == "overview"


def test_terminology_hash_changes_only_when_source_content_changes(tmp_path):
    path = tmp_path / "terms.jsonl"
    item = {
        "chunk_id": "CHK_1",
        "title": "Murabaha",
        "text": "Murabaha maliyet artı kâr esaslı bir akittir.",
        "metadata": {"term_id": "TRM_1", "source_url": "sözlük"},
    }
    path.write_text(json.dumps(item, ensure_ascii=False) + "\n", encoding="utf-8")
    first = terminology_documents(path)
    second = terminology_documents(path)

    item["text"] += " Bedel taraflarca bilinir."
    path.write_text(json.dumps(item, ensure_ascii=False) + "\n", encoding="utf-8")
    changed = terminology_documents(path)

    assert first == second
    assert first[0][2]["index_hash"] != changed[0][2]["index_hash"]
