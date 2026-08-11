# Hafta 3 Backend API

Kutay Orallı'nın Hafta 3 backend teslimi; dashboard veri servisini,
açıklanabilir kampanya karşılaştırmasını ve kontrollü veri yenilemeyi FastAPI
altında birleştirir.

## Çalıştırma

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Varsayılan SQLite yolu `data/ragnroll.sqlite3` değeridir. Farklı bir dosya için
`RAGNROLL_DB_PATH`, dashboard origin'leri için virgülle ayrılmış
`RAGNROLL_CORS_ORIGINS` ortam değişkeni kullanılabilir.

OpenAPI arayüzü servis çalışırken `http://localhost:8000/docs` adresindedir.

## Endpointler

| Metot | Yol | Amaç |
| --- | --- | --- |
| GET | `/api/v1/health` | API ve SQLite hazır olma kontrolü |
| GET | `/api/v1/dashboard/summary` | Dashboard sayaçları ve son scraper koşusu |
| GET | `/api/v1/banks` | Banka bazlı kampanya/ürün sayıları |
| GET | `/api/v1/campaigns` | Filtreli ve sayfalı kampanya listesi |
| GET | `/api/v1/campaigns/{id}` | Kampanya detayı |
| POST | `/api/v1/comparisons` | Ağırlıkları ve gerekçeleriyle karşılaştırma |
| POST | `/api/v1/data-refresh` | Arka planda veri toplama işi başlatma |
| GET | `/api/v1/data-refresh/{id}` | Veri toplama işinin durumunu sorgulama |

Kampanya listesi `bank_slug`, `product_type`, `currency`, `search`, `limit` ve
`offset` parametrelerini destekler. Filtreleme, sayfalama ve dashboard
agregasyonları SQLite içinde yapılır; tüm veri seti API belleğine taşınmaz.

Karşılaştırma isteği en fazla 500 aday kabul eder. Daha geniş sonuç kümelerinde
API, istemciden banka veya ürün filtresini daraltmasını ister. Veri yenileme
servisi de eş zamanlı yalnızca tek scraper işi çalıştırır; ikinci istek `409`
döner.

## Örnek karşılaştırma

```bash
curl -X POST http://localhost:8000/api/v1/comparisons \
  -H 'Content-Type: application/json' \
  -d '{"product_type":"financing","currency":"TRY","amount":100000}'
```

## Doğrulama

```bash
pytest tests/test_api.py tests/test_persistence.py tests/test_comparison.py -q
flake8 src tests --max-line-length=100 --extend-ignore=E203
```
