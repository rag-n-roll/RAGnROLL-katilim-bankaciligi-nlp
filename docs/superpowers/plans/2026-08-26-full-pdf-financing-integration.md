# Tam PDF RAG ve Finansman Entegrasyonu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Beş PDF'in tamamını doğrulanmış sayfa/paragraf parçalarıyla embedding indekslerine yüklemek ve `ui_son` finansman modülünü chatbot ile `/compare` sayfasının kullandığı tek bir kaynaklı teklif servisi olarak entegre etmek.

**Architecture:** PDF hattı, SHA-256 kayıt defteriyle fail-closed doğrulanan tam sayfa çıkarımı ve deterministik semantik parçalama üretir; aynı belge kimlikleri Chroma ve EVREN/Qdrant'a artımlı yüklenir. Finansman hattı, `ui_son/src/financing` içindeki resmî banka adaptörlerini mevcut FastAPI servisine port eder; API, chatbot tool executor ve Next.js `/compare` sayfası aynı `FinancingQuote` çıktısını kullanır.

**Tech Stack:** Python 3.11, FastAPI, Pydantic 2, PyMuPDF/pypdf, Qdrant BGE-M3, Chroma, pytest, Next.js 16, React 19, Node test runner.

---

## Dosya yapısı

- `data/source_documents/pdf_source_registry.json`: resmî metadata ve beklenen PDF SHA-256 değerleri.
- `data/source_documents/pdf_extraction_report.json`: belge/sayfa/parça kapsam raporu.
- `data/source_documents/pdf_evidence.jsonl`: doğrulanmış, kararlı tam PDF parçaları.
- `src/ingestion/pdf_registry.py`: kayıt defteri ve kaynak hash doğrulaması.
- `src/ingestion/pdf_evidence.py`: sayfa çıkarımı, temizleme, parçalama ve rapor üretimi.
- `scripts/extract_pdf_evidence.py`: tam çıkarım CLI'ı.
- `src/retrieval/documents.py`: fail-closed PDF JSONL loader.
- `src/services/assistant.py`: PDF kaynak filtresi ve finansman tool execution.
- `src/financing/calculator.py`: normalize teklif ve türetilmiş ödeme hesabı.
- `src/financing/official_sources.py`: allowlist resmî banka adaptörleri.
- `src/api/schemas.py`, `src/api/main.py`: finansman ürün/teklif API'si.
- `src/policy/tool_policy.py`, `src/llm/decisions.py`: `financing_quote` araç politikası.
- `src/dashboard/services/api.ts`: finansman API istemcisi ve tipleri.
- `src/dashboard/app/compare/page.tsx`: gerçek teklif tabanlı karşılaştırma ekranı.
- `src/dashboard/app/compare/page.module.css`: mevcut marka sistemiyle yeni input/durum düzeni.

### Task 1: PDF kayıt defteri ve fail-closed kaynak doğrulaması

**Files:**
- Create: `src/ingestion/pdf_registry.py`
- Create: `data/source_documents/pdf_source_registry.json`
- Modify: `src/ingestion/pdf_sources.py`
- Test: `tests/test_pdf_registry.py`

- [ ] **Step 1: Beklenen hash ve yerel yol gizliliği testini yaz**

```python
def test_registry_accepts_only_expected_pdf_hash(tmp_path):
    source = tmp_path / "guide.pdf"
    source.write_bytes(b"verified")
    registry = PdfSourceRegistry.from_items([{
        "document_id": "guide",
        "filenames": ["guide.pdf"],
        "sha256": sha256(b"verified").hexdigest(),
        "title": "Guide",
        "source_url": "https://example.test/guide.pdf",
    }])
    verified = registry.verify(source)
    assert verified.document_id == "guide"
    source.write_bytes(b"tampered")
    with pytest.raises(PdfSourceIntegrityError):
        registry.verify(source)

def test_manifest_does_not_serialize_local_path(verified_source):
    assert "local_path" not in build_pdf_manifest([verified_source])[0]
    assert "C:\\Users" not in json.dumps(build_pdf_manifest([verified_source]))
```

