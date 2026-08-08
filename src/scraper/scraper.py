"""BDDK ve banka kampanya scraper'lari icin komut satiri arayuzu."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

from src.comparison import ComparisonQuery, compare_records
from src.persistence import CampaignStore
from src.preprocessing.clean_text import preprocess_dataset

from .bddk import fetch_participation_banks
from .base import build_failure
from .coverage import build_coverage_report
from .http import HttpClient
from .registry import SCRAPERS, resolve_banks
from .storage import campaign_dataset, write_json
from .validation import (
    build_processed_coverage,
    build_quality_report,
    select_valid_campaigns,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_DATABASE_PATH = Path(os.getenv("RAGNROLL_DB_PATH", "data/ragnroll.sqlite3"))


def _client(args: argparse.Namespace) -> HttpClient:
    return HttpClient(
        delay_seconds=args.delay,
        timeout_seconds=args.timeout,
        respect_robots=not args.ignore_robots,
    )


def run_banks(args: argparse.Namespace) -> int:
    payload = fetch_participation_banks(_client(args))
    write_json(args.output, payload)
    print(f"{payload['count']} katılım bankası yazıldı: {args.output}")
    return 0


def _require_distinct_paths(*paths: Path) -> None:
    resolved = [path.resolve() for path in paths]
    if len(resolved) != len(set(resolved)):
        raise ValueError("collect output paths must differ")


def run_collect(args: argparse.Namespace) -> int:
    """BDDK katalogundan başlayarak ham, işlenmiş ve kalite çıktısı üretir."""
    _require_distinct_paths(
        args.banks_output,
        args.raw_output,
        args.processed_output,
        args.quality_report,
    )
    client = _client(args)
    catalog = fetch_participation_banks(client)
    coverage = build_coverage_report(catalog["banks"], SCRAPERS)
    selected_slugs = [
        bank["slug"] for bank in catalog["banks"] if bank["slug"] in SCRAPERS
    ]

    records = []
    failures: list[dict[str, Any]] = []
    for slug in selected_slugs:
        scraper_class = SCRAPERS[slug]
        bank_base_url = ""
        LOGGER.info("Scraper started for %s", slug)
        try:
            configured_base_url = getattr(
                getattr(scraper_class, "config", None), "base_url", ""
            )
            if isinstance(configured_base_url, str):
                bank_base_url = configured_base_url
            bank_records, bank_failures = scraper_class(client=client).scrape(
                limit=args.max_per_bank
            )
        except Exception as exc:
            LOGGER.exception("Scraper failed for %s", slug)
            failures.append(build_failure(slug, "scrape", bank_base_url, exc))
            continue
        records.extend(bank_records)
        failures.extend(bank_failures)
        LOGGER.info(
            "Bank completed for %s: %d records, %d failures",
            slug,
            len(bank_records),
            len(bank_failures),
        )

    valid_records, duplicates, record_issues = select_valid_campaigns(records)
    raw = campaign_dataset(valid_records)
    processed = preprocess_dataset(raw)
    quality = build_quality_report(
        records,
        failures,
        duplicates,
        record_issues=record_issues,
        persisted_records=valid_records,
    )
    expected_banks = [bank["slug"] for bank in catalog["banks"]]
    quality["coverage"] = coverage
    quality["processed_coverage"] = build_processed_coverage(
        processed["records"], expected_banks=expected_banks
    )

    write_json(args.banks_output, catalog)
    if valid_records:
        database = getattr(args, "database", None)
        if database is not None:
            store = CampaignStore(database)
            store.upsert_rows(
                processed["records"],
                run_status=(
                    "partial" if failures or quality["error_count"] else "success"
                ),
            )
            raw, processed = store.export_datasets()
        write_json(args.raw_output, raw)
        write_json(args.processed_output, processed)
    write_json(args.quality_report, quality)

    print(
        f"{len(valid_records)} kayıt, "
        f"{quality['processed_coverage']['bank_coverage']['represented']}/"
        f"{quality['processed_coverage']['bank_coverage']['expected']} banka: "
        f"{args.quality_report}"
    )
    bank_complete = quality["processed_coverage"]["bank_coverage"]["ratio"] == 1.0
    if (
        not coverage["complete"]
        or not valid_records
        or quality["error_count"]
        or failures
        or not bank_complete
    ):
        return 2
    return 0


def run_db_init(args: argparse.Namespace) -> int:
    CampaignStore(args.database).initialize()
    print(f"SQLite schema hazır: {args.database}")
    return 0


def run_db_import(args: argparse.Namespace) -> int:
    with args.input.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    count = CampaignStore(args.database).import_dataset(payload)
    print(f"{count} kayıt SQLite'a içe aktarıldı: {args.database}")
    return 0


def run_db_export(args: argparse.Namespace) -> int:
    _require_distinct_paths(args.raw_output, args.processed_output)
    raw, processed = CampaignStore(args.database).export_datasets()
    write_json(args.raw_output, raw)
    write_json(args.processed_output, processed)
    print(f"{raw['record_count']} kayıt JSON'a aktarıldı")
    return 0


def run_compare(args: argparse.Namespace) -> int:
    store = CampaignStore(args.database)
    result = compare_records(
        store.list_campaigns(),
        ComparisonQuery(
            product_type=args.product_type,
            currency=args.currency,
            duration_days=args.duration_days,
            eligibility=args.eligibility,
            financing_type=getattr(args, "financing_type", None),
            amount=getattr(args, "amount", None),
            title=getattr(args, "title", None),
        ),
    )
    write_json(args.output, result.to_dict())
    print(f"{len(result['included'])} karşılaştırılabilir kayıt yazıldı: {args.output}")
    return 0


def run_campaigns(args: argparse.Namespace) -> int:
    if args.output.resolve() == args.quality_report.resolve():
        raise ValueError("Campaign and quality report output paths must differ")
    bank_slugs = resolve_banks(args.banks)
    client = _client(args)
    records = []
    failures: list[dict[str, Any]] = []
    for slug in bank_slugs:
        scraper_class = SCRAPERS[slug]
        bank_base_url = ""
        LOGGER.info("Scraper started for %s", slug)
        try:
            configured_base_url = getattr(
                getattr(scraper_class, "config", None), "base_url", ""
            )
            if isinstance(configured_base_url, str):
                bank_base_url = configured_base_url
            bank_scraper = scraper_class(client=client)
            bank_records, bank_failures = bank_scraper.scrape(limit=args.max_per_bank)
        except Exception as exc:
            LOGGER.exception("Scraper failed for %s", slug)
            failures.append(build_failure(slug, "scrape", bank_base_url, exc))
            continue
        records.extend(bank_records)
        failures.extend(bank_failures)
        LOGGER.info(
            "Bank completed for %s: %d records, %d failures",
            slug,
            len(bank_records),
            len(bank_failures),
        )

    valid_records, duplicates, record_issues = select_valid_campaigns(records)
    LOGGER.info("Duplicates removed: %d", len(duplicates))
    report = build_quality_report(
        records,
        failures,
        duplicates,
        record_issues=record_issues,
        persisted_records=valid_records,
    )
    LOGGER.info("Validation completed: %d errors", report["error_count"])
    LOGGER.info(
        "Discarded invalid campaign records: %d", report["rejected_record_count"]
    )
    dataset = campaign_dataset(valid_records)
    if valid_records:
        write_json(args.output, dataset)
        LOGGER.info("Data persisted: campaign dataset %s", args.output)
    elif records:
        LOGGER.info(
            "Campaign data preserved: all collected records rejected by validation; "
            "skipped write to %s",
            args.output,
        )
    else:
        LOGGER.info(
            "Campaign data preserved: no records collected; skipped write to %s",
            args.output,
        )
    write_json(args.quality_report, report)
    LOGGER.info("Quality report persisted: %s", args.quality_report)
    if valid_records:
        print(
            f"{len(valid_records)} kampanya yazıldı: {args.output} "
            f"(kalite skoru={report['quality_score']:.2%}, çekme hatası={len(failures)}, "
            f"yinelenen={len(duplicates)})"
        )
    else:
        print(
            f"0 kampanya için veri seti yazılmadı: {args.output} "
            f"(kalite skoru={report['quality_score']:.2%}, çekme hatası={len(failures)}, "
            f"yinelenen={len(duplicates)})"
        )
    if not records or report["error_count"] or failures:
        return 2
    return 0


def run_validate(args: argparse.Namespace) -> int:
    with args.input.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    # JSON'dan model kurmaya gerek olmadan temel dis veri seti kontrolleri.
    from .models import Campaign

    rows = payload.get("records", [])
    if not isinstance(rows, list):
        raise ValueError("Veri setinde 'records' listesi bulunmuyor")
    records = []
    conversion_errors: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        try:
            from datetime import date, datetime

            if not isinstance(row, dict):
                raise TypeError("Kayıt bir JSON nesnesi olmalı")
            converted = dict(row)
            for name in ("start_date", "end_date"):
                if converted.get(name):
                    converted[name] = date.fromisoformat(converted[name])
                else:
                    converted[name] = None
            if converted.get("scraped_at"):
                converted["scraped_at"] = datetime.fromisoformat(
                    converted["scraped_at"]
                )
            else:
                converted["scraped_at"] = None
            records.append(Campaign(**converted))
        except (TypeError, ValueError) as exc:
            source_url = row.get("source_url", "") if isinstance(row, dict) else ""
            conversion_errors.append(
                {"record_index": index, "url": str(source_url), "error": str(exc)}
            )
    report = build_quality_report(records)
    report["input_record_count"] = len(rows)
    report["conversion_error_count"] = len(conversion_errors)
    report["conversion_errors"] = conversion_errors
    report["overall_quality_score"] = (
        round(report["valid_record_count"] / len(rows), 4) if rows else 0.0
    )
    write_json(args.output, report)
    print(f"Genel kalite skoru={report['overall_quality_score']:.2%}: {args.output}")
    return 2 if report["error_count"] or conversion_errors else 0


def run_preprocess(args: argparse.Namespace) -> int:
    with args.input.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    result = preprocess_dataset(payload)
    write_json(args.output, result)
    print(f"{result['record_count']} işlenmiş kayıt yazıldı: {args.output}")
    return 0


def add_http_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Aynı sunucu istekleri arasındaki saniye",
    )
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument(
        "--ignore-robots",
        action="store_true",
        help="Yalnızca site sahibinden açık izin varsa kullanın",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    banks = subparsers.add_parser("banks", help="BDDK katılım bankası listesini çek")
    banks.add_argument(
        "--output", type=Path, default=Path("data/raw/participation_banks.json")
    )
    add_http_options(banks)
    banks.set_defaults(handler=run_banks)

    campaigns = subparsers.add_parser("campaigns", help="Banka kampanyalarını çek")
    campaigns.add_argument(
        "--banks",
        default="priority",
        help="priority, all veya virgülle ayrılmış banka slug'ları",
    )
    campaigns.add_argument("--max-per-bank", type=int, default=20)
    campaigns.add_argument(
        "--output", type=Path, default=Path("data/raw/campaigns.json")
    )
    campaigns.add_argument(
        "--quality-report", type=Path, default=Path("outputs/quality_report.json")
    )
    add_http_options(campaigns)
    campaigns.set_defaults(handler=run_campaigns)

    collect = subparsers.add_parser(
        "collect",
        help="BDDK katalogundan başlayarak tüm veri hattını çalıştır",
    )
    collect.add_argument("--max-per-bank", type=int, default=20)
    collect.add_argument(
        "--banks-output",
        type=Path,
        default=Path("data/raw/participation_banks.json"),
    )
    collect.add_argument(
        "--raw-output", type=Path, default=Path("data/raw/campaigns.json")
    )
    collect.add_argument(
        "--processed-output",
        type=Path,
        default=Path("data/processed/campaigns.json"),
    )
    collect.add_argument(
        "--quality-report", type=Path, default=Path("outputs/quality_report.json")
    )
    collect.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    add_http_options(collect)
    collect.set_defaults(handler=run_collect)

    validate = subparsers.add_parser(
        "validate", help="Mevcut kampanya JSON'unu doğrula"
    )
    validate.add_argument("input", type=Path)
    validate.add_argument(
        "--output", type=Path, default=Path("outputs/quality_report.json")
    )
    validate.set_defaults(handler=run_validate)

    preprocess = subparsers.add_parser(
        "preprocess",
        help="Kampanya metinlerini temizle ve tokenize et",
    )
    preprocess.add_argument("input", type=Path)
    preprocess.add_argument(
        "--output", type=Path, default=Path("data/processed/campaigns.json")
    )
    preprocess.set_defaults(handler=run_preprocess)

    database = subparsers.add_parser("db", help="SQLite kalıcılık işlemleri")
    database_subparsers = database.add_subparsers(dest="db_command", required=True)
    db_init = database_subparsers.add_parser("init", help="SQLite şemasını oluştur")
    db_init.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    db_init.set_defaults(handler=run_db_init)
    db_import = database_subparsers.add_parser(
        "import-json", help="JSON veri setini SQLite'a aktar"
    )
    db_import.add_argument("input", type=Path)
    db_import.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    db_import.set_defaults(handler=run_db_import)
    db_export = database_subparsers.add_parser(
        "export-json", help="SQLite verisini JSON'a aktar"
    )
    db_export.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    db_export.add_argument(
        "--raw-output", type=Path, default=Path("data/raw/campaigns.json")
    )
    db_export.add_argument(
        "--processed-output", type=Path, default=Path("data/processed/campaigns.json")
    )
    db_export.set_defaults(handler=run_db_export)

    compare = subparsers.add_parser("compare", help="SQLite kampanyalarını karşılaştır")
    compare.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    compare.add_argument("--product-type", required=True)
    compare.add_argument("--currency", required=True)
    compare.add_argument("--duration-days", type=int)
    compare.add_argument("--eligibility")
    compare.add_argument("--financing-type")
    compare.add_argument("--amount", type=float)
    compare.add_argument("--title")
    compare.add_argument("--output", type=Path, default=Path("outputs/comparison.json"))
    compare.set_defaults(handler=run_compare)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return args.handler(args)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
