# Campaign Pipeline Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the existing six-bank scraper architecture while adding stable URL normalization, persistence-time deduplication, bank-level failure isolation, structured failures, fixture integration coverage, and refreshed six-bank datasets.

**Architecture:** Extend the existing `Campaign`, `BaseBankScraper`, validation, CLI runner, storage, and preprocessing components in place. Keep FastAPI and JSON field contracts backward compatible; add only quality-report metadata and stronger behavior at existing boundaries.

**Tech Stack:** Python 3.11, dataclasses, requests/urllib3, BeautifulSoup4, pytest, FastAPI, JSON, Next.js 16, TypeScript.

---

## File Map

**Modify:**

- `src/scraper/models.py` — normalize source URLs before ID generation.
- `src/scraper/validation.py` — validate required bank fields and HTML residue; deduplicate normalized campaign URLs.
- `src/scraper/base.py` — create structured failures and isolate discovery/fetch/parse errors.
- `src/scraper/scraper.py` — isolate each bank, integrate deduplication, persist partial successes, and log pipeline milestones.
- `tests/test_validation.py` — cover required fields, HTML residue, and duplicate removal.
- `tests/test_scraper_base.py` — cover structured discovery/fetch failures.
- `tests/test_scraper_cli.py` — cover bank-level isolation, partial persistence, deduplication, and report metadata.
- `README.md` — document smoke versus final data runs and failure semantics.
- `data/README.md` — document deduplication and quality-report fields.
- `data/raw/participation_banks.json` — refresh from BDDK.
- `data/raw/campaigns.json` — regenerate from all six banks.
- `data/processed/campaigns.json` — regenerate derived clean text and tokens.
- `outputs/quality_report.json` — regenerate validation, duplicate, and failure results.

**Create:**

- `tests/test_models.py` — URL normalization and stable ID tests.
- `tests/test_priority_bank_integration.py` — fixture-based priority-bank pipeline tests.
- `tests/fixtures/banks/kuveyt_turk_listing.html`
- `tests/fixtures/banks/kuveyt_turk_detail.html`
- `tests/fixtures/banks/albaraka_listing.html`
- `tests/fixtures/banks/albaraka_detail.html`
- `tests/fixtures/banks/turkiye_finans_listing.html`
- `tests/fixtures/banks/turkiye_finans_detail.html`

Do not modify or stage the pre-existing user change in
`src/dashboard/package-lock.json`.

### Task 1: Normalize Campaign Source URLs and Stable IDs

**Files:**

- Create: `tests/test_models.py`
- Modify: `src/scraper/models.py`

- [ ] **Step 1: Write the failing URL normalization tests**

Create `tests/test_models.py`:

```python
import pytest

from src.scraper.models import Campaign, normalize_source_url


def make_campaign(source_url: str) -> Campaign:
    return Campaign(
        bank_slug="ornek-katilim",
        bank_name="Örnek Katılım Bankası A.Ş.",
        title="Geçerli Kampanya Başlığı",
        content="Kampanya koşullarını açıklayan yeterli uzunlukta örnek içerik metnidir.",
        source_url=source_url,
    )


def test_normalize_source_url_removes_tracking_and_fragment():
    value = (
        " HTTPS://BANK.EXAMPLE/kampanya?utm_source=bulten&campaign=42"
        "&gclid=tracking#kosullar "
    )
    assert normalize_source_url(value) == "https://bank.example/kampanya?campaign=42"


def test_campaign_id_is_stable_across_tracking_variants():
    first = make_campaign("https://bank.example/kampanya?campaign=42")
    second = make_campaign(
        "https://BANK.EXAMPLE/kampanya?utm_medium=email&campaign=42#detay"
    )
    assert first.source_url == second.source_url
    assert first.id == second.id


def test_campaign_rejects_non_string_required_text():
    with pytest.raises(TypeError, match="title string olmali"):
        Campaign(
            bank_slug="ornek-katilim",
            bank_name="Örnek Katılım Bankası A.Ş.",
            title=None,  # type: ignore[arg-type]
            content="Geçerli içerik",
            source_url="https://bank.example/kampanya",
        )
```

