# BDDK PRD Data Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BDDK'nin resmî Türkçe `/Kurulus/Liste/77` kataloğundaki tüm katılım bankalarından ürün ve kampanya metinlerini toplayan, PRD alanlarını yapılandıran ve gerçek uçtan uca kalite raporu üreten veri hattını tamamlamak.

**Architecture:** BDDK kataloğu banka kapsamının tek otoritesi olacak; katalogdaki kanonik slug'lar scraper registry ile eşleştirilecek. Bankaya özgü adaptörler ham ürün/kampanya metnini kayıpsız toplayacak, ortak yerel çıkarım katmanı PRD alanlarını işlenmiş veri setine ekleyecek ve tek bir `collect` komutu katalog, ham veri, işlenmiş veri, kapsam ve kalite raporlarını atomik olarak üretecek.

**Tech Stack:** Python 3.11+, requests/truststore, BeautifulSoup 4, dataclasses, pytest, JSON

---

## Dosya yapısı

- Modify: `src/scraper/bddk.py` - normatif BDDK URL'si, kanonik slug ve katalog kaydı
- Create: `src/scraper/coverage.py` - katalog/registry kapsam karşılaştırması
- Modify: `src/scraper/models.py` - ürün/kampanya kayıt türü ve birleşik sayfa öğe anahtarı
- Create: `src/extraction/campaign_fields.py` - PRD alanlarının deterministik çıkarımı
- Modify: `src/preprocessing/clean_text.py` - işlenmiş kayda PRD alanlarını ekleme
- Create: `src/scraper/banks/adil_katilim.py` - Adil ürün/hizmet kaynağı
- Create: `src/scraper/banks/dunya_katilim.py` - Dünya kampanya kaynağı
- Create: `src/scraper/banks/hayat_finans.py` - Hayat kampanya kaynağı
- Create: `src/scraper/banks/tom_katilim.py` - TOM birleşik kampanya sayfası adaptörü
- Modify: `src/scraper/banks/__init__.py` - yeni adaptör ihracı
- Modify: `src/scraper/registry.py` - 10 bankalık registry
- Modify: `src/scraper/validation.py` - banka ve PRD alan doluluk metrikleri
- Modify: `src/scraper/scraper.py` - BDDK güdümlü `collect` orkestrasyonu
- Modify: `README.md` ve `data/README.md` - kaynak, şema ve canlı çalıştırma belgeleri
- Test: `tests/test_bddk.py`, `tests/test_coverage.py`, `tests/test_models.py`
- Test: `tests/test_campaign_extraction.py`, `tests/test_preprocessing.py`
- Test: `tests/test_all_bank_integration.py`, `tests/test_scraper_cli.py`, `tests/test_validation.py`
- Create: `tests/fixtures/banks/{adil_katilim,dunya_katilim,hayat_finans,tom_katilim}_*.html`

### Task 1: Normatif BDDK kataloğu ve kapsam raporu

**Files:**
- Modify: `src/scraper/bddk.py`
- Create: `src/scraper/coverage.py`
- Modify: `tests/test_bddk.py`
- Create: `tests/test_coverage.py`

- [ ] **Step 1: Normatif URL ve kanonik slug için başarısız testleri yaz**

```python
from src.scraper.bddk import BDDK_BANKS_URL, fetch_participation_banks


def test_bddk_uses_normative_turkish_participation_bank_page():
    assert BDDK_BANKS_URL == "https://www.bddk.org.tr/Kurulus/Liste/77"


def test_bddk_rows_include_canonical_slug():
    payload = fetch_participation_banks(FakeClient())
    assert payload["banks"][0]["slug"] == "ornek-katilim"
```

`FakeClient` fixture banka adlarını gerçek kanonik haritada bulunan `DÜNYA KATILIM BANKASI A.Ş.` ve `HAYAT FİNANS KATILIM BANKASI A.Ş.` değerleriyle güncellenecek; beklenen slug'lar sırasıyla `dunya-katilim` ve `hayat-finans` olacak.

- [ ] **Step 2: Testleri çalıştır ve beklendiği gibi başarısız olduklarını doğrula**

Run: `..\..\.venv\Scripts\python.exe -m pytest tests/test_bddk.py -q`

Expected: URL `/90` olduğu ve `slug` alanı bulunmadığı için FAIL.

- [ ] **Step 3: BDDK URL'sini ve açık kanonik banka haritasını uygula**

