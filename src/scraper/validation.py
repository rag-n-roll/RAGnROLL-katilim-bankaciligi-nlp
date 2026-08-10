"""Kampanya veri seti kalite ve butunluk kontrolleri."""

from __future__ import annotations

from collections import Counter
import re
from typing import Any, Iterable, Sequence
from urllib.parse import urlparse

from .models import Campaign, normalize_source_url


HTML_ELEMENT_NAMES = (
    "a|abbr|address|area|article|aside|audio|b|base|bdi|bdo|blockquote|body|br|button|"
    "canvas|caption|cite|code|col|colgroup|data|datalist|dd|del|details|dfn|dialog|div|dl|"
    "dt|em|embed|fieldset|figcaption|figure|footer|form|h1|h2|h3|h4|h5|h6|head|header|hgroup|"
    "hr|html|i|iframe|img|input|ins|kbd|label|legend|li|link|main|map|mark|menu|meta|meter|nav|"
    "noscript|object|ol|optgroup|option|output|p|picture|pre|progress|q|rp|rt|ruby|s|samp|script|"
    "search|section|select|slot|small|source|span|strong|style|sub|summary|sup|table|tbody|td|"
    "template|textarea|tfoot|th|thead|time|title|tr|track|u|ul|var|video|wbr"
)
HTML_TAG_PATTERN = re.compile(
    rf"<!--[\s\S]*?-->|</?\s*(?:{HTML_ELEMENT_NAMES})(?=[\s/>])[^>]*>",
    re.IGNORECASE,
)

PRD_FIELDS = (
    "product_type",
    "financing_type",
    "profit_share_rate",
    "term_months",
    "installment_count",
    "campaign_benefit",
    "reward_amount",
    "discount_rate",
    "target_audience",
    "campaign_start_date",
    "campaign_end_date",
    "fee_information",
)


def build_processed_coverage(
    records: Sequence[dict[str, Any]],
    *,
    expected_banks: Sequence[str],
) -> dict[str, Any]:
    """İşlenmiş veri setinin banka ve PRD alan doluluk oranlarını üretir."""
    expected = set(expected_banks)
    represented = {str(record.get("bank_slug") or "") for record in records}
    represented.discard("")
    by_bank = {
        slug: {"record_count": 0, "campaign_count": 0, "product_count": 0}
        for slug in sorted(expected | represented)
    }
    for record in records:
        slug = str(record.get("bank_slug") or "")
        if not slug:
            continue
        row = by_bank[slug]
        row["record_count"] += 1
        kind = str(record.get("record_kind") or "campaign")
        if kind == "product":
            row["product_count"] += 1
        else:
            row["campaign_count"] += 1

    total = len(records)
    field_fill_rates = {}
    for field in PRD_FIELDS:
        filled = sum(
            1
            for record in records
            if isinstance(record.get("structured"), dict)
            and record["structured"].get(field) not in (None, "", [])
        )
        field_fill_rates[field] = round(filled / total, 4) if total else 0.0

    represented_expected = represented & expected
    return {
        "bank_coverage": {
            "expected": len(expected),
            "represented": len(represented_expected),
            "missing": sorted(expected - represented),
            "ratio": round(len(represented_expected) / len(expected), 4) if expected else 1.0,
        },
        "field_fill_rates": field_fill_rates,
        "by_bank": by_bank,
    }


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
    records = list(records)
    record_issues: list[list[dict[str, str]]] = [[] for _ in records]
    unique_records, duplicate_rows, _ = _select_url_representatives(
        records, record_issues
    )
    return unique_records, duplicate_rows


def _has_error(issues: Sequence[dict[str, str]]) -> bool:
    return any(issue["severity"] == "error" for issue in issues)


def _select_url_representatives(
    records: Sequence[Campaign],
    record_issues: Sequence[Sequence[dict[str, str]]],
) -> tuple[list[Campaign], list[dict[str, str]], list[int]]:
    grouped_indexes, record_keys = _group_record_indexes(records)

    selected_indexes_by_key: dict[tuple[str, str], int] = {}
    for key, indexes in grouped_indexes.items():
        selected_indexes_by_key[key] = next(
            (index for index in indexes if not _has_error(record_issues[index])),
            indexes[0],
        )

    selected_indexes = list(selected_indexes_by_key.values())
    unique_records = [records[index] for index in selected_indexes]
    duplicate_rows: list[dict[str, str]] = []
    for index, record in enumerate(records):
        selected_index = selected_indexes_by_key[record_keys[index]]
        if index == selected_index:
            continue
        duplicate_rows.append(
            _duplicate_row(record, records[selected_index])
        )
    return unique_records, duplicate_rows, selected_indexes


