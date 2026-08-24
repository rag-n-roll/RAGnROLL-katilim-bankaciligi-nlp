# EVREN Öncelikli Kesintisiz Model Entegrasyon Planı

- Durum: Kod entegrasyonu tamamlandı; korumalı EVREN canary geçişi bekleniyor
- Hedef depo: `RAGnROLL-katilim-bankaciligi-nlp`
- Hazırlanma tarihi: 24.08.2026
- Referans kod tabanı: `origin/main` - `2c369a1`

## Uygulama durumu

24.08.2026 itibarıyla sağlayıcı zinciri, `llm-fast` generation, `router`/`guard`
advisory kararları, `bge-m3-embed` + takım Qdrant retrieval, Qwen/Chroma ve
BM25/graph fallback'leri, çift indeksleme, NLP enrichment, circuit breaker,
capability matrisi, SSE heartbeat, içeriksiz gözlemlenebilirlik ve son-iyi SQLite
geri kazanımı kod tabanına uygulanmıştır.

Anahtar gerektirmeyen kabul tamamlanmıştır: 440 Python testi, 11 dashboard testi,
Python/JavaScript lint, Next production build, bağımlılık uyumluluk kontrolü,
container build/smoke ve 471 kayıtlı canlı yerel API fallback akışı geçmiştir.
Bu çalışma ortamında `EVREN_API_KEY`, `EVREN_QDRANT_API_KEY` ve takım prefix'i
bulunmadığı için EVREN'e gerçek preflight, uzak Qdrant yüklemesi, shadow ölçümü ve
canary trafik açılışı bilinçli olarak yapılmamıştır. Bunlar kod değişikliği değil,
korumalı ortam kimlik bilgisi ve gerçek trafik gerektiren üretim kapılarıdır.

## 1. Amaç ve karar

SSB EVREN tarafından sunulan, yarışma kapsamında kullanımı onaylanmış model ve vektör servisleri sistemin birincil yapay zeka katmanı olacaktır. Mevcut yerel Qwen/Chroma, BM25 + knowledge graph, yerel model ve deterministik kaynaklı cevap mekanizmaları kaldırılmayacak; aynı sözleşmeyi koruyan kademeli fallback zinciri olarak çalışacaktır.

Bu planda "EVREN öncelikli" şu anlama gelir:

- İlgili EVREN yeteneği sağlıklıysa ilk istek EVREN'e gider.
- Model çıktısı güven, kaynak, şema ve aritmetik doğrulamalarını geçmeden kullanıcıya gösterilmez.
- EVREN erişilemez, yavaş, yanlış modeli sunuyor veya geçersiz çıktı üretiyorsa yalnız o yetenek için yerel fallback devreye girer.
- Bir dış servis arızası bütün sistemi kapatmaz; SQL, yerel indeks ve doğrulanmış cevap üretimi çalışmayı sürdürür.
- Mevcut Qwen modeli silinmez. EVREN `bge-m3-embed` ve takım Qdrant'ı birincil retrieval yolu olur; Qwen3-Embedding + Chroma ikinci, BM25 + knowledge graph üçüncü yoldur.

## 2. Kaynak ve şartname özeti