```python
BDDK_BANKS_URL = "https://www.bddk.org.tr/Kurulus/Liste/77"

BANK_NAME_TO_SLUG = {
    "ADİL KATILIM BANKASI A.Ş.": "adil-katilim",
    "ALBARAKA TÜRK KATILIM BANKASI A.Ş.": "albaraka-turk",
    "DÜNYA KATILIM BANKASI A.Ş.": "dunya-katilim",
    "HAYAT FİNANS KATILIM BANKASI A.Ş.": "hayat-finans",
    "KUVEYT TÜRK KATILIM BANKASI A.Ş.": "kuveyt-turk",
    "T.O.M. KATILIM BANKASI A.Ş.": "tom-katilim",
    "TÜRKİYE EMLAK KATILIM BANKASI A.Ş.": "emlak-katilim",
    "TÜRKİYE FİNANS KATILIM BANKASI A.Ş.": "turkiye-finans",
    "VAKIF KATILIM BANKASI A.Ş.": "vakif-katilim",
    "ZİRAAT KATILIM BANKASI A.Ş.": "ziraat-katilim",
}
```

Parser bilinmeyen bir banka adı gördüğünde slug uydurmayacak; `ValueError(f"BDDK banka adi kanonik haritada yok: {name}")` üretecek. Her banka satırına `slug` eklenecek.

- [ ] **Step 4: Kapsam raporu için başarısız testleri yaz**

```python
from src.scraper.coverage import build_coverage_report


def test_coverage_reports_supported_unsupported_and_stale():
    catalog = [{"slug": "a"}, {"slug": "b"}]
    report = build_coverage_report(catalog, {"a": object, "c": object})
    assert report == {
        "catalog_count": 2,
        "supported_count": 1,
        "supported": ["a"],
        "unsupported": ["b"],
        "stale": ["c"],
        "complete": False,
    }
```

- [ ] **Step 5: Minimal kapsam raporu implementasyonunu yaz**

```python
def build_coverage_report(catalog_banks, scrapers):
    catalog = {str(bank["slug"]) for bank in catalog_banks}
    registered = set(scrapers)
    supported = sorted(catalog & registered)
    unsupported = sorted(catalog - registered)
    stale = sorted(registered - catalog)
    return {
        "catalog_count": len(catalog),
        "supported_count": len(supported),
        "supported": supported,
        "unsupported": unsupported,
        "stale": stale,
        "complete": not unsupported and not stale,
    }
```

- [ ] **Step 6: Task testlerini ve regresyonu çalıştır**

Run: `..\..\.venv\Scripts\python.exe -m pytest tests/test_bddk.py tests/test_coverage.py -q`

Expected: PASS.

- [ ] **Step 7: Commit et**

```powershell
git add src/scraper/bddk.py src/scraper/coverage.py tests/test_bddk.py tests/test_coverage.py
git commit -m "feat: make BDDK catalog authoritative"
```

### Task 2: Ham kayıt kimliği ve ürün/kampanya ayrımı

**Files:**
- Modify: `src/scraper/models.py`
- Modify: `src/scraper/validation.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_validation.py`

- [ ] **Step 1: Kayıt türü ve birleşik sayfa öğesi testlerini yaz**

```python
def test_campaign_defaults_to_campaign_record_kind():
    value = campaign("https://bank.example/kampanya")
    assert value.record_kind == "campaign"
    assert value.source_item_key is None


def test_same_page_items_have_distinct_ids():
    first = campaign("https://bank.example/kampanyalar", source_item_key="restoran")
    second = campaign("https://bank.example/kampanyalar", source_item_key="okul")
    assert first.id != second.id


def test_record_kind_rejects_unknown_value():
    with pytest.raises(ValueError, match="record_kind"):
        campaign("https://bank.example/x", record_kind="news")
```

- [ ] **Step 2: Testi çalıştır ve yeni alanlar bulunmadığı için FAIL olduğunu doğrula**

Run: `..\..\.venv\Scripts\python.exe -m pytest tests/test_models.py -q`

- [ ] **Step 3: Modele alanları ve kararlı kimlik anahtarını ekle**

```python
record_kind: str = "campaign"
source_item_key: str | None = None

# __post_init__ içinde
if self.record_kind not in {"campaign", "product"}:
    raise ValueError("record_kind campaign veya product olmali")
if self.source_item_key is not None:
    self.source_item_key = self.source_item_key.strip() or None
if self.id is None:
    key = (
        f"{self.bank_slug}\0{self.source_url}\0"
        f"{self.source_item_key or ''}\0{self.record_kind}"
    ).encode("utf-8")
    self.id = sha256(key).hexdigest()[:20]
```

