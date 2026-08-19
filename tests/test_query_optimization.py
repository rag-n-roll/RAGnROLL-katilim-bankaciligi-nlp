import sqlite3

from src.persistence import CampaignStore


def _plan(connection: sqlite3.Connection, sql: str, parameters: tuple) -> str:
    return "\n".join(
        row[3]
        for row in connection.execute("EXPLAIN QUERY PLAN " + sql, parameters)
    )


def test_campaign_query_indexes_are_idempotent_and_match_access_patterns(tmp_path):
    store = CampaignStore(tmp_path / "plans.sqlite3")

    store.initialize()
    store.initialize()

    with sqlite3.connect(store.path) as connection:
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(campaigns)")
        }

    assert {
        "campaigns_updated_page_idx",
        "campaigns_bank_updated_page_idx",
        "campaigns_product_type_updated_page_idx",
        "campaigns_reward_currency_updated_page_idx",
        "campaigns_max_currency_updated_page_idx",
        "campaigns_effective_freshness_idx",
    } <= indexes


def test_filtered_pagination_uses_targeted_indexes_without_sorting(tmp_path):
    store = CampaignStore(tmp_path / "plans.sqlite3")
    store.initialize()

    with sqlite3.connect(store.path) as connection:
        unfiltered_plan = _plan(
            connection,
            """SELECT c.processed_json FROM campaigns c
               ORDER BY c.updated_at DESC, c.id LIMIT ? OFFSET ?""",
            (20, 0),
        )
        bank_plan = _plan(
            connection,
            """SELECT c.processed_json
               FROM campaigns c JOIN banks b ON b.id = c.bank_id
               WHERE b.slug = ?
               ORDER BY c.updated_at DESC, c.id LIMIT ? OFFSET ?""",
            ("ornek", 20, 0),
        )
        product_plan = _plan(
            connection,
            """SELECT c.processed_json FROM campaigns c
               WHERE c.product_type = ?
               ORDER BY c.updated_at DESC, c.id LIMIT ? OFFSET ?""",
            ("card", 20, 0),
        )

    assert "campaigns_updated_page_idx" in unfiltered_plan
    assert "campaigns_bank_updated_page_idx" in bank_plan
    assert "campaigns_product_type_updated_page_idx" in product_plan
    assert "USE TEMP B-TREE FOR ORDER BY" not in unfiltered_plan
    assert "USE TEMP B-TREE FOR ORDER BY" not in bank_plan
    assert "USE TEMP B-TREE FOR ORDER BY" not in product_plan


def test_currency_or_filter_uses_both_currency_indexes(tmp_path):
    store = CampaignStore(tmp_path / "plans.sqlite3")
    store.initialize()

    with sqlite3.connect(store.path) as connection:
        plan = _plan(
            connection,
            """SELECT c.processed_json FROM campaigns c
               WHERE c.reward_currency = ? OR c.max_amount_currency = ?
               ORDER BY c.updated_at DESC, c.id LIMIT ? OFFSET ?""",
            ("TRY", "TRY", 20, 0),
        )

    assert "MULTI-INDEX OR" in plan
    assert "campaigns_reward_currency_updated_page_idx" in plan
    assert "campaigns_max_currency_updated_page_idx" in plan
    assert "SCAN c" not in plan


def test_recent_campaigns_expression_index_avoids_table_scan_and_sort(tmp_path):
    store = CampaignStore(tmp_path / "plans.sqlite3")
    store.initialize()

    with sqlite3.connect(store.path) as connection:
        plan = _plan(
            connection,
            """SELECT c.id, b.slug
               FROM campaigns c JOIN banks b ON b.id = c.bank_id
               ORDER BY COALESCE(c.scraped_at, c.updated_at) DESC, c.id
               LIMIT ?""",
            (5,),
        )

    assert "campaigns_effective_freshness_idx" in plan
    assert "USE TEMP B-TREE FOR ORDER BY" not in plan


def test_query_without_bank_filter_does_not_join_banks(tmp_path, monkeypatch):
    store = CampaignStore(tmp_path / "plans.sqlite3")
    store.initialize()
    statements: list[str] = []

    def trace(statement: str) -> None:
        statements.append(statement)

    original_connect = store._connect

    def traced_connect():
        connection = original_connect()
        connection.set_trace_callback(trace)
        return connection

    monkeypatch.setattr(store, "_connect", traced_connect)
    store.query_campaigns(product_type="card")

    selects = [statement for statement in statements if statement.startswith("SELECT")]
    assert selects
    assert all("JOIN banks" not in statement for statement in selects)