- [ ] **Step 2: Run the model tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_models.py -q
```

Expected: collection fails because `normalize_source_url` does not exist.

- [ ] **Step 3: Add minimal URL normalization and text type checks**

In `src/scraper/models.py`, extend the imports and add the helper immediately
after `SCHEMA_VERSION`:

```python
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_QUERY_KEYS = frozenset(
    {"dclid", "fbclid", "gclid", "mc_cid", "mc_eid", "msclkid", "yclid"}
)


def normalize_source_url(value: str) -> str:
    """Remove non-functional tracking data while preserving campaign parameters."""
    if not isinstance(value, str):
        raise TypeError("source_url string olmali")
    parsed = urlsplit(value.strip())
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in TRACKING_QUERY_KEYS
    ]
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            urlencode(query, doseq=True),
            "",
        )
    )
```

Replace `Campaign.__post_init__` with:

```python
def __post_init__(self) -> None:
    for field_name in ("bank_slug", "bank_name", "title", "content", "source_url"):
        if not isinstance(getattr(self, field_name), str):
            raise TypeError(f"{field_name} string olmali")
    for field_name in ("summary", "category", "image_url"):
        value = getattr(self, field_name)
        if value is not None and not isinstance(value, str):
            raise TypeError(f"{field_name} string veya null olmali")

    self.bank_slug = self.bank_slug.strip()
    self.bank_name = self.bank_name.strip()
    self.title = self.title.strip()
    self.content = self.content.strip()
    self.source_url = normalize_source_url(self.source_url)
    self.summary = self.summary.strip() or None if self.summary is not None else None
    self.category = self.category.strip() or None if self.category is not None else None
    self.image_url = self.image_url.strip() or None if self.image_url is not None else None
    if self.scraped_at is None:
        self.scraped_at = datetime.now(timezone.utc)
    if self.id is None:
        key = f"{self.bank_slug}\0{self.source_url}".encode("utf-8")
        self.id = sha256(key).hexdigest()[:20]
```

- [ ] **Step 4: Run model and existing tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_models.py tests/test_scraper_base.py tests/test_scraper_cli.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- src/scraper/models.py tests/test_models.py
git commit -m "feat: normalize campaign source URLs"
```

### Task 2: Strengthen Validation and Remove Duplicate Records

**Files:**

- Modify: `tests/test_validation.py`
- Modify: `src/scraper/validation.py`

- [ ] **Step 1: Write failing validation and deduplication tests**

Append to `tests/test_validation.py` and extend its validation import with
`deduplicate_campaigns`:

```python
def test_empty_bank_fields_are_errors():
    record = valid_campaign()
    record.bank_slug = ""
    record.bank_name = ""
    issues = validate_campaign(record)
    assert {issue["field"] for issue in issues if issue["severity"] == "error"} >= {
        "bank_slug",
        "bank_name",
    }


def test_html_residue_in_content_is_error():
    record = valid_campaign()
    record.content = "<p>" + record.content + "</p>"
    issues = validate_campaign(record)
    assert {
        "severity": "error",
        "field": "content",
        "message": "Kampanya metninde HTML etiketi kalmis",
    } in issues


def test_deduplicate_campaigns_uses_bank_and_normalized_url():
    first = valid_campaign()
    second = valid_campaign()
    second.source_url = first.source_url + "?utm_source=email#detay"
    unique, duplicates = deduplicate_campaigns([first, second])
    assert unique == [first]
    assert len(duplicates) == 1
    assert duplicates[0]["duplicate_of"] == first.id
```

- [ ] **Step 2: Run the new validation tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_validation.py -q
```

Expected: import fails because `deduplicate_campaigns` does not exist.

- [ ] **Step 3: Implement validation and deduplication**

In `src/scraper/validation.py`, import `re`, `normalize_source_url`, and define:

```python
HTML_TAG_RE = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


def deduplicate_campaigns(
    records: Iterable[Campaign],
) -> tuple[list[Campaign], list[dict[str, str]]]:
    unique: list[Campaign] = []
    duplicates: list[dict[str, str]] = []
    seen: dict[tuple[str, str], Campaign] = {}
    for record in records:
        key = (record.bank_slug.casefold(), normalize_source_url(record.source_url))
        original = seen.get(key)
        if original is not None:
            duplicates.append(
                {
                    "record_id": str(record.id),
                    "duplicate_of": str(original.id),
                    "bank_slug": record.bank_slug,
                    "source_url": record.source_url,
                }
            )
            continue
        seen[key] = record
        unique.append(record)
    return unique, duplicates