- [ ] **Step 4: Tekilleştirme anahtarını öğe anahtarıyla genişleten testi yaz ve uygula**

```python
def _record_key(record: Campaign) -> tuple[str, str, str, str]:
    return (
        record.bank_slug.casefold(),
        normalize_source_url(record.source_url),
        record.source_item_key or "",
        record.record_kind,
    )
```

`_group_record_indexes` bu yardımcıyı kullanacak. Aynı sayfadaki farklı `source_item_key` değerlerinin duplicate sayılmadığı test edilecek.

- [ ] **Step 5: Task testlerini çalıştır**

Run: `..\..\.venv\Scripts\python.exe -m pytest tests/test_models.py tests/test_validation.py -q`

Expected: PASS.

- [ ] **Step 6: Commit et**

```powershell
git add src/scraper/models.py src/scraper/validation.py tests/test_models.py tests/test_validation.py
git commit -m "feat: support product and compound-page records"
```

### Task 3: PRD alan çıkarımı ve işlenmiş şema

**Files:**
- Create: `src/extraction/__init__.py`
- Replace: `src/extraction/main.py`
- Create: `src/extraction/campaign_fields.py`
- Create: `tests/test_campaign_extraction.py`
- Modify: `src/preprocessing/clean_text.py`
- Modify: `tests/test_preprocessing.py`

- [ ] **Step 1: Temel PRD çıkarım testlerini yaz**

```python
from src.extraction.campaign_fields import extract_prd_fields


def test_extracts_financing_fields_with_evidence():
    result = extract_prd_fields(
        "Yeni müşterilere özel %2,05 kâr payı oranı, 36 ay vade ve "
        "masrafsız ihtiyaç finansmanı."
    )
    assert result["product_type"] == "financing"
    assert result["financing_type"] == "consumer"
    assert result["profit_share_rate"] == 0.0205
    assert result["term_months"] == 36
    assert result["target_audience"] == "new_customer"
    assert result["fee_information"] == "masrafsız"
    assert result["evidence"]["profit_share_rate"] == "%2,05 kâr payı oranı"


def test_extracts_reward_discount_and_installments():
    result = extract_prd_fields(
        "Kartınızla 4 taksit ve %10 indirim; en fazla 500 TL nakit ödül."
    )
    assert result["product_type"] == "card"
    assert result["installment_count"] == 4
    assert result["discount_rate"] == 0.10
    assert result["reward_amount"] == {"amount": 500.0, "currency": "TRY"}


def test_missing_values_are_null_not_guessed():
    result = extract_prd_fields("Avantajlı ürünümüzü keşfedin.")
    assert result["profit_share_rate"] is None
    assert result["term_months"] is None
    assert result["extraction_method"] == "rules-v1"
```

- [ ] **Step 2: Testleri çalıştır ve modül olmadığı için FAIL olduğunu doğrula**

Run: `..\..\.venv\Scripts\python.exe -m pytest tests/test_campaign_extraction.py -q`

- [ ] **Step 3: Deterministik çıkarım API'sini uygula**

`extract_prd_fields(text: str, *, start_date: str | None = None, end_date: str | None = None) -> dict[str, Any]` aşağıdaki sabit anahtarları her çağrıda döndürecek:

```python
{
    "product_type": product_type,
    "financing_type": financing_type,
    "profit_share_rate": profit_share_rate,
    "term_months": term_months,
    "installment_count": installment_count,
    "campaign_benefit": campaign_benefit,
    "reward_amount": reward_amount,
    "discount_rate": discount_rate,
    "target_audience": target_audience,
    "campaign_start_date": start_date,
    "campaign_end_date": end_date,
    "fee_information": fee_information,
    "evidence": evidence,
    "extraction_method": "rules-v1",
}
```

Regex'ler bağlam kelimesini değere dahil edecek; genel yüzdeler `kâr payı`, `indirim`, `iade` yakınlığı olmadan kâr payı sayılmayacak. Para birimleri `TL/₺ -> TRY`, `USD/$ -> USD`, `EUR/€ -> EUR` normalize edilecek.

- [ ] **Step 4: Ürün türlerinin tamamı için parametrik test ekle**

