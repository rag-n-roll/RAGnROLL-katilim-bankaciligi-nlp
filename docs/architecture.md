# Mimari

Platform, kaynak metni kaybetmeden yapılandırılmış ve denetlenebilir bir bilgi
ürününe dönüştürür.

```text
Resmî kaynaklar
      │
      ▼
Toplama ve doğrulama ──► ham kayıt
      │
      ▼
Temizleme ──► hash / tekrar kümesi / kaynak sürümü
      │
      ▼
Alan çıkarımı ──► değer + durum + güven + kanıt
      │
      ├──► SQL-first sorgu ve karşılaştırma
      └──► BM25 + ontoloji retrieval
                    │
                    ▼
             Kanıt paketli yanıt
                    │
                    ▼
              API ve dashboard
```

## Katmanlar

1. **Bronze:** Kaynak URL, ham başlık/metin ve çekim zamanı değişmeden korunur.
2. **Silver:** Unicode/boşluk temizliği, tokenizasyon, canonical URL, exact hash,
   simhash ve banka içi near-duplicate kümesi üretilir.
3. **Gold:** Finansman, oran, tutar, vade, avantaj, koşul ve kanal alanları
   tipli sözleşmeyle sunulur.
4. **Gold Eval:** İnsan doğrulamalı Golden Set ile intent ve desteklenen çıkarım
   alanları tekrar üretilebilir biçimde ölçülür.

SQLite güncel görünümü tutar; `record_versions` tablosu içerik değişimini
`valid_from`, `valid_to`, `superseded_by` ve tekrar görülme sayısıyla saklar.
Yapılandırılmış sorular SQL rotasına, tanım/koşul soruları retrieval rotasına,
şikâyet ve işlem talepleri güvenli yönlendirmeye gider.

Ana cevap motoru ağ veya model servisi olmadan çalışır. İsteğe bağlı üretim
modeli yalnız `facts` ve `sources` paketini sözele dökebilir; sayısal olgu
üretme yetkisi yoktur.
