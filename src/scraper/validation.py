"""Kampanya veri seti kalite ve butunluk kontrolleri."""

from __future__ import annotations

from collections import Counter
import re
from typing import Any, Iterable
from urllib.parse import urlparse

from .models import Campaign, normalize_source_url


HTML_TAG_PATTERN = re.compile(r"</?[A-Za-z][^>]*>")


def validate_campaign(record: Campaign) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    def add(severity: str, field: str, message: str) -> None:
        issues.append({"severity": severity, "field": field, "message": message})

    if not record.bank_slug:
        add("error", "bank_slug", "Banka kodu bos olamaz")
    if not record.bank_name:
        add("error", "bank_name", "Banka adi bos olamaz")
    if len(record.title) < 5:
        add("error", "title", "Baslik en az 5 karakter olmali")
    if len(record.content) < 80:
        add("error", "content", "Kampanya metni en az 80 karakter olmali")
    if HTML_TAG_PATTERN.search(record.content):
        add("error", "content", "Kampanya metninde HTML etiketi kalmis")
    parsed = urlparse(record.source_url)
    if parsed.scheme != "https" or not parsed.netloc:
        add("error", "source_url", "Kaynak URL gecerli bir HTTPS adresi olmali")
    if record.start_date and record.end_date and record.start_date > record.end_date:
        add("error", "date_range", "Baslangic tarihi bitis tarihinden sonra olamaz")
    if not record.start_date or not record.end_date:
        add("warning", "date_range", "Tarih araligi eksik veya ayiklanamadi")
    if not record.summary:
        add("warning", "summary", "Ozet bulunamadi")
    if record.summary and len(record.summary) > 500:
        add("warning", "summary", "Ozet 500 karakteri geciyor")
    return issues


def deduplicate_campaigns(
    records: Iterable[Campaign],
) -> tuple[list[Campaign], list[dict[str, str]]]:
    """Ayni banka ve normalize edilmis kaynak URL kayitlarini ayikla."""
    unique_records: list[Campaign] = []
    duplicate_rows: list[dict[str, str]] = []
    first_record_ids: dict[tuple[str, str], str] = {}
    for record in records:
        key = (record.bank_slug.casefold(), normalize_source_url(record.source_url))
        if key not in first_record_ids:
            first_record_ids[key] = str(record.id)
            unique_records.append(record)
            continue
        duplicate_rows.append(
            {
                "record_id": str(record.id),
                "duplicate_of": first_record_ids[key],
                "bank_slug": str(record.bank_slug),
                "source_url": str(record.source_url),
            }
        )
    return unique_records, duplicate_rows


def build_quality_report(
    records: Iterable[Campaign],
    failures: list[dict[str, Any]] | None = None,
    duplicates: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    records = list(records)
    failures = failures or []
    duplicates = duplicates or []
    issue_rows: list[dict[str, str]] = []
    id_counts = Counter(record.id for record in records)
    url_counts = Counter(record.source_url for record in records)
    valid_records = 0
    for record in records:
        record_issues = validate_campaign(record)
        if id_counts[record.id] > 1:
            record_issues.append(
                {"severity": "error", "field": "id", "message": "Tekrarlanan kayit kimligi"}
            )
        if url_counts[record.source_url] > 1:
            record_issues.append(
                {"severity": "error", "field": "source_url", "message": "Tekrarlanan kaynak URL"}
            )
        issue_rows.extend(
            {"record_id": str(record.id), "bank_slug": record.bank_slug, **issue}
            for issue in record_issues
        )
        if not any(issue["severity"] == "error" for issue in record_issues):
            valid_records += 1

    errors = sum(issue["severity"] == "error" for issue in issue_rows)
    warnings = sum(issue["severity"] == "warning" for issue in issue_rows)
    return {
        "record_count": len(records),
        "valid_record_count": valid_records,
        "error_count": errors,
        "warning_count": warnings,
        "fetch_failure_count": len(failures),
        "duplicate_count": len(duplicates),
        "quality_score": round(valid_records / len(records), 4) if records else 0.0,
        "issues": issue_rows,
        "fetch_failures": failures,
        "duplicates": duplicates,
    }
