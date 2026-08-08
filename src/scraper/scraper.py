"""BDDK ve banka kampanya scraper'lari icin komut satiri arayuzu."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from src.preprocessing.clean_text import preprocess_dataset

from .bddk import fetch_participation_banks
from .base import build_failure
from .http import HttpClient
from .registry import SCRAPERS, resolve_banks
from .storage import campaign_dataset, write_json
from .validation import build_quality_report, deduplicate_campaigns

LOGGER = logging.getLogger(__name__)


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

    records, duplicates = deduplicate_campaigns(records)
    LOGGER.info("Duplicates removed: %d", len(duplicates))
    report = build_quality_report(records, failures, duplicates)
    LOGGER.info("Validation completed: %d errors", report["error_count"])
    invalid_record_ids = {
        issue["record_id"]
        for issue in report["issues"]
        if issue["severity"] == "error"
    }
    valid_records = [record for record in records if str(record.id) not in invalid_record_ids]
    LOGGER.info("Discarded invalid campaign records: %d", len(records) - len(valid_records))
    dataset = campaign_dataset(valid_records)
    if valid_records:
        write_json(args.output, dataset)
        LOGGER.info("Data persisted: campaign dataset %s", args.output)
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
                converted["scraped_at"] = datetime.fromisoformat(converted["scraped_at"])
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
    banks.add_argument("--output", type=Path, default=Path("data/raw/participation_banks.json"))
    add_http_options(banks)
    banks.set_defaults(handler=run_banks)

    campaigns = subparsers.add_parser("campaigns", help="Banka kampanyalarını çek")
    campaigns.add_argument(
        "--banks",
        default="priority",
        help="priority, all veya virgülle ayrılmış banka slug'ları",
    )
    campaigns.add_argument("--max-per-bank", type=int, default=20)
    campaigns.add_argument("--output", type=Path, default=Path("data/raw/campaigns.json"))
    campaigns.add_argument(
        "--quality-report", type=Path, default=Path("outputs/quality_report.json")
    )
    add_http_options(campaigns)
    campaigns.set_defaults(handler=run_campaigns)

    validate = subparsers.add_parser("validate", help="Mevcut kampanya JSON'unu doğrula")
    validate.add_argument("input", type=Path)
    validate.add_argument("--output", type=Path, default=Path("outputs/quality_report.json"))
    validate.set_defaults(handler=run_validate)

    preprocess = subparsers.add_parser(
        "preprocess",
        help="Kampanya metinlerini temizle ve tokenize et",
    )
    preprocess.add_argument("input", type=Path)
    preprocess.add_argument("--output", type=Path, default=Path("data/processed/campaigns.json"))
    preprocess.set_defaults(handler=run_preprocess)
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
