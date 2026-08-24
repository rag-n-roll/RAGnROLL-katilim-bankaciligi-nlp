import json

from scripts.label_context_entities import (
    ContextEntityLabeler,
    _entity_payload,
    _overlay,
    merge_training_dataset,
    validate_entities,
)


def _entity(text, label, value):
    start = text.index(value)
    return {
        "label": label,
        "evidence": {
            "text": value,
            "char_start": start,
            "char_end": start + len(value),
        },
    }


def test_accepts_fenced_or_bare_entity_arrays_from_model():
    assert _entity_payload("[]") == {"entities": []}
    assert _entity_payload("```json\n[]\n```") == {"entities": []}


def test_validates_channel_named_card_and_customer_reference():
    text = "Paraf kart müşterilerimiz mobil uygulama üzerinden katılabilir."
    payload = {
        "entities": [
            _entity(text, "CARD_NAME", "Paraf"),
            _entity(text, "CUSTOMER_REFERENCE", "müşterilerimiz"),
            _entity(text, "APPLICATION_CHANNEL", "mobil uygulama"),
        ]
    }

    result = validate_entities(payload, text=text)

    assert [item["label"] for item in result] == [
        "CARD_NAME",
        "CUSTOMER_REFERENCE",
        "APPLICATION_CHANNEL",
    ]
    assert result[0]["normalized"] == "Paraf"
    assert result[1]["context_kind"] == "eligibility"
    assert result[2]["normalized"] == "mobile"


def test_rejects_generic_card_and_non_channel_mobile_wording():
    text = "Kartınızla ödeme yapın, mobil cihazınızı yanınızda tutun."
    payload = {
        "entities": [
            _entity(text, "CARD_NAME", "Kartınızla"),
            _entity(text, "APPLICATION_CHANNEL", "mobil cihazınızı"),
        ]
    }

    assert validate_entities(payload, text=text) == []


def test_rejects_bankkart_reward_currency_but_keeps_card_product_context():
    reward_text = "Alışverişinize 500 TL Bankkart Lira kazanabilirsiniz."
    card_text = "Bankkart kredi kartınızla ödeme yapabilirsiniz."

    rejected = validate_entities(
        {"entities": [_entity(reward_text, "CARD_NAME", "Bankkart Lira")]},
        text=reward_text,
    )
    accepted = validate_entities(
        {"entities": [_entity(card_text, "CARD_NAME", "Bankkart kredi kartınızla")]},
        text=card_text,
    )

    assert rejected == []
    assert accepted[0]["normalized"] == "Bankkart"
    assert accepted[0]["evidence"]["text"] == "Bankkart"


def test_accepts_llm_proposed_open_card_name_but_rejects_generic_modifier():
    named = "Maximum Platinum Kart ile ödeme yapın."
    generic = "Yalnızca asıl kart ile katılım sağlanır."

    accepted = validate_entities(
        {"entities": [_entity(named, "CARD_NAME", "Maximum Platinum Kart")]},
        text=named,
    )
    rejected = validate_entities(
        {"entities": [_entity(generic, "CARD_NAME", "asıl kart")]},
        text=generic,
    )

    assert accepted[0]["normalized"] == "Maximum Platinum Kart"
    assert rejected == []


def test_reanchors_only_unique_exact_surface():
    text = "Başvurunuzu görüntülü görüşme ile tamamlayın."
    payload = {
        "entities": [
            {
                "label": "APPLICATION_CHANNEL",
                "evidence": {
                    "text": "görüntülü görüşme",
                    "char_start": 0,
                    "char_end": 18,
                },
            }
        ]
    }

    result = validate_entities(payload, text=text)

    assert result[0]["evidence"]["char_start"] == text.index("görüntülü görüşme")
    assert result[0]["normalized"] == "video_call"


def test_long_chunks_restore_global_offsets():
    text = "Koşullar. " * 700 + "Başvuru Albaraka Mobil üzerinden yapılır."

    class StaticClient:
        enabled = True
        model = "llm-large"

        def stream_chat(self, *, user_prompt, **_kwargs):
            entities = []
            if "Albaraka Mobil" in user_prompt:
                entities.append(
                    _entity(user_prompt, "APPLICATION_CHANNEL", "Albaraka Mobil")
                )
            yield json.dumps({"entities": entities}, ensure_ascii=False)

    result = ContextEntityLabeler(StaticClient()).label(text)

    assert result[0]["evidence"]["char_start"] == text.index("Albaraka Mobil")


