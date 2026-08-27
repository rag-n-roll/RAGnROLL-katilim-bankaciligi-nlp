# RAGnROLL NLP Model Evaluation & Benchmark Report

**Project:** RAGnROLL Katılım Bankacılığı NLP Platform  
**Evaluation Date:** 2026-08-27  
**Catalog Scope:** 10 Participation Banks (BDDK Normative List)  
**Active Campaign Corpus:** 476 Verified Active Records  
**Status:** Production-Ready / Continuous Evaluation  

---

## 1. Executive Summary & Platform Overview

The **RAGnROLL Katılım Bankacılığı NLP Platform** is an end-to-end, high-precision domain-specific conversational intelligence and structured analytics engine engineered for Turkey's participation banking ecosystem. The system unifies automated multi-channel scraping, dynamic AJAX pagination, PDF regulatory evidence extraction, domain-specific NLP classification, Spacy NER tagging, DSPy-optimized LLM reasoning, hybrid vector/keyword retrieval, and strict deterministic guardrails.

### Key Performance Indicators (KPIs) Summary

| Subsystem | Primary Metric | Result | Benchmark Target | Status |
| :--- | :--- | :---: | :---: | :---: |
| **Catalog Coverage** | BDDK Bank Coverage | **10 / 10 (100%)** | 100% | PASS |
| **Active Dataset** | Valid Active Campaigns | **476 records** | > 350 | PASS |
| **Quality Score** | Dataset Error/Warning Rate | **0.00% (1.00 score)** | < 2% | PASS |
| **Field Extraction** | Golden Exact Match | **97.32%** | > 85% | PASS |
| **Multilabel Classifier**| Overall Product Accuracy | **92.86%** | > 90% | PASS |
| **NER Entity Extractor** | Overall F1-Score | **91.94%** | > 88% | PASS |
| **Query Routing** | Golden Route Accuracy | **98.18%** | > 95% | PASS |
| **Prompt Optimization** | DSPy GEPA Calibration | **0.9126 (+17.14%)** | > 0.85 | PASS |
| **RAG Retrieval** | Hybrid Hit@5 / MRR | **96.36% / 0.9145** | > 90% | PASS |
| **Guardrails & Safety** | PII & Injection Block | **100.00%** | 100% | PASS |
| **Leakage Isolation** | Cross-Split Overlap | **0.00 (0 cross)** | 0 | PASS |

---

## 2. PRD Field Extraction Benchmark

Across the complete corpus of **476 active campaigns** harvested across all 10 participation banks, rule-based and regex-grounded heuristic extractors parse, validate, and normalize key structured product dimensions without ungrounded hallucination or default guessing.

### 476 Active Campaigns Fill Rate Analysis

| PRD Field | Fill Rate (%) | Active Count | Extraction Modality & Evidence Contract |
| :--- | :---: | :---: | :--- |
| `product_type` | **94.96%** | 452 / 476 | Deterministic keyword mapping & title classification |
| `campaign_end_date` | **87.82%** | 418 / 476 | Multi-line range collapsing, textual & numeric date parsing |
| `target_audience` | **81.93%** | 390 / 476 | Segment matching (Yeni Müşteri, Emekli, KOBİ, vb.) |
| `campaign_benefit` | **81.72%** | 389 / 476 | Sentence-level reward clause identification |
| `campaign_start_date`| **67.23%** | 320 / 476 | Explicit interval start extraction |
| `installment_count` | **59.45%** | 283 / 476 | Installment regex matching (`aya varan taksit`) |
| `reward_amount` | **29.62%** | 141 / 476 | Monetary reward proximity parsing (TL, Bankkart Lira, ParafPara) |
| `financing_type` | **16.39%** | 78 / 476 | Financing category detection (Konut, Taşıt, İhtiyaç, vb.) |
| `discount_rate` | **12.82%** | 61 / 476 | Percentage discount clause matching |
| `term_months` | **3.78%** | 18 / 476 | Explicit maturity duration normalization |
| `profit_share_rate` | **2.73%** | 13 / 476 | Exact profit share percentage extraction (`%X kâr payı`) |
| `fee_information` | **1.26%** | 6 / 476 | Explicit fee exemption/waiver statements (`masrafsız`) |

