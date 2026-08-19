"""Geriye uyumlu JSON export üreten SQLite ana veri kaynağı."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import sqlite3
from typing import Any, Iterable

from src.preprocessing.clean_text import preprocess_record
from src.scraper.models import SCHEMA_VERSION

_DERIVED_FIELDS = frozenset({"clean_text", "tokens", "token_count", "structured"})


class CampaignStore:
    """Banka ürün/kampanya kayıtlarını idempotent şekilde saklar."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

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
                """)
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
                ("schema_version", "1"),
            )
            for column, definition in (
                ("product_type", "TEXT"),
                ("reward_currency", "TEXT"),
                ("max_amount_currency", "TEXT"),
                ("scraped_at", "TEXT"),
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

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection, table: str, column: str, definition: str
    ) -> None:
        columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def import_dataset(self, dataset: dict[str, Any]) -> int:
        rows = dataset.get("records")
        if not isinstance(rows, list):
            raise ValueError("Veri setinde 'records' listesi bulunmuyor")
        prepared = [self._prepare_row(row) for row in rows if isinstance(row, dict)]
        self.upsert_rows(prepared, run_status="imported")
        return len(prepared)

    def upsert_rows(self, rows: Iterable[dict[str, Any]], *, run_status: str) -> None:
        prepared = [self._prepare_row(row) for row in rows]
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
        raw_json = json.dumps(raw, ensure_ascii=False, sort_keys=True)
        structured_json = json.dumps(structured, ensure_ascii=False, sort_keys=True)
        record_id = str(raw["id"])
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
                  processed_json, created_at, updated_at, scraped_at
               )
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                  scraped_at=excluded.scraped_at""",
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
                json.dumps(row, ensure_ascii=False, sort_keys=True),
                now,
                now,
                raw.get("scraped_at"),
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
        return campaigns + [
            {**preprocess_record(raw), "structured": structured}
            for raw, structured in products
        ]

    def query_campaigns(
        self,
        *,
        bank_slug: str | None = None,
        product_type: str | None = None,
        currency: str | None = None,
        search: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Kampanyaları SQL tarafında filtreler ve sayfalar."""
        self.initialize()
        clauses: list[str] = []
        parameters: list[Any] = []
        if bank_slug:
            clauses.append("b.slug = ?")
            parameters.append(bank_slug)
        if product_type:
            clauses.append("c.product_type = ?")
            parameters.append(product_type)
        if currency:
            clauses.append(
                "(c.reward_currency = ? OR c.max_amount_currency = ?)"
            )
            parameters.extend((currency, currency))
        if search:
            clauses.append("c.title LIKE ? COLLATE NOCASE")
            parameters.append(f"%{search}%")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        bank_join = " JOIN banks b ON b.id = c.bank_id" if bank_slug else ""
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
        return [json.loads(row[0]) for row in rows], int(total)

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT processed_json FROM campaigns WHERE id = ?",
                (campaign_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

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
