# Katılım finans kaynak paketi

Bu dizin, kullanıcı tarafından sağlanan beş PDF’in özgün dosyalarını değil, doğrulanabilir kaynak manifestosunu ve sayfa numarası taşıyan RAG kanıt kayıtlarını içerir.

- `pdf_source_registry.json`: izin verilen dosya adları, beklenen SHA-256 ve resmî kaynak metadata'sı.
- `pdf_evidence.manifest.json`: yerel yol içermeyen dosya adı, SHA-256 ve toplam sayfa sayısı.
- `pdf_evidence.jsonl`: belge/parça hash'i, sayfa aralığı, konu, kaynak URL'si ve tam metin parçası.
- `pdf_extraction_report.json`: her belgenin denenmiş, çıkarılmış, boş ve hatalı sayfa kapsamı.
- `pdf_topic_mapping.json`: konu kayıtlarının mevcut ontoloji terimleriyle eşlemesi.

Kanıt üretimi varsayılan olarak PDF'lerin bütün sayfalarını işler. `--max-pages` yalnız geliştirme smoke testleri için açıkça verilebilir; kısmi çalışmanın raporunda `complete=false` olur ve tam kaynak paketi olarak kabul edilmez. `scripts/verify_pdf_evidence.py` sayfa kapsamını, belge/parça hash'lerini, benzersiz kimlikleri ve yerel yol sızıntısını fail-closed biçimde denetler.

Özgün PDF’ler lisans ve depo boyutu nedeniyle çalışma alanının dışında tutulur. Manifestodaki SHA-256 ile yerel kopyanın bütünlüğü doğrulanabilir.

## Doğrulanmış korpus özeti

26 Ağustos 2026 tarihli tam üretim çalışması beş belgede 2.602 sayfanın tamamını denedi. 2.459 sayfadan metin çıkarıldı, metin katmanı yetersiz olan 269 sayfa OCR ile kurtarıldı, 143 boş sayfa raporlandı; düşük kaliteli veya başarısız sayfa kalmadı. Sonuçta sayfa aralığı ve kaynak kimliği taşıyan 2.509 RAG parçası üretildi.

İndeks, 683 kampanya ve 1.241 terminoloji kaydıyla birlikte toplam 4.433 belge içerir. Aynı içerik parmak izleri Chroma (`Qwen/Qwen3-Embedding-0.6B`) ve EVREN/Qdrant (`bge-m3-embed`) koleksiyonlarında doğrulanmıştır. Artımlı ikinci geçişte iki koleksiyonda da 4.433 kayıt değişmeden bulunmuş, yeniden embedding yapılmamıştır.

Tamlık ve bütünlük kontrolü:

```powershell
.\.venv311\Scripts\python.exe -m scripts.verify_pdf_evidence
```

EVREN yapılandırmasının da zorunlu olduğu artımlı indeks kontrolü:

```powershell
.\.venv311\Scripts\python.exe -m scripts.ingest_chroma --batch-size 16 --require-evren
```
