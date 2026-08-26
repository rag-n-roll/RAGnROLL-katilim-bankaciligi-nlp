# Tam PDF RAG ve Finansman Karşılaştırma Entegrasyonu Tasarımı

## Amaç

Kullanıcının sağladığı beş katılım finans PDF'inin tamamını doğrulanabilir,
sayfa kaynaklı ve anlamsal parçalara dönüştürmek; parçaları EVREN/Qdrant ile
yerel Chroma indekslerine artımlı olarak yüklemek; aynı zamanda
`C:\Users\kuti\Desktop\ui_son` içindeki finansman hesaplama modülünü mevcut
Pusula AI backend, chatbot ve `/compare` sayfasına tek bir ortak servis olarak
entegre etmek.

## Kapsam

### PDF kaynakları

1. `FAIZSIZ-FINANS-KURULUSLARI-MUHASEBESI.pdf`
2. `Faizsiz Finans Standartları AAOIFI (Güncellenmiş Versiyon).pdf`
3. `Katilim_Finans_Urunleri_ve_Muhasebe_Surecleri_2.pdf`
4. `8803561630-2025-faaliyet-raporu.pdf`
5. `KATILIM_BANKACILIGINDA_KAR_DAGITIMI.pdf`

Orijinal PDF dosyaları lisans ve depo boyutu nedeniyle Git'e eklenmez. Git'te
yalnız kaynağın resmî adı/URL'si, beklenen SHA-256 değeri, çıkarım raporu ve
üretilmiş metin parçaları bulunur. Kullanıcıya özgü mutlak dosya yolları hiçbir
sürümlenen dosyaya yazılmaz.

### Finansman özelliği

- `ui_son/src/financing` altındaki hesaplama motoru ve resmî banka adaptörleri
  mevcut backend mimarisine port edilir.
- Ortak finansman servisi hem FastAPI uç noktaları hem chatbot araç çağrısı
  tarafından kullanılır.
- `/compare` sayfasındaki hardcoded `BANK_RATE_BASE`, kaynaksız fallback oranları
  ve sahte banka teklifleri kaldırılır.
- Kullanıcı ürün, tutar, vade ve banka seçerek doğrulanmış teklifleri karşılaştırır.
- Veri bulunmayan bankalar listeden kaybolmaz; açık bir uygunluk/veri durumu ve
  resmî kaynak bağlantısı gösterir.

## Mimari

```text
Kullanıcı PDF'leri
  -> SHA-256 kaynak kayıt defteri
  -> tam sayfa metin çıkarımı
  -> düzen temizleme + paragraf/sayfa parçalama
  -> parça/manifest doğrulaması
  -> EVREN BGE-M3/Qdrant + yerel Chroma
  -> HybridRetriever
  -> evidence paketi + LLM yanıtı + sayfa kaynak kartı

Resmî banka hesaplayıcıları / yayımlanmış oranlar
  -> banka adaptörleri
  -> FinancingQuoteService
       -> POST /api/v1/financing-quotes
       -> GET /api/v1/financing-products
       -> chatbot financing_quote aracı
       -> /compare kullanıcı arayüzü
```

PDF ve finansman hatları aynı cevap güvenliği sözleşmesinde birleşir: LLM yalnız
retrieval kanıtı veya doğrulanmış finansman teklifinde bulunan nicel/nitel
iddiaları söyleyebilir; teklif servisi sonucu olmayan oran, taksit veya “en iyi”
hükmü üretemez.

## Tam PDF çıkarım sözleşmesi

### Kaynak kayıt defteri

Her belge için aşağıdaki alanlar zorunludur:

- kararlı `document_id`;
- kullanıcıdan bağımsız görünen başlık;
- beklenen SHA-256;
- toplam sayfa sayısı;
- resmî kaynak URL'si;
- yayıncı ve belge tarihi/sürümü;
- izin verilen yerel dosya adı eşleşmeleri.

Çıkarım başlamadan önce yerel PDF'nin SHA-256 değeri kayıt defteriyle eşleşir.
Eşleşme yoksa işlem fail-closed durur; aynı dosya adına sahip değiştirilmiş bir
belge resmî TKBB kaynağı olarak işaretlenemez.

### Sayfa çıkarımı

- Varsayılan işlem sınırı yoktur; belgenin tüm sayfaları denenir.
- Bir sayfanın çıkarımı hata verirse belge bütünü kaybolmaz. Hata, sayfa numarası
  ve sebebiyle raporlanır; başarısız sayfa sayısı kabul kapısında görünür.
- Metni bulunan her sayfa normalizasyon hattına girer.
- Boş veya görsel ağırlıklı sayfalar `empty_or_image_only` olarak raporlanır.
- Çıkarım kütüphanesi sayfa başına izolasyon ve süre sınırı sağlayacak şekilde
  kullanılır; tek bir karmaşık sayfa tüm belgeyi sonsuza kadar bloke edemez.

### Temizleme ve parçalama

- Tekrarlanan üstbilgi/altbilgiler belge genelindeki frekansla saptanıp kaldırılır.
- Satır sonu tire bölünmeleri, fazla boşluklar ve sayfa numarası gürültüsü
  normalize edilir.