```python
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Konut finansmanı", "financing"),
        ("Kart harcamanıza bonus", "card"),
        ("Altın katılma hesabı yatırım ürünü", "investment"),
        ("Alışveriş puanı kazanın", "shopping_points"),
        ("İlk kez müşteri olanlara özel", "new_customer"),
    ],
)
def test_classifies_prd_product_types(text, expected):
    assert extract_prd_fields(text)["product_type"] == expected
```

- [ ] **Step 5: Ön işleme entegrasyon testini yaz**

```python
def test_preprocess_record_adds_structured_prd_fields():
    record = {
        "content": "%1,89 kâr payı ile 120 ay vadeli konut finansmanı",
        "start_date": "2026-08-01",
        "end_date": "2026-12-31",
    }
    result = preprocess_record(record)
    assert result["structured"]["profit_share_rate"] == 0.0189
    assert result["structured"]["campaign_end_date"] == "2026-12-31"
```

- [ ] **Step 6: `preprocess_record` içinde çıkarımı bağla**

```python
result["structured"] = extract_prd_fields(
    "\n".join(filter(None, [str(record.get("title") or ""), cleaned])),
    start_date=record.get("start_date"),
    end_date=record.get("end_date"),
)
```

- [ ] **Step 7: Task testlerini çalıştır ve commit et**

Run: `..\..\.venv\Scripts\python.exe -m pytest tests/test_campaign_extraction.py tests/test_preprocessing.py -q`

Expected: PASS.

```powershell
git add src/extraction src/preprocessing/clean_text.py tests/test_campaign_extraction.py tests/test_preprocessing.py
git commit -m "feat: extract structured PRD campaign fields"
```

### Task 4: BDDK'daki eksik dört banka adaptörü

**Files:**
- Create: `src/scraper/banks/adil_katilim.py`
- Create: `src/scraper/banks/dunya_katilim.py`
- Create: `src/scraper/banks/hayat_finans.py`
- Create: `src/scraper/banks/tom_katilim.py`
- Modify: `src/scraper/banks/__init__.py`
- Modify: `src/scraper/registry.py`
- Create: `tests/test_all_bank_integration.py`
- Create: `tests/fixtures/banks/adil_katilim_product.html`
- Create: `tests/fixtures/banks/dunya_katilim_listing.html`
- Create: `tests/fixtures/banks/dunya_katilim_detail.html`
- Create: `tests/fixtures/banks/hayat_finans_listing.html`
- Create: `tests/fixtures/banks/hayat_finans_detail.html`
- Create: `tests/fixtures/banks/tom_katilim_campaigns.html`

- [ ] **Step 1: 10 bankalık registry testini yaz**

```python
def test_registry_covers_all_normative_bddk_slugs():
    assert set(SCRAPERS) == {
        "adil-katilim", "albaraka-turk", "dunya-katilim", "hayat-finans",
        "kuveyt-turk", "tom-katilim", "emlak-katilim", "turkiye-finans",
        "vakif-katilim", "ziraat-katilim",
    }
```

- [ ] **Step 2: Resmî sayfalardan minimal fixture'ları kaydet ve kişisel/veri dışı içeriği çıkar**

Fixture'lar yalnızca ayrıştırma davranışını kanıtlayan küçük HTML parçaları içerecek:

- Adil: `https://www.adilkatilim.com.tr/katilim-bankaciligi/urun-ve-hizmetler`
- Dünya: `https://dunyakatilim.com.tr/kampanyalar` ve `/kampanyalar/network`
- Hayat: `https://hayatfinans.com.tr/kampanyalar` ve `/kampanyalar/hayatfinansla-islem-yaptikca-kazan`
- TOM: `https://www.tombank.com.tr/kampanyalar.html`

- [ ] **Step 3: Dünya ve Hayat için standart adaptör testlerini yaz**

```python
@pytest.mark.parametrize(
    ("scraper_class", "expected_kind"),
    [(DunyaKatilimScraper, "campaign"), (HayatFinansScraper, "campaign")],
)
def test_new_detail_page_scrapers_return_valid_records(scraper_class, expected_kind):
    records, failures = scraper_class(client=fixture_client(scraper_class)).scrape(limit=1)
    assert failures == []
    assert len(records) == 1
    assert records[0].record_kind == expected_kind
    assert not [i for i in validate_campaign(records[0]) if i["severity"] == "error"]
```