- [ ] **Step 2: Testlerin doğru nedenle kırmızı olduğunu doğrula**

Run: `pytest -q tests/test_pdf_registry.py`

Expected: `ModuleNotFoundError: src.ingestion.pdf_registry`.

- [ ] **Step 3: Kayıt defteri modelini ve hash kontrolünü uygula**

```python
@dataclass(frozen=True)
class VerifiedPdfSource:
    document_id: str
    title: str
    sha256: str
    source_url: str
    publisher: str
    path: Path = field(repr=False)

class PdfSourceRegistry:
    def verify(self, path: Path) -> VerifiedPdfSource:
        actual = file_sha256(path)
        item = self._by_filename.get(unicodedata.normalize("NFC", path.name))
        if item is None or not hmac.compare_digest(actual, item["sha256"]):
            raise PdfSourceIntegrityError(f"PDF kaynağı doğrulanamadı: {path.name}")
        return VerifiedPdfSource(path=path, **public_fields(item))
```

Registry beş mevcut PDF'nin daha önce hesaplanmış SHA-256 değerlerini ve resmî TKBB URL'lerini içerir. Manifest yalnız `document_id`, `filename`, `sha256`, `page_count`, `title`, `publisher`, `source_url` ve `extracted_at` alanlarını yazar.

- [ ] **Step 4: Testi yeşile getir ve commit et**

Run: `pytest -q tests/test_pdf_registry.py tests/test_pdf_sources.py`

Expected: PASS.

```bash
git add src/ingestion/pdf_registry.py src/ingestion/pdf_sources.py data/source_documents/pdf_source_registry.json tests/test_pdf_registry.py
git commit -m "feat: verify PDF sources against immutable registry"
```

### Task 2: Deterministik tam sayfa/paragraf çıkarımı

**Files:**
- Modify: `src/ingestion/pdf_evidence.py`
- Modify: `scripts/extract_pdf_evidence.py`
- Test: `tests/test_pdf_evidence_extraction.py`

- [ ] **Step 1: Gerçek küçük PDF fixture'ı ile kırmızı testleri yaz**

```python
def test_chunk_contains_matching_topic_context(sample_pdf, verified_source):
    result = extract_pdf_document(verified_source, extractor=FakeExtractor([
        "Üst başlık\nKâr payı havuzu katılma hesaplarından oluşur.\nAlt bilgi"
    ]))
    chunk = next(item for item in result.chunks if "fon_havuzu" in item["topics"])
    assert "kâr payı havuzu" in chunk["text"].casefold()

def test_extraction_is_deterministic(sample_pdf, verified_source):
    first = extract_pdf_document(verified_source, extractor=fixture_extractor)
    second = extract_pdf_document(verified_source, extractor=fixture_extractor)
    assert [item["chunk_id"] for item in first.chunks] == [item["chunk_id"] for item in second.chunks]

def test_every_page_is_accounted_for(verified_source):
    result = extract_pdf_document(verified_source, extractor=FakeExtractor(["a", "", RuntimeError("bad")]))
    assert result.report["page_count"] == 3
    assert result.report["attempted"] == 3
    assert result.report["extracted"] == 1
    assert result.report["empty"] == 1
    assert result.report["failed"] == 1
```

- [ ] **Step 2: Testlerin mevcut `text[:1200]` davranışında kırmızı olduğunu doğrula**

Run: `pytest -q tests/test_pdf_evidence_extraction.py`

Expected: deterministic/topic context/report assertions FAIL.

- [ ] **Step 3: Sayfa izolasyonu, gürültü temizleme ve semantic chunker uygula**

