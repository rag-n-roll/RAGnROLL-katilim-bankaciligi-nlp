from src.comparison import (
    ComparisonConfig,
    ComparisonQuery,
    ComparisonResult,
    compare_records,
)


def offer(
    identifier: str,
    *,
    rate=None,
    amount=None,
    currency="TRY",
    product_type="financing",
    title="Finansman"
):
    structured = {
        "product_type": product_type,
        "financing_type": "consumer",
        "profit_share_rate": rate,
        "max_amount": amount,
        "fee_information": "masrafsız",
        "target_audience": "new_customer",
        "duration": {"value": 3, "unit": "month", "approx_days": 90},
    }
    return {
        "id": identifier,
        "title": title,
        "structured": structured,
        "currency": currency,
    }


def test_comparison_ranks_lower_financing_rate_and_explains_weights():
    results = compare_records(
        [
            offer("a", rate=0.45, amount={"amount": 100000, "currency": "TRY"}),
            offer("b", rate=0.35, amount={"amount": 120000, "currency": "TRY"}),
        ],
        ComparisonQuery(product_type="financing", currency="TRY"),
    )

    assert [row["id"] for row in results["included"]] == ["b", "a"]
    assert results["included"][0]["criteria"]["rate"]["weight"] == 0.45
    assert results["included"][0]["criteria"]["rate"]["contribution"] > 0
    assert "düşük kâr payı oranı" in results["included"][0]["ranking_reason"]


def test_comparison_excludes_different_currency_and_keeps_missing_rate_unknown():
    results = compare_records(
        [
            offer("known", rate=0.35, amount={"amount": 100000, "currency": "TRY"}),
            offer("unknown", rate=None, amount=None),
            offer("usd", rate=0.20, amount={"amount": 1000, "currency": "USD"}),
        ],
        ComparisonQuery(product_type="financing", currency="TRY"),
    )

    unknown = next(row for row in results["included"] if row["id"] == "unknown")
    assert "rate" in unknown["missing_fields"]
    assert "rate" not in unknown["criteria"]
    assert results["excluded"] == [{"id": "usd", "reason": "currency_mismatch"}]


def test_comparison_reuses_sorted_pair_key_once():
    records = [offer("b", rate=0.35), offer("a", rate=0.45)]
    results = compare_records(
        records, ComparisonQuery(product_type="financing", currency="TRY")
    )

    assert results["pair_cache_keys"] == ["a:b"]


def test_matching_score_uses_optional_structured_and_title_filters():
    results = compare_records(
        [
            offer(
                "match",
                rate=0.35,
                amount={"amount": 100000, "currency": "TRY"},
                title="İhtiyaç Finansmanı",
            ),
            offer(
                "different",
                rate=0.35,
                amount={"amount": 100000, "currency": "TRY"},
                title="Taşıt Finansmanı",
            ),
        ],
        ComparisonQuery(
            product_type="financing",
            currency="TRY",
            financing_type="consumer",
            amount=100000,
            duration_days=90,
            eligibility="new_customer",
            title="İhtiyaç Finansmanı",
        ),
    )

    scores = {row["id"]: row["match_score"] for row in results["included"]}
    assert scores["match"] == 1.0
    assert scores["different"] < 1.0


def test_comparison_returns_serializable_result_contract():
    result = compare_records(
        [offer("one", rate=0.35)],
        ComparisonQuery(product_type="financing", currency="TRY"),
    )

    assert isinstance(result, ComparisonResult)
    assert result.to_dict()["included"][0]["id"] == "one"


def test_comparison_tie_order_is_deterministic_across_input_order():
    records = [offer("b", rate=0.35), offer("a", rate=0.35)]
    query = ComparisonQuery(product_type="financing", currency="TRY")

    forward = compare_records(records, query)
    reversed_result = compare_records(reversed(records), query)

    assert [row["id"] for row in forward["included"]] == ["a", "b"]
    assert forward.to_dict() == reversed_result.to_dict()


def test_comparison_scores_duplicate_ids_without_overwriting_rows():
    results = compare_records(
        [offer("same", rate=0.20), offer("same", rate=0.40)],
        ComparisonQuery(product_type="financing", currency="TRY"),
    )

    rate_scores = [row["criteria"]["rate"]["score"] for row in results["included"]]
    assert rate_scores == [1.0, 0.0]


def test_comparison_treats_non_finite_and_malformed_numbers_as_missing():
    record = offer("invalid", rate=float("nan"), amount={"amount": "-", "currency": "TRY"})
    record["structured"]["duration"] = {"approx_days": "unknown"}

    results = compare_records(
        [record],
        ComparisonQuery(
            product_type="financing", currency="TRY", duration_days=90
        ),
    )

    row = results["included"][0]
    assert "rate" in row["missing_fields"]
    assert "amount" in row["missing_fields"]
    assert row["match_score"] == 1.0


def test_comparison_supports_explicitly_empty_weight_configuration():
    results = compare_records(
        [offer("one", rate=0.35)],
        ComparisonQuery(product_type="financing", currency="TRY"),
        ComparisonConfig(matching_weights={}, financing_weights={}),
    )

    row = results["included"][0]
    assert row["match_score"] == 0.0
    assert row["advantage_score"] is None
    assert row["criteria"] == {}
