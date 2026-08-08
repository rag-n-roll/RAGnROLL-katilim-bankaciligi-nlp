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
NUMERIC_DATE_PATTERN = r"(?<!\d)\d{1,2}[./-]\d{1,2}[./-]\d{4}"
TEXTUAL_DATE_PATTERN = rf"(?<!\d)\d{{1,2}}\s+(?:{MONTH_PATTERN})(?:\s+\d{{4}})?"
FULL_TEXTUAL_DATE_PATTERN = rf"(?<!\d)\d{{1,2}}\s+(?:{MONTH_PATTERN})\s+\d{{4}}"


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
    """Acik kampanya donemlerini kapsayan tarih araligini dondurur."""
    compact = clean_lines(text).replace("\n", " ")
    ranges: list[tuple[date, date]] = []

    numeric_ranges = re.finditer(
        rf"({NUMERIC_DATE_PATTERN})\s+(?:-|–|—)\s+({NUMERIC_DATE_PATTERN})",
        compact,
        re.IGNORECASE,
    )
    for match in numeric_ranges:
        start = _parse_date(match.group(1))
        end = _parse_date(match.group(2))
        if start and end and start <= end:
            ranges.append((start, end))

    textual_ranges = re.finditer(
        rf"({TEXTUAL_DATE_PATTERN})\s*"
        rf"(?:saat\s+\d{{1,2}}[.:]\d{{2}}\s*)?"
        rf"(?:-|–|—)\s*({FULL_TEXTUAL_DATE_PATTERN})",
        compact,
        re.IGNORECASE,
    )
    for match in textual_ranges:
        end = _parse_date(match.group(2))
        start = _parse_date(match.group(1), default_year=end.year if end else None)
        if start and end and start <= end:
            ranges.append((start, end))

    shared_month_ranges = re.finditer(
        rf"(?<!\d)(\d{{1,2}})\s*(?:-|–|—)\s*(?<!\d)(\d{{1,2}})\s+"
        rf"({MONTH_PATTERN})\s+(\d{{4}})(?=\s+tarih(?:leri|lerinde)\b)",
        compact,
        re.IGNORECASE,
    )
    for match in shared_month_ranges:
        start = _parse_date(
            f"{match.group(1)} {match.group(3)} {match.group(4)}"
        )
        end = _parse_date(
            f"{match.group(2)} {match.group(3)} {match.group(4)}"
        )
        if start and end and start <= end:
            ranges.append((start, end))

    if ranges:
        return min(start for start, _ in ranges), max(end for _, end in ranges)

    end_only_matches = re.finditer(
        rf"({NUMERIC_DATE_PATTERN}|{FULL_TEXTUAL_DATE_PATTERN})"
        rf"(?:\s+tarihine|\s+saat\s+\d{{1,2}}[.:]\d{{2}}(?:['’]?[a-zçğıöşü]+)?)?"
        rf"\s+kadar\b",
        compact,
        re.IGNORECASE,
    )
    for match in end_only_matches:
        left = max(compact.rfind(mark, 0, match.start()) for mark in ".!?;") + 1
        right_candidates = [compact.find(mark, match.end()) for mark in ".!?;"]
        right = min(
            (position for position in right_candidates if position >= 0),
            default=len(compact),
        )
        context = compact[left:right].casefold().replace("i̇", "i")
        reward_expiry = any(word in context for word in ("kazanılan", "kullanılmayan")) and any(
            word in context for word in ("parafpara", "puan", "bonus", "ödül", "hediye")
        )
        campaign_context = any(
            word in context
            for word in (
                "kampanya",
                "fırsat",
                "firsat",
                "indirim kod",
                "geçerli",
                "gecerli",
                "alışveriş",
                "alisveris",
                "harcama",
                "mağaza",
                "magaza",
                "kiralama",
                "bilet",
            )
        )
        if campaign_context and not reward_expiry:
            return None, _parse_date(match.group(1))
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

    def _discover_urls_for_scrape(self) -> tuple[list[str], list[dict[str, Any]]]:
        if type(self).discover_urls is not BaseBankScraper.discover_urls:
            try:
                return self.discover_urls(), []
            except Exception as exc:
                discovery_url = self.config.listing_urls[0] if self.config.listing_urls else ""
                if not discovery_url:
                    discovery_url = self.config.base_url
                LOGGER.exception("Campaign URL discovery failed for %s", self.config.slug)
                failure = build_failure(self.config.slug, "discovery", discovery_url, exc)
                return [], [failure]

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
        return urls, failures

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

        campaign_text = clean_lines("\n".join((title, description, content)))
        start_date, end_date = extract_date_range(campaign_text)
        if start_date is None and end_date is None:
            # Bazi eski sayfalarda tarih yalnizca icerik kapsami disindaki ust bilgide bulunur.
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
        urls, failures = self._discover_urls_for_scrape()

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
