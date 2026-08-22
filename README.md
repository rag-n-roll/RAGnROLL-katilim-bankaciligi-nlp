# RAGnROLL — Katılım Bankacılığı Bilgi Platformu

Katılım bankalarının resmî ürün ve kampanya içeriklerini toplayan; metni
yapılandırılmış ve kanıtlanabilir alanlara dönüştüren; açıklanabilir
karşılaştırma ve kaynaklı soru-cevap sunan yerel çalışabilir platform.

## Neler sunar?

- BDDK kataloğu güdümlü, robots/TLS kurallarına saygılı 10 banka adaptörü
- Ham kayıt, temiz metin, yapılandırılmış alan ve değerlendirme katmanları
- Exact hash, near-duplicate kümeleri ve zamansal kayıt sürüm geçmişi
- Her alan için değer, durum, güven, yöntem ve karakter aralıklı kanıt
- 12 intent, katılım finans terminolojisi ve SQL-first sorgu derleyici
- Koşul/tanım soruları için Chroma + çok dilli embedding + BM25 + ontoloji retrieval
- vLLM-Metal üzerinde Gemma ile kaynak etiketli, token bazlı streaming yanıt
- Model hatasında kesintisiz çalışan doğrulanabilir yerel fallback
- DSPy GEPA ile ölçülebilir ve tekrar üretilebilir Türkçe istem iyileştirme
- FastAPI sözleşmeleri ve canlı Next.js dashboard
- Golden Set, edge-case testleri, gecikme/hata ve veri kalitesi metrikleri

## Hızlı başlangıç

Python 3.11 veya üstü önerilir.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn src.main:app --reload
```

Dashboard için ayrı terminalde:

```bash
cd src/dashboard
npm ci
npm run dev
```

- API: `http://localhost:8000/api/v1/health`
- OpenAPI: `http://localhost:8000/docs`
- Dashboard: `http://localhost:3000`

Tüm platformu container ile çalıştırmak için:

```bash
docker compose up --build
```

### Yerel Gemma ve Chroma kurulumu

Apple Silicon üzerinde vLLM'in MLX arka uçlu eklentisini bir kez kurun:

```bash
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm-metal/main/install.sh | bash
```

OpenAI uyumlu servisi başlatın. İlk çalıştırmada Gemma 4 E4B'nin vLLM-Metal ile
uyumlu 4 bit MLX kontrol noktası yerel önbelleğe indirilir; API'de
`gemma4:e4b-mlx` adıyla sunulur:

```bash
python -m scripts.serve_local_llm
```

Ollama paketindeki ModelOpt NVFP4 tensor şeması vLLM-Metal'in MLX Gemma
yükleyicisiyle doğrudan uyumlu değildir. Bu nedenle aynı model ailesinin MLX
topluluk dönüşümü kullanılır; başka uyumlu bir yerel dizin `--model` ile
verilebilir.

Düzeltilmiş SQLite kampanyalarını ve terminoloji kayıtlarını Chroma'ya yükleyin:

```bash
python -m scripts.ingest_chroma --batch-size 64
```

Ardından API ve dashboard'u hızlı başlangıçtaki komutlarla çalıştırın. vLLM
erişilemez, boş yanıt üretir veya geçerli kaynak etiketi vermezse kullanıcıya
yarım model cevabı bırakılmaz; doğrulanmış deterministik yanıt otomatik gösterilir.

Türkçe cevap istemini değerlendirme örnekleriyle iyileştirmek için vLLM çalışırken:

```bash
python -m scripts.optimize_assistant_prompt --max-metric-calls 24
```

GEPA çevrimdışı çalışır; canlı kullanıcı mesajını değiştirmez. Eğitim ve doğrulama
örnekleri üzerinde en iyi talimatı seçerek çalışma zamanı istem profiline kaydeder.
Daha geniş bir arama gerektiğinde bunun yerine `--auto light` kullanılabilir.

## Veri hattı

Tüm bankaları toplayıp doğrulama raporu ve SQLite ana kaynağını üretin:

```bash
python -m src.scraper.scraper --verbose collect \
  --banks-output data/raw/participation_banks.json \
  --raw-output data/raw/campaigns.json \
  --processed-output data/processed/campaigns.json \
  --quality-report outputs/quality_report.json \
  --database data/ragnroll.sqlite3
```

Tek banka hatası başarılı bankaların kayıtlarını kaybettirmez; kısmi sonuç `2`
çıkış koduyla ve `fetch_failures` ayrıntılarıyla bildirilir. Kanonik çıktıya
yazmadan önce URL, kayıt, tarih, banka kapsamı ve kalite kontrolleri uygulanır.

Mevcut işlenmiş veri setini SQLite'a almak için:

```bash
python -m src.scraper.scraper db import-json data/processed/campaigns.json \
  --database data/ragnroll.sqlite3
```

## API özeti

- `POST /api/v1/extract`: kanıtlı alan sözleşmesi
- `GET /api/v1/campaigns` ve `GET /api/v1/campaigns/{id}`: kayıt arama/detay
- `GET /api/v1/campaigns/{id}/versions`: zamansal kaynak geçmişi
- `POST /api/v1/compare`: açıklanabilir karşılaştırma
- `POST /api/v1/query/compile`: intent, slot, filtre ve rota planı
- `POST /api/v1/chat`: kanıt paketli yanıt
- `POST /api/v1/chat/stream`: SSE ile kaynak meta verisi ve token akışı
- `GET /api/v1/llm/status`: vLLM bağlantısı ve servis edilen model durumu
- `GET /api/v1/dashboard/snapshot`: dashboard başlangıç verisi
- `GET /api/v1/metrics/summary`: çalışma zamanı ve veri kalitesi özeti

Ayrıntılı sözleşmeler için [API rehberine](docs/api.md) bakın.

## Kalite doğrulaması

```bash
python -m pytest -q
python -m flake8 src tests --max-line-length=100 --extend-ignore=E203 \
  --exclude=src/dashboard/node_modules
python -m src.evaluation.golden \
  data/model_training_data/golden_evaluation_set.jsonl
cd src/dashboard && npm run lint && npm run build
```

Golden Set ölçümü yalnız desteklenen alanları başarı oranına dahil eder;
ölçülmeyen gold alanları ayrıca görünür tutar. Son doğrulama sonuçları ve eşikler
[değerlendirme notunda](docs/evaluation.md) açıklanır.

## Teknik belgeler

- [Mimari](docs/architecture.md)
- [Veri sözleşmesi](docs/data-contract.md)
- [API](docs/api.md)
- [Değerlendirme](docs/evaluation.md)
- [Operasyon rehberi](docs/runbook.md)

Kaynak siteler istemci tanımlı User-Agent, hız sınırı, kontrollü retry ve
varsayılan robots.txt uygulamasıyla taranır. `--ignore-robots` yalnız site
sahibinden açık izin alındığında kullanılmalıdır.
