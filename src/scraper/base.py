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
PRIMARY_DATE_LABEL_RE = re.compile(
    r"\bkampanya\s+(?:tarihleri|başlangıç\s+ve\s+bitiş|dönemi)\b",
    re.IGNORECASE,
)
INLINE_REWARD_CLAUSE_RE = re.compile(
    r",\s+(?=(?:(?:kampanya\s+kapsam(?:ında|inda)|bu\s+kapsamda)\s+)?"
    r"(?:kazan\w*|kullanılmayan|kullanilmayan|"
    r"parafpara|puan\w*|bonus\w*|ödül\w*|hediye\w*)\b)",
    re.IGNORECASE,
)
MAX_CAMPAIGN_DURATION_DAYS = 5 * 366
MAX_CAMPAIGN_FUTURE_YEARS = 10


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


def _find_explicit_ranges(segment: str) -> list[tuple[int, date, date]]:
    ranges: list[tuple[int, date, date]] = []

    numeric_ranges = re.finditer(
        rf"({NUMERIC_DATE_PATTERN})\s+(?:-|–|—)\s+({NUMERIC_DATE_PATTERN})",
        segment,
        re.IGNORECASE,
    )
    for match in numeric_ranges:
        start = _parse_date(match.group(1))
        end = _parse_date(match.group(2))
        if start and end and start <= end:
            ranges.append((match.start(), start, end))

    textual_ranges = re.finditer(
        rf"({TEXTUAL_DATE_PATTERN})\s*"
        rf"(?:saat\s+\d{{1,2}}[.:]\d{{2}}\s*)?"
        rf"(?:-|–|—)\s*({FULL_TEXTUAL_DATE_PATTERN})",
        segment,
        re.IGNORECASE,
    )
    for match in textual_ranges:
        end = _parse_date(match.group(2))
        start = _parse_date(match.group(1), default_year=end.year if end else None)
        if start and end and start <= end:
            ranges.append((match.start(), start, end))

    shared_month_ranges = re.finditer(
        rf"(?<!\d)(\d{{1,2}})\s*(?:-|–|—)\s*(?<!\d)(\d{{1,2}})\s+"
        rf"({MONTH_PATTERN})\s+(\d{{4}})(?=\s+tarih(?:leri|lerinde)\b)",
        segment,
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
            ranges.append((match.start(), start, end))

    return sorted(ranges, key=lambda item: item[0])


def _extract_explicit_ranges(segment: str) -> tuple[date | None, date | None]:
    ranges = _find_explicit_ranges(segment)
    if ranges:
        return min(start for _, start, _ in ranges), max(end for _, _, end in ranges)
    return None, None


def _extract_first_explicit_range(segment: str) -> tuple[date | None, date | None]:
    ranges = _find_explicit_ranges(segment)
    if ranges:
        _, start, end = ranges[0]
        return start, end
    return None, None


def _normalized_context(value: str) -> str:
    return value.casefold().replace("i̇", "i")


def _is_reward_expiry(context: str) -> bool:
    date_match = re.search(
        rf"{NUMERIC_DATE_PATTERN}|{FULL_TEXTUAL_DATE_PATTERN}",
        context,
        re.IGNORECASE,
    )
    if not date_match:
        return False

    reward_positions = [
        context.find(word)
        for word in ("parafpara", "puan", "bonus", "ödül", "hediye")
        if word in context
    ]
    lifecycle_positions = [
        context.find(word, date_match.end())
        for word in (
            "kullanılabilir",
            "kullanilabilir",
            "kullanılacaktır",
            "kullanilacaktir",
            "silinecek",
            "silinir",
        )
        if context.find(word, date_match.end()) >= 0
    ]
    return bool(
        reward_positions
        and min(reward_positions) < date_match.start()
        and lifecycle_positions
    )


def _has_campaign_validity(context: str) -> bool:
    campaign = "kampanya" in context or "fırsat" in context or "firsat" in context
    validity = "geçerli" in context or "gecerli" in context
    return campaign and validity


def _extract_end_only(segment: str) -> tuple[date | None, date | None]:
    context = _normalized_context(segment)

    end_only_matches = re.finditer(
        rf"({NUMERIC_DATE_PATTERN}|{FULL_TEXTUAL_DATE_PATTERN})"
        rf"(?:\s+tarihine|\s+saat\s+\d{{1,2}}[.:]\d{{2}}(?:['’]?[a-zçğıöşü]+)?|"
        rf"['’](?:a|e|ya|ye))?"
        rf"\s+kadar\b",
        segment,
        re.IGNORECASE,
    )
    for match in end_only_matches:
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
        if campaign_context and not _is_reward_expiry(context):
            return None, _parse_date(match.group(1))
    return None, None


def _date_context_score(segment: str) -> int:
    context = _normalized_context(segment)
    score = 0
    if "kampanya tarih" in context:
        score += 6
    if "kampanya dönemi" in context or "kampanya donemi" in context:
        score += 4
    if "kampanya" in context:
        score += 2
    if "geçerli" in context or "gecerli" in context:
        score += 2
    if any(word in context for word in ("parafpara", "puan", "bonus", "ödül", "hediye")):
        score -= 3
    if _is_reward_expiry(context):
        score -= 4
    return score


def _date_segments(text: str) -> list[str]:
    segments: list[str] = []
    lines = clean_lines(text).splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if index + 1 < len(lines) and re.match(r"^\d{4}\b", lines[index + 1]):
            combined = f"{line} {lines[index + 1]}"
            if _extract_explicit_ranges(combined) != (None, None):
                line = combined
                index += 1
        for reward_part in INLINE_REWARD_CLAUSE_RE.split(line):
            for part in re.split(r"(?<=[.!?;])\s+", reward_part):
                compact = re.sub(r"\s+", " ", part).strip()
                if compact:
                    segments.append(compact)
        index += 1
    return segments


def extract_date_range(text: str) -> tuple[date | None, date | None]:
    """Ayni kampanya segmentindeki donemleri kapsayan ana tarih araligini dondurur."""
    candidates: list[tuple[int, int, tuple[date | None, date | None]]] = []
    for index, segment in enumerate(_date_segments(text)):
        context = _normalized_context(segment)
        result = _extract_explicit_ranges(segment)
        if (
            result != (None, None)
            and _is_reward_expiry(context)
            and not _has_campaign_validity(context)
        ):
            continue
        if result == (None, None):
            result = _extract_end_only(segment)
        if result != (None, None):
            candidates.append((_date_context_score(segment), index, result))

    if not candidates:
        return None, None
    return max(candidates, key=lambda candidate: (candidate[0], -candidate[1]))[2]


def _is_plausible_campaign_range(value: tuple[date | None, date | None]) -> bool:
    start, end = value
    latest_year = date.today().year + MAX_CAMPAIGN_FUTURE_YEARS
    return bool(
        start
        and end
        and 0 <= (end - start).days <= MAX_CAMPAIGN_DURATION_DAYS
        and end.year <= latest_year
    )


def _merge_campaign_dates(
    scoped: tuple[date | None, date | None],
    page: tuple[date | None, date | None],
    *,
    page_is_primary: bool,
) -> tuple[date | None, date | None]:
    scoped_start, scoped_end = scoped
    page_start, page_end = page
    if page_start and page_end and not _is_plausible_campaign_range(page):
        page = (None, None)
        page_start, page_end = page
    if scoped == (None, None):
        return page
    if page == (None, None):
        return scoped
    if scoped_start is None and scoped_end and page_start and page_end == scoped_end:
        return page_start, scoped_end
    if scoped_start and scoped_end and page_start and page_end and page_is_primary:
        return page
    return scoped


@dataclass(frozen=True, slots=True)
class ScraperConfig:
    slug: str
    bank_name: str
    base_url: str
    listing_urls: tuple[str, ...]
    detail_pattern: str
    content_selectors: tuple[str, ...]
    record_kind: str = "campaign"
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

    def _primary_page_date_range(
        self,
        soup: BeautifulSoup,
        content_nodes: list[Tag],
    ) -> tuple[date | None, date | None]:
        for text_node in soup.find_all(string=PRIMARY_DATE_LABEL_RE):
            label = text_node.parent
            if not isinstance(label, Tag):
                continue
            if any(label is node or label in node.descendants for node in content_nodes):
                continue

            container = label
            for _ in range(4):
                value = clean_lines(container.get_text(" ", strip=True))
                marker = PRIMARY_DATE_LABEL_RE.search(value)
                if marker:
                    dates = _extract_first_explicit_range(
                        value[marker.start() : marker.end() + 160]
                    )
                    if dates != (None, None):
                        return dates
                parent = container.parent
                if not isinstance(parent, Tag) or parent.name in {"body", "html"}:
                    break
                container = parent
        return None, None

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
        scoped_dates = extract_date_range(campaign_text)
        full_text = clean_lines(soup.get_text("\n", strip=True))
        page_dates = self._primary_page_date_range(soup, nodes)
        page_is_primary = page_dates != (None, None)
        if not page_is_primary:
            page_dates = extract_date_range(full_text)
        # Tam sayfa tarihi yalnizca ana metadata ise veya scoped bitisle uyusuyorsa kullanilir.
        start_date, end_date = _merge_campaign_dates(
            scoped_dates,
            page_dates,
            page_is_primary=page_is_primary,
        )
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
            record_kind=self.config.record_kind,
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