Bu plan, canlı [katılımcı dokümantasyonu](https://evren-teknofest.ssyz.org.tr/) ile kullanıcı tarafından sağlanan `/Users/kutay/Downloads/dokumantasyon.pdf` dosyasına dayanır. 24.08.2026 tarihinde canlı siteden indirilen PDF ile ekli PDF'nin SHA-256 değeri aynıdır:

```text
ece6232beb0600dece7468b47e228f00856dc4131c8bd091dee3b1644fde5b60
```

Şartnameden planı doğrudan etkileyen kararlar:

| Konu | Şartname bulgusu | Plan kararı |
|---|---|---|
| Finansal metin | `llm-fast`, katılım bankacılığı finansal metin analizi ve şema kısıtlı çıktı için öneriliyor (PDF s. 14, 36-37). | Cevap yazımı, sınıflandırma ve kontrollü alan önerilerinde birincil model `llm-fast`. |
| Getirme | `bge-m3-embed` ölçülen en yüksek ilk-isabet sonucuna sahip: R@1 0,95, boyut 1024 (PDF s. 34-43). | Birincil embedding `bge-m3-embed`; yarışma alanındaki kendi golden setimizle ayrıca doğrulanacak. |
| Alternatif embedding | `embed`, ölçümde R@3 1,00 ve boyut 2560 (PDF s. 41). | Yalnız ilk üçte yakalamanın kritik olduğu deneysel rota; varsayılan değil. |
| Rerank | Yoğun getirme + `rerank`, belgede R@1'i 0,95'ten 0,55'e düşürüyor (PDF s. 41-42). | Varsayılan akışa `rerank` eklenmeyecek. Ayrı bir deney geçidi olmadan üretimde açılmayacak. |
| Sparse/ColBERT | Standart `/v1/embeddings` yerine `/pooling/<alias>` gerekiyor; sparse çıktı token sıralı dizidir (PDF s. 41-43, 109-111). | İlk sürüm kapsamı dışında. Sessiz biçim hatasını önlemek için kullanılmayacak. |
| Model adı | Bilinmeyen alias 404 yerine sessizce `llm-fast` hedefine gidiyor (PDF s. 36, 114). | Başlangıçta `/v1/models` doğrulaması ve her yanıtta istenen/sunulan model karşılaştırması zorunlu. |
| Akıl yürütme | `enable_thinking` önerilmiyor; dar token bütçesinde HTTP 200 ile boş çıktı dönebiliyor (PDF s. 44-45, 108). | Her EVREN çağrısında `enable_thinking=false`; boş/yarım çıktı reddedilecek. |
| Matematik | `llm-fast` ve `llm-large` matematikte zayıf (PDF s. 8, 45). | Toplama, oran, sıralama ve uygunluk hesabı yalnız uygulama kodunda yapılacak. |
| Zaman aşımı | İstemci için 1800 saniye öneriliyor; streaming tavsiye ediliyor (PDF s. 46, 107). | Taşıma tavanı 1800 saniye, SSE heartbeat ve ilk-token metriği; kullanıcı deneyimi için canary verisinden ayrı bir ürün son tarihi belirlenecek. |
| Yeniden deneme | Kısa metinde sınırlı retry uygun; uzun video otomatik tekrar edilmemeli (PDF s. 116). | İlk token öncesinde en fazla bir kontrollü retry; token geldikten sonra veya video isteğinde otomatik retry yok. |
| Qdrant | REST, port 443 ve takım `prefix` değeri zorunlu; gRPC yok; Qdrant anahtarı LLM anahtarından farklı (PDF s. 84, 111-113). | Ayrı gizli anahtar, `port=443`, `prefix=teamNN`, REST ve takım izolasyonu zorunlu yapılandırma. |

Detaylı referanslar: [Hızlı Başlangıç](https://evren-teknofest.ssyz.org.tr/hizli-baslangic), [Model Rehberi](https://evren-teknofest.ssyz.org.tr/model-rehberi), [Model Kartları](https://evren-teknofest.ssyz.org.tr/model-kartlari), [Mimari](https://evren-teknofest.ssyz.org.tr/mimari), [Yeniden Üretilebilirlik](https://evren-teknofest.ssyz.org.tr/yeniden-uretilebilirlik), [Sorun Giderme](https://evren-teknofest.ssyz.org.tr/sorun-giderme) ve canlı [servis yoklaması](https://evren-teknofest.ssyz.org.tr/status).

## 3. Hedef mimari

```text
Kullanıcı isteği
      |
      v
Yerel giriş/politika doğrulaması
      |
      +--> Yapılandırılmış finansal sorgu --> SQL + uygulama hesabı
      |
      +--> Semantik sorgu
              |
              +--> 1. EVREN bge-m3-embed + takım Qdrant
              |         başarısız/geçersiz
              +--> 2. Yerel Qwen3-Embedding + Chroma
              |         başarısız/boş
              +--> 3. BM25 + knowledge graph
                            |
                            v
                 Kaynaklı deterministik cevap
                            |
                            +--> 1. EVREN llm-fast ile kaynaklı yazım
                            |         reddedildi/erişilemedi
                            +--> 2. Yapılandırılmış yerel model (opsiyonel)
                            |         reddedildi/erişilemedi
                            +--> 3. Deterministik cevap
                                          |
                                          v
                                SSE ile kesintisiz yanıt
```

Model hiçbir aşamada kaynak gerçekliğinin sahibi değildir. Model yalnızca izin verilen rota, öneri veya cevap metni üretir; kaynak, SQL sonucu, kanıt aralığı, sayısal değer ve kullanıcıya sunulacak son çıktı yerel kod tarafından doğrulanır.

## 4. Yetenek bazlı öncelik ve fallback matrisi

| Yetenek | Birincil | İkinci yol | Son güvenli yol | Zorunlu kapı |
|---|---|---|---|---|
| Sorgu yönlendirme | EVREN `router` | Mevcut intent detector/query compiler | Güvenli tanım veya yönlendirme rotası | Route allowlist, Pydantic şeması |
| Finansal retrieval | `bge-m3-embed` + EVREN Qdrant | Qwen3-Embedding + Chroma | BM25 + knowledge graph | Metadata filtresi, kaynak kimliği, indeks/model sürümü |
| Cevap yazımı | EVREN `llm-fast` | Mevcut yerel OpenAI-uyumlu model | Mevcut deterministik kaynaklı cevap | Kaynak etiketi, sayısal iddia, boş çıktı ve `<think>` kontrolü |
| İçerik güvenliği | EVREN `guard` | Yerel güvenlik ve safe-redirect kuralları | Sabit güvenli yönlendirme | Lokal politika her zaman nihai otorite |
| NLP enrichment | Şema kısıtlı `llm-fast` önerisi | Doğrulanmış classifier + spaCy NER | Mevcut deterministik extraction | Kanıt aralığı, içerik hash'i, provenance ve alan allowlist'i |
| Finansal hesap | Kullanılmaz | Kullanılmaz | Uygulama kodu | Decimal, para birimi, süre ve eksik alan kontrolleri |
| Video, ileriki faz | `vlm`; özet + JSON birlikteyse `llm-large` | Yerel işlem veya kuyruğa alma | Kullanıcıya açıklamalı erteleme | Boyut, süre, modalite ve otomatik retry yasağı |

`llm-large` genel varsayılan olmayacaktır. Yalnız bilgi ağırlıklı, kültürel/tarihsel veya tek çağrıda video + Türkçe özet + JSON gerektiren görevler için açık policy kararıyla seçilecektir.

## 5. İstek yaşam döngüsü

### 5.1 Giriş ve politika

1. Her isteğe `request_id` atanır.
2. Uzunluk, içerik tipi, kaynak limiti ve izin verilen araçlar yerelde doğrulanır.
3. API anahtarı, sistem promptu veya kişisel veri loglanmaz.
4. Yerel güvenlik kuralları modelden önce çalışır. Model bu kuralları gevşetemez.
5. Finansal hesap veya filtre sorguları modele gönderilmeden SQL-first rotasına alınır.

### 5.2 Model ve servis ön kontrolü

- Uygulama başlangıcında ve yapılandırılabilir TTL sonunda `GET /v1/models` çağrılır.
- Gereken aliaslar (`llm-fast`, `router`, `guard`, `bge-m3-embed`) yoksa ilgili devre açık başlar.
- `GET /v1/models` yalnız yapılandırma bilgisidir; canlı sağlık için dokümantasyonun `/status` yoklaması ve gerçek küçük preflight çağrısı birlikte kullanılır.
- Her cevapta `response.model`, istenen alias ile karşılaştırılır. Sessiz `llm-fast` yönlendirmesi yanlış modele atfedilmez.
- Kimlik doğrulama preflight'ı küçük bir metin isteği ve küçük bir embedding isteğiyle yapılır; gizli anahtar çıktıya yazılmaz.

### 5.3 Retrieval

1. Metadata/SQL filtreleri yerelde uygulanır; model filtre uyduramaz.
2. Sorgu `bge-m3-embed` ile 1024 boyutlu yoğun vektöre dönüştürülür.
3. Takım Qdrant koleksiyonu yalnız aynı embedding modeli ve indeks sözleşmesiyle sorgulanır.
4. Sonuçlarda `record_id`, `document_id`, `source_url`, `source_version`, `index_hash`, karakter aralığı, `embedding_provider` ve `embedding_model` bulunması zorunludur.
5. EVREN embedding veya Qdrant başarısızsa aynı sorgu mevcut Qwen/Chroma yoluna gider.
6. Qwen/Chroma da kullanılamıyorsa BM25 + knowledge graph çalışır.
7. `rerank`, sparse ve ColBERT ilk üretim sürümünde devre dışıdır.

EVREN ve yerel embedding uzayları aynı koleksiyonda karıştırılmayacaktır. Model boyutu aynı olsa bile vektörler semantik olarak değiştirilebilir değildir.

### 5.4 Cevap üretimi

1. Mevcut sistem önce kaynaklardan deterministik ve doğrulanmış bir cevap üretir.
2. `llm-fast` yalnız soru, sınırlı kanıt paketi ve doğrulanmış fallback cevabı alır.
3. `temperature=0`, `enable_thinking=false`, `stream=true` ve açık `max_tokens` kullanılır.
4. Gelen metin mevcut doğrulamalardan geçer:
   - boş veya çok kısa cevap yok;
   - `<think>` ve ayrıştırılmamış düşünme izi yok;
   - kaynak varsa geçerli `[K1]` benzeri atıf zorunlu;
   - her sayısal iddia atıf verilen kaynakta bulunmalı;
   - kaynak aralığı dışında yeni oran, tutar, tarih veya koşul üretilemez;
   - yarım SSE veya `finish_reason=length` kabul edilmez.
5. Doğrulama başarısızsa üretilen parçalar kullanıcıya nihai cevap olarak bırakılmaz; `replace` olayıyla deterministik cevap gösterilir.
6. EVREN kullanılamazsa opsiyonel yerel model aynı kapılardan geçer. O da başarısızsa deterministik cevap doğrudan sunulur.

### 5.5 Streaming ve kullanıcı deneyimi

- Mevcut `meta -> delta -> done` sözleşmesi korunur.
- Uzun kuyruklarda bağlantının canlı olduğunu göstermek için içeriksiz SSE heartbeat eklenir.
- İlk token geldikten sonra otomatik retry yapılmaz; mükerrer cevap engellenir.
- Taşıma timeout'u şartnameye uygun 1800 saniyedir. İnteraktif ilk-token ürün son tarihi, canary p95 ölçümü görülmeden sabitlenmez.
- Devre açık veya `/status` sağlıksızsa kullanıcı EVREN çağrısını beklemez; doğrudan yerel zincire alınır.
- `generation` meta verisine geriye uyumlu, opsiyonel alanlar eklenir: `provider`, `requested_model`, `served_model`, `fallback_chain`, `fallback_reason`, `circuit_state` ve `first_token_ms`.

## 6. Devre kesici ve hata politikası

Her yetenek için ayrı devre tutulur: `chat`, `embedding`, `router`, `guard` ve `qdrant`. Bir yeteneğin arızası diğerlerini kapatmaz.

Önerilen başlangıç politikası:

- `401/403`: retry yapılmaz; yapılandırma hatası olarak devre yeniden yüklemeye kadar açılır ve kritik alarm üretilir.
- Alias yok veya yanıt modeli farklı: çıktı reddedilir; ilgili model devresi açılır.
- `429`, bağlantı hatası veya `5xx`: ilk token öncesinde en fazla bir kez, jitter'lı kısa bekleme ve `Retry-After` dikkate alınarak denenir.
- Arka arkaya 3 uygun hata: devre 30 saniye açılır.
- 30 saniye sonunda tek half-open probe yapılır; başarılıysa kapanır, başarısızsa açık süre kademeli artar.
- HTTP 200 + boş içerik, yarım SSE, geçersiz JSON veya desteklenmeyen iddia: ulaşılabilirlik değil çıktı doğrulama hatasıdır; cevap reddedilir ve fallback çalışır.
- Video çağrısı otomatik tekrar edilmez.
- Veri yenileme veya indeksleme başarısızsa son iyi veri/indeks atomik olarak korunur; boş indeks üretime geçirilmez.

| Arıza | Kullanıcıya hizmet | Operasyonel kayıt |
|---|---|---|
| EVREN chat erişilemiyor | Yerel model, sonra deterministik cevap | `fallback_reason=evren_unavailable` |
| EVREN geçersiz cevap | Deterministik doğrulanmış cevap | `fallback_reason=evren_output_rejected` |
| EVREN embedding erişilemiyor | Qwen/Chroma | `retrieval_backend=local_qwen_chroma` |
| EVREN Qdrant erişilemiyor | Qwen/Chroma, sonra BM25 | Qdrant hata sınıfı ve circuit state |
| Qwen/Chroma da erişilemiyor | BM25 + graph | `retrieval_backend=bm25_graph_fallback` |
| Bütün modeller kapalı | Kaynaklı deterministik cevap | Kullanıcıya uyarı, HTTP 200 |
| Aktif SQLite bozuk/erişilemiyor | Son iyi salt-okunur snapshot | Kritik alarm; yeni veri yazımı durur |
| Kaynak bulunamıyor | Güvenli "kaynakta bulunamadı" cevabı | Halüsinasyon yerine `evidence_not_found` |

## 7. İndeks ve veri geçişi

### 7.1 Çift indeks

- EVREN koleksiyonu: `bge-m3-embed`, 1024 boyut, cosine, takım Qdrant.
- Yerel koleksiyon: mevcut Qwen3-Embedding + Chroma; aynen korunur.
- Her belge iki bağımsız indeks kuyruğuna yazılır. Başarı durumu belge ve sağlayıcı bazında tutulur.
- `index_hash` değişmeyen doküman yeniden embed edilmez.
- Yeni EVREN koleksiyonu tam dolmadan birincil okunmaz.
- Aktif doküman sayısı, benzersiz `document_id`, kaynak sürümü ve silinen/stale kayıt sayısı yerel indeksle karşılaştırılır.
- Silme önce tombstone olarak işaretlenir; her iki indeks güncellendikten sonra fiziksel temizlik yapılır.

### 7.2 Koleksiyon sözleşmesi

Koleksiyon adı model ve tarih ailesini açıkça belirtmelidir; örnek:

```text
katilim_campaigns_bge_m3_202608
```

Zorunlu payload alanları:

```text
document_id, record_id, bank_slug, product_type, financing_type,
source_url, source_version, index_hash, source_start, source_end,
embedding_provider, embedding_model, embedding_dimensions, indexed_at
```

Qdrant yapılandırması yalnız ortam değişkenlerinden veya secret store'dan alınır. Takım yolu URL'ye elle eklenmez; `prefix` parametresiyle verilir. REST ve port 443 zorunludur, gRPC kapalıdır.

## 8. Yapılandırma taslağı

Gizli değer içermeyen önerilen değişkenler:

```dotenv
RAGNROLL_GENERATION_PROVIDER_ORDER=evren,local,deterministic
RAGNROLL_RETRIEVAL_PROVIDER_ORDER=evren_qdrant,local_qwen_chroma,bm25_graph

EVREN_LLM_BASE_URL=https://evren-llmapi.ssyz.org.tr/v1
EVREN_LLM_MODEL=llm-fast
EVREN_CONNECT_TIMEOUT=5
EVREN_READ_TIMEOUT=1800
EVREN_MODELS_CACHE_TTL=300

EVREN_QDRANT_URL=https://evren-vektor.ssyz.org.tr
EVREN_QDRANT_PORT=443
EVREN_QDRANT_PREFIX=teamNN

RAGNROLL_EVREN_CIRCUIT_FAILURE_THRESHOLD=3
RAGNROLL_EVREN_CIRCUIT_OPEN_SECONDS=30
RAGNROLL_EVREN_MAX_PRETOKEN_RETRIES=1
```

Secret store dışında tutulmaması gereken değerler:

```text
EVREN_API_KEY
EVREN_QDRANT_API_KEY
```

Compose dosyasında gerçek anahtar, örnek anahtar veya varsayılan token bulunmayacaktır. Uygulama eksik anahtarla açılabilir; EVREN devresi `disabled/misconfigured` görünür ve yerel fallback hizmet verir.

## 9. Kod değişikliği haritası

| Alan | Önerilen değişiklik |
|---|---|
| `src/llm/client.py` | Tek sağlayıcı istemcisini sağlayıcı arayüzü, EVREN istemcisi, model doğrulaması, hata sınıfları ve stream metadata ile genişlet. |
| `src/services/assistant.py` | Sağlayıcı sırası, yetenek bazlı fallback, EVREN çıktı reddi ve ek generation metadata alanlarını ekle. Mevcut doğrulanmış fallback'i aynen koru. |
| `src/retrieval/evren.py` | `bge-m3-embed` istemcisi, boyut/model kontrolü ve sınırlı batch desteği. |
| `src/retrieval/qdrant.py` | Takım prefix'li REST istemcisi, payload sözleşmesi, health ve collection doğrulaması. |
| `src/retrieval/hybrid.py` | EVREN Qdrant -> Qwen/Chroma -> BM25/graph sırası ve ayrıntılı backend nedeni. |
| `src/retrieval/chroma.py` | Yerel fallback olarak korunur; EVREN vektörleriyle koleksiyon paylaşmasını engelleyen model sözleşmesi sürdürülür. |
| `src/query/` | `router` çıktısı için allowlist/şema; başarısızlıkta mevcut compiler. SQL-first otoritesi değişmez. |
| `src/nlp_runtime/` | EVREN önerilerini mevcut advisory sözleşmesine bağla; provenance/hash doğrulamasını gevşetme. |
| `src/observability/events.py` | Sağlayıcı, alias, devre, retry, ilk-token, fallback ve doğrulama metrikleri; içerik ve secret yok. |
| `src/api/main.py` | `/llm/status` yerine geriye uyumlu capability matrisi ve SSE heartbeat. |
| `docker-compose.yml` | Secret'sız EVREN ve provider-order değişkenleri; yerel fallback varsayılanları korunur. |
| `requirements.txt` | Tam sürümü sabitlenmiş `qdrant-client`; `pip check` ve container contract ile doğrulama. |
| `tests/` | Sağlayıcı sözleşmesi, failure injection, dual-index, fallback ve canlı opt-in testleri. |

Yeni modüller işlev odaklı adlandırılacak; sürüm eki kullanılmayacaktır.

## 10. Uygulama fazları

### Faz 0 - Baseline ve erişim doğrulaması

- Takım LLM ve Qdrant anahtarlarının secret store'da bulunduğunu doğrula.
- `/status`, `/v1/models`, küçük `llm-fast` çağrısı, küçük `bge-m3-embed` çağrısı ve Qdrant takım izolasyonu için preflight çalıştır.
- Mevcut Qwen ve BM25 golden sonuçlarını, kaynak doğruluğunu, p50/p95'i ve fallback oranını kaydet.
- EVREN dokümanındaki genel R@1 sonucu kendi katılım bankacılığı verimiz için kanıt sayılmaz; kendi golden setimizle karşılaştır.

Çıkış kriteri: Anahtarlar loglanmadan bütün preflight kontrolleri geçer ve baseline raporu üretilir.

### Faz 1 - Sağlayıcı ve dayanıklılık temeli

- Provider arayüzü, EVREN hata taksonomisi, model alias doğrulaması ve yetenek bazlı circuit breaker ekle.
- Mevcut tek LLM yapılandırmasını geriye uyumlu sağlayıcı sırasına dönüştür.
- Status/capability çıktısını ve içeriksiz metrikleri ekle.
- EVREN kapalıyken mevcut 425 testlik davranışın değişmediğini doğrula.

Çıkış kriteri: Ağ tamamen kapalıyken bütün chatbot ve retrieval sözleşmeleri mevcut fallback ile geçer.

### Faz 2 - EVREN `llm-fast` birincil cevap yazımı

- Önce shadow modunda aynı kanıt paketini EVREN'e gönder; kullanıcıya mevcut cevap gösterilir.
- Kaynak etiketi, sayısal iddia ve boş/yarım çıktı ret oranlarını ölç.
- Ardından küçük bir canary grubunda EVREN çıktısını kullanıcıya aç.
- Yerel model ve deterministik cevap tek işlemde geri alınabilir şekilde hazır kalır.

Çıkış kriteri: Desteksiz sayısal iddia yok, geçerli kaynak etiketi oranı en az %99, kritik golden sorgularda regresyon yok.

### Faz 3 - EVREN embedding ve Qdrant birincil retrieval

- `bge-m3-embed` ve takım Qdrant istemcilerini ekle.
- Aktif korpusu ayrı EVREN koleksiyonuna idempotent biçimde yükle.
- Shadow sorgularda EVREN, Qwen ve BM25 sonuçlarını karşılaştır.
- Domain golden sette R@1, R@3, MRR, kritik madde kaçırma ve kaynak çeşitliliğini ölç.
- Cutover sonrasında Qwen/Chroma indeksi sürekli güncel tutulur.

Çıkış kriteri: EVREN retrieval kritik sorgularda Qwen baseline'ından kötü değildir; indeks sayısı/hash eşitliği ve zorunlu payload alanları tamdır.

### Faz 4 - Router, guard ve enrichment

- `router` yalnız izinli rota seçimi için kullanılır; SQL-first ve güvenlik otoritesi yerelde kalır.
- `guard` sonucu yerel politikanın üzerine ek sinyal olur, yerel yasağı kaldıramaz.
- `llm-fast` enrichment çıktısı yalnız kanıt aralıklı advisory öneri olarak kabul edilir.
- Classifier + NER çalışmaya devam eder ve EVREN yokken aynı sözleşmeyi doldurur.

Çıkış kriteri: Geçersiz rota/alan enjeksiyonu testleri geçer; authoritative structured alanlarda kanıtsız mutasyon yoktur.

### Faz 5 - Kademeli üretim geçişi

Önerilen sıra:

1. Shadow trafik, kullanıcı çıktısı %0 EVREN.
2. İç ekip/canary %5.
3. Trafik %25.
4. Trafik %50.
5. Trafik %100, yerel fallback sıcak tutulur.

Her basamak en az bir yoğun ve bir sakin kullanım penceresi görmeden ilerletilmez. Geçiş yalnız ortam değişkeni/feature flag ile geri alınabilir; veri şeması rollback'i gerektirmemelidir.

## 11. Test ve kabul planı

### 11.1 Sözleşme ve birim testleri

- `/v1/models` alias doğrulaması ve sessiz model değiştirme tespiti.
- 401, 403, 404, 429, 5xx, DNS, connect/read timeout ve bozuk JSON.
- HTTP 200 + boş içerik + `finish_reason=length`.
- SSE ilk token öncesi kopma, token sonrası kopma ve duplicate delta.
- `response.model` uyuşmazlığı.
- Embedding boyutu 1024 dışında olduğunda ret.
- Qdrant prefix/443/REST zorunluluğu ve 403 takım izolasyonu.
- EVREN -> Qwen -> BM25 sırasının deterministik çalışması.
- EVREN -> yerel model -> deterministik cevap sırasının çalışması.
- Circuit open/half-open/closed geçişleri ve eşzamanlı istek güvenliği.

### 11.2 Güvenlik testleri

- Prompt injection içeren kampanya metni model sistem talimatını değiştiremez.
- Model, olmayan kaynak numarası veya sayısal değer eklediğinde cevap reddedilir.
- API anahtarları exception, log, metric, OpenAPI ve dashboard içinde görünmez.
- Qdrant takım prefix'i kullanıcı girdisinden alınamaz.
- Outbound host allowlist yalnız resmi EVREN LLM, vektör ve durum hostlarını içerir.
- Kullanıcı mesajları varsayılan olarak kalıcı model loguna yazılmaz.

### 11.3 Domain değerlendirmesi

Mevcut golden set iki sağlayıcıyla aynı anda çalıştırılacaktır:

- Retrieval: R@1, R@3, MRR, banka dengesi, kritik koşul ve kaynak URL doğruluğu.
- Cevap: kaynak desteği, sayısal iddia doğruluğu, eksik bilgi dürüstlüğü, Türkçe açıklık.
- Operasyon: ilk-token p50/p95, toplam p50/p95, hata, retry ve fallback oranı.
- Tekrarlanabilirlik: en az üç çalıştırma; alias, seed, temperature, soğuk/sıcak ayrımı ve medyan raporu.

Promosyon eşikleri:

- Desteksiz kritik finansal iddia: 0.
- Kaynaksız model cevabı kullanıcıya geçişi: 0.
- Kritik golden sorgu kaybı: 0.
- Geçerli model cevabı: en az %99.
- EVREN retrieval domain R@1: Qwen baseline'ından en fazla 2 puan düşük olabilir; kritik sorgularda düşüş olamaz.
- Fallback başarı oranı: %100; EVREN kesildiğinde kullanıcı geçerli bir nihai cevap alır.

### 11.4 Canlı kabul

Anahtar gerektiren canlı testler varsayılan CI'da çalışmaz; yalnız korumalı ortamda opt-in çalışır:

1. Küçük `/v1/models` ve `llm-fast` preflight.
2. Bir kısa katılım bankacılığı sorusuna kaynaklı streaming cevap.
3. Bir sorgu ve bir doküman için `bge-m3-embed` boyut/model kontrolü.
4. Qdrant'a tek test kaydı yaz/oku/sil ve takım izolasyonu kontrolü.
5. EVREN bağlantısını keserek aynı sorgunun Qwen'e düştüğünü kanıtlama.
6. Qwen'i de kapatarak BM25/graph ve deterministik cevabı kanıtlama.
7. Gerçek dashboard chatbot akışında kaynaklar, fallback uyarısı ve yeni sohbet davranışı.

## 12. Gözlemlenebilirlik ve alarm

İçerik kaydetmeden aşağıdaki metrikler tutulacaktır:

- `provider_request_total{capability,provider,model,outcome}`
- `provider_latency_ms` ve `provider_first_token_ms`
- `provider_model_mismatch_total`
- `provider_output_rejected_total{reason}`
- `fallback_total{from,to,reason}`
- `circuit_state{capability,provider}`
- `retrieval_hit_total{backend}`
- `index_documents{provider,model}` ve `index_stale_total`
- `qdrant_operation_total{operation,outcome}`

Alarm önerileri:

- Herhangi bir desteklenmeyen kritik finansal iddia: anında EVREN generation kapatma.
- Model alias uyuşmazlığı veya 401/403: kritik alarm, retry yok.
- Beş dakikada EVREN hata oranı > %10: ilgili devreyi aç ve yerel fallback'e geçir.
- EVREN çıktı ret oranı > %5: canary artışını durdur.
- Qdrant/yerel indeks belge sayısı veya aktif hash farkı: cutover'ı durdur.
- Yerel fallback başarısızlığı: P0; kesintisiz hizmet garantisi bozulur.

## 13. Rollback

Rollback tek yapılandırma değişikliğiyle yapılabilmelidir:

```dotenv
RAGNROLL_GENERATION_PROVIDER_ORDER=local,deterministic
RAGNROLL_RETRIEVAL_PROVIDER_ORDER=local_qwen_chroma,bm25_graph
```

- EVREN Qdrant koleksiyonu rollback sırasında silinmez; yalnız okunmaz.
- Qwen/Chroma ve BM25 indeksleri bütün rollout boyunca güncel tutulur.
- Mevcut API cevap alanları korunur; yeni alanlar opsiyoneldir.
- Veri yenilemede son iyi SQLite snapshot ve iki indeks korunur.
- Rollback için yeniden embedding, veri geri yükleme veya kullanıcı oturumu sıfırlama gerekmez.

## 14. Teslim sırası ve PR sınırları

Hızlı ve düşük riskli ilerleme için çalışma şu PR'lara ayrılmalıdır:

1. **EVREN provider temeli:** ayarlar, secret sözleşmesi, model discovery, hata taksonomisi, circuit breaker ve metrikler.
2. **EVREN generation:** `llm-fast`, streaming, doğrulama kapıları, yerel/deterministik fallback ve canary flag.
3. **EVREN retrieval:** `bge-m3-embed`, Qdrant, çift indeks, shadow eval ve Qwen/BM25 fallback.
4. **Router/guard/enrichment:** advisory entegrasyon ve şema/provenance güvenliği.
5. **Operasyon ve kabul:** dashboard durum görünümü, runbook, failure injection, opt-in canlı kabul ve rollout otomasyonu.

Her PR bağımsız olarak geri alınabilir olmalı; bir PR diğerinin yarım uygulanmış hâline ihtiyaç duymamalıdır. İlk üç PR tamamlanmadan üretim trafiği EVREN'e çevrilmemelidir.

## 15. Tamamlanmış sayılma ölçütü

Çalışma ancak aşağıdakilerin tamamı kanıtlandığında bitmiş sayılır:

- EVREN sağlıklıyken generation ve retrieval trafiği gerçekten EVREN'i birincil kullanıyor.
- İstenen ve sunulan model aliası her çağrıda doğrulanıyor.
- EVREN tamamen kapatıldığında aynı kullanıcı akışı Qwen/Chroma, ardından BM25/graph ve deterministik cevapla tamamlanıyor.
- EVREN ve yerel indeksler ayrı embedding sözleşmeleriyle idempotent güncelleniyor.
- Model hiçbir kanıtsız finansal oran, tutar, tarih veya koşulu kullanıcıya geçiremiyor.
- Secret, log ve metric güvenlik kontrolleri geçiyor.
- Backend testleri, lint, dashboard test/lint/build, container contract ve canlı API + tarayıcı kabulü başarılı.
- Canary metrikleri promosyon eşiklerini sağlıyor ve tek adımlı rollback gerçek ortamda denenmiş durumda.
