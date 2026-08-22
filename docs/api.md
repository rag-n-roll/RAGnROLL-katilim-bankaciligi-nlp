# API rehberi

Tüm yeni sözleşme uçları `api_version` ve benzersiz `request_id` döndürür.
OpenAPI şeması çalışma anında `/openapi.json`, etkileşimli arayüz `/docs`
adresindedir.

## Çıkarım

`POST /api/v1/extract`

```json
{
  "text": "%1,89 kâr payı ile 24 ay vadeli konut finansmanı."
}
```

Yanıt, geriye uyumlu scalar değerlerin yanında `extraction.fields` içinde durum,
güven, yöntem ve karakter aralıklı kanıtı taşır. Çelişki veya ayrıştırma hatası
`warnings` alanına eklenir.

## Sorgu ve sohbet

`POST /api/v1/query/compile` sorguyu intent, canonical sorgu, slot, filtre,
terminoloji eşlemesi ve yürütme rotasına çevirir.

`POST /api/v1/chat` yanıtla birlikte:

- kullanılan facts,
- tıklanabilir kaynak URL veya terminoloji kimliği,
- güven skoru,
- açık uyarılar,
- yürütülen sorgu planı döndürür.

`SAFE_REDIRECT` rotası müşteri işlemi veya şikâyet kaydı yapmaz.

## Karşılaştırma

`POST /api/v1/compare`, `product_type` ve `currency` alanlarını zorunlu tutar.
Her adayda normalleştirilmiş skor, kullanılan kriterler, eksik kriterler ve
Türkçe sıralama gerekçesi bulunur. Eksik değerler sıfır kabul edilmez.

## Sınırlar

- Kampanya sayfalama limiti: 1–100
- Sohbet kaynak limiti: 1–10
- Karşılaştırma limiti: 2–500
- Sorgu uzunluğu: en fazla 2.000 karakter
- Sohbet mesajı: en fazla 4.000 karakter
- Çıkarım metni: en fazla 100.000 karakter
