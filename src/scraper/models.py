"""Scraper veri modelleri."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SCHEMA_VERSION = "1.0.0"
TRACKING_QUERY_KEYS = {
    "dclid",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "msclkid",
    "yclid",
}


def normalize_source_url(value: str) -> str:
    """Kaynak URL'lerden izleme parametrelerini ve fragment'leri kaldir."""
    if not isinstance(value, str):
        raise TypeError("source_url string olmali")

    parsed = urlsplit(value.strip())
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS
    ]
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            urlencode(query),
            "",
        )
    )


@dataclass(slots=True)
class Campaign:
    """Bankalar arasinda ortak, surumlenmis kampanya kaydi."""

    bank_slug: str
    bank_name: str
    title: str
    content: str
    source_url: str
    summary: str | None = None
    category: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    image_url: str | None = None
    scraped_at: datetime | None = None
    id: str | None = None
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in ("bank_slug", "bank_name", "title", "content", "source_url"):
            value = getattr(self, field)
            if not isinstance(value, str):
                raise TypeError(f"{field} string olmali")
            setattr(self, field, value.strip())
        for field in ("summary", "category", "image_url"):
            value = getattr(self, field)
            if value is not None and not isinstance(value, str):
                raise TypeError(f"{field} string veya None olmali")
            if isinstance(value, str):
                setattr(self, field, value.strip() or None)

        self.source_url = normalize_source_url(self.source_url)
        if self.scraped_at is None:
            self.scraped_at = datetime.now(timezone.utc)
        if self.id is None:
            key = f"{self.bank_slug}\0{self.source_url}".encode("utf-8")
            self.id = sha256(key).hexdigest()[:20]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for field in ("start_date", "end_date", "scraped_at"):
            value = result[field]
            result[field] = value.isoformat() if value else None
        return result