def test_deterministic_recovery_fills_explicit_surface_omitted_by_llm():
    text = "Paraf müşterilerimiz internet şubesinden katılabilir."

    class EmptyClient:
        enabled = True
        model = "llm-large"

        def stream_chat(self, **_kwargs):
            yield '{"entities":[]}'

    result = ContextEntityLabeler(EmptyClient()).label(text)

    assert {(item["label"], item["normalized"]) for item in result} == {
        ("CARD_NAME", "Paraf"),
        ("CUSTOMER_REFERENCE", "customer_reference"),
        ("APPLICATION_CHANNEL", "internet_branch"),
    }


def test_overlay_adds_entities_channel_suggestion_and_safe_temporal_observation():
    text = "Paraf müşterileri mobil uygulamadan katılabilir."
    candidate = {
        "id": "campaign",
        "content_hash": "a" * 64,
        "source_version": 1,
        "text_sha256": "b" * 64,
        "scraped_at": "2026-08-11T14:34:00+00:00",
        "structured": {
            "fields": {
                "application_channel": {"status": "NOT_STATED", "value": None},
                "campaign_start_date": {"status": "NOT_STATED", "value": None},
                "campaign_end_date": {"status": "NOT_STATED", "value": None},
            }
        },
    }
    label_row = {
        "entities": validate_entities(
            {
                "entities": [
                    _entity(text, "CARD_NAME", "Paraf"),
                    _entity(text, "CUSTOMER_REFERENCE", "müşterileri"),
                    _entity(text, "APPLICATION_CHANNEL", "mobil uygulamadan"),
                ]
            },
            text=text,
        )
    }

    result = _overlay({}, candidate=candidate, label_row=label_row)

    assert result["suggestions"]["application_channel"]["value"] == "mobile"
    assert result["temporal_observation"]["statement"] == (
        "Kampanya 2026-08-11 tarihinde kaynakta mevcuttu."
    )
    assert {item["label"] for item in result["entities"]} == {
        "UYGULAMA_KANALI",
        "KART_ADI",
        "MUSTERI_HITABI",
    }


def test_overlay_does_not_add_observation_when_source_period_is_known():
    candidate = {
        "id": "campaign",
        "content_hash": "a" * 64,
        "source_version": 1,
        "text_sha256": "b" * 64,
        "scraped_at": "2026-08-11T14:34:00+00:00",
        "structured": {
            "campaign_start_date": "2026-08-01",
            "campaign_end_date": "2026-08-31",
        },
    }

    result = _overlay({}, candidate=candidate, label_row={"entities": []})

    assert "temporal_observation" not in result


def test_merge_training_adds_grounded_spans_and_preserves_existing_overlap(
    tmp_path, monkeypatch
):
    text = "Paraf bireysel müşteriler mobil uygulamadan katılabilir."
    candidate = {
        "id": "campaign",
        "text": text,
        "content_hash": "a" * 64,
    }

    class Store:
        def __init__(self, _database):
            pass

        def nlp_enrichment_candidates(self):
            return [candidate]

    monkeypatch.setattr("scripts.label_context_entities.CampaignStore", Store)
    labels = tmp_path / "labels.jsonl"
    labels.write_text(
        json.dumps(
            {
                "status": "completed",
                "record_id": "campaign",
                "content_hash": "a" * 64,
                "entities": validate_entities(
                    {
                        "entities": [
                            _entity(text, "CARD_NAME", "Paraf"),
                            _entity(
                                text,
                                "CUSTOMER_REFERENCE",
                                "bireysel müşteriler",
                            ),
                            _entity(
                                text,
                                "APPLICATION_CHANNEL",
                                "mobil uygulamadan",
                            ),
                        ]
                    },
                    text=text,
                ),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    ner = tmp_path / "ner.jsonl"
    customer_start = text.index("bireysel müşteriler")
    ner.write_text(
        json.dumps(
            {
                "id": "campaign",
                "source_id": "campaign",
                "source_url": "https://bank.example/campaign",
                "split": "train",
                "text": text,
                "entities": [
                    {
                        "start": customer_start,
                        "end": customer_start + len("bireysel müşteriler"),
                        "text": "bireysel müşteriler",
                        "label": "HEDEF_KITLE",
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    report = merge_training_dataset("unused.sqlite3", labels, ner)
    merged = json.loads(ner.read_text(encoding="utf-8"))

    assert report["entities_added"] == {
        "UYGULAMA_KANALI": 1,
        "KART_ADI": 1,
        "MUSTERI_HITABI": 0,
    }
    assert report["entities_skipped_overlaps"]["MUSTERI_HITABI"] == 1
    assert {entity["label"] for entity in merged["entities"]} == {
        "HEDEF_KITLE",
        "UYGULAMA_KANALI",
        "KART_ADI",
    }
