# PDF Kaynak Paketi ve Ontoloji Zenginleştirme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kullanıcının sağladığı beş PDF’ten sayfa-kaynaklı, denetlenebilir RAG kanıt parçaları üretmek ve bunları katılım bankacılığı ontolojisi/ilişki grafiğiyle bağlamak.

**Architecture:** PDF’ler repoya kopyalanmayacak; sabit kaynak manifestosu PDF hash’i ve dosya yolu ile tutulacak. Çıkarıcı `pdfplumber` ile sayfa numarasını koruyarak başlık/paragraf bloklarını kanıt paketine dönüştürecek. Yalnızca seçilmiş katılım finansı konuları (fon havuzu, kâr dağıtımı, katılma hesabı, muhasebe, ürün süreçleri) RAG’e alınacak; her parça `source_id`, `page`, `quote`, `source_url/local_path`, `topic` ve `confidence` alanları taşıyacak.

**Tech Stack:** Python 3.11, pdfplumber/pypdf, JSONL, mevcut `terminology_documents`, Chroma/Qdrant indexers, pytest.

---

### Task 1: PDF kaynak manifestosu ve güvenli çıkarım sözleşmesi

**Files:**
- Create: `data/source_documents/pdf_sources.json`
- Create: `src/ingestion/pdf_sources.py`
- Test: `tests/test_pdf_sources.py`

- [ ] **Step 1: Write the failing test**

```python
def test_pdf_source_manifest_requires_hash_page_and_source_kind(tmp_path):
    manifest = build_pdf_manifest([tmp_path / "a.pdf"])
    assert manifest[0]["sha256"]
    assert manifest[0]["page_count"] >= 0
    assert manifest[0]["source_kind"] == "user_supplied_pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pdf_sources.py::test_pdf_source_manifest_requires_hash_page_and_source_kind -q`
Expected: FAIL because `src.ingestion.pdf_sources` does not exist.

- [ ] **Step 3: Implement manifest builder**

