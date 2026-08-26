# Operasyon rehberi

## EVREN öncelikli çalışma

EVREN anahtarları hiçbir zaman repoya veya Compose varsayılanına yazılmaz. Üretim
secret store aşağıdaki iki farklı değeri sağlamalıdır:

```text
EVREN_API_KEY
EVREN_QDRANT_API_KEY
```

LLM ve Qdrant anahtarları birbirinin yerine kullanılamaz. Qdrant için ayrıca
`EVREN_QDRANT_PREFIX=teamNN`, `EVREN_QDRANT_PORT=443` ve REST kullanımı zorunludur.

Yerel `.env` dosyasındaki değerlerin sürece gerçekten yüklenmesi için API şu
şekilde başlatılmalıdır; yalnız dosyayı oluşturmak Uvicorn'a otomatik yükletmez:

```bash
python -m uvicorn src.main:app --reload --env-file .env
```

Başlangıç kontrolü:

```bash
curl -fsS https://evren-teknofest.ssyz.org.tr/status
curl -fsS http://localhost:8000/api/v1/capabilities/status
```

`generation.providers` içinde `evren`, retrieval içinde `evren_qdrant` sağlıklı
görünmelidir. EVREN yapılandırılmamışsa API yine açılır ve yerel zinciri kullanır.

Uzak ve yerel indeksleri birlikte güncellemek için mevcut komut kullanılır:

```bash
python -m scripts.ingest_chroma --database data/ragnroll.sqlite3
```

Çıktıdaki `evren.status=ready` uzak indeksin hazır olduğunu gösterir. Uzak indeks
başarısız olsa bile yerel Chroma korunur. Dağıtım kapısında EVREN'i zorunlu kılmak
için aynı komuta `--require-evren` eklenir.

Tek adımlı rollback:

```dotenv
RAGNROLL_GENERATION_PROVIDER_ORDER=local,deterministic
RAGNROLL_RETRIEVAL_PROVIDER_ORDER=local_qwen_chroma,bm25_graph
```

401/403 ve model alias uyuşmazlığında retry yapılmaz. 429/5xx ve bağlantı
hatalarında ilk token öncesinde en fazla bir retry uygulanır. Token geldikten sonra
ve video çağrılarında otomatik retry yoktur. Kullanıcıya yalnız kaynak ve sayısal
iddia doğrulamasını geçen model cevabı gösterilir.

## Container sözleşmesi

Temiz bir Compose projesi API ve dashboard'u şu şekilde başlatır:

```bash
docker compose up --build --detach
curl --fail http://localhost:8000/api/v1/health
curl --fail http://localhost:8000/api/v1/dashboard/summary
curl --fail http://localhost:3000/
```

İmajdaki `/app/bootstrap/campaigns.json` salt-okunur başlangıç snapshot'ıdır.
`runtime_data` boşsa entrypoint bu snapshot'ı `/app/runtime/ragnroll.sqlite3`
veritabanına bir kez aktarır. Scraper yenilemesinin
`data/raw/participation_banks.json`, `data/raw/campaigns.json`,
`data/processed/campaigns.json` ve `outputs/quality_report.json` çıktıları da
`/app/runtime` altında aynı volume'da kalır. Mevcut SQLite veya processed snapshot
başlangıçta silinmez ya da üzerine yazılmaz. Başarılı başlangıçtan sonra SQLite
backup API'siyle `/app/runtime/last-good/ragnroll.sqlite3` atomik olarak yenilenir.
Sonraki başlangıçta aktif veritabanı `PRAGMA quick_check` kontrolünü geçmezse bu
doğrulanmış kopyadan otomatik kurtarılır; ikisi de bozuksa container fail-closed
durur. Bilerek boş bir veritabanı işletilecekse
`RAGNROLL_BOOTSTRAP_ON_EMPTY=false` verilebilir. Chroma ayrı `chroma_data`
volume'unda `/app/chroma_db` yolunda tutulur.

Gerçek yenileme resmî dış kaynaklara çıkar ve robots/TLS/SSRF kontrollerini aynen
uygular. Başarılı veya kısmi yenilemeden sonra doğrulanmış kampanya modelleri,
ardından `scripts.ingest_chroma` otomatik çağrılır:

```bash
curl -X POST http://localhost:8000/api/v1/data-refresh \
  -H 'content-type: application/json' \
  -d '{"max_per_bank":1}'
curl --fail http://localhost:8000/api/v1/data-refresh/JOB_ID
```

Dış banka veya model ağına çıkmadan container refresh→index zincirini denemek
için ayrı bir Compose proje adı kullanın. Bu mod, aynı bootstrap snapshot'ını
SQLite'a yeniden aktarır ve yalnız sözleşme doğrulaması için deterministik hash
embedding üretir; oluşturduğu koleksiyon semantik aramada kullanılmamalıdır:

