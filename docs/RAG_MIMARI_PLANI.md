# Chatbot Mimari Tasarımı - RAG Pipeline Planı

## Amaç
Katılım bankacılığı ürünleri (kampanyalar, kâr payı oranları, finansman türleri) hakkındaki kullanıcı sorularını, dışarıya hiçbir veri sızdırmadan tamamen lokal LLM (Ollama) ile cevaplayan güvenli ve yüksek performanslı bir RAG (Retrieval-Augmented Generation) sistemi kurmak. Amacımız sadece bilgi getirmek değil; finansal regülasyonlara uygun, halüsinasyondan arındırılmış ve hızlı bir asistan altyapısı sağlamaktır.

## Neden RAG?
- Veri Mahremiyeti: Yarışma kuralları ve bankacılık regülasyonları gereği veriler dış API'lere gönderilemez.
- Finansal Doğruluk: LLM'in uydurma (halüsinasyon) yapma riskini sıfıra indirmek zorundayız. Oranlar ve tarihler doğrudan onaylanmış veri setinden çekilir.
- Dinamik Veri Yönetimi: Banka kampanyaları sürekli değiştiği için modeli yeniden eğitmek yerine, vektör veritabanını güncellemek maliyet açısından en verimli çözümdür.

## Genel Akış ve Güvenlik Katmanı
1. Soru Karşılama ve Niyet Analizi: Kullanıcı sorusu geldiğinde, finansal danışmanlık içerip içermediği kural tabanlı bir filtre (Guardrail) ile kontrol edilir.
2. Hibrit Arama (Hybrid Search): Sadece anlamsal arama değil, spesifik kampanya rakamlarını kaçırmamak için kelime bazlı arama ile ChromaDB araması birleştirilir.
3. Prompt Şekillendirme: Bulunan en alakalı metin parçaları ve sisteme özel "Katılım Bankacılığı Jargonu" prompt şablonu birleştirilir.
4. Lokal Üretim (Generation): Hazırlanan bağlam, Ollama üzerindeki yerel modele gönderilir ve cevap üretilir.
5. Yanıt Doğrulama (Post-processing): Çıktı arayüze gitmeden önce format ve istenmeyen karakter kontrollerinden geçirilir.

## Bileşenler
- LLM Engine: Ollama
- Vektör Veritabanı: ChromaDB
- Orkestrasyon: LangChain
- Veri Kaynağı: Standardize edilmiş ve temizlenmiş JSON kampanya dataları

## Sonraki Adımlar (Hafta 2 ve Sonrası)
- Katılım bankacılığı terimlerini doğru anlayan embedding modelinin seçilmesi ve testleri.
- Ollama sunucusunun arayüz ile konuşabilmesi için entegrasyon performansının ölçülmesi.
- Sık sorulan sorulara saniyeler içinde cevap verebilmek için önbellek stratejisi geliştirilmesi.
- Modelin banka asistanı tonunda cevap üretmesi için prompt testleri.