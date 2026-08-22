# Değerlendirme

Dondurulmuş Golden Set 500 örnek içerir. Ölçüm, model eğitmeden çalışan intent
derleyici ve alan çıkarım sözleşmesini aynı veri üzerinde tekrar üretir.

2026-08-22 yerel doğrulama sonucu:

| Ölçüt | Sonuç | Eşik | Durum |
| --- | ---: | ---: | --- |
| Intent exact match | %91,11 (164/180) | %85 | Geçti |
| Desteklenen çıkarım alanı exact match | %97,32 (436/448) | %82 | Geçti |
| Backend satır kapsamı | %80 | %70 | Geçti |

Komut:

```bash
python -m src.evaluation.golden \
  data/model_training_data/golden_evaluation_set.jsonl
pytest -q --cov=src --cov-report=term --cov-fail-under=70
```

Skor kapsamı şeffaftır. `campaign`, `end_date`, `bank`, `product`, `trade_term`,
`document`, `organization` ve serbest `entities` gold alanları mevcut çıkarım
sözleşmesinde desteklenmiyorsa başarı paydasına eklenmez; adetleri
`unsupported_gold_fields` altında raporlanır. Bu alanlar tamamlanmadan tam alan
kapsamı iddiası yapılmamalıdır.

Edge testleri oran yazım varyantı, indirim-oran ayrımı, ödül-finansman tutarı
ayrımı, çelişkili oran, typed missingness, kanıt offseti, farklı banka tekrar
izolasyonu, zamansal sürümleme, sorgu yönlendirme ve API sınırlarını kapsar.
