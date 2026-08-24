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

## Kurulum yolları ve önkoşullar

Platformdan bağımsız tüm yerel kurulumlar Python **3.11** ve Node.js **22**
gerektirir. Python ve Node sürümlerini kurulumdan önce doğrulayın:

```text
python --version
python3 --version
node --version
npm --version
```

Python 3.11, sabitlenmiş model artefaktlarının güvenli şekilde yüklenmesi için
gereklidir. `python` komutu Python 3.11'i göstermiyorsa aşağıdaki platforma özel komutlarda
`python3.11` kullanın. Node.js 22 için [Node.js indirme sayfasındaki](https://nodejs.org/en/download)
LTS sürümünü tercih edin.

### Windows PowerShell

PowerShell'de proje dizininde:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd src\dashboard
npm ci
cd ..\..
```

`Activate.ps1` çalıştırılırken script politikası hatası alırsanız yalnızca açık
olan PowerShell oturumu için şu komutu çalıştırıp aktivasyonu tekrarlayın:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Politikayı değiştirmek istemiyorsanız sanal ortamı aktive etmeden doğrudan
`.\.venv\Scripts\python.exe` ve `.\.venv\Scripts\pip.exe` yürütülebilirlerini
kullanın. Örneğin:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn src.main:app --reload
```

### Linux

Dağıtımınızın paket yöneticisiyle Python 3.11, `python3.11-venv`, Node.js 22
ve npm'i kurduktan sonra:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd src/dashboard
npm ci
cd ../..
```

### macOS

Homebrew veya Python.org üzerinden Python 3.11'i, Node.js 22'yi ise Node.js
LTS paketinden kurun. Ardından:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cd src/dashboard
npm ci
cd ../..
```

### Yol 1 — Baseline API ve dashboard

İlk kurulum için yalnızca API ve dashboard'u çalıştırın; Python ve Node
bağımlılıkları yukarıdaki platform bölümünde bir kez kurulmuş olmalıdır. API'yi
bir terminalde başlatın:

```bash
python -m uvicorn src.main:app --reload
```

Windows PowerShell'de aynı komut çalışır. Dashboard için ikinci terminalde:

```bash
cd src/dashboard
npm run dev
```

Bu baseline yolunda yerel Gemma servisi veya embedding modeli başlatmanız
gerekmez; API'nin deterministik fallback'i kullanılabilir.

### Yol 2 — Chroma ve Qwen embedding

Yerel retrieval'i etkinleştirmek için API'yi durdurmadan önce aynı sanal ortamda
işlenmiş kampanyaları ve terminolojiyi indeksleyin:

```bash
python -m scripts.ingest_chroma --batch-size 64
```

İlk çalıştırma `Qwen/Qwen3-Embedding-0.6B` modelini ve Chroma indeksini indirir;
sonraki çalıştırmalar yalnızca değişen parçaları embed eder. API yenilemesinden
sonra otomatik indeksleme için `RAGNROLL_CHROMA_AUTO_INDEX=true` ayarlayın.

### Yol 3 — İsteğe bağlı Gemma/vLLM

Bu yol baseline için zorunlu değildir. Apple Silicon üzerinde vLLM-Metal'i bir
kez kurup OpenAI uyumlu Gemma endpoint'ini başlatın:

```bash
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm-metal/main/install.sh | bash
python -m scripts.serve_local_llm
```

Linux veya Windows'ta Gemma/vLLM kullanacaksanız, makinenize uygun ve OpenAI
uyumlu vLLM kurulumunu ayrıca sağlayın; API adresini `RAGNROLL_LLM_BASE_URL`,
model adını `RAGNROLL_LLM_MODEL` ile verin. Servis erişilemezse API doğrulanmış
deterministik fallback'e döner. Model uyumluluğu ve MLX kontrol noktası hakkında
ayrıntılar aşağıdaki mevcut Gemma bölümündedir.

### Yol 4 — İsteğe bağlı GEPA prompt optimizasyonu

GEPA yalnız deney ortamı içindir; baseline veya retrieval kurulumu için gerekli
değildir:

```bash
python -m pip install -r requirements-prompt-optimization.txt
python -m src.prompt_optimization.optimize_gepa --check
```

Gerçek deney için ayrıca çalışan OpenAI uyumlu model endpoint'i gerekir:

```bash
python -m src.prompt_optimization.optimize_gepa --runtime-dir runtime --max-metric-calls 24
```

### Docker Desktop ve Linux Docker Compose

Docker kullanacaksanız Python/Node'u host'a kurmak zorunda değilsiniz. Windows ve
macOS'ta Docker Desktop'ı başlatın; Linux'ta Docker Engine ile Compose plugin'in
kurulu olduğunu doğrulayın:

```bash
docker version
docker compose version
```

Windows PowerShell'de imajları oluşturup servisleri arka planda başlatın:

```powershell
docker compose up --build --detach
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:3000/
```

Linux'ta ve macOS'ta aynı işlemin `curl` karşılığı:

```bash
docker compose up --build --detach
curl --fail http://localhost:8000/api/v1/health
curl --fail http://localhost:3000/
```

Compose API, dashboard ve Chroma için gerekli servisleri başlatır. Gemma host'ta
çalışıyorsa Compose API'si varsayılan olarak `host.docker.internal:8001` adresini
kullanır. Snapshot, SQLite ve Chroma volume'larının davranışı için
[operasyon rehberindeki container sözleşmesine](docs/runbook.md#container-sözleşmesi)
bakın.

## Kurulum doğrulaması ve güvenli temizlik

Çalışan baseline kurulumunu aşağıdaki kesin komutlarla doğrulayın.

Windows PowerShell:

```powershell
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:3000/
```

Linux/macOS:

```bash
curl --fail http://localhost:8000/api/v1/health
curl --fail http://localhost:3000/
```

Kod kalite doğrulaması için:

```bash
python -m pytest tests/ -q --cov=src --cov-report=term
python -m flake8 src tests --max-line-length=100 --extend-ignore=E203 --exclude=src/dashboard/node_modules
cd src/dashboard && npm test && npm run lint && npm run build
cd ../..
```

Compose tanımını ve izole refresh→index smoke yolunu doğrulamak için:

```bash
docker compose config --quiet
COMPOSE_PROJECT_NAME=ragnroll-smoke \
RAGNROLL_REFRESH_DATASET=/app/bootstrap/campaigns.json \
RAGNROLL_INDEX_SMOKE=true \
RAGNROLL_EMBEDDING_WARMUP=false \
RAGNROLL_LLM_ENABLED=false \
RAGNROLL_CHROMA_COLLECTION=ragnroll_container_smoke \
docker compose up --build --detach
job_response="$(curl --fail --silent --show-error -X POST http://localhost:8000/api/v1/data-refresh \
  -H 'content-type: application/json' \
  -d '{"max_per_bank":1}')"
job_id="$(printf '%s' "$job_response" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
status=""
enrichment_status=""
index_status=""
attempt=1
while [ "$attempt" -le 60 ]; do
  job_json="$(curl --fail --silent --show-error "http://localhost:8000/api/v1/data-refresh/$job_id")"
  status="$(printf '%s' "$job_json" | python -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
  enrichment_status="$(printf '%s' "$job_json" | python -c 'import json,sys; print(json.load(sys.stdin)["enrichment_status"])')"
  index_status="$(printf '%s' "$job_json" | python -c 'import json,sys; print(json.load(sys.stdin)["index_status"])')"
  case "$status" in
    completed|partial|failed) break ;;
  esac
  sleep 2
  attempt=$((attempt + 1))
done
[ "$status" = "completed" ] && \
  [ "$enrichment_status" = "completed" ] && \
  [ "$index_status" = "completed" ] || {
    printf 'Smoke job did not complete successfully: status=%s enrichment_status=%s index_status=%s\n' \
      "$status" "$enrichment_status" "$index_status" >&2
    exit 1
  }
```

Windows PowerShell karşılığı:

```powershell
$env:COMPOSE_PROJECT_NAME = "ragnroll-smoke"
$env:RAGNROLL_REFRESH_DATASET = "/app/bootstrap/campaigns.json"
$env:RAGNROLL_INDEX_SMOKE = "true"
$env:RAGNROLL_EMBEDDING_WARMUP = "false"
$env:RAGNROLL_LLM_ENABLED = "false"
$env:RAGNROLL_CHROMA_COLLECTION = "ragnroll_container_smoke"
docker compose up --build --detach
$job = Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/api/v1/data-refresh `
  -ContentType "application/json" `
  -Body '{"max_per_bank":1}'
$jobId = $job.id
$terminalStatuses = @("completed", "partial", "failed")
$state = $null
for ($attempt = 1; $attempt -le 60; $attempt++) {
  $state = Invoke-RestMethod "http://localhost:8000/api/v1/data-refresh/$jobId"
  if ($terminalStatuses -contains $state.status) { break }
  Start-Sleep -Seconds 2
}
if ($null -eq $state -or
    $state.status -ne "completed" -or
    $state.enrichment_status -ne "completed" -or
    $state.index_status -ne "completed") {
  throw "Smoke job did not complete successfully: status=$($state.status) enrichment_status=$($state.enrichment_status) index_status=$($state.index_status)"
}
```

İzole smoke işi bittikten sonra yalnız onun volume'larını kaldırın:

```bash
COMPOSE_PROJECT_NAME=ragnroll-smoke docker compose down --volumes --remove-orphans
```

Windows PowerShell'de yalnızca `ragnroll-smoke` Compose projesinin volume'larını kaldırın:

```powershell
$env:COMPOSE_PROJECT_NAME = "ragnroll-smoke"
docker compose down --volumes --remove-orphans
```

Retrieval ve GEPA yollarını ayrıca doğrulayın:

```bash
python -m scripts.ingest_chroma --batch-size 64
python -m src.prompt_optimization.optimize_gepa --check
```

Yerel servisleri ve verileri koruyarak durdurmak için:

```bash
docker compose down --remove-orphans
```

Yalnız sanal ortamı kaldırmak güvenlidir; kaynak kodu, `data/` ve Docker
volume'larını silmez:

```powershell
Remove-Item -Recurse -Force .venv
```

```bash
rm -rf .venv
```

Chroma ve runtime verilerini de sıfırlamak istiyorsanız bunun geri alınamaz
olduğunu kontrol ettikten sonra yalnızca izole `ragnroll-smoke` Compose
projesinin volume'larını kaldırın:

```bash
COMPOSE_PROJECT_NAME=ragnroll-smoke docker compose down --volumes --remove-orphans
```

## Hızlı başlangıç

Python 3.11 gereklidir. Model artefaktları spaCy 3.8.15, scikit-learn 1.9.0 ve
joblib 1.5.3 ile fail-closed çalışır; farklı sürümde deserialize edilmez.

Linux/macOS'ta proje kökünde:

```bash
python3.11 -m venv .venv
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

Linux/macOS'ta tüm platformu container ile çalıştırmak için:

```bash
docker compose up --build --detach
curl --fail http://localhost:8000/api/v1/health
curl --fail http://localhost:3000/
```

Windows PowerShell'de:

```powershell
docker compose up --build --detach
Invoke-RestMethod http://localhost:8000/api/v1/health
Invoke-RestMethod http://localhost:3000/
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
cd src/dashboard && npm test && npm run lint && npm run build
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