```python
def extract_pdf_document(source, *, extractor, max_tokens=450, overlap_tokens=50):
    pages, failures = extractor.extract_all(source.path)
    repeated = repeated_margin_lines(pages)
    chunks = []
    for page in pages:
        cleaned = clean_page(page.text, repeated_lines=repeated)
        if is_table_of_contents(cleaned):
            continue
        for text in semantic_windows(cleaned, max_tokens=max_tokens, overlap_tokens=overlap_tokens):
            normalized = normalize_text(text)
            digest = sha256(normalized.encode("utf-8")).hexdigest()
            chunks.append({
                "chunk_id": stable_chunk_id(source.sha256, page.number, page.number, normalized),
                "document_id": source.document_id,
                "page_start": page.number,
                "page_end": page.number,
                "text": normalized,
                "quote_hash": digest,
                "topics": detect_topics(normalized),
                "title": source.title,
                "publisher": source.publisher,
                "source_url": source.source_url,
            })
    report = coverage_report(
        document_id=source.document_id,
        page_count=len(pages),
        chunks=chunks,
        failures=failures,
    )
    return PdfExtractionResult(chunks=chunks, report=report)
```

Topic sabit tuple sırasıyla taranır; `set` kullanılmaz. `max_pages` CLI seçeneği yalnız açık kullanıcı override'ıdır, varsayılan `None` tam belgedir.

- [ ] **Step 4: Testleri yeşile getir ve commit et**

Run: `pytest -q tests/test_pdf_evidence_extraction.py tests/test_pdf_sources.py`

Expected: PASS.

```bash
git add src/ingestion/pdf_evidence.py scripts/extract_pdf_evidence.py tests/test_pdf_evidence_extraction.py
git commit -m "feat: extract deterministic full-page PDF evidence"
```

### Task 3: Beş PDF'nin tamamını çıkar ve kapsamı doğrula

**Files:**
- Regenerate: `data/source_documents/pdf_evidence.jsonl`
- Regenerate: `data/source_documents/pdf_evidence.manifest.json`
- Create: `data/source_documents/pdf_extraction_report.json`
- Modify: `data/source_documents/README.md`

- [ ] **Step 1: Tam çıkarım komutunu çalıştır**

Run:

```powershell
.\.venv311\Scripts\python.exe scripts\extract_pdf_evidence.py `
  --registry data\source_documents\pdf_source_registry.json `
  --pdf "C:\Users\kuti\Documents\FAIZSIZ-FINANS-KURULUSLARI-MUHASEBESI.pdf" `
  --pdf "C:\Users\kuti\Documents\Faizsiz Finans Standartları AAOIFI (Güncellenmiş Versiyon).pdf" `
  --pdf "C:\Users\kuti\Documents\Katilim_Finans_Urunleri_ve_Muhasebe_Surecleri_2.pdf" `
  --pdf "C:\Users\kuti\Documents\8803561630-2025-faaliyet-raporu.pdf" `
  --pdf "C:\Users\kuti\Documents\KATILIM_BANKACILIGINDA_KAR_DAGITIMI.pdf" `
  --output data\source_documents\pdf_evidence.jsonl `
  --report data\source_documents\pdf_extraction_report.json
```

Expected: five document summaries; `attempted == page_count` for every document.

- [ ] **Step 2: Kapsam denetleyicisini çalıştır**

Run:

```powershell
.\.venv311\Scripts\python.exe scripts\verify_pdf_evidence.py `
  --registry data\source_documents\pdf_source_registry.json `
  --manifest data\source_documents\pdf_evidence.manifest.json `
  --evidence data\source_documents\pdf_evidence.jsonl `
  --report data\source_documents\pdf_extraction_report.json
```

Expected: exit 0, no local absolute paths, all chunk hashes valid, all pages accounted for. Hatalı/görsel sayfalar varsa sayıları raporda açık kalır; sessiz kayıp kabul edilmez.

- [ ] **Step 3: Üretilen paketi commit et**

```bash
git add data/source_documents scripts/verify_pdf_evidence.py
git commit -m "data: build verified full PDF evidence packet"
```

### Task 4: Fail-closed PDF loader ve chatbot retrieval yolu

**Files:**
- Modify: `src/retrieval/documents.py`
- Modify: `src/retrieval/hybrid.py`
- Modify: `src/retrieval/chroma.py`
- Modify: `src/retrieval/qdrant.py`
- Modify: `src/services/assistant.py`
- Test: `tests/test_pdf_sources.py`
- Test: `tests/test_llm_assistant.py`

