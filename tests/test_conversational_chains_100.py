from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from src.policy import ComparisonCriteria
from src.services.conversation import (
    extract_comparison_criteria,
    extract_financing_type,
    merge_criteria,
)

DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "model_training_data"
    / "conversational_chains_100.jsonl"
)


def _load_dataset() -> list[dict]:
    assert DATASET_PATH.exists(), f"Dataset file not found: {DATASET_PATH}"
    lines = [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return lines


def test_dataset_count_and_schema():
    records = _load_dataset()
    assert len(records) == 100, f"Expected 100 scenarios, found {len(records)}"

    required_keys = {
        "id",
        "domain",
        "category",
        "initial_query",
        "detected_slots",
        "missing_slots",
        "assistant_clarify_prompt",
        "user_follow_up",
        "resolved_slots",
        "expected_action_flow",
        "grounded_sources_cited",
        "final_grounded_answer_preview",
    }

    seen_ids = set()
    for idx, item in enumerate(records, start=1):
        assert required_keys.issubset(item.keys()), f"Row {idx} missing keys"
        expected_id = f"CHAIN_{idx:03d}"
        assert item["id"] == expected_id, f"Row {idx} has ID {item['id']}, expected {expected_id}"
        assert item["id"] not in seen_ids, f"Duplicate ID: {item['id']}"
        seen_ids.add(item["id"])

        assert len(item["initial_query"]) > 3
        assert len(item["assistant_clarify_prompt"]) > 10
        assert len(item["user_follow_up"]) > 2
        assert len(item["final_grounded_answer_preview"]) > 10
        assert item["expected_action_flow"] == ["CLARIFY", "ANSWER"]
        assert len(item["grounded_sources_cited"]) >= 1


def test_domain_distribution():
    records = _load_dataset()
    domain_counts = Counter(item["domain"] for item in records)

    expected_counts = {
        "financing_comparison": 30,
        "terminology_sharia": 25,
        "cards_rewards_installments": 20,
        "accounts_deposits_gold": 15,
        "onboarding_segments": 10,
    }

    assert dict(domain_counts) == expected_counts


def test_financing_criteria_resolution():
    records = _load_dataset()
    financing_records = [r for r in records if r["domain"] == "financing_comparison"]
    assert len(financing_records) == 30

    resolved_count = 0
    for r in financing_records:
        initial = extract_comparison_criteria(r["initial_query"])
        follow_up = extract_comparison_criteria(r["user_follow_up"])
        merged = merge_criteria(ComparisonCriteria(), {**initial, **follow_up})

        resolved_slots = r["resolved_slots"]
        if "term_months" in resolved_slots:
            assert merged.term_months == resolved_slots["term_months"]
        if "amount" in resolved_slots:
            assert merged.amount == resolved_slots["amount"]
        if "fee_priority" in resolved_slots:
            assert merged.fee_priority == resolved_slots["fee_priority"]

        fin_type = extract_financing_type(
            r["initial_query"]
        ) or extract_financing_type(r["user_follow_up"])
        if "financing_type" in resolved_slots:
            assert fin_type == resolved_slots["financing_type"]
        resolved_count += 1

    assert resolved_count == 30


def test_multi_turn_conversation_flow_simulation():
    records = _load_dataset()

    for r in records:
        flow = r["expected_action_flow"]
        assert flow[0] == "CLARIFY"
        assert flow[1] == "ANSWER"
        assert len(r["missing_slots"]) >= 1
        assert len(r["grounded_sources_cited"]) >= 1
