# Operasyon rehberi

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

Chroma koleksiyonunun embedding modeli değiştirildiyse aynı koleksiyona farklı
boyutlu vektör yazmayın. Yeni koleksiyon adı verin veya mevcut indeksi kontrollü
biçimde yeniden kurun. İndeksleyici `upsert` kullanır ve artık kaynakta olmayan
kimlikleri başarılı yüklemenin sonunda temizler.

GEPA optimizasyonunu yalnız vLLM sağlıklıyken çalıştırın:

```bash
python -m scripts.optimize_assistant_prompt --dry-run
python -m scripts.optimize_assistant_prompt --max-metric-calls 24
```

Varsayılan bütçe de 24 metrik çağrısıdır. Daha uzun deneyler için
`--auto light`, `--auto medium` veya `--auto heavy` seçeneklerinden yalnız biri
kullanılabilir. Aynı veri, model ve bütçe birleşimi yarım kalırsa çalışma kendi
parmak izine ait günlük dizininden sürdürülür; `--log-dir` ile bu dizin açıkça
seçilebilir.

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
