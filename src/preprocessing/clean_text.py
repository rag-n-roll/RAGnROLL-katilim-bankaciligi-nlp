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

TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+(?:['’][^\W\d_]+)?", re.UNICODE)


def clean_text(value: str, *, lowercase: bool = False) -> str:
    """HTML, gorunmez karakter ve gereksiz bosluklari temizler.

    Turkce harfleri, para yuzdelerini ve paragraf sinirlarini korur. RAG ve NER
    icin anlam tasiyan noktalama isaretlerini toptan silmez.
    """
    value = unicodedata.normalize("NFC", html.unescape(value or ""))
    if re.search(r"<[^>]+>", value):
        value = BeautifulSoup(value, "html.parser").get_text("\n", strip=True)
    value = value.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    value = re.sub(r" *\n *", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    return value.lower() if lowercase else value


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
    return result


def preprocess_dataset(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("Veri setinde 'records' listesi bulunmuyor")
    result = dict(payload)
    result["preprocessed_at"] = datetime.now(timezone.utc).isoformat()
    result["records"] = [preprocess_record(record) for record in records]
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
