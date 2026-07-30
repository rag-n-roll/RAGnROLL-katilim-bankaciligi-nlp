# Katılım Bankacılığı Kampanya Veri Seti

## Amaç ve kapsam

Veri seti, katılım bankalarının herkese açık kampanya sayfalarındaki Türkçe
metinleri RAG, sınıflandırma, NER ve karşılaştırma çalışmalarına hazırlamak için
oluşturulur. Ham HTML saklanmaz; metin, kaynak URL ve izlenebilirlik alanları
saklanır.

Kampanya kaynakları:

1. Kuveyt Türk
2. Albaraka Türk
3. Türkiye Finans
4. Ziraat Katılım
5. Vakıf Katılım
6. Türkiye Emlak Katılım

Banka evreninin resmî kaynağı BDDK kuruluş listesidir. BDDK'daki yeni bankalar
`participation_banks.json` içinde görünür; kampanya kapsamına otomatik olarak
dahil edilmez.

## Dosyalar

| Dosya | Seviye | Açıklama |
| --- | --- | --- |
| `raw/participation_banks.json` | Ham | BDDK banka adları, web adresleri ve dijital banka işareti |
| `raw/campaigns.json` | Ham | Sayfadan ayıklanan ortak kampanya kayıtları |
| `processed/campaigns.json` | İşlenmiş | `clean_text`, `tokens` ve `token_count` eklenmiş kayıtlar |
| `../outputs/quality_report.json` | Rapor | Doğrulama uyarıları, hataları ve ağ/ayrıştırma hataları |

## Kampanya JSON şeması (`1.0.0`)

| Alan | Tür | Zorunlu | Açıklama |
| --- | --- | --- | --- |
| `id` | string | Evet | Banka slug'ı ve kaynak URL'den üretilen kararlı SHA-256 özeti |
| `schema_version` | string | Evet | Kayıt şeması sürümü |
| `bank_slug` | string | Evet | Makinece okunur banka anahtarı |
| `bank_name` | string | Evet | Bankanın resmî/tam adı |
| `title` | string | Evet | Kampanya başlığı |
| `summary` | string/null | Hayır | İlk anlamlı paragraftan kısa özet |
| `content` | string | Evet | Yapısal satır sonları korunmuş kampanya metni |
| `category` | string/null | Hayır | Kaynakta güvenle bulunabiliyorsa kategori |
| `start_date` | ISO date/null | Hayır | Kampanya başlangıcı |
| `end_date` | ISO date/null | Hayır | Kampanya bitişi |
| `source_url` | HTTPS URL | Evet | Birincil kaynak sayfa |
| `image_url` | URL/null | Hayır | Kaynaktaki ana görsel |
| `scraped_at` | ISO datetime | Evet | UTC toplama zamanı |

İşlenmiş veri bu alanlara `clean_text` (string), `tokens` (string dizisi) ve
`token_count` (integer) ekler. Ham `content` hiçbir zaman üzerine yazılmaz.

## Kalite kuralları

Hata oluşturan kurallar:

- başlık en az 5 karakter olmalı;
- içerik en az 80 karakter olmalı;
- kaynak geçerli bir HTTPS URL olmalı;
- başlangıç tarihi bitiş tarihinden sonra olmamalı;
- kayıt kimliği ve kaynak URL tekil olmalı.

Eksik tarih veya özet uyarıdır; bazı sürekli kampanyalarda tarih gerçekten
bulunmayabilir. `quality_score`, kayıt seviyesinde hata içermeyen kayıtların tüm
kayıtlara oranıdır. Ağ ve HTML ayrıştırma hataları ayrıca `fetch_failures`
alanında tutulur ve sessizce kaybedilmez.

## Ön işleme yaklaşımı

- Unicode NFC normalizasyonu yapılır.
- HTML etiketleri ve görünmez karakterler kaldırılır.
- Türkçe karakterler ve paragraf sınırları korunur.
- Tokenizer `Türkiye'de` gibi kesme işaretli sözcükleri ve `2,99`, `1.000` gibi
  sayıları tek token olarak korur.
- Stop-word silme ve kök bulma uygulanmaz; bu işlemler görev bağımlıdır ve RAG
  bağlamını gereksiz yere bozabilir.

## Veri kökeni, güncelleme ve sınırlılıklar

Her kayıt kaynak URL ve UTC toplama zamanıyla izlenebilir. Bankalar HTML
yapılarını haber vermeden değiştirebilir; boş/azalan kayıt sayısı kalite
raporunda ve CI testlerinde izlenmelidir. Kampanyalar finansal tavsiye değildir;
koşullar için her zaman `source_url` üzerindeki güncel metin esas alınır.

Bu depo üçüncü taraf kampanya metinlerinin telifini devralmaz. Veriyi toplarken
`robots.txt`, makul istek aralığı, site kullanım şartları, KVKK ve yeniden yayın
hakları gözetilmelidir.
