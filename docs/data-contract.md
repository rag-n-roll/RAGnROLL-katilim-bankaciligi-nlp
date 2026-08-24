# Veri sözleşmesi

Her kayıt ham ve işlenmiş görünümü birlikte taşır. Kalıcı kimlik kaynak URL'den,
içerik değişimi başlık ve metnin canonical hash'inden izlenir.

## Alan nesnesi

```json
{
  "raw": "%1,89 kâr payı",
  "value": 0.0189,
  "unit": "RATIO",
  "status": "EXPLICIT",
  "confidence": 0.99,
  "evidence": {
    "text": "%1,89 kâr payı",
    "char_start": 12,
    "char_end": 28
  },
  "method": "rules-v1",
  "conflicting_values": []
}
```

Durumlar:

- `EXPLICIT`: değer kaynak metinde ve kanıt aralığı mevcut.
- `IMPLICIT`: değer kaynak metadata veya açık bağlamdan geliyor; metin aralığı yok.
- `NOT_STATED`: kaynak alan hakkında bilgi vermiyor.
- `NOT_APPLICABLE`: alan ilgili ürün türüne uygulanmıyor.
- `EXTRACTION_FAILED`: kaynak alanı anıyor ancak güvenli değer çıkarılamıyor.
- `CONFLICT`: kaynakta aynı alan için birden fazla farklı değer var; scalar değer
  boş bırakılır ve adaylar `conflicting_values` içinde tutulur.

Eksik değerler sıfır veya boş metinle doldurulmaz. Para değerleri tutar ve ISO
para birimiyle, oranlar 0–1 aralığında, vadeler ay ve yaklaşık gün bilgisiyle
saklanır.

## Köken ve tekrar

- `canonical_url`: izleme parametrelerinden arındırılmış kaynak adresi
- `content_hash`: Unicode ve boşluk farklarına dayanıklı exact içerik izi
- `duplicate_fingerprint`: 64 bit simhash
- `duplicate_cluster_id`: yalnız aynı banka içindeki yakın kayıt kümesi
- `source_version`: içerik değiştikçe artan kayıt sürümü
- `valid_from` / `valid_to`: sürüm geçerlilik aralığı
