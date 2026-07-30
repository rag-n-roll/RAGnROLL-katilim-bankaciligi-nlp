"""Scraper veri modelleri."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from typing import Any


SCHEMA_VERSION = "1.0.0"


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
        self.title = self.title.strip()
        self.content = self.content.strip()
        self.source_url = self.source_url.strip()
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