- [ ] **Step 4: Dünya ve Hayat `ScraperConfig` sınıflarını uygula**

```python
class DunyaKatilimScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="dunya-katilim",
        bank_name="Dünya Katılım Bankası A.Ş.",
        base_url="https://dunyakatilim.com.tr",
        listing_urls=("https://dunyakatilim.com.tr/kampanyalar",),
        detail_pattern=r"/kampanyalar/[^/?#]+$",
        content_selectors=("main",),
        title_selectors=("main h1", "h1"),
    )
```

Hayat adaptörü aynı kalıbı `/kampanyalar/[^/?#]+$` ile ve canlı DOM'a göre daraltılmış liste/içerik seçicileriyle uygulayacak.

- [ ] **Step 5: Adil ürün sayfası testini ve adaptörünü yaz**

Adil'in ayrı kampanya kataloğu bulunmadığından resmî ürün/hizmet sayfası tek `product` kaydı olarak toplanacak:

```python
class AdilKatilimScraper(BaseBankScraper):
    config = ScraperConfig(
        slug="adil-katilim",
        bank_name="Adil Katılım Bankası A.Ş.",
        base_url="https://www.adilkatilim.com.tr",
        listing_urls=(
            "https://www.adilkatilim.com.tr/katilim-bankaciligi/urun-ve-hizmetler",
        ),
        detail_pattern=r"/katilim-bankaciligi/urun-ve-hizmetler$",
        content_selectors=("main",),
        title_selectors=("main h1", "h1"),
    )

    def discover_urls(self):
        return list(self.config.listing_urls)

    def parse_detail(self, url, html):
        record = super().parse_detail(url, html)
        record.record_kind = "product"
        return record
```

- [ ] **Step 6: TOM birleşik sayfa öğesi testini yaz**

```python
def test_tom_compound_page_returns_one_record_per_campaign_section():
    records, failures = TomKatilimScraper(client=tom_fixture_client()).scrape()
    assert failures == []
    assert [r.source_item_key for r in records] == ["restoran-iade", "okul-taksit"]
    assert len({r.id for r in records}) == 2
    assert all(r.source_url == "https://www.tombank.com.tr/kampanyalar.html" for r in records)
```

- [ ] **Step 7: TOM sayfa bölme adaptörünü uygula**

`TomKatilimScraper.scrape` tek sayfayı çekecek, kampanya başlıklarını `h5`/canlı eşdeğer başlık seçicisiyle bölecek, her bölüm için slug biçiminde `source_item_key` ve bölümün tam metnini üretecek. Başlıksız veya 80 karakterden kısa bölümler kaydedilmeyecek; sayfa çekme/parse hataları `build_failure` ile raporlanacak.

- [ ] **Step 8: Yeni sınıfları ihraç et ve registry'yi 10 bankaya tamamla**

`ALL_BANKS` BDDK sırasına göre açık tuple olacak; `priority` geriye dönük korunacak.

- [ ] **Step 9: Task testlerini ve tüm scraper fixture testlerini çalıştır**

Run: `..\..\.venv\Scripts\python.exe -m pytest tests/test_all_bank_integration.py tests/test_priority_bank_integration.py tests/test_scraper_base.py -q`

Expected: PASS.

- [ ] **Step 10: Commit et**

```powershell
git add src/scraper/banks src/scraper/registry.py tests/test_all_bank_integration.py tests/fixtures/banks
git commit -m "feat: cover all BDDK participation banks"
```

### Task 5: Banka ve alan bazlı kalite raporu

**Files:**
- Modify: `src/scraper/validation.py`
- Modify: `tests/test_validation.py`

- [ ] **Step 1: Kapsam ve doluluk metriği testini yaz**

```python
def test_quality_report_contains_bank_and_prd_field_coverage():
    processed = [
        {"bank_slug": "a", "structured": {"profit_share_rate": 0.02}},
        {"bank_slug": "b", "structured": {"profit_share_rate": None}},
    ]
    metrics = build_processed_coverage(processed, expected_banks=["a", "b", "c"])
    assert metrics["bank_coverage"] == {
        "expected": 3, "represented": 2, "missing": ["c"], "ratio": 0.6667
    }
    assert metrics["field_fill_rates"]["profit_share_rate"] == 0.5
```

- [ ] **Step 2: Testi çalıştır ve fonksiyon olmadığı için FAIL olduğunu doğrula**