*Note: In accordance with our deterministic data contract, missing values are retained as explicit typed missingness (`null`) rather than guessed, preventing hallucinated financial conditions.*

---

## 3. NLP Multilabel Text Classifier Evaluation

The classification pipeline categorizes campaign texts into orthogonal multi-dimensional ontology taxonomies using a stratified, source-family isolated test partition.

### Overall Performance

- **Overall Product Category Accuracy:** `92.86%`
- **Global Macro F1:** `0.8942`
- **Global Micro F1:** `0.9318`

### Per-Dimension Multilabel Evaluation

| Classification Dimension | Micro F1 | Macro F1 | Subset Accuracy | Top Classes Represented |
| :--- | :---: | :---: | :---: | :--- |
| **Product Category (`product_category`)** | 0.9412 | 0.9125 | 92.86% | `card`, `financing`, `investment`, `digital` |
| **Campaign Benefits (`benefits`)** | 0.9230 | 0.8845 | 89.29% | `reward_points`, `zero_profit`, `fee_waiver` |
| **Mechanics (`campaign_mechanics`)** | 0.9385 | 0.9012 | 91.07% | `installment`, `cashback`, `discount` |
| **Application Channels (`channels`)** | 0.9520 | 0.9260 | 94.64% | `mobile`, `branch`, `internet_banking` |
| **Requirements (`requirements`)** | 0.8974 | 0.8520 | 85.71% | `min_spend`, `new_to_bank`, `direct_debit` |
| **Target Segments (`target_segments`)** | 0.9180 | 0.8890 | 88.39% | `new_customer`, `sme`, `retiree`, `student` |

---

## 4. Named Entity Recognition (NER) Model Evaluation

The domain-specific Turkish Spacy NER model extracts fine-grained commercial banking and campaign entities from unstructured promotional texts.

### Global NER Metrics

- **Overall Strict Precision:** `92.38%`
- **Overall Strict Recall:** `91.50%`
- **Overall Strict F1-Score:** `91.94%`

### Per-Entity Breakdown

| Entity Label | Precision (%) | Recall (%) | F1-Score (%) | Support |
| :--- | :---: | :---: | :---: | :---: |
| `BANKA` | 98.20% | 97.50% | **97.85%** | 240 |
| `KAR_PAYI_ORANI` | 95.80% | 94.20% | **95.00%** | 95 |
| `TAKSIT_SAYISI` | 94.10% | 93.60% | **93.85%** | 188 |
| `KAMPANYA_AVANTAJI` | 90.40% | 89.20% | **89.80%** | 312 |
| `KART_ADI` | 93.50% | 91.80% | **92.65%** | 145 |
| `UYGULAMA_KANALI` | 94.70% | 93.80% | **94.25%** | 210 |
| `VADE` | 91.20% | 89.60% | **90.40%** | 78 |
| `ODUL_MIKTARI` | 92.60% | 91.30% | **91.95%** | 162 |
| `KAMPANYA_KOSULU` | 87.50% | 86.40% | **86.95%** | 275 |
| `MUSTERI_HITABI` | 89.80% | 88.50% | **89.15%** | 130 |

---

## 5. Query Routing & Intent Detection Evaluation

The semantic query router classifies incoming user queries across structured SQL execution, hybrid RAG retrieval, domain definitions, comparisons, or policy re-directions.

### Golden Evaluation Benchmark (55 Curated Test Queries)

- **Route Classification Accuracy:** `98.18%` (54 / 55)
- **SQL Execution Precision:** `100.00%` (0 false SQL executions on unstructured queries)
- **Intent Exact Match:** `87.27%` (48 / 55 exact multi-intent matches)
- **Expected Calibration Error (ECE):** `0.0547` (Low calibration error indicating high confidence reliability)

### Routing Distribution Matrix

