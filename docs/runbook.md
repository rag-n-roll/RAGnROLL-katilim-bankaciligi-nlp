# Operasyon rehberi

## Sağlık kontrolü

```bash
curl --fail http://localhost:8000/api/v1/health
curl --fail http://localhost:8000/api/v1/metrics/summary
```

Dashboard API'ye erişemiyorsa `NEXT_PUBLIC_API_BASE_URL` değerini ve API'nin
`RAGNROLL_CORS_ORIGINS` listesini kontrol edin.

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
