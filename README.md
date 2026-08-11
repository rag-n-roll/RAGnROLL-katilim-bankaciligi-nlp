# RAGnROLL — Katılım Bankacılığı NLP

TEKNOFEST 2026 Yapay Zekâ Dil Ajanları Yarışması için katılım bankacılığı
kampanyalarını toplayan ve Türkçe NLP işlemine hazırlayan veri hattı.

## PRD Görev Durumu — Hafta 1 (27 Temmuz - 2 Ağustos) ✅ Tamamlandı

### Dilan Kakım — Takım Kaptanı & NLP Mühendisi
- ✅ GitHub repository oluşturma, dizin yapısı, branch stratejisi
- ✅ README.md, CONTRIBUTING.md, LICENSE (Apache 2.0) hazırlama
- ✅ NLP kütüphaneleri araştırma ve karşılaştırma
- ✅ Terminoloji sözlüğü başlatma → `data/terminology/` (10 dosya)
- ✅ NER etiketleme şeması tasarlama → `data/terminology/entity_schema.json`
- ✅ Haftalık toplantı takvimi oluşturma

### Kutay Orallı — Veri Mühendisi & Backend Geliştirici
- ✅ BDDK web sitesinden katılım bankası listesini çekme → `src/scraper/bddk.py`
- ✅ 10 bankanın tamamı için web scraper modülleri → `src/scraper/banks/` (10 adaptör)
- ✅ Kampanya metinlerini toplama ve JSON formatında saklama → `src/scraper/models.py`
- ✅ Veri doğrulama ve kalite kontrol mekanizması → `src/scraper/validation.py`
- ✅ Metin ön işleme pipeline'ı (temizleme, tokenizasyon) → `src/preprocessing/`
- ✅ Veri seti README dokümantasyonu → `data/README.md`

### Elif Naz Topçu — Frontend & Arayüz Geliştirici
- ✅ Dashboard teknoloji seçimi (Next.js) → `docs/week-1-frontend-dashboard-research.md`
- ✅ Dashboard iskelet yapısı → `src/dashboard/` (Next.js + TypeScript)
- ✅ Renk paleti, font, UI component kararları → `docs/dashboard-design-system.md`
- ✅ Veri scraping'de destek (kalan 3 banka)
- ✅ Mockup tasarımları → `docs/mockups/`
- ✅ Sunum şablonu hazırlama

### Gizem Nur Yıldırım — MLOps & Chatbot Mühendisi
- ✅ Docker altyapısı → `Dockerfile`, `docker-compose.yml` (Ollama + Chatbot servisleri)
- ✅ CI/CD pipeline → `.github/workflows/` (lint, test)
- ✅ Virtual environment, requirements.txt hazırlama
- ✅ Ollama kurulumu ve lokal LLM model araştırması → Gemma2 seçildi
- ✅ Chatbot mimari tasarımı → `docs/RAG_MIMARI_PLANI.md`
- ✅ Pytest altyapısı ve birim testleri → `tests/` (17 test dosyası)

## PRD Görev Durumu — Hafta 2 (3-9 Ağustos) 🔄 Devam Ediyor

### Dilan Kakım — Takım Kaptanı & NLP Mühendisi
- ✅ Kural tabanlı bilgi çıkarımı (regex patterns) → `src/extraction/campaign_fields.py`
- ✅ NER eğitim verisi hazırlama (etiketleme) → `data/annotations/`
- ⏳ NER modeli eğitimi (spaCy/HuggingFace BERT) → `src/ner/train.py` (TODO)
- ⏳ Kampanya sınıflandırma modeli → `src/classifier/main.py` (TODO)
- ⏳ Model değerlendirme (F1-Score, Precision, Recall)
- ✅ Terminoloji sözlüğü tamamlama → `data/terminology/` (genişletilmiş şema + regex)

