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
      └──► Chroma + çok dilli embedding + BM25 + ontoloji retrieval
                    │
                    ▼
             Kanıt paketli yanıt
                    │
           ┌────────┴─────────┐
           ▼                  ▼
    Gemma cevap yazımı   yerel fallback
           └────────┬─────────┘
                    ▼
             Streaming API
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

Ana cevap motoru ağ veya model servisi olmadan çalışır. Chroma indeksi mevcutsa
semantik sonuçlar BM25 sıralamasıyla birleştirilir; indeks boş, uyumsuz veya
erişilemezse BM25 geri dönüşü devreye girer.

Gemma, vLLM'in OpenAI uyumlu Chat Completions akışı üzerinden yalnız `facts` ve
`sources` paketini profesyonel Türkçe cevaba dönüştürür. Model sorgu planı üretmez,
SQL çalıştırmaz ve sayısal olgu bulmaz. Kaynaksız, boş, yarım veya geçersiz kaynak
etiketli üretim `replace` olayıyla geri alınır ve deterministik cevap gösterilir.

DSPy GEPA canlı istek yolunda değildir. Değerlendirme örnekleri ve metinsel geri
bildirim metriğiyle istem talimatını çevrimdışı iyileştirir; seçilen profil çalışma
zamanında sade bir yapılandırma dosyasından yüklenir.