```

Add these checks at the start of `validate_campaign`, before title/content
length checks:

```python
if not record.bank_slug:
    add("error", "bank_slug", "Banka slug alani bos olamaz")
if not record.bank_name:
    add("error", "bank_name", "Banka adi bos olamaz")
```

Add this check after the content length check:

```python
if HTML_TAG_RE.search(record.content):
    add("error", "content", "Kampanya metninde HTML etiketi kalmis")
```

Change `build_quality_report` to accept removed duplicates and expose them in
the stable report structure:

```python
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
                {
                    "severity": "error",
                    "field": "source_url",
                    "message": "Tekrarlanan kaynak URL",
                }
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
        "duplicate_count": len(duplicates),
        "fetch_failure_count": len(failures),
        "quality_score": round(valid_records / len(records), 4) if records else 0.0,
        "issues": issue_rows,
        "duplicates": duplicates,
        "fetch_failures": failures,
    }
```

- [ ] **Step 4: Run validation tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_validation.py tests/test_scraper_cli.py -q
```

Expected: all selected tests pass, including existing exact-duplicate reporting.

- [ ] **Step 5: Commit Task 2**

```powershell
git add -- src/scraper/validation.py tests/test_validation.py
git commit -m "feat: validate and deduplicate campaign data"
```

### Task 3: Structure and Isolate Discovery, Fetch, and Parse Failures

**Files:**

- Modify: `tests/test_scraper_base.py`
- Modify: `src/scraper/base.py`

- [ ] **Step 1: Write failing structured-failure tests**

At the top of `tests/test_scraper_base.py`, change the datetime import to
`from datetime import date, datetime` and add `import requests` after it. Then
append:

```python
class DiscoveryFailureClient:
    def get_text(self, url: str) -> str:
        raise requests.Timeout("liste zaman asimina ugradi")


class FetchFailureClient:
    def get_text(self, url: str) -> str:
        if url.endswith("/kampanyalar"):
            return '<a href="/kampanyalar/firsat">Fırsat</a>'
        raise requests.ConnectionError("detay baglantisi kurulamadi")


def test_discovery_failure_is_structured_and_does_not_raise():
    records, failures = ExampleScraper(client=DiscoveryFailureClient()).scrape()
    assert records == []
    assert len(failures) == 1
    assert failures[0]["stage"] == "discovery"
    assert failures[0]["error_type"] == "Timeout"
    assert failures[0]["url"] == "https://bank.example/kampanyalar"
    assert failures[0]["http_status"] is None
    datetime.fromisoformat(failures[0]["timestamp"])


def test_fetch_failure_is_structured_and_does_not_drop_the_job():
    records, failures = ExampleScraper(client=FetchFailureClient()).scrape()
    assert records == []
    assert len(failures) == 1
    assert failures[0]["stage"] == "fetch"
    assert failures[0]["error_type"] == "ConnectionError"
    assert failures[0]["url"] == "https://bank.example/kampanyalar/firsat"
```

- [ ] **Step 2: Run scraper-base tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_scraper_base.py -q
```

Expected: discovery exception escapes or required failure fields are missing.

- [ ] **Step 3: Add structured failure construction and stage boundaries**

In `src/scraper/base.py`, add imports:

```python
import logging
from datetime import date, datetime, timezone
from typing import Any
```

Add after imports:

```python
LOGGER = logging.getLogger(__name__)