- [ ] **Step 1: Bozuk hash ve definition API testlerini kırmızı yaz**

```python
def test_pdf_loader_rejects_tampered_quote(tmp_path):
    evidence = write_evidence(tmp_path, text="değiştirilmiş", quote_hash="wrong")
    with pytest.raises(PdfEvidenceIntegrityError):
        pdf_evidence_documents(evidence, manifest_path=write_manifest(tmp_path))

def test_definition_query_can_use_pdf_evidence(assistant, monkeypatch):
    captured = {}
    monkeypatch.setattr(assistant.retriever, "retrieve", lambda query, **kwargs: captured.update(kwargs) or [pdf_row()])
    result = assistant.answer("Kâr payı havuzu nasıl işler?")
    assert captured["filters"]["source_types"] == ["terminology", "pdf_evidence"]
    assert result["sources"][0]["page_start"] == 42
```

- [ ] **Step 2: Testlerin kırmızı olduğunu doğrula**

Run: `pytest -q tests/test_pdf_sources.py tests/test_llm_assistant.py -k "pdf or definition"`

Expected: tamper accepted / source filter mismatch failures.

- [ ] **Step 3: Loader doğrulamasını ve source filter'ı uygula**

`pdf_evidence_documents()` her satırda metin hash'ini yeniden hesaplar, belge hash'ini manifest registry ile eşleştirir ve metadata'ya `page_start/page_end` ekler. `AssistantService._hybrid_answer()` definition/relationship ve bilgi intentlerinde:

```python
filters["source_types"] = ["terminology", "pdf_evidence"]
```

kullanır; kampanya intentlerinde `campaign` filtresi korunur.

- [ ] **Step 4: Testleri yeşile getir ve commit et**

Run: `pytest -q tests/test_pdf_sources.py tests/test_hybrid_retrieval.py tests/test_llm_assistant.py`

Expected: PASS.

```bash
git add src/retrieval src/services/assistant.py tests/test_pdf_sources.py tests/test_llm_assistant.py
git commit -m "fix: serve verified PDF evidence through assistant retrieval"
```

### Task 5: EVREN/Qdrant ve Chroma tam indeksleme

**Files:**
- Modify: `scripts/ingest_chroma.py`
- Test: `tests/test_chroma_retrieval.py`
- Test: `tests/test_evren_provider.py`

- [ ] **Step 1: İndeks raporunda PDF sayaç testini kırmızı yaz**

```python
assert build_result["source_counts"]["pdf_evidence"] == len(pdf_documents)
assert second_build["embedded"] == 0
assert second_build["unchanged"] == first_build["total"]
```

- [ ] **Step 2: Testi kırmızı doğrula, sayaçları uygula, yeşile getir**

Run: `pytest -q tests/test_chroma_retrieval.py tests/test_evren_provider.py`

Expected before implementation: missing `source_counts`; after implementation: PASS.

- [ ] **Step 3: Yerel smoke ve EVREN indeksini çalıştır**

Run:

```powershell
.\.venv311\Scripts\python.exe -m scripts.ingest_chroma --smoke --batch-size 16
.\.venv311\Scripts\python.exe -m scripts.ingest_chroma --batch-size 16 --require-evren
```

Expected: PDF parça sayısı her iki raporda aynı, EVREN `status=success`, ikinci çalışma yalnız değişen parçaları embed eder.

- [ ] **Step 4: Commit et**

```bash
git add scripts/ingest_chroma.py tests/test_chroma_retrieval.py tests/test_evren_provider.py
git commit -m "feat: report and index full PDF corpus incrementally"
```

### Task 6: Finansman domain modülünü test-first port et

**Files:**
- Create: `src/financing/__init__.py`
- Create: `src/financing/calculator.py`
- Create: `src/financing/official_sources.py`
- Create: `tests/test_financing_calculator.py`
- Source reference: `C:\Users\kuti\Desktop\ui_son\src\financing\*.py`
- Source tests: `C:\Users\kuti\Desktop\ui_son\tests\test_financing_calculator.py`