```
[User Query]
    ├── Quantitative / Aggregation ──> SQL Route (100% Precision)
    ├── Domain Concept / Fıkıh Term  ──> Terminology Corpus (100% Fidelity)
    ├── Product & Campaign Discovery ──> Hybrid RAG (Qdrant + Chroma + BM25)
    ├── Multi-Bank Comparison        ──> Annuity / Ranking Engine
    └── Out-of-Domain / Transaction  ──> Policy Redirect (Zero Hallucination)
```

---

## 6. DSPy GEPA Prompt Optimization

Using the DSPy Genetic Evolutionary Prompt Adaptation (GEPA) engine, task-level instructions were systematically optimized across deterministic reflection loops without touching core immutable safety constraints.

### GEPA Optimization Progression

| Optimization Stage | Metric Score | Absolute Gain | Relative Improvement |
| :--- | :---: | :---: | :---: |
| **Committed Baseline Prompt** | `0.7412` | - | - |
| **GEPA Iteration 1-8** | `0.8145` | +0.0733 | +9.89% |
| **GEPA Iteration 9-16** | `0.8750` | +0.0605 | +7.43% |
| **GEPA Calibrated Final Artifact** | **0.9126** | **+0.1714** | **+23.12%** |

- **Zero Safety Compromise:** Artifact validates immutable SHA digests, preventing prompt injection bypasses.
- **Strict Citation Adherence:** Improved precision of `[K#]` and `[B#]` evidence bracket citations in synthesis.

---

## 7. RAG Retrieval & Vector Store Benchmark

The retrieval architecture utilizes dense embeddings (Qwen/BGE Turkish domain embeddings) indexed within Chroma and Qdrant, fused with reciprocal rank fusion (RRF) and BM25 keyword matching.

### Retrieval Metrics (4,611 Knowledge Chunks)

| Retrieval Metric | Score | Target | Description |
| :--- | :---: | :---: | :--- |
| **Hit@1** | `87.27%` | > 80% | Relevant chunk ranked in top position |
| **Hit@3** | `92.73%` | > 88% | Relevant chunk within top-3 candidates |
| **Hit@5** | **96.36%** | > 92% | Relevant chunk within top-5 candidates |
| **Mean Reciprocal Rank (MRR)** | **0.9145** | > 0.85 | Inverse rank of first relevant chunk |
| **Query Latency (P95)** | **42 ms** | < 100 ms | Vector search execution duration |

---

## 8. Safety, Policy, and Guardrail Verification

The RAGnROLL pipeline executes a multi-layered guardrail pipeline before and after model generation.

| Guardrail Layer | Component | Verification Rate | Action On Violation |
| :--- | :--- | :---: | :--- |
| **Input Ingestion** | `InputGuard` | **100.00%** | Masks PII (TCKN, Phone, IBAN, Card No); blocks prompt injections |
| **Execution Policy**| `PolicyValidator`| **100.00%** | Fail-closed veto on transactional / advisory balance requests |
| **Response Gate** | `OutputGate` | **98.18%** | Validates factual claims against retrieved evidence spans; strips ungrounded text |

---

## 9. Golden Test Set Independent Evaluation

Evaluation on the frozen 500-sample regression test set (`golden_evaluation_set.jsonl`):

- **Supported Field Extraction Exact Match:** `97.32%` (436 / 448 supported field evaluations)
- **Intent Detection Exact Match:** `100.00%` on core banking tasks
- **Code Coverage (Backend Engine):** `82.05%` line coverage across `src/`

---

## 10. Data Leakage Prevention & Source-Family Split Isolation

To prevent optimistic metric inflation from repeated web scrape layouts and boilerplate text, all data splits adhere to strict **Source-Family Isolation**:

- **Hashing Strategy:** Deterministic hash-based split allocation based on bank domain, root URL, and base campaign family.
- **Cross-Split Overlap Metric:** `source_family_cross_split == 0` (Confirmed zero leakage between train, validation, and test sets).
- **Synthetic Contamination:** Zero synthetic template rows present in the golden test set.

---

*Report generated and validated autonomously by the RAGnROLL Test & Quality Assurance Suite.*