- İçindekiler sayfaları varsayılan RAG parçalarından çıkarılır fakat çıkarım
  raporunda sayfa olarak korunur.
- Metin önce paragraflara, ardından yaklaşık 350-500 tokenlık pencerelere ayrılır.
- Parça örtüşmesi 40-60 tokendır ve mümkünse cümle sınırında gerçekleşir.
- Parça tek bir sayfa veya açık `page_start/page_end` aralığı taşır.
- Konu etiketleri ek metadata'dır; hiçbir parça yalnız anahtar kelime bulunmadığı
  için atılmaz.
- Konu eşleşmesi varsa kanıt penceresi eşleşmenin çevresini içerir. Topic sırası
  sabittir; `set` iterasyonu kullanılmaz.

Her parçanın kararlı kimliği şu girdilerden üretilir:

```text
document_sha256 + page_start + page_end + normalized_text
```

Parça JSONL yüklenirken metnin SHA-256 değeri yeniden hesaplanır. Manifest ve
parça hash'i uyuşmazsa kayıt indekslenmez.

### Çıkarım raporu

Her belge için:

- manifest sayfa sayısı;
- denenmiş sayfa;
- metin çıkarılan sayfa;
- boş/görsel sayfa;
- hatalı sayfa;
- üretilen parça;
- toplam token/karakter;
- hata listesi;
- tamamlanma durumu

raporlanır. “Tam çıkarım” iddiası yalnız denenmiş sayfa sayısı manifest sayfa
sayısına eşitse yapılır.

## Retrieval ve embedding

- `pdf_evidence` birinci sınıf kaynak türüdür; terminoloji cache'ine gizlice
  karıştırılmaz, kaynak filtresiyle açıkça seçilir.
- Tanım, açıklama, muhasebe, kâr dağıtımı ve katılım finans ilkesi sorguları
  `terminology` ile `pdf_evidence` kaynaklarını birlikte arar.
- Kampanya/teklif sorguları kampanya ve finansman araçlarını kullanır; PDF metni
  güncel oran yerine geçmez.
- Chroma ve EVREN/Qdrant indexer'ları aynı parça kimliği/index hash sözleşmesini
  kullanır; yalnız değişen parçalar embed edilir, stale parçalar silinir.
- EVREN birincil embedding sağlayıcısıdır; yerel Chroma/Ollama fallback olarak
  korunur.
- Kaynak metadata'sı belge başlığı, sayfa aralığı, yayıncı ve resmî URL içerir.
- LLM evidence paketinde PDF sayfa bilgisi görünür; UI'daki kaynak kartı belge
  başlığı + sayfa + tıklanabilir resmî bağlantı gösterir.

## Finansman servis modeli

### Girdi

```json
{
  "financing_type": "consumer|vehicle|housing",
  "amount": 150000,
  "term_months": 24,
  "currency": "TRY",
  "selected_bank_slugs": ["kuveyt-turk"],
  "selected_product_ids": {},
  "options": {}
}
```

Tutar pozitif, vade desteklenen sınırda ve para birimi destekli olmalıdır.
Ürün/adaptör bazlı limitler resmî katalogdan doğrulanır.

### Çıktı

Her `FinancingQuote` en az şunları taşır:

- banka slug/adı ve ürün;
- `available`, `ineligible`, `unsupported`, `stale` veya
  `temporarily_unavailable` durumu;
- aylık kâr oranı, taksit, toplam geri ödeme, yıllık maliyet ve ücretler;
- hesaplama kaynağı (`official_api`, `official_calculator_live`,
  `official_published_rate`, `last_verified_official_rate`);
- resmî kaynak URL'si ve doğrulama zamanı;
- kullanıcıya gösterilecek açıklama ve bilgilendirme notu.

Sayısal alanlar yalnız resmî hesaplayıcıdan veya kaynaklı oran üzerinden açıkça
tanımlanmış formülden üretilebilir. Kaynak/son doğrulama zamanı olmayan teklif
`available` olarak yayımlanamaz.

### API

- `GET /api/v1/financing-products`: tutar/vade için desteklenen ortak ürün ve
  banka varyantlarını döndürür.
- `POST /api/v1/financing-quotes`: seçilen koşullar için on banka kapsamını
  koruyarak normalize edilmiş teklifleri döndürür.

Bir banka adaptörü hata verdiğinde tüm istek başarısız olmaz. İlgili banka açık
durum koduyla dönülür; diğer doğrulanmış teklifler korunur.

## Chatbot entegrasyonu

- Tool policy'ye `financing_quote` eklenir ve yalnız katılım bankacılığı
  finansman karşılaştırması intent'inde izin verilir.
- Planner, tutar + vade + finansman türü bulunan sorguda aracı çağırır.
- Eksik kriterlerde mevcut konuşma durumu tutar, vade ve masraf/öncelik
  açıklamasını ister.
