import pytest

from src.extraction.campaign_fields import extract_prd_fields


@pytest.mark.parametrize(
    ("surface", "expected"),
    (("%2,05 kâr payı", 0.0205), ("% 2.05 kâr payı", 0.0205), ("2.05 % kâr payı", 0.0205)),
)
def test_profit_rate_format_variants_are_normalized(surface, expected):
    result = extract_prd_fields(f"Konut finansmanı {surface} ile sunulur.")

    assert result["profit_share_rate"] == expected
    assert result["fields"]["profit_share_rate"]["status"] == "EXPLICIT"


def test_field_evidence_offsets_point_to_exact_source_text():
    text = "%20 indirim ve %1,89 kâr payı ile 24 ay vadeli konut finansmanı."
    result = extract_prd_fields(text)

    field = result["fields"]["profit_share_rate"]
    evidence = field["evidence"]
    assert text[evidence["char_start"] : evidence["char_end"]] == evidence["text"]
    assert result["discount_rate"] == 0.2
    assert result["profit_share_rate"] == 0.0189


def test_reward_and_financing_amount_are_not_interchanged():
    result = extract_prd_fields(
        "250.000 TL'ye kadar finansman kullananlara 500 TL ödül sunulur."
    )

    assert result["financing_amount"]["amount"] == 250000.0
    assert result["reward_amount"]["amount"] == 500.0
    assert result["fields"]["financing_amount"]["status"] == "EXPLICIT"
    assert result["fields"]["financing_amount"]["unit"] == "TRY"
    assert result["fields"]["reward_amount"]["unit"] == "TRY"


def test_campaign_benefit_keeps_sentence_as_evidence():
    result = extract_prd_fields("Yeni müşterilere ücretsiz sigorta avantajı sunulur.")

    field = result["fields"]["campaign_benefit"]
    assert field["status"] == "EXPLICIT"
    assert field["evidence"]["text"] == result["campaign_benefit"]


def test_missingness_distinguishes_implicit_not_stated_and_not_applicable():
    implicit = extract_prd_fields("Avantajlı kâr payı ile konut finansmanı.")
    absent = extract_prd_fields("Konut finansmanı başvurusu şubeden yapılır.")
    card = extract_prd_fields("Kart harcamalarına 500 TL ödül.")

    assert implicit["fields"]["profit_share_rate"]["status"] == "IMPLICIT"
    assert absent["fields"]["profit_share_rate"]["status"] == "NOT_STATED"
    assert card["fields"]["profit_share_rate"]["status"] == "NOT_APPLICABLE"


def test_malformed_and_conflicting_rates_are_reported_without_guessing():
    malformed = extract_prd_fields("Kâr payı oranı %x olarak duyuruldu.")
    conflict = extract_prd_fields(
        "%1,89 kâr payı ilk dönem, %2,09 kâr payı sonraki dönem uygulanır."
    )

    assert malformed["fields"]["profit_share_rate"]["status"] == "EXTRACTION_FAILED"
    assert conflict["profit_share_rate"] is None
    assert conflict["fields"]["profit_share_rate"]["status"] == "CONFLICT"
    assert conflict["fields"]["profit_share_rate"]["conflicting_values"] == [
        0.0189,
        0.0209,
    ]


def test_explicit_dates_without_text_span_are_marked_implicit():
    result = extract_prd_fields(
        "Kampanya detayları.", start_date="2026-01-01", end_date="2026-01-31"
    )

    assert result["fields"]["campaign_start_date"]["status"] == "IMPLICIT"
    assert result["fields"]["campaign_end_date"]["status"] == "IMPLICIT"