Container smoke için [README'deki kanonik güvenli akışı](../README.md#kurulum-doğrulaması-ve-güvenli-temizlik)
kullanın. Bu akış Compose başlangıcını başarısızlıkta durdurur, API health için
retry yaparak hazır olmasını bekler, POST'tan sonra job durumunu terminal duruma
dek polling yapar ve `status=completed`, `enrichment_status=completed` ile
`index_status=completed` değerlerinin üçünü de doğrular. PowerShell akışı ayrıca
tüm `COMPOSE_PROJECT_NAME` ve `RAGNROLL_*` smoke değişkenlerini işlem sonunda,
başarısızlık dahil, önceki değerlerine döndürür. CI/smoke için
`RAGNROLL_NLP_MAX_RECORDS=1`, tüm kayıtlar için `0` kullanılır. Yalnız bu izole
smoke projesinin verisini silmek isterseniz
`COMPOSE_PROJECT_NAME=ragnroll-smoke docker compose down --volumes --remove-orphans` kullanın;
normal proje volume'larında `--volumes` veri kaybına yol açar.

## Sağlık kontrolü

```bash
curl --fail http://localhost:8000/api/v1/health
curl --fail http://localhost:8000/api/v1/metrics/summary
```

Dashboard API'ye erişemiyorsa `NEXT_PUBLIC_API_BASE_URL` değerini ve API'nin
`RAGNROLL_CORS_ORIGINS` listesini kontrol edin.

## Yerel model ve retrieval

Apple Silicon servis sırası:

```bash
python -m scripts.serve_local_llm
python -m scripts.ingest_chroma --batch-size 64
```

İki komutu ayrı terminallerde çalıştırın. Varsayılan model kaynağı
`mlx-community/gemma-4-e4b-it-4bit` olup ilk çalıştırmada yerel önbelleğe
indirilir. Ollama ModelOpt NVFP4 tensorları MLX yükleyicisine doğrudan
bağlanmamalıdır. Durumu doğrulayın:

```bash
curl --fail http://127.0.0.1:8001/v1/models
curl --fail http://localhost:8000/api/v1/llm/status
```

`/llm/status` erişilemez görünüyorsa `RAGNROLL_LLM_BASE_URL`, model adı ve vLLM
terminal çıktısını kontrol edin. API'yi durdurmanız gerekmez; bütün sohbet uçları
yerel fallback ile çalışmaya devam eder.

Varsayılan embedding modeli `Qwen/Qwen3-Embedding-0.6B`, koleksiyon ise
`katilim_bankaciligi_qwen3` değeridir. Önceki embedding uzayı ayrı koleksiyonda
kalır; farklı boyutlu vektörler karıştırılmaz. İlk çalıştırma bütün semantik
parçaları üretir. Sonraki çalıştırmalar `index_hash` eşleşen parçaları atlar,
değişenleri embed eder ve artık kaynakta bulunmayan parçaları temizler. Çıktıdaki
`embedded`, `unchanged` ve `stale_deleted` değerlerini kontrol edin.
Apple Silicon birleşik belleğinde aşırı padding ve bellek baskısını önlemek için
model içi varsayılan embedding batch değeri 4'tür;
`RAGNROLL_EMBEDDING_BATCH_SIZE` ile ölçerek değiştirilebilir.
Hazır indeksle API başlatıldığında query modeli varsayılan olarak ısıtılır; böylece
model yükleme maliyeti ilk kullanıcı sorgusuna taşınmaz. Kısıtlı test ortamlarında
bu davranış `RAGNROLL_EMBEDDING_WARMUP=false` ile kapatılabilir.

Model veya koleksiyon açıkça seçilecekse:

```bash
python -m scripts.ingest_chroma \
  --embedding-model Qwen/Qwen3-Embedding-0.6B \
  --collection katilim_bankaciligi_qwen3 \
  --batch-size 64
```

API veri yenilemesinden sonra indeksin otomatik güncellenmesi için
`RAGNROLL_CHROMA_AUTO_INDEX=true` ayarlanır. İndeksleme başarısız olursa veri
korunur, iş `partial` görünür ve sohbet BM25 fallback ile hizmet vermeye devam
eder. Qwen modelini API ile aynı Apple Silicon cihazında kullanırken embedding
servisinin MPS seçmesi için gerekirse `RAGNROLL_EMBEDDING_DEVICE=mps` verilebilir.

NLP danışmanlık analizi doğrudan çalışma zamanında varsayılan kapalı,
Compose'da `RAGNROLL_NLP_AUTO_ENRICH=true` ile açıktır. Model veya bütünlük hatası
işi `partial` yapar; buna rağmen indeksleme çalışır ve hata ayrıntısı
`enrichment_message` alanında kalır. Elle zenginleştirme tek atomik yazma yapar:

Runtime manifesti, model hash'lerine ek olarak beyan edilen sınıflandırıcı/NER
eğitim girdilerini ve eğitim verisi manifestini digest ile sabitler. Otomatik
referanslar yalnız proxy'dir ve bağımsız gold sağlanmamıştır. Bu bağ, beyan edilen
lineage girdilerinin bütünlüğünü doğrular; eğitim çalışmasının bağımsız tasdiki
değildir. Container yalnız bu kapı için gereken üç lineage dosyasını taşır.

```bash
python -m scripts.enrich_nlp --database data/ragnroll.sqlite3
```

Kanal, özel kart adı ve müşteri hitabı bağlamlarını kanıta bağlı toplu çıkarmak
için EVREN ayarlarını yükleyip devam ettirilebilir batch'i çalıştırın. Çıktıyı
uygulamadan önce deterministik uzlaştırma zorunludur:

```bash
python -m scripts.label_context_entities label --workers 4
python -m scripts.label_context_entities reconcile
python -m scripts.label_context_entities apply-database
```

Kampanya başlangıç veya bitiş tarihi bilinmiyorsa bu akış tarih uydurmaz;
`scraped_at` lineage bilgisinden ayrı bir `temporal_observation` yazar. Bu kayıt
yalnız kampanyanın ilgili tarihte kaynakta görüldüğünü ifade eder.

Önce ağ kullanmayan prompt veri/bağımlılık/artifact sözleşmesi kontrolünü çalıştırın:

```bash
pip install -r requirements-prompt-optimization.txt
python -m src.prompt_optimization.optimize_gepa --check
```

Gerçek deney yalnız model endpoint'i sağlıklıyken ve çıktı kökü açıkça verilerek
başlatılır:

```bash
python -m src.prompt_optimization.optimize_gepa \
  --runtime-dir runtime \
  --max-metric-calls 24
```

Cache, GEPA logları, atomik artifact ve raporlar yalnız bu runtime köküne yazılır.
`--auto light`, `--auto medium` veya `--auto heavy`, metrik çağrısı bütçesinin
yerine kullanılabilir. Aday seçimi train+validation ile yapılır; committed test
spliti yalnız seçilen adaya bir kez uygulanır. Raporlar türetilmiş etiketlere
dayalı proxy'dir ve `independent_gold:not_provided` taşır.

Canlı servis varsayılan promptla kalır. İncelenen bir artifact'i etkinleştirmek
için iki değişken birlikte ayarlanır; eksik/geçersiz artifact veya dataset digest
uyuşmazlığı asistanın oluşturulmasını veya ilk asistan isteğini fail-closed
durdurur:

```bash
RAGNROLL_PROMPT_MODE=gepa
RAGNROLL_PROMPT_ARTIFACT=runtime/prompt-optimization/selected_prompt.json
```

Canlı kullanıcı içeriği GEPA eğitim verisine otomatik eklenmez. Yeni örnekler
insan doğrulamasıyla değerlendirme dosyasına alınmalıdır.

## Veri yenileme

Tam yenileme öncesi mevcut SQLite ve kanonik JSON dosyalarını yedekleyin.
Toplama komutu kısmi başarıda `2` döndürebilir; `outputs/quality_report.json`
içindeki `fetch_failures`, sıfır kayıtlı bankalar ve kapsam listesini inceleyin.
Başarılı bankaların verisi kısmi hatada korunur.

API üzerinden yenileme kontrollü ve tek iş olarak çalışır:

```bash
curl -X POST http://localhost:8000/api/v1/data-refresh \
  -H 'content-type: application/json' \
  -d '{"max_per_bank":20}'
```

Aynı anda ikinci yenileme `409` döndürür. İş kimliğini
`GET /api/v1/data-refresh/{job_id}` ile izleyin.

## Kalite alarmı

`/api/v1/metrics/summary` yanıtında hata oranı, p50/p95 gecikme, alan durumları,
kanıt kapsamı ve tekrar kümeleri bulunur. Eşikler
`configs/quality_thresholds.json` dosyasındadır.

Golden Set veya test eşiği düşerse önce failure dilimini inceleyin; yalnız skoru
yükseltmek için gold örnek metnine özel kural eklemeyin. Yeni kuralın karşı
örneğini ve edge testini birlikte ekleyin.

## Geri dönüş

Uygulama container'ları stateless'tir; kalıcı durum `runtime_data` volume'unda
tutulur. Geri dönüşte önce önceki imajı başlatın, ardından veritabanı şema
uyumluluğunu `/health` ve kayıt detay uçlarıyla kontrol edin. Veri volume'unu
silmek geri alınamaz; olağan geri dönüş işleminin parçası değildir.