- [ ] **Step 1: Dış modülün hesaplayıcı/adaptör testlerini mevcut test paketine taşı**

Testler en az şunları kapsar: eşit taksit hesabı, on banka görünürlüğü, resmî kaynak zorunluluğu, ürün limitleri, canlı adaptör parse sonuçları, kısmi hata ve son doğrulanmış kaynak fallback'i.

- [ ] **Step 2: Testlerin import hatasıyla kırmızı olduğunu doğrula**

Run: `pytest -q tests/test_financing_calculator.py`

Expected: `ModuleNotFoundError: src.financing`.

- [ ] **Step 3: İncelenen domain dosyalarını mevcut bağımlılık sınırına port et**

`calculator.py` ve `official_sources.py` public API'si şu şekilde korunur:

```python
build_financing_quotes(
    *, records, banks, financing_type, amount, term_months,
    official_quotes=None, eligible_bank_slugs=None, now=None
) -> dict[str, Any]
financing_campaign_catalog(
    *, amount=None, term_months=None
) -> list[dict[str, Any]]
fetch_official_quotes(
    *, financing_type, amount, term_months,
    eligible_bank_slugs=None, selected_product_ids=None
) -> dict[str, dict[str, Any]]
```

Uzak istekler yalnız `CALCULATOR_SOURCES` allowlist alan adlarına yapılır; kullanıcı URL girdisi kabul edilmez. Kaynaksız kayıt `available` olamaz.

- [ ] **Step 4: Testleri yeşile getir ve commit et**

Run: `pytest -q tests/test_financing_calculator.py`

Expected: port edilen testlerin tümü PASS.

```bash
git add src/financing tests/test_financing_calculator.py
git commit -m "feat: port sourced participation financing quote engine"
```

### Task 7: Finansman API sözleşmesi

**Files:**
- Modify: `src/api/schemas.py`
- Modify: `src/api/main.py`
- Modify: `tests/test_api.py`

- [ ] **Step 1: Ürün kataloğu ve teklif endpoint testlerini kırmızı yaz**

```python
def test_financing_quotes_keeps_catalog_coverage(client, monkeypatch):
    monkeypatch.setattr("src.api.main.fetch_official_quotes", lambda **_: {})
    payload = client.post("/api/v1/financing-quotes", json={
        "financing_type": "consumer", "amount": 50_000, "term_months": 12, "currency": "TRY"
    }).json()
    assert payload["coverage"]["catalog_bank_count"] == 10
    assert len(payload["quotes"]) == 10
    assert all(item["source_url"] for item in payload["quotes"])
```

- [ ] **Step 2: 404 ile kırmızı doğrula**

Run: `pytest -q tests/test_api.py -k financing`

Expected: endpoint 404.

- [ ] **Step 3: Pydantic şemalarını ve endpointleri port et**

`FinancingQuoteRequest`, `FinancingCampaignsResponse`, `FinancingQuoteItem` ve `FinancingQuoteResponse`, incelenen `ui_son/src/api/schemas.py:26-106` sözleşmesiyle eklenir. `src/api/main.py` endpointleri domain servisini çağırır ve adapter exception'larını banka durumuna dönüştürür.

- [ ] **Step 4: Testleri yeşile getir ve commit et**

Run: `pytest -q tests/test_api.py tests/test_financing_calculator.py`

Expected: PASS.

```bash
git add src/api tests/test_api.py
git commit -m "feat: expose sourced financing products and quotes API"
```

### Task 8: Chatbot `financing_quote` araç çağrısı

**Files:**
- Modify: `src/policy/tool_policy.py`
- Modify: `src/llm/decisions.py`
- Modify: `src/services/assistant.py`
- Modify: `src/services/orchestration.py`
- Test: `tests/test_policy_validator.py`
- Test: `tests/test_llm_assistant.py`
- Test: `tests/test_conversation_policy.py`

- [ ] **Step 1: Araç yetkisi, kriter ve answer grounding testlerini kırmızı yaz**

