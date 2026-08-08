"""Banka scraper'lari icin ortak HTML ayiklama altyapisi."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
import logging
from typing import Any
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .http import HttpClient
from .models import Campaign


LOGGER = logging.getLogger(__name__)

MONTHS = {
    "ocak": 1,
    "şubat": 2,
    "subat": 2,
    "mart": 3,
    "nisan": 4,
    "mayıs": 5,
    "mayis": 5,
    "haziran": 6,
    "temmuz": 7,
    "ağustos": 8,
    "agustos": 8,
    "eylül": 9,
    "eylul": 9,
    "ekim": 10,
    "kasım": 11,
    "kasim": 11,
    "aralık": 12,
    "aralik": 12,
}
MONTH_PATTERN = "|".join(MONTHS)


def build_failure(bank_slug: str, stage: str, url: str, exc: Exception) -> dict[str, Any]:
    """Scrape sirasinda olusan hatayi standartlastirilmis kayda donusturur."""
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return {
        "bank_slug": bank_slug,
        "stage": stage,
        "url": url,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "http_status": int(status_code) if isinstance(status_code, int) else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def clean_lines(text: str) -> str:
    """Gorunur metni satir yapisini koruyarak normalize eder."""
    text = text.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t\r\f\v]+", " ", raw_line).strip()
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    return "\n".join(lines)


def _parse_date(value: str, default_year: int | None = None) -> date | None:
    normalized = clean_lines(value).lower().replace("i̇", "i")
    numeric = re.fullmatch(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", normalized)
    if numeric:
        day, month, year = map(int, numeric.groups())
    else:
        textual = re.fullmatch(
            rf"(\d{{1,2}})\s+({MONTH_PATTERN})(?:\s+(\d{{4}}))?", normalized
        )
        if not textual:
            return None
        day = int(textual.group(1))
        month = MONTHS[textual.group(2)]
        year = int(textual.group(3)) if textual.group(3) else default_year
        if year is None:
            return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def extract_date_range(text: str) -> tuple[date | None, date | None]:
    """Turkce ay adli veya sayisal ilk tarih araligini dondurur."""
    compact = clean_lines(text).replace("\n", " ")
    numeric = re.search(
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{4})\s+(?:-|–|—)\s+"
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
        compact,
        re.IGNORECASE,
    )
    if numeric:
        return _parse_date(numeric.group(1)), _parse_date(numeric.group(2))

    textual = re.search(
        rf"(\d{{1,2}}\s+(?:{MONTH_PATTERN})(?:\s+\d{{4}})?)\s*"
        rf"(?:-|–|—)\s*(\d{{1,2}}\s+(?:{MONTH_PATTERN})\s+\d{{4}})",
        compact,
        re.IGNORECASE,
    )
    if textual:
        end = _parse_date(textual.group(2))
        start = _parse_date(textual.group(1), default_year=end.year if end else None)
        return start, end
    return None, None


@dataclass(frozen=True, slots=True)
class ScraperConfig:
    slug: str
    bank_name: str
    base_url: str
    listing_urls: tuple[str, ...]
    detail_pattern: str
    content_selectors: tuple[str, ...]
    title_selectors: tuple[str, ...] = ("h1", "article h2")
    listing_link_selectors: tuple[str, ...] = ("a[href]",)
    remove_selectors: tuple[str, ...] = (
        "script",
        "style",
        "noscript",
        "nav",
        ".breadcrumbs",
        ".breadcrumb",
        ".share-buttons",
        ".tool",
        "form",
    )


class BaseBankScraper:
    config: ScraperConfig

    def __init__(self, client: HttpClient | None = None) -> None:
        self.client = client or HttpClient()
        self._detail_regex = re.compile(self.config.detail_pattern, re.IGNORECASE)

    def _discover_listing_urls(self, listing_url: str, seen: set[str]) -> list[str]:
        urls: list[str] = []
        allowed_host = urlparse(self.config.base_url).hostname
        soup = BeautifulSoup(self.client.get_text(listing_url), "html.parser")
        for selector in self.config.listing_link_selectors:
            for anchor in soup.select(selector):
                href = str(anchor.get("href") or "").strip()
                if not href:
                    continue
                absolute = urldefrag(urljoin(self.config.base_url, href))[0]
                parsed = urlparse(absolute)
                if (
                    parsed.hostname == allowed_host
                    and self._detail_regex.search(parsed.path)
                    and absolute not in seen
                ):
                    seen.add(absolute)
                    urls.append(absolute)
        return urls

    def discover_urls(self) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for listing_url in self.config.listing_urls:
            urls.extend(self._discover_listing_urls(listing_url, seen))
        return urls

    def _content_nodes(self, soup: BeautifulSoup) -> list[Tag]:
        nodes: list[Tag] = []
        for selector in self.config.content_selectors:
            for candidate in soup.select(selector):
                if not any(candidate is old or candidate in old.descendants for old in nodes):
                    nodes.append(candidate)
        if not nodes:
            fallback = soup.select_one("main, article, [role='main']")
            if fallback:
                nodes.append(fallback)
        return nodes

    def _extract_content(self, soup: BeautifulSoup) -> tuple[str, list[Tag]]:
        nodes = self._content_nodes(soup)
        chunks: list[str] = []
        for original in nodes:
            node = BeautifulSoup(str(original), "html.parser")
            for selector in self.config.remove_selectors:
                for unwanted in node.select(selector):
                    unwanted.decompose()
            value = clean_lines(node.get_text("\n", strip=True))
            if value and value not in chunks:
                chunks.append(value)
        return clean_lines("\n".join(chunks)), nodes

    def _first_text(self, soup: BeautifulSoup, selectors: tuple[str, ...]) -> str:
        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                value = clean_lines(element.get_text(" ", strip=True))
                if value:
                    return value
        return ""

    def parse_detail(self, url: str, html: str) -> Campaign:
        soup = BeautifulSoup(html, "html.parser")
        title = self._first_text(soup, self.config.title_selectors)
        content, nodes = self._extract_content(soup)

        description = ""
        for node in nodes:
            paragraph = node.select_one("p, li")
            if paragraph:
                description = clean_lines(paragraph.get_text(" ", strip=True))
                if description:
                    break
        if not description:
            meta = soup.select_one("meta[name='description'], meta[property='og:description']")
            description = clean_lines(str(meta.get("content", ""))) if meta else ""

        image_url = None
        image = soup.select_one("meta[property='og:image']")
        if image and image.get("content"):
            image_url = urljoin(url, str(image["content"]))
        elif nodes:
            image = nodes[0].select_one("img[src], img[data-src]")
            if image:
                image_url = urljoin(url, str(image.get("src") or image.get("data-src")))

        full_text = clean_lines(soup.get_text("\n", strip=True))
        start_date, end_date = extract_date_range(full_text)
        return Campaign(
            bank_slug=self.config.slug,
            bank_name=self.config.bank_name,
            title=title,
            summary=description[:500] or None,
            content=content,
            start_date=start_date,
            end_date=end_date,
            source_url=url,
            image_url=image_url,
        )

    def scrape(self, *, limit: int | None = None) -> tuple[list[Campaign], list[dict[str, Any]]]:
        urls: list[str] = []
        seen: set[str] = set()
        failures: list[dict[str, Any]] = []
        for listing_url in self.config.listing_urls:
            try:
                urls.extend(self._discover_listing_urls(listing_url, seen))
            except Exception as exc:
                LOGGER.exception(
                    "Campaign URL discovery failed for %s: %s", self.config.slug, listing_url
                )
                failures.append(build_failure(self.config.slug, "discovery", listing_url, exc))

        LOGGER.info("Discovered %d campaign URLs for %s", len(urls), self.config.slug)
        if limit is not None:
            urls = urls[: max(0, limit)]
        records: list[Campaign] = []
        for url in urls:
            try:
                html = self.client.get_text(url)
            except Exception as exc:
                LOGGER.exception("Campaign detail fetch failed for %s: %s", self.config.slug, url)
                failures.append(build_failure(self.config.slug, "fetch", url, exc))
                continue
            try:
                record = self.parse_detail(url, html)
                records.append(record)
                LOGGER.info("Campaign detail parsed for %s: %s", self.config.slug, url)
            except Exception as exc:  # Bir bozuk sayfa tum toplama isini durdurmamali.
                LOGGER.exception("Campaign detail parse failed for %s: %s", self.config.slug, url)
                failures.append(build_failure(self.config.slug, "parse", url, exc))
        return records, failures
