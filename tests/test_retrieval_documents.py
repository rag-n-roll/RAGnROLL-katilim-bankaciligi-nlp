import json
from hashlib import sha256

import pytest

from src.nlp_runtime.advisory import RUNTIME_CONTRACT
from src.nlp_runtime.integrity import REQUIRED_RUNTIME_PROVENANCE
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
        "source_version": 3,
        "source_url": "https://ornek.example/campaign-1",
        "structured": {
            "product_type": "card",
            "fields": {"reward_amount": {"value": 500, "unit": "TRY"}},
        },
    }


def _analysis_lineage(record: dict, analyzed_text: str) -> dict:
    return {
        "contract": RUNTIME_CONTRACT,
        "provenance": dict(REQUIRED_RUNTIME_PROVENANCE),
        "record": {
            "source_content_hash": record["content_hash"],
            "source_version": record["source_version"],
            "text_sha256": sha256(analyzed_text.encode("utf-8")).hexdigest(),
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


def test_only_evidence_backed_advisory_lines_change_index_text_and_hash():
    record = _record("Mobil uygulamadan 500 TL ödül kazanılır.")
    original = campaign_documents(record)[0]
    analyzed_text = record["title"] + "\n" + record["clean_text"]
    mobile_start = analyzed_text.index("Mobil uygulamadan")
    reward_start = analyzed_text.index("500 TL")
    record["nlp_analysis"] = {
        **_analysis_lineage(record, analyzed_text),
        "suggestions": {
            "reward_amount": {
                "value": {"amount": 500.0, "currency": "TRY"},
                "evidence": {
                    "text": "500 TL",
                    "char_start": reward_start,
                    "char_end": reward_start + len("500 TL"),
                },
                "method": "deterministic_rule",
                "advisory": True,
            }
        },
        "classification": {
            "product_category": {"value": "card", "evidence": None},
            "dimensions": {
                "channels": [
                    {
                        "value": "mobile",
                        "evidence": {
                            "text": "Mobil uygulamadan",
                            "char_start": mobile_start,
                            "char_end": mobile_start + len("Mobil uygulamadan"),
                        },
                    },
                    {"value": "physical_branch", "evidence": None},
                ]
            },
        },
        "entities": [],
    }

    enriched = campaign_documents(record)[0]

    assert enriched[2]["index_hash"] != original[2]["index_hash"]
    assert "reward_amount" in enriched[1]
    assert "channels: mobile" in enriched[1]
    assert "physical_branch" not in enriched[1]


def test_advisory_classification_never_replaces_authoritative_filter_metadata():
    record = _record("Taşıt fırsatı için mobil uygulamadan başvurun.")
    analyzed_text = record["title"] + "\n" + record["clean_text"]
    evidence_start = analyzed_text.index("Taşıt")
    record["nlp_analysis"] = {
        **_analysis_lineage(record, analyzed_text),
        "suggestions": {},
        "classification": {
            "product_category": {
                "value": "vehicle_finance",
                "evidence": {
                    "text": "Taşıt",
                    "char_start": evidence_start,
                    "char_end": evidence_start + len("Taşıt"),
                },
            },
            "dimensions": {},
        },
        "entities": [],
    }

    document = campaign_documents(record)[0]

    assert "vehicle_finance" in document[1]
    assert document[2]["product_type"] == "card"
    assert document[2]["financing_type"] == ""


def test_numeric_condition_ner_is_not_indexed_as_reward_evidence():
    record = _record("5.000 TL ve üzeri harcamaya 500 TL ödül kazanılır.")
    analyzed_text = record["title"] + "\n" + record["clean_text"]
    spend_start = analyzed_text.index("5.000 TL")
    reward_start = analyzed_text.index("500 TL", spend_start + 1)
    record["nlp_analysis"] = {
        **_analysis_lineage(record, analyzed_text),
        "suggestions": {
            "min_amount": {
                "value": {"amount": 5000.0, "currency": "TRY"},
                "evidence": {
                    "text": "5.000 TL",
                    "char_start": spend_start,
                    "char_end": spend_start + len("5.000 TL"),
                },
                "method": "deterministic_rule",
                "advisory": True,
            },
            "reward_amount": {
                "value": {"amount": 500.0, "currency": "TRY"},
                "evidence": {
                    "text": "500 TL",
                    "char_start": reward_start,
                    "char_end": reward_start + len("500 TL"),
                },
                "method": "deterministic_rule",
                "advisory": True,
            },
        },
        "classification": {"product_category": {}, "dimensions": {}},
        "entities": [
            {
                "start": spend_start,
                "end": spend_start + len("5.000 TL"),
                "text": "5.000 TL",
                "label": "KAMPANYA_KOSULU",
            },
            {
                "start": reward_start,
                "end": reward_start + len("500 TL"),
                "text": "500 TL",
                "label": "KAMPANYA_KOSULU",
            },
        ],
    }

    text = campaign_documents(record)[0][1]

    assert "min_amount" in text and '"amount":5000.0' in text
    assert "reward_amount" in text and '"amount":500.0' in text
    assert "NER sinyali KAMPANYA_KOSULU" not in text


def _fully_evidenced_analysis(record: dict) -> dict:
    analyzed_text = record["title"] + "\n" + record["clean_text"]
    channel_text = "Mobil uygulamadan"
    channel_start = analyzed_text.index(channel_text)
    bank_text = "Örnek Katılım"
    bank_start = analyzed_text.index(bank_text, len(record["title"]) + 1)
    evidence = {
        "text": channel_text,
        "char_start": channel_start,
        "char_end": channel_start + len(channel_text),
    }
    return {
        **_analysis_lineage(record, analyzed_text),
        "suggestions": {
            "application_channel": {
                "value": "mobile",
                "evidence": evidence,
                "method": "classifier_evidence",
                "advisory": True,
            }
        },
        "classification": {
            "product_category": {},
            "dimensions": {
                "channels": [{"value": "mobile", "evidence": evidence}],
            },
        },
        "entities": [
            {
                "start": bank_start,
                "end": bank_start + len(bank_text),
                "text": bank_text,
                "label": "BANKA",
            }
        ],
    }


@pytest.mark.parametrize(
    "invalid_lineage",
    [
        "missing_contract",
        "wrong_contract",
        "missing_source_hash",
        "empty_source_hash",
        "mismatched_source_hash",
        "mismatched_source_version",
        "mismatched_text_hash",
        "missing_runtime_provenance",
        "non_object_runtime_provenance",
        "mismatched_artifact_hash",
        "mismatched_dataset_hash",
        "mismatched_training_manifest_hash",
        "wrong_automatic_reference_contract",
        "wrong_independent_gold_contract",
        "extra_runtime_provenance_key",
    ],
)
def test_invalid_analysis_provenance_blocks_every_advisory_signal(invalid_lineage):
    record = _record("Mobil uygulamadan başvurun; Örnek Katılım kampanyasıdır.")
    baseline = campaign_documents(record)
    analysis = _fully_evidenced_analysis(record)
    if invalid_lineage == "missing_contract":
        analysis.pop("contract")
    elif invalid_lineage == "wrong_contract":
        analysis["contract"] = "untrusted-contract"
    elif invalid_lineage == "missing_source_hash":
        analysis["record"].pop("source_content_hash")
    elif invalid_lineage == "empty_source_hash":
        analysis["record"]["source_content_hash"] = ""
    elif invalid_lineage == "mismatched_source_hash":
        analysis["record"]["source_content_hash"] = "stale-source-hash"
    elif invalid_lineage == "mismatched_source_version":
        analysis["record"]["source_version"] = record["source_version"] + 1
    elif invalid_lineage == "mismatched_text_hash":
        analysis["record"]["text_sha256"] = "0" * 64
    elif invalid_lineage == "missing_runtime_provenance":
        analysis.pop("provenance")
    elif invalid_lineage == "non_object_runtime_provenance":
        analysis["provenance"] = "untrusted"
    elif invalid_lineage == "mismatched_artifact_hash":
        analysis["provenance"]["classifier_sha256"] = "0" * 64
    elif invalid_lineage == "mismatched_dataset_hash":
        analysis["provenance"]["classifier_dataset_sha256"] = "0" * 64
    elif invalid_lineage == "mismatched_training_manifest_hash":
        analysis["provenance"]["training_manifest_sha256"] = "0" * 64
    elif invalid_lineage == "wrong_automatic_reference_contract":
        analysis["provenance"]["automatic_references"] = "gold"
    elif invalid_lineage == "wrong_independent_gold_contract":
        analysis["provenance"]["independent_gold"] = "provided"
    else:
        analysis["provenance"]["unexpected"] = True
    record["nlp_analysis"] = analysis

    documents = campaign_documents(record)
    text = documents[0][1]

    assert documents == baseline
    assert "Alan önerisi application_channel:" not in text
    assert "Sınıflandırma sinyali channels:" not in text
    assert "NER sinyali BANKA:" not in text


def test_non_allowlisted_suggestion_is_never_rendered():
    record = _record("Mobil uygulamadan başvurun; Örnek Katılım kampanyasıdır.")
    analysis = _fully_evidenced_analysis(record)
    analysis["suggestions"]["bank_name"] = {
        "value": "Örnek Katılım",
        "evidence": analysis["entities"][0] | {
            "char_start": analysis["entities"][0]["start"],
            "char_end": analysis["entities"][0]["end"],
        },
        "method": "untrusted",
        "advisory": True,
    }
    record["nlp_analysis"] = analysis

    text = campaign_documents(record)[0][1]

    assert "Alan önerisi application_channel: mobile" in text
    assert "Alan önerisi bank_name:" not in text
