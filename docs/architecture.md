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
      ├──► doğrulanmış sınıflandırıcı + NER ──► yalnız eksik alan önerileri
      ├──► SQL-first sorgu ve karşılaştırma
      └──► semantik chunking
                    │
                    ▼
       EVREN bge-m3 + takım Qdrant (birincil)
                    │
          Qwen/Chroma + BM25 + graph fallback
                    │
                    ▼
             Kanıt paketli yanıt
                    │
           ┌────────┴─────────┐
           ▼                  ▼
 EVREN llm-fast yazımı   yerel model / deterministik fallback
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
4. **Regresyon Eval:** Dondurulmuş referans setiyle intent ve desteklenen çıkarım
   alanları tekrar üretilebilir biçimde proxy olarak ölçülür. Bağımsız insan gold
   holdout'u henüz sağlanmamıştır.

SQLite güncel görünümü tutar; `record_versions` tablosu içerik değişimini
`valid_from`, `valid_to`, `superseded_by` ve tekrar görülme sayısıyla saklar.
Sınıflandırıcı ve NER çıktısı otoriter `structured` alanları değiştirmez;
kanıt aralıklı öneriler üst düzey `nlp_analysis` altında atomik saklanır.
Yapılandırılmış sorular SQL rotasına, tanım/koşul soruları retrieval rotasına,
şikâyet ve işlem talepleri güvenli yönlendirmeye gider.

Ana cevap motoru ağ veya model servisi olmadan çalışır. Uzun kampanyalar kaynak
karakter aralıklarını koruyan semantik pencerelere ayrılır. Qwen doküman
embeddingleri yalnız `index_hash` değiştiğinde üretilir; sorgu embeddingi ise her
istekte aynı model ve sorgu talimatıyla hesaplanır. Chroma indeksi boş, yapım
aşamasında, model/şema açısından uyumsuz veya erişilemezse BM25 geri dönüşü
devreye girer.

EVREN erişim bilgileri sağlandığında retrieval sırası takım-izole Qdrant üzerinde
`bge-m3-embed`, yerel Qwen/Chroma ve BM25 + knowledge graph şeklindedir. EVREN ve
Qwen vektörleri aynı koleksiyonda karıştırılmaz. EVREN koleksiyonu `prefix=teamNN`,
REST ve TCP 443 sözleşmesiyle kullanılır; gRPC kapalıdır. Uzak indeks eksik, yapım
aşamasında veya model/şema bakımından uyumsuzsa yerel indeks doğrudan devreye girer.

BM25 ve Chroma sıralamaları reciprocal-rank fusion ile kampanya düzeyinde
birleştirilir; aynı kampanyanın birden fazla parçası kaynak listesini işgal etmez.
Mevcut kaynaklı ontoloji graph'ı yalnız belge, koşul, teminat ve ilişki sorularında
en fazla iki adımlı komşuluk aramasına açılır. Basit tanım ve kampanya sorguları
graph maliyeti taşımaz.

Değişmeyen doküman korpusu ve tokenize BM25 girdileri süreç içinde önbellekte
tutulur; SQLite veya ontoloji dosyası değiştiğinde önbellek kendini yeniler.
Tekrarlanan query embeddingleri 256 girdilik sınırlı LRU önbelleği kullanır.
Hazır indeksle API açılışında Qwen query modeli ısıtılarak ilk kullanıcı
isteğindeki model yükleme gecikmesi kaldırılır.

EVREN `llm-fast`, sağlıklı ve tam alias doğrulamasından geçmişse birincil cevap
yazarıdır. EVREN kullanılamaz veya çıktısı reddedilirse yerel model aynı kapılardan
geçer; son güvenli yol deterministik cevaptır. Her yetenek kendi circuit breaker
durumuna sahiptir ve bir EVREN arızası diğer yetenekleri kapatmaz.

Yerel Gemma, vLLM'in OpenAI uyumlu Chat Completions akışı üzerinden yalnız `facts` ve
`sources` paketini profesyonel Türkçe cevaba dönüştürür. Model sorgu planı üretmez,
SQL çalıştırmaz ve sayısal olgu bulmaz. Kaynaksız, boş, yarım veya geçersiz kaynak
etiketli üretim `replace` olayıyla geri alınır ve deterministik cevap gösterilir.

Prompt optimizasyonu canlı istek yolunda değildir. Bu değişiklik yalnız
source-family-safe, provenance etiketli örnek ve proxy değerlendirme sözleşmesini
sağlar; optimizer çalışması veya seçilmiş üretim promptu içermez.