### Kutay Orallı — Veri Mühendisi & Backend Geliştirici
- ✅ Kalan banka scraper'ları tamamlama → 10/10 banka aktif
- ✅ Sayısal değer ve para birimi normalizasyon modülü → `src/normalization/values.py`
- ✅ Veritabanı şeması (SQLite) → `src/persistence/store.py`
- ✅ Yapılandırılmış formata dönüştürme → `src/extraction/campaign_fields.py`
- ✅ Ürün karşılaştırma algoritması → `src/comparison/engine.py`
- ✅ NER etiketleme sürecine destek

### Elif Naz Topçu — Frontend & Arayüz Geliştirici
- ✅ Dashboard ana sayfa → `src/dashboard/app/page.tsx` (özet kartlar, grafikler)
- ✅ Karşılaştırma sayfası iskeleti → `src/dashboard/app/compare/`
- ✅ Plotly grafik prototipleri (bar chart, pie chart)
- ✅ NER etiketleme sürecine destek
- ✅ Dashboard-backend API bağlantısı tasarımı

### Gizem Nur Yıldırım — MLOps & Chatbot Mühendisi
- ✅ Ollama ile lokal LLM kurulumu ve model seçimi (Gemma2)
- ✅ LangChain RAG pipeline → `src/chatbot/rag_langchain.py`
- ✅ ChromaDB vektör veritabanı → `src/chatbot/rag.py` + `rag_langchain.py`
- ✅ Intent detection modülü → `src/intent/intent_detector.py`
- ✅ Docker image güncelleme (NLP bağımlılıkları)
- ✅ NER etiketleme sürecine destek

### Hafta 2 Eksikler
- ⏳ NER model eğitimi (`src/ner/train.py` henüz başlanmadı)
- ⏳ Kampanya sınıflandırma modeli (`src/classifier/main.py` henüz başlanmadı)
- ⏳ Model değerlendirme metrikleri (F1-Score, Precision, Recall)

## PRD Görev Durumu — Hafta 3 (10-16 Ağustos) ⬜ Başlanmadı

