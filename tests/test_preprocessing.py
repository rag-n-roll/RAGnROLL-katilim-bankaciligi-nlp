from src.preprocessing.clean_text import clean_text, preprocess_dataset, tokenize_turkish


def test_clean_text_preserves_turkish_and_paragraphs():
    raw = "<p>Kuveyt&nbsp;Türk’te fırsat!</p><p>  1.000 TL  </p>"
    assert clean_text(raw) == "Kuveyt Türk’te fırsat!\n1.000 TL"


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