```python
def test_financing_comparison_calls_quote_tool(assistant):
    result = assistant.answer("150.000 TL için 24 ay taşıt finansmanını karşılaştır")
    assert result["generation"]["tool"] == "financing_quote"
    assert result["facts"][0]["amount"] == 150000

def test_quote_tool_rejects_missing_amount_or_term():
    assert not valid_tool_call("product_comparison", {"name": "financing_quote", "arguments": {}})
```

- [ ] **Step 2: Kırmızı sonucu doğrula**

Run: `pytest -q tests/test_policy_validator.py tests/test_llm_assistant.py tests/test_conversation_policy.py -k financing`

Expected: tool not allowed / no execution.

- [ ] **Step 3: Tool policy, planner ve executor'ı uygula**

```python
ALLOWED_TOOLS = frozenset({
    "structured_sql", "hybrid_rag", "comparison", "ontology", "financing_quote"
})
INTENT_TOOLS["product_comparison"] = frozenset({"structured_sql", "comparison", "financing_quote"})
TOOL_ARGUMENTS["financing_quote"] = frozenset({
    "financing_type", "amount", "term_months", "banks", "product_ids", "fee_priority"
})
```

Plan yalnız `amount`, `term_months` ve finansman türü tamamlandığında aracı seçer. Executor `FinancingQuoteService` sonucunu facts/sources paketine çevirir; kaynak URL/zamanı olmayan teklifleri kanıt olarak kabul etmez. Validator karşılaştırmalı iddiaları yalnız seçilen metric ve available tekliflerle yetkilendirir.

- [ ] **Step 4: Testleri yeşile getir ve commit et**

Run: `pytest -q tests/test_policy_validator.py tests/test_llm_assistant.py tests/test_conversation_policy.py`

Expected: PASS.

```bash
git add src/policy src/llm/decisions.py src/services tests/test_policy_validator.py tests/test_llm_assistant.py tests/test_conversation_policy.py
git commit -m "feat: let guarded chatbot compare sourced financing quotes"
```

### Task 9: Frontend API istemcisi

**Files:**
- Modify: `src/dashboard/services/api.ts`
- Modify: `src/dashboard/tests/live-ui.test.mjs`

- [ ] **Step 1: İstemci sözleşmesi testini kırmızı yaz**

```javascript
assert.match(api, /export function getFinancingCampaigns/);
assert.match(api, /export function getFinancingQuotes/);
assert.match(api, /\/financing-quotes/);
```

- [ ] **Step 2: Kırmızı doğrula**

Run: `npm test -- --test-name-pattern="financing api"`

Working directory: `src/dashboard`.

- [ ] **Step 3: TypeScript tiplerini ve istemci fonksiyonlarını ekle**

`FinancingCampaign`, `FinancingQuoteRequest`, `FinancingQuoteItem` ve `FinancingQuoteResponse` backend Pydantic alanlarıyla birebir eşleşir. İstemci `/financing-campaigns` ve `/financing-quotes` endpointlerini çağırır.

- [ ] **Step 4: Testi yeşile getir ve commit et**

```bash
git add src/dashboard/services/api.ts src/dashboard/tests/live-ui.test.mjs
git commit -m "feat: add financing quote dashboard client"
```

### Task 10: `/compare` sayfasını gerçek teklif servisine bağla

**Files:**
- Modify: `src/dashboard/app/compare/page.tsx`
- Modify: `src/dashboard/app/compare/page.module.css`
- Modify: `src/dashboard/tests/live-ui.test.mjs`
- Reference: `C:\Users\kuti\Desktop\ui_son\src\dashboard\app\financing-calculator\page.tsx`

- [ ] **Step 1: Hardcoded veri yasağı ve yeni alan testlerini kırmızı yaz**

```javascript
assert.doesNotMatch(compare, /BANK_RATE_BASE|Fallback calculated rows|Backend offline: compute/);
assert.match(compare, /getFinancingQuotes/);
assert.match(compare, /financingAmount/);
assert.match(compare, /termMonths/);
assert.match(compare, /source_url/);
assert.match(compare, /Doğrulanmış teklif bulunamadı/);
```

- [ ] **Step 2: Mevcut sayfada kırmızı sonucu doğrula**