Run: `..\..\.venv\Scripts\python.exe -m pytest tests/test_validation.py::test_quality_report_contains_bank_and_prd_field_coverage -q`

- [ ] **Step 3: `build_processed_coverage` fonksiyonunu uygula**

Fonksiyon sabit PRD alan listesini kullanacak, kayıt sayısı sıfırken oranları `0.0` döndürecek ve banka başına `record_count`, `campaign_count`, `product_count` üretecek.

- [ ] **Step 4: Sıfır kayıt ve eksik banka testlerini ekle**

```python
def test_processed_coverage_handles_empty_dataset():
    metrics = build_processed_coverage([], expected_banks=["a"])
    assert metrics["bank_coverage"]["missing"] == ["a"]
    assert all(rate == 0.0 for rate in metrics["field_fill_rates"].values())
```

- [ ] **Step 5: Task testlerini çalıştır ve commit et**

Run: `..\..\.venv\Scripts\python.exe -m pytest tests/test_validation.py -q`

```powershell
git add src/scraper/validation.py tests/test_validation.py
git commit -m "feat: report bank and PRD field coverage"
```

### Task 6: BDDK güdümlü uçtan uca `collect` komutu

**Files:**
- Modify: `src/scraper/scraper.py`
- Modify: `tests/test_scraper_cli.py`

- [ ] **Step 1: Tam orkestrasyon için başarısız CLI testini yaz**

```python
def test_collect_uses_bddk_catalog_and_writes_all_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(scraper, "fetch_participation_banks", fake_catalog)
    monkeypatch.setattr(scraper, "SCRAPERS", fake_complete_registry())
    args = collect_args(tmp_path)
    assert run_collect(args) == 0
    assert json_load(args.banks_output)["count"] == 2
    assert json_load(args.raw_output)["record_count"] == 2
    assert json_load(args.processed_output)["record_count"] == 2
    quality = json_load(args.quality_report)
    assert quality["coverage"]["complete"] is True
    assert quality["processed_coverage"]["bank_coverage"]["ratio"] == 1.0
```

- [ ] **Step 2: Eksik registry'nin sessizce atlanmadığını test et**

```python
def test_collect_reports_unsupported_bddk_bank_and_returns_partial_status(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        scraper,
        "fetch_participation_banks",
        lambda client: {
            "source_url": BDDK_BANKS_URL,
            "count": 2,
            "banks": [{"slug": "working"}, {"slug": "missing-bank"}],
        },
    )
    monkeypatch.setattr(scraper, "SCRAPERS", {"working": WorkingScraper})
    args = collect_args(tmp_path)
    assert run_collect(args) == 2
    report = json_load(args.quality_report)
    assert report["coverage"]["unsupported"] == ["missing-bank"]
```

- [ ] **Step 3: Testleri çalıştır ve `run_collect` olmadığı için FAIL olduğunu doğrula**

Run: `..\..\.venv\Scripts\python.exe -m pytest tests/test_scraper_cli.py -q`

- [ ] **Step 4: `run_collect` orkestrasyonunu uygula**

Akış:

```python
catalog = fetch_participation_banks(client)
coverage = build_coverage_report(catalog["banks"], SCRAPERS)
selected_slugs = [bank["slug"] for bank in catalog["banks"] if bank["slug"] in SCRAPERS]
records, failures = scrape_selected_banks(selected_slugs, client, args.max_per_bank)
valid_records, duplicates, issues = select_valid_campaigns(records)
raw = campaign_dataset(valid_records)
processed = preprocess_dataset(raw)
quality = build_quality_report(
    records,
    failures,
    duplicates,
    record_issues=issues,
    persisted_records=valid_records,
)
quality["coverage"] = coverage
quality["processed_coverage"] = build_processed_coverage(
    processed["records"], expected_banks=[bank["slug"] for bank in catalog["banks"]]
)
```

Tüm payload'lar bellekte başarılı oluşturulduktan sonra ayrı yollar atomik `write_json` ile yazılacak. Çıktı yollarından herhangi ikisinin aynı olması çalıştırmadan önce `ValueError` üretecek.

- [ ] **Step 5: Parser'a `collect` alt komutunu ekle**

Varsayılanlar:

```text
--banks-output data/raw/participation_banks.json
--raw-output data/raw/campaigns.json
--processed-output data/processed/campaigns.json
--quality-report outputs/quality_report.json
--max-per-bank 20
```