def _group_record_indexes(
    records: Sequence[Campaign],
) -> tuple[
    dict[tuple[str, str, str, str], list[int]],
    list[tuple[str, str, str, str]],
]:
    grouped_indexes: dict[tuple[str, str, str, str], list[int]] = {}
    record_keys: list[tuple[str, str, str, str]] = []
    for index, record in enumerate(records):
        key = (
            record.bank_slug.casefold(),
            normalize_source_url(record.source_url),
            record.source_item_key or "",
            record.record_kind,
        )
        record_keys.append(key)
        grouped_indexes.setdefault(key, []).append(index)
    return grouped_indexes, record_keys


def _duplicate_row(record: Campaign, representative: Campaign) -> dict[str, str]:
    return {
        "record_id": str(record.id),
        "duplicate_of": str(representative.id),
        "bank_slug": str(record.bank_slug),
        "source_url": str(record.source_url),
    }


def select_valid_campaigns(
    records: Iterable[Campaign],
) -> tuple[
    list[Campaign],
    list[dict[str, str]],
    list[list[dict[str, str]]],
]:
    """Dogrula, URL gruplarindan gecerli temsilci sec ve ID tekilligini uygula."""
    records = list(records)
    record_issues = [validate_campaign(record) for record in records]
    grouped_indexes, _ = _group_record_indexes(records)
    valid_records: list[Campaign] = []
    duplicate_rows: list[dict[str, str]] = []
    used_ids: set[tuple[type, object]] = set()
    for indexes in grouped_indexes.values():
        selected_index: int | None = None
        for index in indexes:
            if _has_error(record_issues[index]):
                continue
            record = records[index]
            exact_id = (type(record.id), record.id)
            if exact_id in used_ids:
                record_issues[index].append(
                    {
                        "severity": "error",
                        "field": "id",
                        "message": "Tekrarlanan kayit kimligi",
                    }
                )
                continue
            selected_index = index
            used_ids.add(exact_id)
            valid_records.append(record)
            break
        if selected_index is None:
            continue
        duplicate_rows.extend(
            _duplicate_row(records[index], records[selected_index])
            for index in indexes
            if index != selected_index
        )
    return valid_records, duplicate_rows, record_issues


def build_quality_report(
    records: Iterable[Campaign],
    failures: list[dict[str, Any]] | None = None,
    duplicates: list[dict[str, str]] | None = None,
    *,
    record_issues: Sequence[Sequence[dict[str, str]]] | None = None,
    persisted_records: Iterable[Campaign] | None = None,
) -> dict[str, Any]:
    records = list(records)
    failures = failures or []
    duplicates = duplicates or []
    input_record_count = len(records)
    if record_issues is None:
        id_counts = Counter((type(record.id), record.id) for record in records)
        url_counts = Counter(record.source_url for record in records)
        computed_issues: list[list[dict[str, str]]] = []
        for record in records:
            issues = validate_campaign(record)
            if id_counts[(type(record.id), record.id)] > 1:
                issues.append(
                    {
                        "severity": "error",
                        "field": "id",
                        "message": "Tekrarlanan kayit kimligi",
                    }
                )
            if url_counts[record.source_url] > 1:
                issues.append(
                    {
                        "severity": "error",
                        "field": "source_url",
                        "message": "Tekrarlanan kaynak URL",
                    }
                )
            computed_issues.append(issues)
        record_issues = computed_issues
    elif len(record_issues) != input_record_count:
        raise ValueError("record_issues kayit sayisiyla ayni uzunlukta olmali")

    issue_rows: list[dict[str, str]] = []
    rejected_record_count = 0
    for record, issues in zip(records, record_issues):
        issue_rows.extend(
            {"record_id": str(record.id), "bank_slug": record.bank_slug, **issue}
            for issue in issues
        )
        if _has_error(issues):
            rejected_record_count += 1

    if persisted_records is None:
        record_count = input_record_count
        valid_record_count = input_record_count - rejected_record_count
    else:
        record_count = len(list(persisted_records))
        valid_record_count = record_count

    errors = sum(issue["severity"] == "error" for issue in issue_rows)
    warnings = sum(issue["severity"] == "warning" for issue in issue_rows)
    return {
        "record_count": record_count,
        "valid_record_count": valid_record_count,
        "input_record_count": input_record_count,
        "rejected_record_count": rejected_record_count,
        "error_count": errors,
        "warning_count": warnings,
        "fetch_failure_count": len(failures),
        "duplicate_count": len(duplicates),
        "quality_score": (
            round((input_record_count - rejected_record_count) / input_record_count, 4)
            if input_record_count
            else 0.0
        ),
        "issues": issue_rows,
        "fetch_failures": failures,
        "duplicates": duplicates,
    }
