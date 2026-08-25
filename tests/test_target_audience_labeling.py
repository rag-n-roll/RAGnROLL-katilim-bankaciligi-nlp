import json

from scripts.label_target_audience import (
    TargetAudienceLabeler,
    _grounded_analysis,
    validate_entities,
)


class StaticClient:
    enabled = True
    model = "llm-large"

    def __init__(self, payload):
        self.payload = payload

    def stream_chat(self, **_kwargs):
        yield json.dumps(self.payload, ensure_ascii=False)


def _entity(text, label, evidence, *, start=None):
    offset = text.index(evidence) if start is None else start
    return {
        "label": label,
        "evidence": {
            "text": evidence,
            "char_start": offset,
            "char_end": offset + len(evidence),
        },
    }


def test_accepts_explicit_distinct_customer_segments():
    text = (
        "Kampanya yeni müşteriler ve bireysel müşteriler içindir. "
        "Özel bankacılık müşterileri de katılabilir."
    )
    payload = {
        "entities": [
            _entity(text, "new_customer", "yeni müşteriler"),
            _entity(text, "individual_customer", "bireysel müşteriler"),
            _entity(
                text,
                "private_banking_customer",
                "Özel bankacılık müşterileri",
            ),
        ]
    }

    result = TargetAudienceLabeler(StaticClient(payload)).label(text)

    assert [item["label"] for item in result] == [
        "new_customer",
        "individual_customer",
        "private_banking_customer",
    ]


def test_rejects_channel_as_digital_customer_and_generic_card_usage():
    text = "Mobil uygulamadan başvurun ve kartınızla ödeme yapın."
    payload = {
        "entities": [
            _entity(text, "digital_customer", "Mobil uygulamadan"),
            _entity(text, "cardholder", "kartınızla"),
        ]
    }

    assert validate_entities(payload, text=text) == []


def test_reanchors_only_unique_exact_evidence():
    text = "Yalnızca mevcut müşteriler kampanyadan yararlanabilir."
    payload = {
        "entities": [
            _entity(text, "existing_customer", "mevcut müşteriler", start=0),
        ]
    }

    result = validate_entities(payload, text=text)

    assert result[0]["evidence"]["char_start"] == text.index("mevcut müşteriler")


def test_rejects_ambiguous_evidence_when_offsets_are_wrong():
    text = "yeni müşteriler katılır; yeni müşteriler ödül alır."
    payload = {
        "entities": [
            _entity(text, "new_customer", "yeni müşteriler", start=1),
        ]
    }

    assert validate_entities(payload, text=text) == []


def test_prunes_excluded_customer_and_cardholder_contexts():
    text = (
        "Ticari müşteriler kampanyaya dahil değildir. "
        "Kart sahipleri kampanya kapsamında yararlanamaz."
    )
    payload = {
        "entities": [
            _entity(text, "commercial_sme", "Ticari müşteriler"),
            _entity(text, "cardholder", "Kart sahipleri"),
        ]
    }

    assert validate_entities(payload, text=text) == []


def test_cardholder_requires_positive_eligibility_context():
    text = "Kart sahipleri güncel sözleşmelerini bankadan alabilir."
    payload = {"entities": [_entity(text, "cardholder", "Kart sahipleri")]}

    assert validate_entities(payload, text=text) == []


def test_long_text_chunks_preserve_global_evidence_offsets():
    prefix = "Genel koşullar. " * 500
    suffix = "Kampanya yalnızca dijital müşteriler için geçerlidir."
    text = prefix + suffix

    class ChunkClient:
        enabled = True
        model = "llm-large"

        def stream_chat(self, *, user_prompt, **_kwargs):
            entities = []
            if "dijital müşteriler" in user_prompt:
                entities.append(
                    _entity(user_prompt, "digital_customer", "dijital müşteriler")
                )
            yield json.dumps({"entities": entities}, ensure_ascii=False)

    result = TargetAudienceLabeler(ChunkClient()).label(text)

    assert len(result) == 1
    assert result[0]["evidence"]["char_start"] == text.index("dijital müşteriler")
    assert text[
        result[0]["evidence"]["char_start"] : result[0]["evidence"]["char_end"]
    ] == "dijital müşteriler"


def test_prunes_card_product_name_and_product_first_customer_context():
    text = (
        "Kampanyaya Sağlam Kart Genç dahildir. "
        "İlk kez yatırım hesabı açan müşteriler yararlanabilir."
    )
    payload = {
        "entities": [
            _entity(text, "youth_student", "Sağlam Kart Genç"),
            _entity(
                text,
                "new_customer",
                "İlk kez yatırım hesabı açan müşteriler",
            ),
        ]
    }

    assert validate_entities(payload, text=text) == []


def test_grounded_analysis_replaces_untyped_target_entities_and_false_suggestion():
    text = "Kampanya yalnızca bireysel müşteriler içindir."
    evidence = _entity(text, "individual_customer", "bireysel müşteriler")[
        "evidence"
    ]
    candidate = {
        "id": "campaign",
        "content_hash": "a" * 64,
        "source_version": 1,
        "text_sha256": "b" * 64,
        "structured": {"fields": {"target_audience": {"status": "NOT_STATED"}}},
    }
    previous = {
        "entities": [
            {"label": "HEDEF_KITLE", "text": "kart", "start": 1, "end": 5},
            {"label": "VADE", "text": "12 ay", "start": 50, "end": 55},
        ],
        "suggestions": {
            "target_audience": {
                "value": "cardholder",
                "evidence": {"text": "kart", "char_start": 1, "char_end": 5},
                "method": "classifier_sensitive_regex",
                "advisory": True,
            }
        },
    }
    label_row = {
        "review_status": "auto_high_confidence",
        "entities": [
            {
                "label": "individual_customer",
                "context_kind": "customer_segment",
                "evidence": evidence,
            }
        ],
    }

    result = _grounded_analysis(previous, candidate=candidate, label_row=label_row)

    target_entities = [
        item for item in result["entities"] if item["label"] == "HEDEF_KITLE"
    ]
    assert target_entities == [
        {
            "label": "HEDEF_KITLE",
            "segment": "individual_customer",
            "context_kind": "customer_segment",
            "text": "bireysel müşteriler",
            "start": text.index("bireysel müşteriler"),
            "end": text.index("bireysel müşteriler") + len("bireysel müşteriler"),
        }
    ]
    assert result["suggestions"]["target_audience"]["value"] == (
        "individual_customer"
    )
