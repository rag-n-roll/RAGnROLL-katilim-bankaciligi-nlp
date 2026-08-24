# RAGnROLL — Katılım Bankacılığı Bilgi Platformu

Katılım bankalarının resmî ürün ve kampanya içeriklerini toplayan; metni
yapılandırılmış ve kanıtlanabilir alanlara dönüştüren; açıklanabilir
karşılaştırma ve kaynaklı soru-cevap sunan yerel çalışabilir platform.

## Neler sunar?

- BDDK kataloğu güdümlü, robots/TLS kurallarına saygılı 10 banka adaptörü
- Ham kayıt, temiz metin, yapılandırılmış alan ve değerlendirme katmanları
- Exact hash, near-duplicate kümeleri ve zamansal kayıt sürüm geçmişi
- Hash ve tam bağımlılık sürümü doğrulanan sınıflandırıcı + NER danışmanlık analizi
- Her alan için değer, durum, güven, yöntem ve karakter aralıklı kanıt
- 12 intent, katılım finans terminolojisi ve SQL-first sorgu derleyici
- Koşul/tanım soruları için Qwen embedding + Chroma + BM25 + yönlendirilmiş graph retrieval
- Kaynak konumunu koruyan semantik chunking ve yalnız değişen parçaları embed eden indeksleme
- vLLM-Metal üzerinde Gemma ile kaynak etiketli, token bazlı streaming yanıt
- Model hatasında kesintisiz çalışan doğrulanabilir yerel fallback
- DSPy GEPA ile ölçülebilir ve tekrar üretilebilir Türkçe istem iyileştirme
- FastAPI sözleşmeleri ve canlı Next.js dashboard
- Golden Set, edge-case testleri, gecikme/hata ve veri kalitesi metrikleri

## Hızlı başlangıç

Python 3.11 önerilir. Model artefaktları spaCy 3.8.15, scikit-learn 1.9.0 ve
joblib 1.5.3 ile fail-closed çalışır; farklı sürümde deserialize edilmez.

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
docker compose up --build --detach
curl --fail http://localhost:8000/api/v1/health
curl --fail http://localhost:3000/
```

İmaj içindeki işlenmiş kampanya snapshot'ı yalnız boş `runtime_data` volume'unu
başlatmak için kullanılır. SQLite, yenilemeyle oluşan ham/işlenmiş JSON ve kalite
raporu `runtime_data`; Chroma koleksiyonu ise `chroma_data` volume'unda kalır.
Container refresh/index smoke adımları ve volume sıfırlama uyarıları
[operasyon rehberinde](docs/runbook.md#container-sözleşmesi) yer alır.

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

Düzeltilmiş SQLite kampanyalarını ve terminoloji kayıtlarını Chroma'ya yükleyin.
İlk geçişte Qwen modeli ve yeni indeks bir kez oluşturulur; sonraki çalıştırmalarda
yalnız içerik parmak izi değişen parçalar yeniden embed edilir:

```bash
python -m scripts.ingest_chroma --batch-size 64
```

Varsayılan `Qwen/Qwen3-Embedding-0.6B` modeli, Türkçe sorguya özel İngilizce
retrieval talimatıyla çalışır. Uzun kampanyalar yaklaşık 320 kelimelik, sınırlı
örtüşen parçalara ayrılır. Banka, ürün ve finansman türü filtreleri vektör
aramasından önce uygulanır; ontoloji graph'ı yalnız ilişkisel sorgularda açılır.

API üzerinden başarılı veya kısmi veri yenilemesinden sonra artımlı indekslemeyi
otomatik çalıştırmak için `RAGNROLL_CHROMA_AUTO_INDEX=true` ayarlanabilir. Compose
kurulumunda `RAGNROLL_NLP_AUTO_ENRICH=true` ile danışmanlık analizi de açıktır;
iş sırası scrape, zenginleştirme ve indekslemedir. Doğrudan Python çalıştırmada
zenginleştirme varsayılan olarak kapalıdır. Elle çalıştırmak için:

```bash
python -m scripts.enrich_nlp --database data/ragnroll.sqlite3
```

Analiz `structured` alanları değiştirmez; yalnız eksik alan önerilerini üst düzey
`nlp_analysis` altında saklar. İndeks filtreleri otoriter alanlardan gelmeye devam
eder.

Ardından API ve dashboard'u hızlı başlangıçtaki komutlarla çalıştırın. vLLM
erişilemez, boş yanıt üretir veya geçerli kaynak etiketi vermezse kullanıcıya
yarım model cevabı bırakılmaz; doğrulanmış deterministik yanıt otomatik gösterilir.

Opsiyonel DSPy/GEPA bağımlılıklarını yalnız deney ortamına kurup önce çevrimdışı
sözleşme kontrolünü çalıştırın:

```bash
pip install -r requirements-prompt-optimization.txt
python -m src.prompt_optimization.optimize_gepa --check
```

Gerçek deney ayrıca çalışan OpenAI uyumlu model endpoint'i ve açık bir runtime
dizini gerektirir:

```bash
python -m src.prompt_optimization.optimize_gepa \
  --runtime-dir runtime \
  --max-metric-calls 24
```

934 örneğin committed train/validation/test alanları değiştirilmez. Adaylar yalnız
validation proxy skoruyla seçilir; test yalnız seçilen adaya uygulanır. Referanslar
sınıflandırma/NER etiketlerinden türetildiği için bütün sonuçlar `proxy`dir;
bağımsız gold sağlanmamıştır. Yeni bir deney sonucu bu repoda varsayılmaz veya
raporlanmaz. Varsayılan canlı prompt değişmez; üretilen aday ancak
`RAGNROLL_PROMPT_MODE=gepa` ve doğrulanan artifact ile açılır. Ayrıntılar için
[prompt optimizasyon sözleşmesine](docs/prompt-optimization.md) bakın.

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

Dondurulmuş regresyon seti yalnız desteklenen alanları proxy başarı oranına dahil
eder; ölçülmeyen referans alanlarını ayrıca görünür tutar. Bağımsız insan gold'u
henüz sağlanmamıştır. Son doğrulama sonuçları ve sınırlar
[değerlendirme notunda](docs/evaluation.md), dataset lineage/digest sözleşmesi ise
[eğitim verisi notunda](docs/training-data-contract.md) açıklanır.

## Teknik belgeler

- [Mimari](docs/architecture.md)
- [Veri sözleşmesi](docs/data-contract.md)
- [API](docs/api.md)
- [Değerlendirme](docs/evaluation.md)
- [Eğitim verisi sözleşmesi](docs/training-data-contract.md)
- [Operasyon rehberi](docs/runbook.md)

Kaynak siteler istemci tanımlı User-Agent, hız sınırı, kontrollü retry ve
varsayılan robots.txt uygulamasıyla taranır. `--ignore-robots` yalnız site
sahibinden açık izin alındığında kullanılmalıdır.