### Dilan Kakım — Takım Kaptanı & NLP Mühendisi
- ⬜ NLP model iyileştirme (edge case'ler, farklı ifade biçimleri)
- ⬜ Bilgi çıkarımı doğruluğunu artırma
- ⬜ NLP pipeline'ını dashboard API'sine entegre etme
- ⬜ Chatbot yanıtları için doğruluk testleri
- ⬜ Model performans raporu hazırlama
- ⬜ Proje ilerleme takibi ve koordinasyon

### Kutay Orallı — Veri Mühendisi & Backend Geliştirici
- ⬜ REST API endpointleri geliştirme (FastAPI) → `src/api/`
- ⬜ Dashboard için veri servisi oluşturma
- ⬜ Karşılaştırma motoru optimizasyonu
- ⬜ Veritabanı sorgu optimizasyonu
- ⬜ Backend birim testleri yazma
- ⬜ Veri güncelleme mekanizması (scraper yeniden çalıştırma)

### Elif Naz Topçu — Frontend & Arayüz Geliştirici
- ⬜ Dashboard karşılaştırma sayfası (filtreler, tablo, grafikler)
- ⬜ Dashboard detay sayfası (banka bazlı kampanya listeleme)
- ⬜ Chatbot UI tasarımı ve entegrasyonu
- ⬜ Dashboard - Backend API entegrasyonu
- ⬜ Responsive tasarım ayarları
- ⬜ UX iyileştirmeleri ve kullanıcı akış testleri

### Gizem Nur Yıldırım — MLOps & Chatbot Mühendisi
- ⬜ Chatbot RAG pipeline tamamlama → `src/chatbot/`
- ⬜ Intent detection modülü tamamlama → `src/intent/`
- ⬜ Chatbot yanıt formatlama ve doğruluk iyileştirme
- ⬜ Chatbot - Dashboard entegrasyonu
- ⬜ Docker Compose ile tüm servisleri birleştirme
- ⬜ Uçtan uca entegrasyon testleri

### Hafta 3 Ortak Teslim Hedefleri
- ⬜ Çalışan 3 sayfalık dashboard
- ⬜ Çalışan chatbot (soru-cevap)
- ⬜ Dashboard + Chatbot entegre çözüm
- ⬜ REST API
- ⬜ Docker Compose ile tek komutla çalışma

## 1. hafta veri mühendisliği kapsamı

- BDDK'nın resmî Türkçe `/Kurulus/Liste/77` sayfasından güncel katılım bankası listesi
- BDDK kataloğundaki 10 banka için bağımsız ürün/kampanya scraper adaptörleri
- İlk öncelik: Kuveyt Türk, Albaraka Türk ve Türkiye Finans
- Sürümlü ortak JSON şeması ve atomik dosya yazımı
- Kayıt, tarih, URL, tekrar ve çekme hatası kalite kontrolleri
- Unicode/Türkçe uyumlu temizleme ve hafif tokenizasyon
- SQLite ana kaynak, geriye uyumlu ham/işlenmiş JSON export'ları
- Deterministik sayı, para birimi, oran ve süre normalizasyonu
- Açıklanabilir ürün/kampanya karşılaştırması

BDDK listesi Ağustos 2026 itibarıyla 10 banka içerir. Veri hattı bu katalogdaki
hiçbir bankayı sessizce atlamaz. Adil Katılım'ın kamuya açık ürün/hizmet metni,
Dünya Katılım, Hayat Finans ve T.O.M. Katılım dahil diğer bankaların resmî
kampanya metinleri ortak ham şemada saklanır.

## Kurulum

Python 3.11 veya üstü önerilir.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Kullanım

BDDK kataloğundan başlayarak tüm veri hattını tek komutla çalıştırın:

```bash
python -m src.scraper.scraper --verbose collect \
  --max-per-bank 20 \
  --banks-output data/raw/participation_banks.json \
  --raw-output data/raw/campaigns.json \
  --processed-output data/processed/campaigns.json \
  --quality-report outputs/quality_report.json \
  --database data/ragnroll.sqlite3
```

Komut BDDK kapsam raporunu, ham kayıtları, PRD alanları çıkarılmış işlenmiş
veriyi ve banka/alan doluluk metriklerini birlikte üretir. SQLite ana kaynaktır;
JSON çıktıları başarılı veritabanı yazımından sonra üretilir. Eksik banka, sıfır
kayıtlı banka, ağ/ayrıştırma hatası veya doğrulama hatası varsa `2` ile çıkar.

BDDK listesini çekin:

```bash
python -m src.scraper.scraper banks
```

Öncelikli üç bankadan banka başına en fazla 10 kampanya çekin ve kalite
raporunu üretin:

```bash
python -m src.scraper.scraper --verbose campaigns \
  --banks priority \
  --max-per-bank 10 \
  --output outputs/smoke_campaigns.json \
  --quality-report outputs/smoke_quality_report.json
```

Registry'deki bankaların tümünü yalnızca ham toplama modunda çalıştırın:

```bash
python -m src.scraper.scraper campaigns \
  --banks all \
  --max-per-bank 20 \
  --output data/raw/campaigns.json \
  --quality-report outputs/quality_report.json
```

`--banks priority` ile düşük `--max-per-bank` sınırı kullanan çalıştırmalar
geçici smoke kontrolleri içindir; `outputs/smoke_*.json` dosyaları Git tarafından
yok sayılır ve kanonik veri setinin üzerine yazmaz. Kalıcı yenilemede BDDK
güdümlü `collect` komutu kullanılmalıdır. `campaigns` ve `preprocess` alt
komutları tanılama ve kısmi yeniden çalıştırma için korunur.

Bir bankadaki hata diğer bankaların taramasını durdurmaz; başarılı kayıtlar
yazılır ve kısmi başarı durumunda komut `2` çıkış koduyla tamamlanır. Banka,
aşama, URL, hata türü/mesajı, HTTP durumu ve UTC zamanı içeren ayrıntılar kalite
raporunun `fetch_failures` alanında tutulur. Hiç kayıt alınamayan toplam
kesintide son bilinen iyi kampanya dosyası korunur. Kampanya çıktısı ile kalite
raporu için aynı dosya yolu verilmesi de veri kaybını önlemek üzere reddedilir.

Ham metinleri temizleyip tokenize edin:

```bash
python -m src.scraper.scraper preprocess data/raw/campaigns.json \
  --output data/processed/campaigns.json
```

Mevcut bir veri setini yeniden doğrulayın:

```bash
python -m src.scraper.scraper validate data/raw/campaigns.json \
  --output outputs/validation_report.json
```

Bu ayrı doğrulama raporu, tarama sırasında üretilen tekrar ve `fetch_failures`
ayrıntılarını içeren kanonik `outputs/quality_report.json` dosyasını korur.

### SQLite ve karşılaştırma

SQLite şemasını güvenle oluşturun:

```bash
python -m src.scraper.scraper db init --database data/ragnroll.sqlite3
```

Önceki JSON veri setini açıkça içe aktarın; komut tekrar çalıştırıldığında kayıt
çoğaltmaz:

```bash
python -m src.scraper.scraper db import-json data/processed/campaigns.json \
  --database data/ragnroll.sqlite3
```

SQLite'tan geriye uyumlu snapshot üretin:

```bash
python -m src.scraper.scraper db export-json --database data/ragnroll.sqlite3 \
  --raw-output data/raw/campaigns.json \
  --processed-output data/processed/campaigns.json
```

Aynı ürün türü ve para birimindeki kayıtları karşılaştırın:

```bash
python -m src.scraper.scraper compare --database data/ragnroll.sqlite3 \
  --product-type financing --currency TRY --output outputs/comparison.json
```

`RAGNROLL_DB_PATH` ortam değişkeni varsayılan veritabanı yolunu değiştirir.
Karşılaştırma currency conversion yapmaz; açıkça farklı para birimleri sonuçtan
`currency_mismatch` gerekçesiyle elenir. Eksik alanlar sıfır kabul edilmez.
Önceki uyumlu SQLite şemalarında eksik indeks alanları güvenle eklenir; bilinmeyen
ve eksik zorunlu kolonlu şemalar sessiz veri kaybı yerine açık hata ile reddedilir.

Testler:

```bash
python -m pytest
```

## NLP model eğitimi ve değerlendirme

Kural tabanlı + spaCy NER hibrit çıkarımı, kampanya sınıflandırması, insan
doğrulamalı etiketleme akışı ve PRD KPI raporu için
[`docs/week-2-nlp-models.md`](docs/week-2-nlp-models.md) dokümanını izleyin.
Sentetik model verilerinden alınan skorlar yarışma performansı olarak
raporlanmaz; araçlar bu raporları otomatik olarak uyarı ile işaretler.

## Çıktılar

- `data/raw/participation_banks.json`: BDDK kuruluş listesi
- `data/raw/campaigns.json`: ortak şemadaki ham kampanyalar
- `data/processed/campaigns.json`: temiz metin, tokenlar ve PRD `structured` alanları
- `outputs/quality_report.json`: kapsam, alan doluluğu, kayıt ve çekme hata raporu
- `data/ragnroll.sqlite3`: bankalar, ürünler, kampanyalar ve scrape-run kayıtları

Alan tanımları, kalite ölçütleri, veri kökeni ve kullanım notları için
[`data/README.md`](data/README.md), teknik kararlar için
[`docs/week-1-data-engineering.md`](docs/week-1-data-engineering.md) dosyasına
bakın.

## Sorumlu tarama

İstemci tanımlı bir User-Agent kullanır, `robots.txt` kurallarını varsayılan
olarak uygular, aynı alan adına istekler arasında bekler ve geçici hatalarda
kontrollü tekrar dener. `--ignore-robots` yalnızca site sahibinden açık izin
alındığında kullanılmalıdır. Üretilen verinin yeniden yayımlanmasından önce
ilgili sitelerin kullanım şartları ve içerik hakları ayrıca kontrol edilmelidir.

Kaynak URL'lerdeki `utm_*`, `gclid`, `fbclid` gibi izleme parametreleri kararlı
kayıt kimliği üretilmeden önce kaldırılır. Kayıtlar kalıcı depolamadan önce
`bank_slug + normalize edilmiş source_url` anahtarıyla tekilleştirilir;
çıkarılan kayıtların ayrıntıları kalite raporunun `duplicates` alanına yazılır.

## Proje yapısı

```
src/
├── scraper/           # Veri toplama hattı (Kutay)
│   ├── bddk.py        # BDDK katalog çekimi
│   ├── banks/         # 10 banka için bağımsız adaptörler
│   │   ├── adil_katilim.py
│   │   ├── albaraka.py
│   │   ├── dunya_katilim.py
│   │   ├── emlak_katilim.py
│   │   ├── hayat_finans.py
│   │   ├── kuveyt_turk.py
│   │   ├── tom_katilim.py
│   │   ├── turkiye_finans.py
│   │   ├── vakif_katilim.py
│   │   └── ziraat_katilim.py
│   ├── models.py       # Ortak Campaign/Product şeması (v1.0.0)
│   ├── validation.py   # Veri doğrulama ve quality report
│   ├── storage.py      # Atomik dosya yazımı
│   ├── http.py         # Kibar HTTP (robots.txt, retry, delay)
│   └── coverage.py     # BDDK kapsam ve doluluk metrikleri
├── preprocessing/      # Metin temizleme ve tokenizasyon (Kutay)
│   └── clean_text.py
├── normalization/      # Sayı, para birimi, oran, süre normalizasyonu (Kutay)
│   └── values.py
├── extraction/         # PRD alan çıkarımı — regex tabanlı (Dilan)
│   └── campaign_fields.py
├── comparison/         # Açıklanabilir ürün karşılaştırma (Kutay)
│   └── engine.py
├── persistence/        # SQLite şema ve import/export (Kutay)
│   └── store.py
├── chatbot/            # RAG pipeline (Gizem)
│   ├── rag.py           # ChromaDB + Ollama
│   └── rag_langchain.py # LangChain 1.x + Ollama + Chroma
├── intent/             # Intent detection (Gizem)
│   └── intent_detector.py
├── ner/                # NER model eğitimi (Dilan) — TODO
│   └── train.py
├── classifier/         # Kampanya sınıflandırma (Dilan) — TODO
│   └── main.py
├── dashboard/          # Next.js dashboard (Elif Naz)
│   ├── app/
│   │   ├── page.tsx     # Ana sayfa (özet kartlar, grafikler)
│   │   ├── campaigns/   # Kampanya listesi
│   │   ├── chatbot/     # Chatbot arayüzü
│   │   └── compare/     # Karşılaştırma sayfası
│   └── components/
└── api/                # Backend API (Elif Naz) — TODO
    └── main.py

data/
├── raw/                    # Ham JSON çıktıları
├── processed/              # İşlenmiş JSON + structured alanlar
├── terminology/            # Katılım bankacılığı terminoloji sözlüğü (Dilan)
│   ├── terminology_master_phase1_phase2.json
│   ├── entity_schema.json
│   ├── entity_schema_extended.json
│   ├── regex_patterns.json
│   ├── regex_patterns_extended.json
│   ├── relation_schema.json
│   ├── alias_dictionary.json
│   └── source_registry.json
├── annotations/            # NER etiketleme verisi
├── model_training_data/    # Model eğitim verisi
└── ontology/               # Domain ontolojisi

docs/
├── week-1-data-engineering.md      # Hafta 1 veri tasarımı
├── week-1-frontend-dashboard-research.md
├── dashboard-design-system.md
├── RAG_MIMARI_PLANI.md
├── 2026-08-08-campaign-pipeline-hardening.md
└── mockups/                        # Dashboard tasarım mockupları
```