`build_pdf_manifest(paths)` computes SHA-256, PDF page count, original filename, absolute path, extraction timestamp, and `source_kind`; reject missing/non-PDF paths with a typed error.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pdf_sources.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ingestion/pdf_sources.py data/source_documents/pdf_sources.json tests/test_pdf_sources.py
git commit -m "feat: add hashed pdf source manifest"
```

### Task 2: Sayfa-kaynaklı PDF kanıt çıkarıcı

**Files:**
- Create: `src/ingestion/pdf_evidence.py`
- Create: `scripts/extract_pdf_evidence.py`
- Test: `tests/test_pdf_evidence.py`

- [ ] **Step 1: Write the failing test**

```python
def test_extract_evidence_preserves_page_and_never_emits_empty_quote(fake_pdf):
    rows = extract_pdf_evidence(fake_pdf, topics={"fon havuzu"})
    assert rows
    assert all(row["page"] >= 1 and row["quote"].strip() for row in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pdf_evidence.py::test_extract_evidence_preserves_page_and_never_emits_empty_quote -q`
Expected: FAIL because extractor is not implemented.

- [ ] **Step 3: Implement extraction and filtering**

Extract page text with `pdfplumber`, normalize whitespace, split bounded paragraphs, retain only paragraphs matching configured topic terms or nearby headings, cap each quote at 1200 characters, and attach `document_id`, `page`, `topic`, `quote_hash`, `local_path`, and `source_url` (blank for local-only PDFs). Do not infer facts or rewrite source text.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pdf_evidence.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ingestion/pdf_evidence.py scripts/extract_pdf_evidence.py tests/test_pdf_evidence.py
git commit -m "feat: extract page-level pdf evidence"
```

### Task 3: Kaynak paketini RAG sözleşmesine bağlama

**Files:**
- Create: `data/source_documents/pdf_evidence.jsonl`
- Modify: `src/retrieval/documents.py`
- Modify: `data/ontology/rag_chunks.jsonl`
- Test: `tests/test_pdf_rag_contract.py`

- [ ] **Step 1: Write the failing test**

```python
def test_pdf_rag_document_has_provenance_and_bounded_text():
    docs = pdf_evidence_documents(Path("data/source_documents/pdf_evidence.jsonl"))
    assert docs
    assert all(d[2]["source_type"] == "pdf_evidence" for d in docs)
    assert all(d[2]["page"] >= 1 for d in docs)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pdf_rag_contract.py -q`
Expected: FAIL because PDF documents are not part of the retrieval corpus.

- [ ] **Step 3: Implement corpus adapter**

Add `pdf_evidence_documents()` with deterministic IDs `pdf:{document_id}:{page}:{quote_hash}` and include PDF evidence in `HybridRetriever._load_corpus()` without changing campaign/terminology IDs. Add only source-backed summaries to `rag_chunks.jsonl` when a stable ontology term needs an enriched definition.

- [ ] **Step 4: Generate the evidence package**

Run:
`python -m scripts.extract_pdf_evidence --manifest data/source_documents/pdf_sources.json --output data/source_documents/pdf_evidence.jsonl`

Expected: JSONL rows with page numbers, hashes, topic labels, and no empty quotes.

- [ ] **Step 5: Run tests and commit**

Run: `pytest tests/test_pdf_rag_contract.py tests/test_hybrid_retrieval.py -q`

```bash
git add src/retrieval/documents.py data/source_documents/pdf_evidence.jsonl data/ontology/rag_chunks.jsonl tests/test_pdf_rag_contract.py
git commit -m "feat: add pdf evidence to rag corpus"
```

### Task 4: Ontoloji ve ilişki grafiği eşleme

**Files:**
- Modify: `data/ontology/alias_dictionary.json`
- Modify: `data/ontology/relation_graph.json`
- Modify: `configs/query_rules.json`
- Test: `tests/test_pdf_ontology_mapping.py`

- [ ] **Step 1: Write the failing test**

```python
def test_pdf_topics_map_to_existing_finance_terms():
    mapping = build_pdf_topic_mapping()
    assert mapping["fon_havuzu"] == "TRM0452"
    assert mapping["kar_paylasim_orani"] == "TRM0454"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pdf_ontology_mapping.py -q`
Expected: FAIL for missing mapping helper or missing terms.

- [ ] **Step 3: Implement mappings without replacing existing IDs**

Add aliases and edges only for concepts supported by extracted PDF evidence: `Fon Havuzu`, `Katılma Hesabı`, `Kâr Paylaşım Oranı`, `Kâr Payı Dağıtımı`, `Günlük Kâr Dağıtımı`, `Murabaha`, `İcâre`, `Müşareke`, `Mudârebe`, `Birim Değer`, and `Zorunlu Karşılık`. Keep uncertain concepts as unmapped evidence topics rather than inventing ontology IDs.

- [ ] **Step 4: Run tests and commit**

Run: `pytest tests/test_pdf_ontology_mapping.py tests/test_knowledge_terminology.py tests/test_graph_retrieval.py -q`

```bash
git add data/ontology/alias_dictionary.json data/ontology/relation_graph.json configs/query_rules.json tests/test_pdf_ontology_mapping.py
git commit -m "feat: map pdf finance concepts into ontology"
```

### Task 5: İndeksleme, kalite raporu ve canlı doğrulama

**Files:**
- Modify: `scripts/ingest_chroma.py`
- Create: `docs/source-packets/pdf-kaynak-paketi.md`
- Test: `tests/test_pdf_indexing_smoke.py`

- [ ] **Step 1: Add indexing smoke test**

Assert that a changed PDF evidence hash causes exactly that evidence row to re-embed, while unchanged campaign and terminology rows remain unchanged.

- [ ] **Step 2: Run smoke test to verify it fails**

Run: `pytest tests/test_pdf_indexing_smoke.py -q`
Expected: FAIL until the indexer reads PDF evidence rows.

- [ ] **Step 3: Extend indexer and document provenance policy**

Include PDF evidence in both local Chroma and EVREN Qdrant index builds; preserve `document_id`, `page`, `quote_hash`, `source_url`, and `source_type`. Never delete user-provided PDFs; if a source file changes, mark the old evidence stale through hash comparison.

- [ ] **Step 4: Ingest and verify**

Run the indexer with `.env` loaded, then query:
`Katılım bankacılığında kâr payı havuzu nasıl işler?`

Verify the response cites a PDF page-backed source and does not emit unsupported hypothetical amounts or guaranteed returns.

- [ ] **Step 5: Run full verification and commit**

Run:
`pytest -q`
`python -m scripts.ingest_chroma --batch-size 16 --require-evren`

```bash
git add scripts/ingest_chroma.py docs/source-packets/pdf-kaynak-paketi.md tests/test_pdf_indexing_smoke.py
git commit -m "feat: index and document pdf source packet"
```
