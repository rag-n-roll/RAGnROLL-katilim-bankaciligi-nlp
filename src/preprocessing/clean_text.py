"""Turkce kampanya metinleri icin kayipsiz on isleme hatti."""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from src.data_quality import cluster_near_duplicates, content_hash, simhash
from src.extraction.campaign_fields import extract_prd_fields

TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+(?:['’][^\W\d_]+)?", re.UNICODE)
TURKISH_LOWER_TRANSLATION = str.maketrans({"I": "ı", "İ": "i"})
INVISIBLE_TEXT_RE = re.compile(r"[\u00ad\u200b-\u200f\u202a-\u202e\u2060\ufeff]")


def turkish_lower(value: str) -> str:
    """Python'un dil bagimsiz lower davranisini Turkce icin duzeltir."""
    return value.translate(TURKISH_LOWER_TRANSLATION).lower()


def clean_text(value: str, *, lowercase: bool = False) -> str:
    """HTML, gorunmez karakter ve gereksiz bosluklari temizler.

    Turkce harfleri, para yuzdelerini ve paragraf sinirlarini korur. RAG ve NER
    icin anlam tasiyan noktalama isaretlerini toptan silmez.
    """
    value = unicodedata.normalize("NFC", html.unescape(value or ""))
    if re.search(r"<[^>]+>", value):
        value = BeautifulSoup(value, "html.parser").get_text("\n", strip=True)
    value = value.replace("\u00a0", " ")
    value = INVISIBLE_TEXT_RE.sub("", value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    return turkish_lower(value) if lowercase else value


def normalize_link_text(value: str) -> str:
    """CTA ve navigasyon metnini Turkce karakterleri koruyarak eslestirilebilir yapar."""
    normalized = clean_text(value, lowercase=True)
    return re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()


def tokenize_turkish(value: str, *, lowercase: bool = True) -> list[str]:
    """Unicode uyumlu, Turkce kesme isaretlerini koruyan hafif tokenizer."""
    normalized = clean_text(value, lowercase=lowercase)
    return TOKEN_RE.findall(normalized)


def preprocess_record(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    cleaned = clean_text(str(record.get("content") or ""))
    tokens = tokenize_turkish(cleaned)
    result["clean_text"] = cleaned
    result["tokens"] = tokens
    result["token_count"] = len(tokens)
    result["canonical_url"] = record.get("canonical_url") or record.get("source_url")
    result["content_hash"] = content_hash(
        str(record.get("title") or ""), str(record.get("content") or "")
    )
    result["duplicate_fingerprint"] = simhash(cleaned)
    source_text = "\n".join(
        filter(None, [str(record.get("title") or ""), str(record.get("content") or cleaned)])
    )
    result["structured"] = extract_prd_fields(
        source_text,
        start_date=record.get("start_date"),
        end_date=record.get("end_date"),
    )
    return result


def preprocess_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("Veri setinde 'records' listesi bulunmuyor")
    result = dict(payload)
    result["preprocessed_at"] = datetime.now(timezone.utc).isoformat()
    result["records"] = cluster_near_duplicates(
        preprocess_record(record) for record in records if isinstance(record, dict)
    )
    result["record_count"] = len(result["records"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Kampanya JSON veri setini on isle")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.input.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    processed = preprocess_dataset(payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(processed, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    temporary.replace(args.output)
    print(f"{processed['record_count']} kayit yazildi: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