- Tool sonucu evidence/facts paketine eklenir; LLM tarafsız özet üretir.
- “En uygun” veya “en iyi” hükmü yalnız kullanıcının ölçütü ve karşılaştırılabilir
  `available` sonuçlar varsa söylenir.
- Validator; yanıtta geçen oran, taksit, toplam, masraf ve banka üstünlük
  iddialarını tool sonucuna bağlar.
- PDF'ler güncel banka teklifi üretmek için kullanılmaz; kavramsal açıklama ve
  hesaplamanın terminolojik gerekçesi için kullanılır.

## `/compare` kullanıcı arayüzü

Mevcut marka, navbar ve responsive düzen korunur. `ui_son` finansman hesaplama
ekranındaki işlevler mevcut `/compare` sayfasına uyarlanır:

- finansman türü;
- finansman tutarı;
- vade;
- banka seçimi;
- ortak kampanya/ürün seçimi;
- “Teklifleri Hesapla” eylemi;
- teklif özeti ve doğrulanmış sonuç tablosu.

Hardcoded oranlar ve backend kapalıyken sahte finansal sonuç üretme kaldırılır.
Backend erişilemiyorsa kullanıcı açık hata ve yeniden deneme mesajı görür.
Önceki doğrulanmış sonuç ancak backend bunu `last_verified_official_rate` olarak
işaretlediyse gösterilir.

Sonuç satırları:

- banka ve ürün;
- aylık kâr oranı;
- aylık taksit;
- toplam geri ödeme;
- ücret/maliyet;
- doğrulanma zamanı;
- durum mesajı;
- resmî kaynağa bağlantı

alanlarını gösterir. Sıralama yalnız karşılaştırılabilir `available` teklifler
arasında yapılır. Diğer bankalar aşağıda durumlarıyla görünür.

## Hata ve güvenlik davranışı

- PDF kaynak doğrulaması hash uyuşmazlığında fail-closed olur.
- Retrieved PDF içeriği talimat değil veri olarak işaretlenir.
- Finansman adaptörleri yalnız allowlist resmî banka alan adlarına gider.
- Kullanıcı girdisi uzak URL oluşturmak için doğrudan kullanılmaz.
- Hassas müşteri/kimlik/hesap verisi finansman teklif isteğine kabul edilmez.
- Loglar API anahtarı, kimlik verisi veya tam kullanıcı belgesi yolu içermez.
- UI ve chatbot sonuçları “bilgilendirme amaçlıdır; kesin teklif değildir” notunu
  taşır.

## Test ve kabul kriterleri

### PDF

- Beş PDF'nin SHA-256 değeri manifestle eşleşir.
- Her belgenin tüm sayfaları denenir ve rapor toplamları manifestle tutarlıdır.
- Parçalar deterministiktir; iki çalıştırma aynı kimlikleri üretir.
- Alıntı topic etiketliyse eşleşme metin penceresinde bulunur.
- JSONL veya manifest değiştirildiğinde loader kaydı reddeder.
- Sürümlenen veride kullanıcıya ait mutlak dosya yolu bulunmaz.
- Chroma smoke ve EVREN/Qdrant artımlı indeks raporu PDF parça sayısını içerir.
- API tanım sorgusu en az bir gerçek PDF sayfa kaynağını evidence paketine alır.

### Finansman

- Port edilen hesaplama/adaptör testleri mevcut backend içinde geçer.
- API on banka kapsamını korur ve banka hatalarını kısmi başarıyla döndürür.
- Chatbot tutar/vade içeren finansman sorgusunda `financing_quote` aracını çağırır.
- Chatbot doğrulanmamış oran veya “en iyi” hükmü üretemez.
- `/compare` kaynak kodunda `BANK_RATE_BASE` veya finansal sahte fallback kalmaz.
- Frontend yüklenme, hata, boş, kısmi ve başarılı sonuç durumlarını test eder.
- Backend ve frontend tam test/lint/build paketleri geçer.
- Canlı tarayıcı testinde `/compare` teklif üretir; aynı koşul chatbot üzerinden
  sorulduğunda aynı servis verileriyle tutarlı yanıt alınır.

## Uygulama sırası

1. PDF kaynak kayıt defteri ve güvenli tam çıkarım hattı.
2. Deterministik paragraf parçalama, doğrulayıcı ve tam kaynak paketinin üretimi.
3. Chroma/EVREN indeksleme ve chatbot PDF retrieval filtresinin düzeltilmesi.
4. Finansman domain modülü, şemalar ve API uç noktaları.
5. Chatbot tool policy/planner/executor/validator entegrasyonu.
6. `/compare` sayfasının gerçek finansman API'sine bağlanması.
7. Tam test, indeks, canlı API/UI doğrulaması ve mevcut PR'nin güncellenmesi.

## Kapsam dışı

- Banka adına başvuru veya işlem yapmak.
- Kullanıcıya kişisel yatırım/finansman tavsiyesi vermek.
- Üçüncü taraf karşılaştırma sitelerinden oran almak.
- Orijinal telifli PDF dosyalarını Git deposuna eklemek.
- Kaynağı olmayan oranları demo/fallback adıyla kullanıcıya göstermek.