Run: `npm test -- --test-name-pattern="comparison financing"`

Expected: hardcoded pattern assertions FAIL.

- [ ] **Step 3: UI'ı mevcut tasarım sistemine port et**

Sayfa; mevcut banka picker ve marka bileşenlerini korur, `ui_son` hesaplayıcıdan tutar/vade/ürün akışını alır. `handleCompare()` yalnız `getFinancingQuotes()` kullanır. API hatasında finansal satır üretmez; hata paneli ve yeniden deneme sunar. Grafikler yalnız `status=available` ve sayısal alanı olan tekliflerle çizilir. Tabloda unavailable bankalar mesaj/source link ile korunur.

- [ ] **Step 4: Frontend test/lint/build çalıştır ve commit et**

Run:

```powershell
npm test
npm run lint
npm run build
```

Working directory: `src/dashboard`.

Expected: all PASS.

```bash
git add src/dashboard/app/compare src/dashboard/tests/live-ui.test.mjs
git commit -m "feat: replace mock comparison rates with sourced quotes"
```

### Task 11: Tam regresyon ve canlı sözleşme doğrulaması

**Files:**
- Modify if defects found: tests alongside affected implementation

- [ ] **Step 1: Backend tam test paketini çalıştır**

Run: `.\.venv311\Scripts\python.exe -m pytest -q`

Expected: all tests pass; existing single documented NER alignment warning dışında yeni warning yok.

- [ ] **Step 2: Backend/frontend'i yeniden başlat ve sağlık kontrolü yap**

Backend: `http://127.0.0.1:8000/api/v1/health` returns 200.

Frontend: `http://127.0.0.1:3000/compare` returns 200.

- [ ] **Step 3: Canlı finansman API ve chatbot tutarlılık testi**

`POST /api/v1/financing-quotes` için 50.000 TRY, 12 ay consumer sorgusu çalıştır. Aynı koşulu `/api/v1/chat/stream` üzerinden sor. Chatbot sources/facts içinde aynı banka oran/teklif kimliklerinin bulunduğunu doğrula; kaynak dışı sayı olmamalı.

- [ ] **Step 4: Tarayıcı UI testi**

`/compare` sayfasında ürün, tutar ve vade seç; teklifleri hesapla; available ve unavailable satırların, resmî kaynak bağlantılarının ve bilgilendirme notunun görünür olduğunu doğrula. Mobil viewport'ta yatay tablo erişimini ve input klavye kullanımını kontrol et.

- [ ] **Step 5: PDF kaynaklı canlı cevap testi**

“Katılım bankacılığında kâr payı havuzu nasıl işler?” sorgusunda en az bir `pdf_evidence` kaynağı, belge başlığı ve sayfa numarası dönmelidir. UI kaynak kartı tıklanabilir resmî URL göstermelidir.

### Task 12: Review, PR ve tamamlanma denetimi

**Files:**
- Update: existing PR #39

- [ ] **Step 1: Diff ve gizlilik kontrolü**

Run:

```powershell
git diff --check origin/main...HEAD
rg -n "C:\\Users\\kuti|BANK_RATE_BASE|Fallback calculated rows" data/source_documents src -g '!*.md'
git status --short
```

Expected: no tracked local path, no hardcoded rate fallback, clean worktree except deliberate runtime logs ignored/removed.

- [ ] **Step 2: Code review iste ve Important/Critical bulguları düzelt**

Review PDF integrity, assistant source routing, financial claim grounding, adapter allowlist, partial failures and UI hardcoded-data absence.

- [ ] **Step 3: Final verification tekrarını çalıştır**

Backend pytest, frontend test/lint/build, PDF verifier, Chroma smoke, EVREN index report ve live API/UI checks yeniden çalışır. Her iddia bu son çıktılara dayanır.

- [ ] **Step 4: Branch'i push et ve PR #39'u güncelle**

```bash
git push origin feature/pusula-ai-guardrails
```

PR açıklamasına tam PDF kapsam raporu, embedding sayaçları, finansman endpointleri, chatbot tool testi ve frontend build sonucu eklenir.
