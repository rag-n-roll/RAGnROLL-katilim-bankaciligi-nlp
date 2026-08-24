# Değerlendirme

Dondurulmuş regresyon seti 500 örnek içerir. Ölçüm, model eğitmeden çalışan intent
derleyici ve alan çıkarım sözleşmesini aynı veri üzerinde tekrar üretir. Dosyanın
bağımsız insan yazımı/ikinci inceleme lineage manifesti yoktur; aşağıdaki sonuçlar
sözleşme regresyonu için proxy'dir ve bağımsız gold ya da yarışma performansı
olarak raporlanmamalıdır.

2026-08-22 yerel doğrulama sonucu:

| Proxy ölçüt | Sonuç | Regresyon eşiği | Durum |
| --- | ---: | ---: | --- |
| Intent exact match | %91,11 (164/180) | %85 | Geçti |
| Desteklenen çıkarım alanı exact match | %97,32 (436/448) | %82 | Geçti |
| Backend satır kapsamı | %82,05 | %70 | Geçti |

Komut:

```bash
python -m src.evaluation.golden \
  data/model_training_data/golden_evaluation_set.jsonl
pytest -q --cov=src --cov-report=term --cov-fail-under=70
```

Skor kapsamı şeffaftır. `campaign`, `end_date`, `bank`, `product`, `trade_term`,
`document`, `organization` ve serbest `entities` referans alanları mevcut çıkarım
sözleşmesinde desteklenmiyorsa başarı paydasına eklenmez; adetleri
`unsupported_gold_fields` altında raporlanır. Bu alanlar tamamlanmadan tam alan
kapsamı iddiası yapılmamalıdır. Eğitim/prompt verilerinin güncel digest,
provenance ve bağımsız-gold durumu
[eğitim verisi sözleşmesinde](training-data-contract.md) açıklanır.

Edge testleri oran yazım varyantı, indirim-oran ayrımı, ödül-finansman tutarı
ayrımı, çelişkili oran, typed missingness, kanıt offseti, farklı banka tekrar
izolasyonu, zamansal sürümleme, sorgu yönlendirme, anlamsal parçalama, yalnız
değişen parçaların indekslenmesi, stale parça temizliği, graph genişletme ve API
sınırlarını kapsar.
