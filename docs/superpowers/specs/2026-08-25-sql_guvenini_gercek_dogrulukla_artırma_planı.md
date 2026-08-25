# SQL Güvenini Gerçek Doğrulukla Artırma Planı

> **Durum: Birleşik plana alındı.** Bu belge bağımsız uygulanmamalıdır. İçeriği,
> `docs/superpowers/plans/2026-08-25-pusula-ai-birlesik-dogruluk-guardrails.md`
> belgesinin özellikle Görev 3, Görev 6 ve Görev 11 bölümlerine bağımlılık sırasıyla
> taşınmıştır. Birleşik plan tek uygulama kaynağıdır.

## Özet

`%55`, SQL motorunun başarısızlığı değil; hiçbir intent kalıbı eşleşmeyince `product_search` için verilen fallback değeridir. Bu intent yanlışlıkla `STRUCTURED_SQL` rotasına girdiği için düşük skor görünmektedir.

Amaç skoru yapay yükseltmek değil, SQL rotasını ölçülebilir sorgularla sınırlayıp gerçek güveni en az `%85` doğrulukla kalibre etmektir.

## Ana değişiklikler

- [compiler.py](C:/Users/kuti/Desktop/ii/RAGnROLL-katilim-bankaciligi-nlp/src/query/compiler.py)
  - `product_search` tamamen Hybrid RAG rotasına taşınacak.
  - Ölçütsüz `product_comparison` da Hybrid RAG’e gidecek.
  - SQL’de yalnızca sayım, banka listesi, ölçütü belirli oran/vade ve hesaplanabilir karşılaştırma sorguları kalacak.
  - Ürün keşfi kalıpları (`seçenek`, `alternatif`, `uygun`, `bul`, `öner`, `hangi ürün/finansman`) tanınacak.
  - Güven bileşenleri ve düşük kanıt uyarısı plana eklenecek; fallback tabanı doğrudan yükseltilmeyecek.

- [query_rules.json](C:/Users/kuti/Desktop/ii/RAGnROLL-katilim-bankaciligi-nlp/configs/query_rules.json) ve [decisions.py](C:/Users/kuti/Desktop/ii/RAGnROLL-katilim-bankaciligi-nlp/src/llm/decisions.py)
  - `product_search` SQL allowlistinden çıkarılacak.
  - `product_search + HYBRID_RAG` LLM validator tarafından kabul edilecek.
  - LLM’nin yüksek güvenli SQL önerisi, yerel rota politikasını geçemeyecek.
  - LLM güveni yalnızca trace/observability için tutulacak; kullanıcı skorunu tek başına belirlemeyecek.

- [assistant.py](C:/Users/kuti/Desktop/ii/RAGnROLL-katilim-bankaciligi-nlp/src/services/assistant.py)
  - Hybrid RAG’e banka, ürün ve finansman filtreleri aktarılmaya devam edecek.
  - SQL yanıt güveni; typed field, evidence ve aday kapsamasıyla hesaplanacak.
  - Geçerli sayım/listelerde yüksek güven korunacak.
  - Ölçüm alanı eksik veya doğrulanabilir aday yoksa güven düşürülecek; kaynak yoksa `0` kalacak.
  - Plan güveni ile uçtan uca yanıt güveni ayrı tutulacak.

## Test ve kabul

- Ürün keşfi sorguları:
  - `Konut finansmanı için seçenekler neler?` → `product_search`, `HYBRID_RAG`
  - `Bana bir finansman bul` → `product_search`, `HYBRID_RAG`
- SQL sorguları:
  - `Konut finansmanında en düşük kâr payı hangisi?`
  - `Albaraka Türk kampanyalarını say`
  - Banka listesi ve vade/oran sorguları
- LLM’nin `product_search + STRUCTURED_SQL` önerdiği testte yerel Hybrid kapısı korunacak.
- Golden intent setinde:
  - intent exact-match ≥ `%85`
  - rota doğruluğu ≥ `%85`
  - SQL precision ≥ `%85`
  - confidence calibration/ECE raporu üretilecek.
- Mevcut ilgili test tabanı: `30 passed`.
- API ve değerlendirme dokümantasyonu güncellenecek; veritabanı migration’ı yapılmayacak.
- Önceden mevcut kirli çalışma ağacındaki kullanıcı değişiklikleri korunacak.

## Varsayımlar

- `%55` gözlemi, `QueryPlan.confidence` veya chat yanıt güveninden geliyor.
- Ürün arama/öneri sorguları ölçülebilir SQL sorgusu değil, filtreli retrieval problemidir.
- İlk başarı eşiği `%85`; daha yüksek eşik için bağımsız insan-onaylı holdout veri seti gerekir.
- Bu Plan Mode turunda dosya değişikliği yapılmadı.