def build_failure(
    bank_slug: str,
    stage: str,
    url: str,
    exc: Exception,
) -> dict[str, Any]:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return {
        "bank_slug": bank_slug,
        "stage": stage,
        "url": url,
        "error_type": type(exc).__name__,
        "error": str(exc),
        "http_status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
```

Replace `BaseBankScraper.scrape` with:

```python
def scrape(
    self, *, limit: int | None = None
) -> tuple[list[Campaign], list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    try:
        urls = self.discover_urls()
    except Exception as exc:
        listing_url = self.config.listing_urls[0] if self.config.listing_urls else self.config.base_url
        failure = build_failure(self.config.slug, "discovery", listing_url, exc)
        failures.append(failure)
        LOGGER.exception("%s kampanya kesfi basarisiz", self.config.slug)
        return [], failures

    if limit is not None:
        urls = urls[: max(0, limit)]
    LOGGER.info("%s: %d kampanya URL'si kesfedildi", self.config.slug, len(urls))

    records: list[Campaign] = []
    for url in urls:
        try:
            html = self.client.get_text(url)
        except Exception as exc:
            failures.append(build_failure(self.config.slug, "fetch", url, exc))
            LOGGER.exception("%s kampanya sayfasi alinamadi: %s", self.config.slug, url)
            continue
        try:
            records.append(self.parse_detail(url, html))
            LOGGER.info("%s kampanya parse edildi: %s", self.config.slug, url)
        except Exception as exc:
            failures.append(build_failure(self.config.slug, "parse", url, exc))
            LOGGER.exception("%s kampanya parse edilemedi: %s", self.config.slug, url)
    return records, failures
```

- [ ] **Step 4: Run scraper-base tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_scraper_base.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 3**

```powershell
git add -- src/scraper/base.py tests/test_scraper_base.py
git commit -m "feat: report structured scraper failures"
```

### Task 4: Isolate Banks and Integrate Deduplication in the CLI

**Files:**

- Modify: `tests/test_scraper_cli.py`
- Modify: `src/scraper/scraper.py`

- [ ] **Step 1: Write failing bank-isolation and persistence tests**

At the top of `tests/test_scraper_cli.py`, add `import logging` beside `json`,
add `from types import SimpleNamespace`, add `SCRAPERS` to the project imports,
and extend the scraper CLI import with `run_campaigns`. Then append:

```python
def campaign_args(tmp_path, banks: str) -> Namespace:
    return Namespace(
        banks=banks,
        delay=0.0,
        timeout=1.0,
        ignore_robots=True,
        max_per_bank=5,
        output=tmp_path / "campaigns.json",
        quality_report=tmp_path / "quality.json",
    )


class BrokenScraper:
    config = SimpleNamespace(base_url="https://broken.example")

    def __init__(self, client):
        self.client = client

    def scrape(self, *, limit):
        raise RuntimeError("banka scraper'i coktu")


class WorkingScraper:
    config = SimpleNamespace(base_url="https://working.example")

    def __init__(self, client):
        self.client = client

    def scrape(self, *, limit):
        return [
            Campaign(
                bank_slug="working",
                bank_name="Çalışan Katılım",
                title="Çalışan Banka Kampanyası",
                content=(
                    "Çalışan banka diğer banka hata verse bile kaydedilecek kadar "
                    "uzun ve açıklayıcı kampanya koşulları sunmaktadır."
                ),
                summary="Kampanya özeti",
                source_url="https://working.example/kampanya/1",
            )
        ], []


class DuplicateScraper:
    config = SimpleNamespace(base_url="https://duplicate.example")

    def __init__(self, client):
        self.client = client

    def scrape(self, *, limit):
        common = {
            "bank_slug": "duplicate",
            "bank_name": "Duplicate Katılım",
            "title": "Tek Kampanya",
            "content": (
                "Aynı kampanyanın tracking parametreli ikinci kopyasını "
                "ayırt etmek için yeterli uzunlukta açıklama metnidir."
            ),
            "summary": "Kampanya özeti",
        }
        return [
            Campaign(**common, source_url="https://duplicate.example/kampanya/1"),
            Campaign(
                **common,
                source_url="https://duplicate.example/kampanya/1?utm_source=email#detay",
            ),
        ], []


def test_one_bank_failure_does_not_prevent_other_bank_persistence(tmp_path, monkeypatch):
    monkeypatch.setitem(SCRAPERS, "broken", BrokenScraper)
    monkeypatch.setitem(SCRAPERS, "working", WorkingScraper)
    args = campaign_args(tmp_path, "broken,working")

    exit_code = run_campaigns(args)
    dataset = json.loads(args.output.read_text(encoding="utf-8"))
    report = json.loads(args.quality_report.read_text(encoding="utf-8"))

    assert exit_code == 2
    assert dataset["record_count"] == 1
    assert dataset["records"][0]["bank_slug"] == "working"
    assert report["fetch_failure_count"] == 1
    assert report["fetch_failures"][0]["stage"] == "scrape"


def test_run_campaigns_deduplicates_before_persistence(
    tmp_path, monkeypatch, caplog
):
    monkeypatch.setitem(SCRAPERS, "duplicate", DuplicateScraper)
    args = campaign_args(tmp_path, "duplicate")

    with caplog.at_level(logging.INFO):
        exit_code = run_campaigns(args)
    dataset = json.loads(args.output.read_text(encoding="utf-8"))
    report = json.loads(args.quality_report.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert dataset["record_count"] == 1
    assert report["duplicate_count"] == 1
    assert "duplicate" in caplog.text.lower()
    assert "persist" in caplog.text.lower()
```

- [ ] **Step 2: Run CLI tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_scraper_cli.py -q
```

Expected: the broken bank exception escapes or duplicate metadata is absent.

- [ ] **Step 3: Implement bank isolation, deduplication, and milestone logs**

In `src/scraper/scraper.py`, import `build_failure` and
`deduplicate_campaigns`:

```python
from .base import build_failure
from .validation import build_quality_report, deduplicate_campaigns
```

Replace `run_campaigns` with:

```python
def run_campaigns(args: argparse.Namespace) -> int:
    bank_slugs = resolve_banks(args.banks)
    client = _client(args)
    records = []
    failures: list[dict[str, object]] = []
    for slug in bank_slugs:
        LOGGER.info("scraper started: %s", slug)
        scraper_class = SCRAPERS[slug]
        bank_url = getattr(scraper_class.config, "base_url", "")
        try:
            scraper = scraper_class(client=client)
            bank_records, bank_failures = scraper.scrape(limit=args.max_per_bank)
        except Exception as exc:
            bank_records = []
            bank_failures = [build_failure(slug, "scrape", bank_url, exc)]
            LOGGER.exception("scraper failed: %s", slug)
        records.extend(bank_records)
        failures.extend(bank_failures)
        LOGGER.info(
            "scraper completed: %s records=%d failures=%d",
            slug,
            len(bank_records),
            len(bank_failures),
        )

    records, duplicates = deduplicate_campaigns(records)
    LOGGER.info("duplicates removed: %d", len(duplicates))
    dataset = campaign_dataset(records)
    report = build_quality_report(records, failures, duplicates)
    LOGGER.info(
        "validation completed: records=%d errors=%d warnings=%d",
        len(records),
        report["error_count"],
        report["warning_count"],
    )
    write_json(args.output, dataset)
    write_json(args.quality_report, report)
    LOGGER.info("data persisted: %s and %s", args.output, args.quality_report)
    print(
        f"{len(records)} kampanya yazıldı: {args.output} "
        f"(kalite skoru={report['quality_score']:.2%}, "
        f"çekme hatası={len(failures)}, duplicate={len(duplicates)})"
    )
    if not records or report["error_count"] or failures:
        return 2
    return 0
```

- [ ] **Step 4: Run CLI and related tests and verify GREEN**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_scraper_cli.py tests/test_validation.py -q
```

Expected: all selected tests pass; the partial-success case returns 2 after
writing the working bank record.

- [ ] **Step 5: Commit Task 4**

```powershell
git add -- src/scraper/scraper.py tests/test_scraper_cli.py
git commit -m "feat: isolate bank scraping jobs"
```

### Task 5: Add Fixture Integration Tests for the Three Priority Banks

**Files:**

- Create: `tests/test_priority_bank_integration.py`
- Create: six HTML fixtures under `tests/fixtures/banks/`

- [ ] **Step 1: Create bank-specific listing fixtures**

Create `tests/fixtures/banks/kuveyt_turk_listing.html`:

```html
<div class="campaign-item">
  <a href="/kampanyalar/kendim-icin/kart-kampanyalari/ornek-firsat">Fırsat</a>
</div>
```

Create `tests/fixtures/banks/albaraka_listing.html`:

```html
<div class="kampanyalar-card">
  <a href="/tr/kampanyalar/detay/ornek-firsat">Fırsat</a>
</div>
```

Create `tests/fixtures/banks/turkiye_finans_listing.html`:

```html
<div class="campaign-list">
  <div class="campaign">
    <a href="/tr-tr/kampanyalar/Sayfalar/ornek-firsat.aspx">Fırsat</a>
  </div>
</div>
```

- [ ] **Step 2: Create bank-specific detail fixtures**

Create `tests/fixtures/banks/kuveyt_turk_detail.html`:

```html
<html><body>
  <h1 id="pageTitle">Kuveyt Türk Örnek Kampanyası</h1>
  <div class="subpage-content"><div class="search-content">
    <p>1 Ağustos - 31 Ağustos 2026 tarihleri arasında geçerlidir.</p>
    <p>Kuveyt Türk müşterilerine özel kampanya koşullarını ve katılım ayrıntılarını açıklayan yeterince uzun içerik metnidir.</p>
  </div></div>
</body></html>
```

Create `tests/fixtures/banks/albaraka_detail.html`:

```html
<html><body>
  <h1 class="searchTitle">Albaraka Türk Örnek Kampanyası</h1>
  <div class="searchContent custom-table">
    <p>1 Ağustos - 31 Ağustos 2026 tarihleri arasında geçerlidir.</p>
    <p>Albaraka Türk müşterilerine özel kampanya koşullarını ve katılım ayrıntılarını açıklayan yeterince uzun içerik metnidir.</p>
  </div>
</body></html>
```

Create `tests/fixtures/banks/turkiye_finans_detail.html`:

```html
<html><body>
  <div class="subpage-content page">
    <div class="header"><h1>Türkiye Finans Örnek Kampanyası</h1></div>
    <div class="ms-rtestate-field">
      <p>1 Ağustos - 31 Ağustos 2026 tarihleri arasında geçerlidir.</p>
      <p>Türkiye Finans müşterilerine özel kampanya koşullarını ve katılım ayrıntılarını açıklayan yeterince uzun içerik metnidir.</p>
    </div>
  </div>
</body></html>
```

- [ ] **Step 3: Add the fixture pipeline test**

Create `tests/test_priority_bank_integration.py`:

```python
from pathlib import Path

import pytest

from src.scraper.banks import AlbarakaScraper, KuveytTurkScraper, TurkiyeFinansScraper
from src.scraper.validation import validate_campaign


FIXTURES = Path(__file__).parent / "fixtures" / "banks"


class FixtureClient:
    def __init__(self, listing_urls: tuple[str, ...], listing: str, detail: str):
        self.listing_urls = set(listing_urls)
        self.listing = listing
        self.detail = detail

    def get_text(self, url: str) -> str:
        return self.listing if url in self.listing_urls else self.detail


@pytest.mark.parametrize(
    ("scraper_class", "fixture_prefix", "expected_slug"),
    [
        (KuveytTurkScraper, "kuveyt_turk", "kuveyt-turk"),
        (AlbarakaScraper, "albaraka", "albaraka-turk"),
        (TurkiyeFinansScraper, "turkiye_finans", "turkiye-finans"),
    ],
)
def test_priority_bank_fixture_pipeline(
    scraper_class, fixture_prefix: str, expected_slug: str
):
    listing = (FIXTURES / f"{fixture_prefix}_listing.html").read_text(encoding="utf-8")
    detail = (FIXTURES / f"{fixture_prefix}_detail.html").read_text(encoding="utf-8")
    client = FixtureClient(scraper_class.config.listing_urls, listing, detail)

    records, failures = scraper_class(client=client).scrape(limit=1)

    assert failures == []
    assert len(records) == 1
    assert records[0].bank_slug == expected_slug
    assert records[0].title
    assert records[0].content
    assert records[0].source_url.startswith("https://")
    assert not [
        issue for issue in validate_campaign(records[0]) if issue["severity"] == "error"
    ]
```

- [ ] **Step 4: Run the characterization integration tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_priority_bank_integration.py -q
```

Expected: three cases pass with the existing bank selectors. If a case fails,
stop and use the systematic-debugging workflow to determine whether the fixture
or current bank configuration is inconsistent before changing production code.

- [ ] **Step 5: Commit Task 5**

```powershell
git add -- tests/test_priority_bank_integration.py tests/fixtures/banks
git commit -m "test: cover priority bank scraper pipelines"
```

### Task 6: Update Existing Documentation Without Rewriting It

**Files:**

- Modify: `README.md`
- Modify: `data/README.md`

- [ ] **Step 1: Add smoke and final-run guidance to the root README**

Add the following after the existing six-bank command in `README.md`:

```markdown
Canlı smoke doğrulaması ilk üç öncelikli bankayı düşük limit ile geçici bir
çıktı dizinine yazar. Kalıcı veri dosyaları bu kontrol sırasında değiştirilmez.
Kalıcı veri yenilemesi ise `--banks all` ile altı banka için yapılır.

Pipeline bir bankada hata oluştuğunda diğer bankalara devam eder. Başarılı
kayıtlar yazılır; komut kısmi başarısızlığı exit code `2` ile ve
`fetch_failures` alanıyla görünür kılar.
```

Add the following to the responsible-scraping section:

```markdown
Kaynak URL'lerdeki `utm_*`, `gclid`, `fbclid` ve benzeri tracking alanları
kimlik üretiminden önce kaldırılır. Duplicate kayıtlar
`bank_slug + normalized source_url` anahtarıyla persistence öncesinde elenir;
kaldırılan kayıtlar kalite raporundaki `duplicates` alanında tutulur.
```

- [ ] **Step 2: Document quality-report additions in `data/README.md`**

Add this subsection after the existing quality rules:

```markdown
### Duplicate ve failure raporu

`duplicate_count` persistence öncesinde kaldırılan kayıt sayısını,
`duplicates` ise kaldırılan kayıt ile korunan kayıt kimliği arasındaki ilişkiyi
gösterir. `fetch_failures` kayıtlarında banka, pipeline aşaması, URL, hata tipi,
mesaj, mümkünse HTTP status ve UTC timestamp bulunur. Bir bankanın failure'ı
başarılı bankaların raw kayıtlarını geçersiz kılmaz.
```

- [ ] **Step 3: Check documentation diff and formatting**

Run:

```powershell
git diff --check -- README.md data/README.md
```

Expected: exit code 0 and no whitespace diagnostics.

- [ ] **Step 4: Commit Task 6**

```powershell
git add -- README.md data/README.md
git commit -m "docs: document scraper quality controls"
```

### Task 7: Run Automated Checks and Live Smoke Tests

**Files:** None; smoke output stays outside the repository.

- [ ] **Step 1: Run all Python tests**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all tests pass with zero failures.

- [ ] **Step 2: Lint only tracked Python files**

```powershell
$pythonFiles = git ls-files '*.py'
.\.venv\Scripts\python.exe -m flake8 $pythonFiles --max-line-length=100 --extend-ignore=E203
```

Expected: exit code 0. Using tracked files prevents local
`src/dashboard/node_modules` contents from polluting the backend lint result.

- [ ] **Step 3: Run BDDK and priority-bank smoke checks into a temporary directory**

```powershell
$smokeRoot = Join-Path $env:TEMP ("ragnroll-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $smokeRoot | Out-Null
.\.venv\Scripts\python.exe -m src.scraper.scraper --verbose banks `
  --delay 0.1 --timeout 25 --output (Join-Path $smokeRoot "banks.json")
.\.venv\Scripts\python.exe -m src.scraper.scraper --verbose campaigns `
  --banks priority --max-per-bank 3 --delay 0.1 --timeout 25 `
  --output (Join-Path $smokeRoot "campaigns.json") `
  --quality-report (Join-Path $smokeRoot "quality.json")
```

Expected: BDDK output contains active participation-bank rows; each priority
bank produces at least one record; smoke quality has zero validation errors and
zero fetch failures.

### Task 8: Regenerate the Six-Bank Repository Outputs

**Files:**

- Modify: `data/raw/participation_banks.json`
- Modify: `data/raw/campaigns.json`
- Modify: `data/processed/campaigns.json`
- Modify: `outputs/quality_report.json`

- [ ] **Step 1: Refresh the BDDK bank registry**

```powershell
.\.venv\Scripts\python.exe -m src.scraper.scraper --verbose banks `
  --output data/raw/participation_banks.json
```

Expected: exit code 0 and valid UTF-8 JSON with a non-zero `count`.

- [ ] **Step 2: Run all six bank scrapers into the tracked raw and quality files**

```powershell
.\.venv\Scripts\python.exe -m src.scraper.scraper --verbose campaigns `
  --banks all --max-per-bank 20 `
  --output data/raw/campaigns.json `
  --quality-report outputs/quality_report.json
```

Expected success state: exit code 0, all six configured bank slugs represented,
zero validation errors, and zero fetch failures. If an external source fails,
keep successful data only after inspecting the structured failure and report
the exact bank and stage; do not claim the failed bank succeeded.

- [ ] **Step 3: Regenerate processed data from the new raw dataset**

```powershell
.\.venv\Scripts\python.exe -m src.scraper.scraper preprocess `
  data/raw/campaigns.json --output data/processed/campaigns.json
```

Expected: exit code 0 and processed `record_count` equals raw `record_count`.

- [ ] **Step 4: Validate raw data without overwriting the crawl quality report**

```powershell
$validationReport = Join-Path $env:TEMP "ragnroll-raw-validation.json"
.\.venv\Scripts\python.exe -m src.scraper.scraper validate `
  data/raw/campaigns.json --output $validationReport
```

Expected: exit code 0. The temporary validation report must not replace
`outputs/quality_report.json`, which retains crawl failures and duplicate data.

- [ ] **Step 5: Verify JSON and raw/processed consistency**

```powershell
.\.venv\Scripts\python.exe -c "import json; from pathlib import Path; raw=json.loads(Path('data/raw/campaigns.json').read_text(encoding='utf-8')); processed=json.loads(Path('data/processed/campaigns.json').read_text(encoding='utf-8')); quality=json.loads(Path('outputs/quality_report.json').read_text(encoding='utf-8')); assert raw['record_count']==processed['record_count']==quality['record_count']; assert {r['bank_slug'] for r in raw['records']}=={'kuveyt-turk','albaraka-turk','turkiye-finans','ziraat-katilim','vakif-katilim','emlak-katilim'}; assert all({'clean_text','tokens','token_count'} <= r.keys() for r in processed['records']); assert all(r['content']==p['content'] for r,p in zip(raw['records'],processed['records'])); print(raw['record_count'], quality['error_count'], quality['fetch_failure_count'], quality['duplicate_count'])"
```

Expected: command prints record count followed by `0 0` and the observed
duplicate count without assertion failures.

- [ ] **Step 6: Commit generated datasets separately**

```powershell
git add -- data/raw/participation_banks.json data/raw/campaigns.json data/processed/campaigns.json outputs/quality_report.json
git commit -m "data: refresh participation bank campaigns"
```

### Task 9: Full Regression Verification and Review

**Files:** All changed files, inspected read-only.

- [ ] **Step 1: Run fresh backend verification**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
$pythonFiles = git ls-files '*.py'
.\.venv\Scripts\python.exe -m flake8 $pythonFiles --max-line-length=100 --extend-ignore=E203
```

Expected: zero test failures and zero lint findings.

- [ ] **Step 2: Verify existing API contracts directly**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_basic.py -q
```

Expected: `/health`, `/chat`, and request-validation tests pass.

- [ ] **Step 3: Run frontend regression checks**

```powershell
npm run lint
npm run build
```

Run from `src/dashboard`.

Expected: ESLint exits 0 and Next.js production build completes successfully.

- [ ] **Step 4: Inspect scope and protect the user change**

```powershell
git status --short
git diff --check main...HEAD
git diff -- src/dashboard/package-lock.json
```

Expected: the package-lock diff remains unstaged and unchanged from its
pre-existing 90-line deletion; implementation commits contain only planned
files.

- [ ] **Step 5: Request a focused code review**

Provide the reviewer with the design spec, this plan, the pre-implementation
base SHA, the current HEAD SHA, changed-file diff, automated test output, smoke
results, and six-bank output summary. Fix every Critical or Important issue
with a new failing test before changing production code.

- [ ] **Step 6: Run final fresh verification after review fixes**

Repeat Tasks 9.1 through 9.3 and re-run the JSON consistency command from Task
8.5. Record exact test counts, bank counts, failures, warnings, duplicates, and
build status for the required 11-section final report.
