import json
from src.preprocessing.clean_text import (
    clean_text,
    normalize_link_text,
    preprocess_dataset,
    preprocess_record,
    tokenize_turkish,
)


def test_clean_text_preserves_turkish_and_paragraphs():
    raw = "<p>Kuveyt&nbsp;Türk’te fırsat!</p><p>  1.000 TL  </p>"
    assert clean_text(raw) == "Kuveyt Türk’te fırsat!\n1.000 TL"


def test_normalize_link_text_removes_invisible_chars_and_cta_punctuation():
    assert normalize_link_text("Güncel\u00ad kampanyaları gör →") == (
        "güncel kampanyaları gör"
    )


def test_turkish_tokenizer_keeps_apostrophe_and_numbers():
    assert tokenize_turkish("Türkiye'de %2,99 ve 1.000 TL") == [
        "türkiye'de",
        "2,99",
        "ve",
        "1.000",
        "tl",
    ]


def test_turkish_tokenizer_does_not_split_capital_dotted_i():
    assert tokenize_turkish("İşlemlerin IŞIK koşulları") == [
        "işlemlerin",
        "ışık",
        "koşulları",
    ]


def test_preprocess_dataset_adds_derived_fields():
    result = preprocess_dataset({"records": [{"content": "Merhaba dünya"}]})
    assert result["record_count"] == 1
    assert result["records"][0]["tokens"] == ["merhaba", "dünya"]
    assert result["records"][0]["token_count"] == 2


def test_preprocess_record_adds_structured_prd_fields():
    record = {
        "content": "%1,89 kâr payı ile 120 ay vadeli konut finansmanı",
        "start_date": "2026-08-01",
        "end_date": "2026-12-31",
    }

    result = preprocess_record(record)

    assert result["structured"]["profit_share_rate"] == 0.0189
    assert result["structured"]["term_months"] == 120
    assert result["structured"]["campaign_end_date"] == "2026-12-31"


def test_preprocess_dataset_requires_records_list():
    import pytest

    from src.preprocessing.clean_text import preprocess_dataset

    with pytest.raises(ValueError, match="records"):
        preprocess_dataset({"kayitlar": []})


def _run_cli(argv):
    import sys

    from src.preprocessing.clean_text import main

    original = sys.argv
    sys.argv = argv
    try:
        return main()
    finally:
        sys.argv = original


def test_cli_preprocesses_json_payload_atomically(tmp_path, capsys):
    payload = {
        "records": [
            {
                "id": "1",
                "title": "Kampanya",
                "content": "<p>%2,50&nbsp;kâr payı</p>",
                "source_url": "https://ornek.example/k",
            }
        ]
    }
    source = tmp_path / "payload.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "out" / "processed.json"

    exit_code = _run_cli(["clean_text.py", str(source), str(output)])

    assert exit_code == 0
    processed = json.loads(output.read_text(encoding="utf-8"))
    assert processed["record_count"] == 1
    assert "preprocessed_at" in processed
    record = processed["records"][0]
    assert record["token_count"] > 0
    assert record["canonical_url"] == "https://ornek.example/k"
    assert "1 kayit yazildi" in capsys.readouterr().out
    assert not output.with_suffix(".json.tmp").exists()
