"""Geriye uyumlu JSON export üreten SQLite ana veri kaynağı."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from src.data_quality import cluster_near_duplicates, content_hash, hamming_distance, simhash
from src.nlp_runtime.advisory import (
    RUNTIME_CONTRACT,
    SUGGESTION_ALLOWLIST,
    field_is_missing,
)
from src.preprocessing.clean_text import preprocess_record
from src.scraper.models import SCHEMA_VERSION

_DERIVED_FIELDS = frozenset({"clean_text", "tokens", "token_count", "structured"})


class StaleNlpAnalysisError(RuntimeError):
    """Analiz kaynağı ile güncel kayıt artık aynı olmadığında yükseltilir."""


class CampaignStore:
    """Banka ürün/kampanya kayıtlarını idempotent şekilde saklar."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _enrich_processed(payload: dict[str, Any]) -> dict[str, Any]:
        structured = payload.get("structured")
        if isinstance(structured, dict) and isinstance(structured.get("fields"), dict):
            return payload
        return preprocess_record(payload)

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scrape_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    record_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS banks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    website TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    bank_id INTEGER NOT NULL REFERENCES banks(id),
                    name TEXT NOT NULL,
                    product_type TEXT,
                    financing_type TEXT,
                    currency TEXT,
                    source_url TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    structured_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY,
                    bank_id INTEGER NOT NULL REFERENCES banks(id),
                    product_id TEXT REFERENCES products(id),
                    title TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    product_type TEXT,
                    financing_type TEXT,
                    profit_share_rate REAL,
                    discount_rate REAL,
                    reward_amount_minor INTEGER,
                    reward_currency TEXT,
                    max_amount_minor INTEGER,
                    max_amount_currency TEXT,
                    duration_value INTEGER,
                    duration_unit TEXT,
                    duration_days INTEGER,
                    eligibility TEXT,
                    fee_information TEXT,
                    raw_json TEXT NOT NULL,
                    processed_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    scraped_at TEXT
                );
                CREATE TABLE IF NOT EXISTS record_versions (
                    record_id TEXT NOT NULL,
                    source_version INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    raw_json TEXT NOT NULL,
                    processed_json TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_to TEXT,
                    superseded_by TEXT,
                    is_current INTEGER NOT NULL DEFAULT 1,
                    occurrence_count INTEGER NOT NULL DEFAULT 1,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY(record_id, source_version)
                );
                """)
            connection.execute(
                "INSERT INTO schema_meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value "
                "WHERE schema_meta.value <> excluded.value",
                ("schema_version", "2026.08"),
            )
            for column, definition in (
                ("product_type", "TEXT"),
                ("reward_currency", "TEXT"),
                ("max_amount_currency", "TEXT"),
                ("scraped_at", "TEXT"),
                ("content_hash", "TEXT"),
                ("duplicate_fingerprint", "TEXT"),
                ("duplicate_cluster_id", "TEXT"),
                ("source_version", "INTEGER NOT NULL DEFAULT 1"),
                ("valid_from", "TEXT"),
            ):
                self._ensure_column(connection, "campaigns", column, definition)
            required_columns = {
                "bank_id",
                "title",
                "source_url",
                "raw_json",
                "processed_json",
                "created_at",
                "updated_at",
                "scraped_at",
            }
            existing_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(campaigns)")
            }
            missing_columns = required_columns - existing_columns
            if missing_columns:
                raise ValueError(
                    "desteklenmeyen campaigns şeması: "
                    + ", ".join(sorted(missing_columns))
                )
            self._backfill_legacy_lineage(connection)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_filter_idx "
                "ON campaigns(product_type, reward_currency, max_amount_currency)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_bank_updated_idx "
                "ON campaigns(bank_id, updated_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_title_idx "
                "ON campaigns(title COLLATE NOCASE)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_freshness_idx "
                "ON campaigns(updated_at DESC, scraped_at DESC)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS products_bank_type_idx "
                "ON products(bank_id, product_type)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_updated_page_idx "
                "ON campaigns(updated_at DESC, id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_bank_updated_page_idx "
                "ON campaigns(bank_id, updated_at DESC, id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_product_type_updated_page_idx "
                "ON campaigns(product_type, updated_at DESC, id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_reward_currency_updated_page_idx "
                "ON campaigns(reward_currency, updated_at DESC, id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_max_currency_updated_page_idx "
                "ON campaigns(max_amount_currency, updated_at DESC, id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_effective_freshness_idx "
                "ON campaigns(COALESCE(scraped_at, updated_at) DESC, id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_content_hash_idx "
                "ON campaigns(content_hash)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS campaigns_duplicate_cluster_idx "
                "ON campaigns(duplicate_cluster_id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS record_versions_current_idx "
                "ON record_versions(record_id, is_current)"
            )

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any]:
        try:
            payload = json.loads(str(value))
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _backfill_version(
        connection: sqlite3.Connection,
        *,
        record_id: str,
        hash_value: str,
        raw_json: str,
        processed_json: str,
        observed_at: str,
    ) -> tuple[int, str]:
        """Create missing history without counting a migration as an observation."""
        current = connection.execute(
            "SELECT source_version, content_hash, valid_from FROM record_versions "
            "WHERE record_id = ? AND is_current = 1",
            (record_id,),
        ).fetchone()
        if current and str(current[1]) == hash_value:
            connection.execute(
                "UPDATE record_versions SET raw_json = ?, processed_json = ? "
                "WHERE record_id = ? AND source_version = ?",
                (raw_json, processed_json, record_id, current[0]),
            )
            return int(current[0]), str(current[2])

        next_version = int(
            connection.execute(
                "SELECT COALESCE(MAX(source_version), 0) + 1 "
                "FROM record_versions WHERE record_id = ?",
                (record_id,),
            ).fetchone()[0]
        )
        if current:
            connection.execute(
                "UPDATE record_versions SET valid_to = ?, superseded_by = ?, "
                "is_current = 0, last_seen_at = ? "
                "WHERE record_id = ? AND source_version = ?",
                (
                    observed_at,
                    f"{record_id}:{next_version}",
                    observed_at,
                    record_id,
                    current[0],
                ),
            )
        connection.execute(
            "INSERT INTO record_versions(record_id, source_version, content_hash, "
            "raw_json, processed_json, valid_from, valid_to, superseded_by, "
            "is_current, occurrence_count, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 1, 1, ?)",
            (
                record_id,
                next_version,
                hash_value,
                raw_json,
                processed_json,
                observed_at,
                observed_at,
            ),
        )
        return next_version, observed_at

    def _backfill_legacy_lineage(self, connection: sqlite3.Connection) -> None:
        """Backfill lineage for databases created before the 2026.08 schema."""
        marker = connection.execute(
            "SELECT value FROM schema_meta WHERE key = ?",
            ("lineage_backfill_version",),
        ).fetchone()
        if marker and marker[0] == "1":
            return

        candidates: list[dict[str, Any]] = []
        campaign_rows = connection.execute(
            "SELECT c.id, b.slug, c.title, c.source_url, c.raw_json, "
            "c.processed_json, c.created_at, c.updated_at "
            "FROM campaigns c JOIN banks b ON b.id = c.bank_id ORDER BY c.id"
        ).fetchall()
        for row in campaign_rows:
            raw = self._json_object(row[4])
            processed = self._json_object(row[5])
            title = str(raw.get("title") or processed.get("title") or row[2] or "")
            content = str(raw.get("content") or processed.get("content") or "")
            candidates.append(
                {
                    "record_kind": "campaign",
                    "id": str(row[0]),
                    "bank_slug": str(row[1]),
                    "title": title,
                    "content": content,
                    "source_url": str(raw.get("source_url") or row[3] or ""),
                    "content_hash": content_hash(title, content),
                    "duplicate_fingerprint": simhash(content),
                    "raw": raw,
                    "processed": processed,
                    "created_at": str(row[6] or row[7] or ""),
                    "updated_at": str(row[7] or row[6] or ""),
                }
            )

        product_rows = connection.execute(
            "SELECT p.id, b.slug, p.name, p.source_url, p.raw_json, "
            "p.structured_json, p.created_at, p.updated_at "
            "FROM products p JOIN banks b ON b.id = p.bank_id ORDER BY p.id"
        ).fetchall()
        for row in product_rows:
            raw = self._json_object(row[4])
            structured = self._json_object(row[5])
            title = str(raw.get("title") or row[2] or "")
            content = str(raw.get("content") or "")
            candidates.append(
                {
                    "record_kind": "product",
                    "id": str(row[0]),
                    "bank_slug": str(row[1]),
                    "title": title,
                    "content": content,
                    "source_url": str(raw.get("source_url") or row[3] or ""),
                    "content_hash": content_hash(title, content),
                    "duplicate_fingerprint": simhash(content),
                    "raw": raw,
                    "structured": structured,
                    "created_at": str(row[6] or row[7] or ""),
                    "updated_at": str(row[7] or row[6] or ""),
                }
            )

        for item in cluster_near_duplicates(candidates):
            raw = dict(item["raw"])
            raw.setdefault("record_kind", item["record_kind"])
            raw.setdefault("id", item["id"])
            raw.setdefault("bank_slug", item["bank_slug"])
            raw.setdefault("title", item["title"])
            raw.setdefault("content", item["content"])
            raw.setdefault("source_url", item["source_url"])
            raw["canonical_url"] = raw.get("canonical_url") or item["source_url"]
            raw["content_hash"] = item["content_hash"]
            raw["duplicate_fingerprint"] = item["duplicate_fingerprint"]
            raw["duplicate_cluster_id"] = item["duplicate_cluster_id"]

            if item["record_kind"] == "campaign":
                processed = dict(item["processed"])
            else:
                processed = self._enrich_processed(
                    {**raw, "structured": item.get("structured", {})}
                )
            processed.update(
                content_hash=item["content_hash"],
                duplicate_fingerprint=item["duplicate_fingerprint"],
                duplicate_cluster_id=item["duplicate_cluster_id"],
                canonical_url=raw["canonical_url"],
            )
            observed_at = item["created_at"] or item["updated_at"]
            if not observed_at:
                observed_at = datetime.now(timezone.utc).isoformat()
            provisional_raw = json.dumps(raw, ensure_ascii=False, sort_keys=True)
            provisional_processed = json.dumps(
                processed, ensure_ascii=False, sort_keys=True
            )
            source_version, valid_from = self._backfill_version(
                connection,
                record_id=item["id"],
                hash_value=item["content_hash"],
                raw_json=provisional_raw,
                processed_json=provisional_processed,
                observed_at=observed_at,
            )
            raw.update(source_version=source_version, valid_from=valid_from)
            processed.update(source_version=source_version, valid_from=valid_from)
            raw_json = json.dumps(raw, ensure_ascii=False, sort_keys=True)
            processed_json = json.dumps(
                processed, ensure_ascii=False, sort_keys=True
            )
            connection.execute(
                "UPDATE record_versions SET raw_json = ?, processed_json = ? "
                "WHERE record_id = ? AND source_version = ?",
                (raw_json, processed_json, item["id"], source_version),
            )
            if item["record_kind"] == "campaign":
                connection.execute(
                    "UPDATE campaigns SET raw_json = ?, processed_json = ?, "
                    "content_hash = ?, duplicate_fingerprint = ?, "
                    "duplicate_cluster_id = ?, source_version = ?, valid_from = ? "
                    "WHERE id = ?",
                    (
                        raw_json,
                        processed_json,
                        item["content_hash"],
                        item["duplicate_fingerprint"],
                        item["duplicate_cluster_id"],
                        source_version,
                        valid_from,
                        item["id"],
                    ),
                )
            else:
                connection.execute(
                    "UPDATE products SET raw_json = ? WHERE id = ?",
                    (raw_json, item["id"]),
                )

        connection.execute(
            "INSERT INTO schema_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("lineage_backfill_version", "1"),
        )

    def import_dataset(self, dataset: dict[str, Any]) -> int:
        rows = dataset.get("records")
        if not isinstance(rows, list):
            raise ValueError("Veri setinde 'records' listesi bulunmuyor")
        accepted = [row for row in rows if isinstance(row, dict)]
        self.upsert_rows(accepted, run_status="imported")
        return len(accepted)

    def upsert_rows(self, rows: Iterable[dict[str, Any]], *, run_status: str) -> None:
        prepared = cluster_near_duplicates(self._prepare_row(row) for row in rows)
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            for row in prepared:
                self._upsert_row(connection, row, now)
            connection.execute(
                "INSERT INTO scrape_runs("
                "started_at, completed_at, status, record_count"
                ") VALUES (?, ?, ?, ?)",
                (now, now, run_status, len(prepared)),
            )

    def _prepare_row(self, row: dict[str, Any]) -> dict[str, Any]:
        raw = {
            key: value for key, value in dict(row).items() if key not in _DERIVED_FIELDS
        }
        raw.setdefault("record_kind", "campaign")
        if raw["record_kind"] not in {"campaign", "product"}:
            raw["record_kind"] = "campaign"
        raw["content_hash"] = content_hash(
            str(raw.get("title") or ""), str(raw.get("content") or "")
        )
        raw["duplicate_fingerprint"] = simhash(str(raw.get("content") or ""))
        return preprocess_record(raw)

    @staticmethod
    def _minor(money: Any) -> tuple[int | None, str | None]:
        if not isinstance(money, dict):
            return None, None
        try:
            amount = Decimal(str(money["amount"]))
            minor = int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            return minor, str(money["currency"])
        except (ArithmeticError, KeyError, TypeError, ValueError):
            return None, None

    @staticmethod
    def _duplicate_cluster(
        connection: sqlite3.Connection,
        *,
        bank_id: int,
        record_id: str,
        fingerprint: str,
        suggested: str,
    ) -> str:
        candidates = connection.execute(
            "SELECT duplicate_fingerprint, duplicate_cluster_id "
            "FROM campaigns WHERE bank_id = ? AND id <> ? "
            "AND duplicate_fingerprint IS NOT NULL",
            (bank_id, record_id),
        ).fetchall()
        nearby = [
            str(cluster_id)
            for existing_fingerprint, cluster_id in candidates
            if cluster_id
            and hamming_distance(fingerprint, str(existing_fingerprint)) <= 6
        ]
        return min([suggested, *nearby]) if nearby else suggested

    @staticmethod
    def _persist_version(
        connection: sqlite3.Connection,
        *,
        record_id: str,
        hash_value: str,
        raw_json: str,
        processed_json: str,
        now: str,
    ) -> tuple[int, str]:
        current = connection.execute(
            "SELECT source_version, content_hash, valid_from FROM record_versions "
            "WHERE record_id = ? AND is_current = 1",
            (record_id,),
        ).fetchone()
        if current and current[1] == hash_value:
            connection.execute(
                "UPDATE record_versions SET occurrence_count = occurrence_count + 1, "
                "last_seen_at = ?, raw_json = ?, processed_json = ? "
                "WHERE record_id = ? AND source_version = ?",
                (now, raw_json, processed_json, record_id, current[0]),
            )
            return int(current[0]), str(current[2])
        next_version = int(
            connection.execute(
                "SELECT COALESCE(MAX(source_version), 0) + 1 "
                "FROM record_versions WHERE record_id = ?",
                (record_id,),
            ).fetchone()[0]
        )
        if current:
            connection.execute(
                "UPDATE record_versions SET valid_to = ?, superseded_by = ?, "
                "is_current = 0, last_seen_at = ? "
                "WHERE record_id = ? AND source_version = ?",
                (
                    now,
                    f"{record_id}:{next_version}",
                    now,
                    record_id,
                    current[0],
                ),
            )
        connection.execute(
            "INSERT INTO record_versions(record_id, source_version, content_hash, "
            "raw_json, processed_json, valid_from, valid_to, superseded_by, "
            "is_current, occurrence_count, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, 1, 1, ?)",
            (record_id, next_version, hash_value, raw_json, processed_json, now, now),
        )
        return next_version, now

    def _upsert_row(
        self, connection: sqlite3.Connection, row: dict[str, Any], now: str
    ) -> None:
        raw = {key: value for key, value in row.items() if key not in _DERIVED_FIELDS}
        structured = (
            row.get("structured") if isinstance(row.get("structured"), dict) else {}
        )
        slug = str(raw.get("bank_slug") or "")
        name = str(raw.get("bank_name") or "")
        if not slug or not name or not raw.get("id"):
            raise ValueError("SQLite kaydı için bank_slug, bank_name ve id zorunludur")
        connection.execute(
            """INSERT INTO banks(slug, name, created_at, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                 name=excluded.name,
                 updated_at=excluded.updated_at""",
            (slug, name, now, now),
        )
        bank_id = connection.execute(
            "SELECT id FROM banks WHERE slug = ?", (slug,)
        ).fetchone()[0]
        record_id = str(raw["id"])
        hash_value = str(
            raw.get("content_hash")
            or content_hash(str(raw.get("title") or ""), str(raw.get("content") or ""))
        )
        fingerprint = str(
            raw.get("duplicate_fingerprint") or simhash(str(raw.get("content") or ""))
        )
        suggested_cluster = str(
            raw.get("duplicate_cluster_id") or f"dup-{hash_value[:16]}"
        )
        duplicate_cluster = self._duplicate_cluster(
            connection,
            bank_id=bank_id,
            record_id=record_id,
            fingerprint=fingerprint,
            suggested=suggested_cluster,
        )
        raw.update(
            content_hash=hash_value,
            duplicate_fingerprint=fingerprint,
            duplicate_cluster_id=duplicate_cluster,
            canonical_url=raw.get("canonical_url") or raw.get("source_url"),
        )
        processed_payload = {
            **row,
            "content_hash": hash_value,
            "duplicate_fingerprint": fingerprint,
            "duplicate_cluster_id": duplicate_cluster,
            "canonical_url": raw["canonical_url"],
        }
        provisional_raw_json = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        provisional_processed_json = json.dumps(
            processed_payload, ensure_ascii=False, sort_keys=True
        )
        source_version, valid_from = self._persist_version(
            connection,
            record_id=record_id,
            hash_value=hash_value,
            raw_json=provisional_raw_json,
            processed_json=provisional_processed_json,
            now=now,
        )
        raw.update(source_version=source_version, valid_from=valid_from)
        processed_payload.update(source_version=source_version, valid_from=valid_from)
        raw_json = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        processed_json = json.dumps(
            processed_payload, ensure_ascii=False, sort_keys=True
        )
        connection.execute(
            "UPDATE record_versions SET raw_json = ?, processed_json = ? "
            "WHERE record_id = ? AND source_version = ?",
            (raw_json, processed_json, record_id, source_version),
        )
        structured_json = json.dumps(structured, ensure_ascii=False, sort_keys=True)
        if raw.get("record_kind") == "product":
            connection.execute(
                """INSERT INTO products(
                     id, bank_id, name, product_type, financing_type, currency,
                     source_url, raw_json, structured_json, created_at, updated_at
                   )
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name,
                     product_type=excluded.product_type,
                     financing_type=excluded.financing_type,
                     currency=excluded.currency,
                     source_url=excluded.source_url,
                     raw_json=excluded.raw_json,
                     structured_json=excluded.structured_json,
                     updated_at=excluded.updated_at""",
                (
                    record_id,
                    bank_id,
                    raw.get("title", ""),
                    structured.get("product_type"),
                    structured.get("financing_type"),
                    None,
                    raw.get("source_url", ""),
                    raw_json,
                    structured_json,
                    now,
                    now,
                ),
            )
            return
        product_matches = connection.execute(
            "SELECT id FROM products WHERE bank_id = ? AND lower(name) = lower(?)",
            (bank_id, raw.get("title", "")),
        ).fetchall()
        product_id = product_matches[0][0] if len(product_matches) == 1 else None
        reward_minor, reward_currency = self._minor(structured.get("reward_amount"))
        max_minor, max_currency = self._minor(structured.get("max_amount"))
        duration = (
            structured.get("duration")
            if isinstance(structured.get("duration"), dict)
            else {}
        )
        connection.execute(
            """INSERT INTO campaigns(
                  id, bank_id, product_id, title, source_url, product_type,
                  financing_type, profit_share_rate, discount_rate,
                  reward_amount_minor, reward_currency, max_amount_minor,
                  max_amount_currency, duration_value, duration_unit,
                  duration_days, eligibility, fee_information, raw_json,
                  processed_json, created_at, updated_at, scraped_at,
                  content_hash, duplicate_fingerprint, duplicate_cluster_id,
                  source_version, valid_from
               )
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                  bank_id=excluded.bank_id,
                  product_id=excluded.product_id,
                  title=excluded.title,
                  source_url=excluded.source_url,
                  product_type=excluded.product_type,
                  financing_type=excluded.financing_type,
                  profit_share_rate=excluded.profit_share_rate,
                  discount_rate=excluded.discount_rate,
                  reward_amount_minor=excluded.reward_amount_minor,
                  reward_currency=excluded.reward_currency,
                  max_amount_minor=excluded.max_amount_minor,
                  max_amount_currency=excluded.max_amount_currency,
                  duration_value=excluded.duration_value,
                  duration_unit=excluded.duration_unit,
                  duration_days=excluded.duration_days,
                  eligibility=excluded.eligibility,
                  fee_information=excluded.fee_information,
                  raw_json=excluded.raw_json,
                  processed_json=excluded.processed_json,
                  updated_at=excluded.updated_at,
                  scraped_at=excluded.scraped_at,
                  content_hash=excluded.content_hash,
                  duplicate_fingerprint=excluded.duplicate_fingerprint,
                  duplicate_cluster_id=excluded.duplicate_cluster_id,
                  source_version=excluded.source_version,
                  valid_from=excluded.valid_from""",
            (
                record_id,
                bank_id,
                product_id,
                raw.get("title", ""),
                raw.get("source_url", ""),
                structured.get("product_type"),
                structured.get("financing_type"),
                structured.get("profit_share_rate"),
                structured.get("discount_rate"),
                reward_minor,
                reward_currency,
                max_minor,
                max_currency,
                duration.get("value"),
                duration.get("unit"),
                duration.get("approx_days"),
                structured.get("target_audience"),
                structured.get("fee_information"),
                raw_json,
                processed_json,
                now,
                now,
                raw.get("scraped_at"),
                hash_value,
                fingerprint,
                duplicate_cluster,
                source_version,
                valid_from,
            ),
        )

    def export_datasets(self) -> tuple[dict[str, Any], dict[str, Any]]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT raw_json, processed_json FROM campaigns ORDER BY id"
            ).fetchall()
            product_rows = connection.execute(
                "SELECT raw_json, structured_json FROM products ORDER BY id"
            ).fetchall()
        raw_records = [json.loads(row[0]) for row in rows]
        processed_records = [json.loads(row[1]) for row in rows]
        for raw_json, structured_json in product_rows:
            raw = json.loads(raw_json)
            raw_records.append(raw)
            processed_records.append(
                preprocess_record(raw)
                if not structured_json
                else {
                    **preprocess_record(raw),
                    "structured": json.loads(structured_json),
                }
            )
        generated_at = datetime.now(timezone.utc).isoformat()
        raw = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at,
            "record_count": len(raw_records),
            "records": raw_records,
        }
        processed = {
            **raw,
            "preprocessed_at": generated_at,
            "records": processed_records,
            "record_count": len(processed_records),
        }
        return raw, processed

    def list_campaigns(self) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as connection:
            campaigns = [
                json.loads(row[0])
                for row in connection.execute(
                    "SELECT processed_json FROM campaigns ORDER BY id"
                )
            ]
            products = [
                (json.loads(raw_json), json.loads(structured_json))
                for raw_json, structured_json in connection.execute(
                    "SELECT raw_json, structured_json FROM products ORDER BY id"
                )
            ]
        return [self._enrich_processed(row) for row in campaigns] + [
            self._enrich_processed({**preprocess_record(raw), "structured": structured})
            for raw, structured in products
        ]

    @staticmethod
    def _nlp_text(record: dict[str, Any]) -> str:
        title = str(record.get("title") or "").strip()
        content = str(record.get("clean_text") or record.get("content") or "").strip()
        return "\n".join(part for part in (title, content) if part)

    def nlp_enrichment_candidates(
        self, *, max_records: int | None = None
    ) -> list[dict[str, Any]]:
        """Return a stable snapshot used for analyze-then-apply enrichment."""

        if max_records is not None and (
            isinstance(max_records, bool)
            or not isinstance(max_records, int)
            or max_records < 1
        ):
            raise ValueError("max_records pozitif bir tam sayı olmalıdır")
        self.initialize()
        query = (
            "SELECT id, content_hash, source_version, processed_json, scraped_at "
            "FROM campaigns ORDER BY id"
        )
        parameters: tuple[Any, ...] = ()
        if max_records is not None:
            query += " LIMIT ?"
            parameters = (max_records,)
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        result = []
        for record_id, hash_value, source_version, processed_json, scraped_at in rows:
            processed = self._json_object(processed_json)
            text = self._nlp_text(processed)
            if not text:
                continue
            structured = processed.get("structured")
            result.append(
                {
                    "id": str(record_id),
                    "content_hash": str(hash_value or processed.get("content_hash") or ""),
                    "source_version": int(source_version or 1),
                    "text": text,
                    "text_sha256": sha256(text.encode("utf-8")).hexdigest(),
                    "scraped_at": str(scraped_at or processed.get("scraped_at") or ""),
                    "structured": structured if isinstance(structured, dict) else {},
                }
            )
        return result

    @staticmethod
    def _validated_analysis(analysis: Any) -> tuple[str, str, int, str]:
        if not isinstance(analysis, dict) or analysis.get("contract") != RUNTIME_CONTRACT:
            raise ValueError("Geçersiz NLP analiz sözleşmesi")
        record = analysis.get("record")
        if not isinstance(record, dict):
            raise ValueError("NLP analizinde kayıt bilgisi eksik")
        record_id = record.get("id")
        hash_value = record.get("source_content_hash")
        source_version = record.get("source_version")
        text_hash = record.get("text_sha256")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("NLP analizinde kayıt kimliği eksik")
        if not isinstance(hash_value, str) or len(hash_value) != 64:
            raise ValueError("NLP analizinde kaynak SHA256 eksik")
        if (
            isinstance(source_version, bool)
            or not isinstance(source_version, int)
            or source_version < 1
        ):
            raise ValueError("NLP analizinde kaynak sürümü eksik")
        if not isinstance(text_hash, str) or len(text_hash) != 64:
            raise ValueError("NLP analizinde metin SHA256 eksik")
        suggestions = analysis.get("suggestions")
        if not isinstance(suggestions, dict):
            raise ValueError("NLP analizinde öneri nesnesi eksik")
        unexpected = set(suggestions) - SUGGESTION_ALLOWLIST
        if unexpected:
            raise ValueError(
                "İzin verilmeyen NLP önerileri: " + ", ".join(sorted(unexpected))
            )
        return record_id, hash_value, source_version, text_hash

    @staticmethod
    def _validate_analysis_evidence(
        analysis: dict[str, Any], *, text: str, structured: dict[str, Any]
    ) -> None:
        for field, suggestion in analysis["suggestions"].items():
            if not field_is_missing(structured, field):
                raise ValueError(f"NLP önerisi yalnız eksik alan için saklanabilir: {field}")
            if not isinstance(suggestion, dict) or suggestion.get("advisory") is not True:
                raise ValueError(f"Geçersiz NLP önerisi: {field}")
            suggested_value = suggestion.get("value")
            if suggested_value in (None, "", [], {}):
                raise ValueError(f"NLP önerisi değersiz olamaz: {field}")
            evidence = suggestion.get("evidence")
            if not isinstance(evidence, dict):
                raise ValueError(f"NLP önerisi kanıtsız olamaz: {field}")
            start = evidence.get("char_start")
            end = evidence.get("char_end")
            value = evidence.get("text")
            if (
                isinstance(start, bool)
                or not isinstance(start, int)
                or isinstance(end, bool)
                or not isinstance(end, int)
                or not isinstance(value, str)
                or start < 0
                or end <= start
                or text[start:end] != value
            ):
                raise ValueError(f"NLP önerisi kanıt aralığı geçersiz: {field}")

    def apply_nlp_analyses(self, analyses: Iterable[dict[str, Any]]) -> int:
        """Atomically attach advisory analysis without changing source lineage."""

        prepared = list(analyses)
        if not prepared:
            return 0
        identities = [self._validated_analysis(item) for item in prepared]
        record_ids = [item[0] for item in identities]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("Aynı kayıt için birden fazla NLP analizi verildi")
        ordered = sorted(zip(identities, prepared), key=lambda item: item[0][0])
        self.initialize()
        changed = 0
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for identity, analysis in ordered:
                record_id, expected_hash, expected_version, expected_text_hash = identity
                row = connection.execute(
                    "SELECT content_hash, source_version, processed_json "
                    "FROM campaigns WHERE id = ?",
                    (record_id,),
                ).fetchone()
                if row is None:
                    raise StaleNlpAnalysisError(
                        f"NLP analiz kaydı artık mevcut değil: {record_id}"
                    )
                current_hash = str(row[0] or "")
                current_version = int(row[1] or 1)
                processed = self._json_object(row[2])
                text = self._nlp_text(processed)
                current_text_hash = sha256(text.encode("utf-8")).hexdigest()
                if (
                    current_hash != expected_hash
                    or current_version != expected_version
                    or current_text_hash != expected_text_hash
                ):
                    raise StaleNlpAnalysisError(
                        f"NLP analiz kaynağı güncel değil: {record_id}"
                    )
                structured = processed.get("structured")
                structured = structured if isinstance(structured, dict) else {}
                self._validate_analysis_evidence(
                    analysis, text=text, structured=structured
                )
                if processed.get("nlp_analysis") == analysis:
                    continue
                processed["nlp_analysis"] = analysis
                processed_json = json.dumps(
                    processed, ensure_ascii=False, sort_keys=True
                )
                updated = connection.execute(
                    "UPDATE campaigns SET processed_json = ? "
                    "WHERE id = ? AND content_hash = ? AND source_version = ?",
                    (processed_json, record_id, expected_hash, expected_version),
                )
                if updated.rowcount != 1:
                    raise StaleNlpAnalysisError(
                        f"NLP analiz kaynağı yazma sırasında değişti: {record_id}"
                    )
                version_updated = connection.execute(
                    "UPDATE record_versions SET processed_json = ? "
                    "WHERE record_id = ? AND source_version = ? "
                    "AND content_hash = ? AND is_current = 1",
                    (processed_json, record_id, expected_version, expected_hash),
                )
                if version_updated.rowcount != 1:
                    raise StaleNlpAnalysisError(
                        f"NLP analiz kaynak sürümü bulunamadı: {record_id}"
                    )
                changed += 1
        return changed

    def query_campaigns(
        self,
        *,
        bank_slug: str | None = None,
        bank_slugs: Iterable[str] | None = None,
        product_type: str | None = None,
        financing_type: str | None = None,
        currency: str | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Kampanyaları SQL tarafında filtreler ve sayfalar."""
        self.initialize()
        clauses: list[str] = []
        parameters: list[Any] = []
        selected_banks = list(dict.fromkeys(bank_slugs or ()))
        if bank_slug and selected_banks:
            raise ValueError("bank_slug ile bank_slugs birlikte kullanılamaz")
        if bank_slug:
            clauses.append("b.slug = ?")
            parameters.append(bank_slug)
        elif selected_banks:
            placeholders = ",".join("?" for _ in selected_banks)
            clauses.append(f"b.slug IN ({placeholders})")
            parameters.extend(selected_banks)
        if product_type:
            clauses.append("c.product_type = ?")
            parameters.append(product_type)
        if financing_type:
            clauses.append("c.financing_type = ?")
            parameters.append(financing_type)
        if currency:
            clauses.append(
                "(c.reward_currency = ? OR c.max_amount_currency = ?)"
            )
            parameters.extend((currency, currency))
        if search:
            clauses.append("c.title LIKE ? COLLATE NOCASE")
            parameters.append(f"%{search}%")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        bank_join = (
            " JOIN banks b ON b.id = c.bank_id"
            if bank_slug or selected_banks
            else ""
        )
        base = " FROM campaigns c" + bank_join + where
        with self._connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*)" + base, parameters
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT c.processed_json" + base
                + " ORDER BY c.updated_at DESC, c.id LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            ).fetchall()
        return [self._enrich_processed(json.loads(row[0])) for row in rows], int(total)

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT processed_json FROM campaigns WHERE id = ?",
                (campaign_id,),
            ).fetchone()
        return self._enrich_processed(json.loads(row[0])) if row else None

    def record_versions(self, record_id: str) -> list[dict[str, Any]]:
        """Bir kaydın kapanmış ve güncel kaynak sürümlerini kronolojik döndürür."""
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT source_version, content_hash, valid_from, valid_to, "
                "superseded_by, is_current, occurrence_count, last_seen_at "
                "FROM record_versions WHERE record_id = ? ORDER BY source_version",
                (record_id,),
            ).fetchall()
            if not rows:
                current = connection.execute(
                    "SELECT content_hash, created_at, updated_at FROM campaigns "
                    "WHERE id = ?",
                    (record_id,),
                ).fetchone()
                if current:
                    rows = [(1, current[0] or "", current[1], None, None, 1, 1, current[2])]
        return [
            {
                "source_version": int(row[0]),
                "content_hash": row[1],
                "valid_from": row[2],
                "valid_to": row[3],
                "superseded_by": row[4],
                "is_current": bool(row[5]),
                "occurrence_count": int(row[6]),
                "last_seen_at": row[7],
            }
            for row in rows
        ]

    def data_quality_summary(self) -> dict[str, Any]:
        """Teknik dashboard için kanıt, eksiklik ve tekrar kapsamını özetler."""
        records = self.list_campaigns()
        statuses: dict[str, int] = {}
        evidenced_fields = 0
        enriched_evidenced_fields = 0
        recovered_failed_fields = 0
        grounded_entity_counts: dict[str, int] = {}
        temporal_observation_count = 0
        field_count = 0
        clusters: dict[str, int] = {}
        for record in records:
            cluster_id = record.get("duplicate_cluster_id")
            if cluster_id:
                key = str(cluster_id)
                clusters[key] = clusters.get(key, 0) + 1
            structured = record.get("structured")
            fields = structured.get("fields", {}) if isinstance(structured, dict) else {}
            analysis = record.get("nlp_analysis")
            suggestions = (
                analysis.get("suggestions", {}) if isinstance(analysis, dict) else {}
            )
            suggestions = suggestions if isinstance(suggestions, dict) else {}
            if isinstance(analysis, dict):
                temporal_observation_count += isinstance(
                    analysis.get("temporal_observation"), dict
                )
                entities = analysis.get("entities")
                entities = entities if isinstance(entities, list) else []
                for entity in entities:
                    if not isinstance(entity, dict):
                        continue
                    if entity.get("source") != "grounded_context_extraction":
                        continue
                    label = str(entity.get("label") or "")
                    if label:
                        grounded_entity_counts[label] = (
                            grounded_entity_counts.get(label, 0) + 1
                        )
            for field_name, field in fields.items():
                if not isinstance(field_name, str) or not isinstance(field, dict):
                    continue
                status = str(field.get("status") or "UNKNOWN")
                statuses[status] = statuses.get(status, 0) + 1
                field_count += 1
                has_source_evidence = field.get("evidence") is not None
                has_verified_suggestion = field_name in suggestions
                evidenced_fields += has_source_evidence
                enriched_evidenced_fields += (
                    has_source_evidence or has_verified_suggestion
                )
                recovered_failed_fields += (
                    status == "EXTRACTION_FAILED" and has_verified_suggestion
                )
        return {
            "record_count": len(records),
            "duplicate_cluster_count": sum(
                count > 1 for count in clusters.values()
            ),
            "field_statuses": statuses,
            "evidence_coverage": (
                round(evidenced_fields / field_count, 4) if field_count else 0.0
            ),
            "enriched_evidence_coverage": (
                round(enriched_evidenced_fields / field_count, 4)
                if field_count
                else 0.0
            ),
            "verified_enrichment_fields": (
                enriched_evidenced_fields - evidenced_fields
            ),
            "recovered_extraction_failures": recovered_failed_fields,
            "grounded_entity_counts": grounded_entity_counts,
            "temporal_observation_count": temporal_observation_count,
        }

    def dashboard_summary(self) -> dict[str, Any]:
        """Dashboard kartları için tek bağlantıda toplu istatistik üretir."""
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """WITH records AS (
                       SELECT bank_id, product_type, updated_at, 1 AS is_campaign,
                              profit_share_rate
                       FROM campaigns
                       UNION ALL
                       SELECT bank_id, product_type, updated_at, 0, NULL
                       FROM products
                   )
                   SELECT COUNT(DISTINCT bank_id),
                          SUM(is_campaign),
                          COUNT(*) - SUM(is_campaign),
                          COUNT(*),
                          MAX(updated_at),
                          AVG(profit_share_rate)
                   FROM records"""
            ).fetchone()
            product_types = {
                item[0]: int(item[1])
                for item in connection.execute(
                    """SELECT COALESCE(NULLIF(TRIM(product_type), ''), 'unspecified'),
                              COUNT(*)
                       FROM campaigns
                       GROUP BY COALESCE(NULLIF(TRIM(product_type), ''), 'unspecified')
                       ORDER BY COUNT(*) DESC, 1 COLLATE NOCASE"""
                )
            }
        bank_count, campaign_count, product_count, record_count, updated_at, average = row
        return {
            "campaign_count": int(campaign_count or 0),
            "product_count": int(product_count or 0),
            "bank_count": int(bank_count or 0),
            "record_count": int(record_count or 0),
            "average_profit_share_rate": (
                round(float(average), 4) if average is not None else None
            ),
            "last_updated_at": updated_at,
            "campaigns_by_product_type": product_types,
        }

    def bank_summary(self) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """WITH totals AS (
                       SELECT bank_id, SUM(campaign_count) AS campaign_count,
                              SUM(product_count) AS product_count,
                              MAX(last_updated_at) AS last_updated_at
                       FROM (
                           SELECT bank_id, COUNT(*) AS campaign_count,
                                  0 AS product_count, MAX(updated_at) AS last_updated_at
                           FROM campaigns GROUP BY bank_id
                           UNION ALL
                           SELECT bank_id, 0, COUNT(*), MAX(updated_at)
                           FROM products GROUP BY bank_id
                       )
                       GROUP BY bank_id
                   )
                   SELECT b.slug, b.name, b.website,
                          COALESCE(t.campaign_count, 0),
                          COALESCE(t.product_count, 0), t.last_updated_at
                   FROM banks b
                   LEFT JOIN totals t ON t.bank_id = b.id
                   ORDER BY b.name COLLATE NOCASE"""
            ).fetchall()
        return [
            {
                "slug": row[0],
                "name": row[1],
                "website": row[2],
                "campaign_count": int(row[3]),
                "product_count": int(row[4]),
                "last_updated_at": row[5],
            }
            for row in rows
        ]

    def bank_distribution(self) -> list[dict[str, Any]]:
        """Banka dağılımını çarpımsız SQL agregasyonuyla üretir."""
        banks = self.bank_summary()
        campaign_total = sum(item["campaign_count"] for item in banks)
        record_total = sum(
            item["campaign_count"] + item["product_count"] for item in banks
        )
        return [
            {
                **item,
                "record_count": item["campaign_count"] + item["product_count"],
                "campaign_share": (
                    round(item["campaign_count"] / campaign_total, 4)
                    if campaign_total
                    else 0.0
                ),
                "record_share": (
                    round(
                        (item["campaign_count"] + item["product_count"])
                        / record_total,
                        4,
                    )
                    if record_total
                    else 0.0
                ),
            }
            for item in banks
        ]

    def product_type_distribution(self) -> list[dict[str, Any]]:
        """Kampanya ve ürün türü dağılımını yalnızca SQL agregasyonuyla döndürür."""
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """WITH typed AS (
                       SELECT COALESCE(NULLIF(TRIM(product_type), ''), 'unspecified')
                                  AS product_type,
                              1 AS campaign_count, 0 AS product_count
                       FROM campaigns
                       UNION ALL
                       SELECT COALESCE(NULLIF(TRIM(product_type), ''), 'unspecified'),
                              0, 1
                       FROM products
                   ), totals AS (
                       SELECT product_type, SUM(campaign_count) AS campaign_count,
                              SUM(product_count) AS product_count
                       FROM typed GROUP BY product_type
                   )
                   SELECT product_type, campaign_count, product_count,
                          campaign_count + product_count AS record_count,
                          CAST(campaign_count + product_count AS REAL)
                              / SUM(campaign_count + product_count) OVER () AS share
                   FROM totals
                   ORDER BY record_count DESC, product_type COLLATE NOCASE"""
            ).fetchall()
        return [
            {
                "product_type": row[0],
                "campaign_count": int(row[1]),
                "product_count": int(row[2]),
                "record_count": int(row[3]),
                "share": round(float(row[4]), 4),
            }
            for row in rows
        ]

    def freshness_summary(self) -> dict[str, Any]:
        """Kayıtların ve kaynağın son güncellik zamanlarını özetler."""
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """SELECT
                       (SELECT MAX(updated_at) FROM (
                           SELECT updated_at FROM campaigns
                           UNION ALL SELECT updated_at FROM products
                       )),
                       (SELECT MAX(scraped_at) FROM campaigns),
                       (SELECT COUNT(*) FROM campaigns WHERE scraped_at IS NULL)"""
            ).fetchone()
        return {
            "last_record_updated_at": row[0],
            "last_scraped_at": row[1],
            "campaigns_without_scraped_at": int(row[2]),
            "latest_scrape_run": self.latest_scrape_run(),
        }

    def recent_campaigns(self, *, limit: int = 5) -> list[dict[str, Any]]:
        """Dashboard tablosu için küçük, sınırlı bir projeksiyon döndürür."""
        if not 1 <= limit <= 50:
            raise ValueError("limit 1 ile 50 arasında olmalıdır")
        self.initialize()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT c.id, b.slug, b.name, c.title, c.source_url,
                          c.product_type, c.updated_at, c.scraped_at
                   FROM campaigns c
                   JOIN banks b ON b.id = c.bank_id
                   ORDER BY COALESCE(c.scraped_at, c.updated_at) DESC, c.id
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {
                "id": row[0],
                "bank_slug": row[1],
                "bank_name": row[2],
                "title": row[3],
                "source_url": row[4],
                "product_type": row[5],
                "updated_at": row[6],
                "scraped_at": row[7],
            }
            for row in rows
        ]

    def filter_options(self) -> dict[str, Any]:
        """API filtre seçeneklerini tüm kayıtları yüklemeden SQL'de üretir."""
        self.initialize()
        with self._connect() as connection:
            banks = [
                {"value": row[0], "label": row[1], "count": int(row[2])}
                for row in connection.execute(
                    """SELECT b.slug, b.name, COUNT(c.id)
                       FROM banks b JOIN campaigns c ON c.bank_id = b.id
                       GROUP BY b.id
                       ORDER BY b.name COLLATE NOCASE"""
                )
            ]
            product_types = [
                {"value": row[0], "label": row[0], "count": int(row[1])}
                for row in connection.execute(
                    """SELECT product_type, COUNT(*) FROM campaigns
                       WHERE product_type IS NOT NULL AND TRIM(product_type) <> ''
                       GROUP BY product_type
                       ORDER BY product_type COLLATE NOCASE"""
                )
            ]
            currencies = [
                {"value": row[0], "label": row[0], "count": int(row[1])}
                for row in connection.execute(
                    """SELECT currency, COUNT(DISTINCT campaign_id) FROM (
                           SELECT id AS campaign_id, reward_currency AS currency
                           FROM campaigns
                           UNION ALL
                           SELECT id, max_amount_currency FROM campaigns
                       )
                       WHERE currency IS NOT NULL AND TRIM(currency) <> ''
                       GROUP BY currency
                       ORDER BY currency COLLATE NOCASE"""
                )
            ]
        return {
            "banks": banks,
            "product_types": product_types,
            "currencies": currencies,
        }

    def latest_scrape_run(self) -> dict[str, Any] | None:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, started_at, completed_at, status, record_count "
                "FROM scrape_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "started_at": row[1],
            "completed_at": row[2],
            "status": row[3],
            "record_count": row[4],
        }
