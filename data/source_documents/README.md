# Katılım finans kaynak paketi

Bu dizin, kullanıcı tarafından sağlanan beş PDF’in özgün dosyalarını değil, doğrulanabilir kaynak manifestosunu ve sayfa numarası taşıyan RAG kanıt kayıtlarını içerir.

- `pdf_evidence.manifest.json`: dosya adı, SHA-256 ve toplam sayfa sayısı.
- `pdf_evidence.jsonl`: alıntı, PDF kimliği, sayfa, konu, kaynak URL’si ve alıntı parmak izi.
- `pdf_topic_mapping.json`: konu kayıtlarının mevcut ontoloji terimleriyle eşlemesi.

Kanıt üretimi varsayılan olarak her PDF’in ilk 80 sayfasını işler; bu, büyük/karmaşık belgelerde güvenli ve tekrarlanabilir indeksleme sağlar. Tam kapsamlı üretim için `scripts/extract_pdf_evidence.py --max-pages 0` kullanılabilir (0 değeri sınırsız sayfa anlamına gelir).

Özgün PDF’ler lisans ve depo boyutu nedeniyle çalışma alanının dışında tutulur. Manifestodaki SHA-256 ile yerel kopyanın bütünlüğü doğrulanabilir.