- [ ] **Step 6: Kısmi başarının çıkış kodlarını test et**

Çıkış `0`: kapsam tam, en az bir kayıt, doğrulama hatası/fetch failure yok. Çıkış `2`: unsupported/stale banka, sıfır kayıtlı banka, fetch failure veya doğrulama hatası var. Beklenmeyen programlama hataları bastırılmayacak.

- [ ] **Step 7: CLI testlerini ve regresyonu çalıştır**

Run: `..\..\.venv\Scripts\python.exe -m pytest tests/test_scraper_cli.py -q`

Expected: PASS.

- [ ] **Step 8: Commit et**

```powershell
git add src/scraper/scraper.py tests/test_scraper_cli.py
git commit -m "feat: add BDDK-driven collection pipeline"
```

### Task 7: Dokümantasyon, tam regresyon ve canlı doğrulama

**Files:**
- Modify: `README.md`
- Modify: `data/README.md`
- Modify: `docs/week-1-data-engineering.md`
- Generated and ignored: `outputs/live_*.json`

- [ ] **Step 1: Dokümantasyonu güncelle**

Belgelerde `/Kurulus/Liste/77`, 10 banka, ürün/kampanya ayrımı, `structured` alanları, çıkış kodları ve aşağıdaki gerçek komut yer alacak:

```powershell
python -m src.scraper.scraper --verbose collect `
  --max-per-bank 3 `
  --banks-output outputs/live_banks.json `
  --raw-output outputs/live_raw.json `
  --processed-output outputs/live_processed.json `
  --quality-report outputs/live_quality.json
```

- [ ] **Step 2: Tüm test paketini çalıştır**

Run: `..\..\.venv\Scripts\python.exe -m pytest -q`

Expected: mevcut 104 test dahil tüm testler PASS.

- [ ] **Step 3: Lint çalıştır**

Run: `..\..\.venv\Scripts\python.exe -m flake8 src tests`

Expected: çıkış kodu 0.

- [ ] **Step 4: Düşük limitli gerçek uçtan uca smoke testi çalıştır**

Run: yukarıdaki `collect --max-per-bank 3` komutu.

Expected: BDDK katalog sayısı 10; dört JSON çıktı mevcut; her banka kalite raporunda görünür; kamuya açık kayıt üretemeyen banka açık durum/hata ile raporlanır; sahte kayıt yoktur.

- [ ] **Step 5: Canlı çıktıların iç tutarlılığını kontrol et**

```powershell
@'
import json
from pathlib import Path
banks=json.loads(Path("outputs/live_banks.json").read_text(encoding="utf-8"))
raw=json.loads(Path("outputs/live_raw.json").read_text(encoding="utf-8"))
processed=json.loads(Path("outputs/live_processed.json").read_text(encoding="utf-8"))
quality=json.loads(Path("outputs/live_quality.json").read_text(encoding="utf-8"))
assert banks["count"] == 10
assert raw["record_count"] == processed["record_count"]
assert quality["coverage"]["catalog_count"] == 10
assert {r["bank_slug"] for r in raw["records"]} <= {b["slug"] for b in banks["banks"]}
print(raw["record_count"], quality["processed_coverage"])
'@ | ..\..\.venv\Scripts\python.exe -
```

- [ ] **Step 6: Dokümantasyon ve son düzeltmeleri commit et**

```powershell
git add README.md data/README.md docs/week-1-data-engineering.md
git commit -m "docs: document complete BDDK data collection"
```

- [ ] **Step 7: Feature branch'in temiz ve main'e göre farkını doğrula**

```powershell
git status --short
git log --oneline main..HEAD
git diff --check main...HEAD
```

Expected: temiz worktree, yalnızca feature commit'leri, diff-check hatası yok.

- [ ] **Step 8: Branch'i push et ve PR aç**

```powershell
git push -u origin feature/bddk-prd-data-pipeline
gh pr create --base main --head feature/bddk-prd-data-pipeline `
  --title "feat: complete BDDK PRD data pipeline" `
  --body-file .github/pull_request_template.md
```

Repo'da PR şablonu yoksa doğrulama sonuçlarını, canlı banka/kayıt sayılarını, bilinen kaynak kısıtlarını ve `Closes` kullanılmadan kapsam özetini içeren geçici body dosyası oluşturulacak. PR merge edilmeyecek; kullanıcı incelemesine bırakılacak.
