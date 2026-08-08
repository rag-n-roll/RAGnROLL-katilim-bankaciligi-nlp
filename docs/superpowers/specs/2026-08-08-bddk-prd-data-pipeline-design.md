# BDDK ve PRD Veri Pipeline Tasarımı

## Amaç

BDDK'nin güncel katılım bankası listesini kaynak kabul ederek desteklenen tüm bankalardan kampanya ve ürün verisi toplamak; ham kaynak metnini korumak; TEKNOFEST 2026 PRD'sinde tanımlanan finansal alanları yapılandırılmış biçimde üretmek; süreci tekrarlanabilir, doğrulanabilir ve on-premise çalışabilir hale getirmek.

## Doğrulanmış Mevcut Durum

- Canlı `https://www.bddk.gov.tr/Kurulus/Liste/90` sayfası 10 katılım bankası döndürmektedir.
- Mevcut scraper registry'si 6 bankayı desteklemektedir: Kuveyt Türk, Albaraka Türk, Türkiye Finans, Ziraat Katılım, Vakıf Katılım ve Emlak Katılım.
- Adil Katılım, Dünya Katılım, Hayat Finans ve T.O.M. Katılım için scraper yoktur.
- Kayıtlı 6 bankanın canlı smoke testinde banka başına 3 kayıtla toplam 18 kampanya toplanmış, tüm kayıtlar doğrulamadan geçmiş ve ön işlenmiştir.
- Ham model başlık, içerik, özet, kategori, kaynak URL, tarih ve görsel alanlarını taşımaktadır.
- PRD'nin istediği kâr payı, vade, taksit, avantaj, ödül, hedef kitle ve masraf alanları yapılandırılmış modelde yoktur. `category` alanı canlı örneklerin tamamında boştur.

## Kapsam

### Kapsam içi

- BDDK'dan güncel katılım bankası keşfi
- BDDK listesi ile scraper registry kapsam karşılaştırması
- Güncel 10 banka için scraper desteği
- Finansman, kart, yatırım, alışveriş puanı ve yeni müşteri kampanyaları
- Ham kampanya içeriğinin kayıpsız saklanması
- PRD alanlarının deterministik, yerel çıkarımı
- Şema sürümleme ve geriye dönük veri okuma
- Veri doğrulama, yinelenen kayıt kontrolü ve banka bazlı kalite raporu
- Fixture tabanlı birim/entegrasyon testleri ve isteğe bağlı canlı smoke testi
- Tekrarlanabilir CLI akışı ve çıktı dokümantasyonu

### Kapsam dışı

- Dashboard ve chatbot değişiklikleri
- Ücretli veya harici LLM/API kullanımı
- Konvansiyonel bankalar
- Müşteri verileri
- Selenium gerektirmeyen sitelerde tarayıcı otomasyonu

## Mimari

### 1. BDDK banka kataloğu

`bddk.py` resmi BDDK sayfasından banka adı, web sitesi ve dijital banka bilgisini çıkarır. Kaynak URL sabit olarak kod içinde görünür kalır ve CLI çıktısında kaydedilir. BDDK sayfa yapısı değişirse sessizce boş sonuç üretmek yerine açık hata verir.

Katalog kayıtları kanonik slug ile zenginleştirilir. Registry denetimi her BDDK bankasını şu durumlardan biriyle raporlar:

- `supported`: scraper kayıtlı
- `unsupported`: BDDK'da var, scraper yok
- `stale`: registry'de var, güncel BDDK listesinde yok

### 2. Bankaya özgü veri toplama

Mevcut `BaseBankScraper` ortak HTTP, robots.txt, hız sınırlama, URL keşfi, detay ayrıştırma ve hata izolasyonu davranışını korur. Her banka modülü yalnızca siteye özgü liste URL'leri ve seçicileri tanımlar.

Yeni scraper'lar:

- Adil Katılım
- Dünya Katılım
- Hayat Finans
- T.O.M. Katılım

Bir banka kamuya açık kampanya sayfası sunmuyorsa bu durum başarı gibi gösterilmez; banka bazlı raporda `no_public_campaign_source` olarak kaydedilir. Dinamik veya erişimi engellenen sayfalar için yalnızca gerekliyse açık kaynak tarayıcı otomasyonu ayrı adaptör olarak kullanılabilir.

### 3. Ham kampanya şeması

Ham kayıt, kaynağın tekrar denetlenebilmesi için aşağıdaki alanları korur:

- kimlik ve şema sürümü
- banka slug ve adı
- başlık, özet ve tam içerik
- kaynak ve görsel URL'si
- başlangıç/bitiş tarihi
- kaynak kategori etiketi
- çekim zamanı

Ham veri `data/raw/` altında saklanır. Kaynak metin çıkarım sonucuyla değiştirilmez.

### 4. PRD yapılandırılmış alanları

İşlenmiş kayıt şunları üretir:

- `product_type`: finansman, kart, yatırım, alışveriş puanı, yeni müşteri veya diğer
- `financing_type`: ihtiyaç, konut, taşıt veya diğer
- `profit_share_rate`: normalize ondalık oran
- `term_months`: ay cinsinden vade
- `installment_count`: taksit sayısı
- `campaign_benefit`: kampanya avantajının metinsel özeti
- `reward_amount`: tutar ve para birimi
- `discount_rate`: normalize indirim oranı
- `target_audience`: hedef müşteri segmenti
- `campaign_start_date` ve `campaign_end_date`
- `fee_information`: masraf/ücret açıklaması

Her çıkarılmış değer, mümkün olduğunda `evidence_text` ve `extraction_method` bilgisiyle izlenebilir olur. Bulunamayan değerler `null` kalır; tahmin edilmez.

### 5. Çıkarım yaklaşımı

İlk sürüm yerel ve deterministik hibrit çıkarım kullanır:

1. Türkçe metin ve sayı normalizasyonu
2. Regex ile oran, para, vade, taksit ve tarih adayları
3. Yakın bağlam anahtarlarıyla alan ayrımı
4. Terminoloji sözlüğüyle ürün ve hedef kitle sınıflandırması
5. Çelişkili adaylarda güvenli seçim veya `null`

Model/LLM tabanlı çıkarım bu teslimin zorunlu parçası değildir. Sonradan eklense bile ham metin ve deterministik sonuç korunur.

## Veri Akışı

```text
BDDK banka keşfi
  -> katalog/registry kapsam raporu
  -> desteklenen bankalarda kampanya URL keşfi
  -> detay sayfası çekimi ve ham kayıt
  -> doğrulama ve yinelenen kayıt temizliği
  -> PRD alan çıkarımı ve normalizasyon
  -> işlenmiş veri seti
  -> banka/alan bazlı kalite raporu
```

CLI tek bir uçtan uca komut sunar; mevcut alt komutlar tanılama ve kısmi yeniden çalıştırma için korunur. Başarısız bir banka diğer bankaların verisini kaybetmesine yol açmaz. Son bilinen geçerli veri seti, tüm bankalar başarısız olduğunda üzerine yazılmaz.

## Hata Yönetimi

- HTTP, robots.txt, URL keşfi, detay çekimi, ayrıştırma ve doğrulama hataları ayrı aşamalar olarak raporlanır.
- Her hata banka slug, aşama, URL, hata türü ve mesaj içerir.
- Banka bazlı sıfır kayıt, sebebi belirlenmeden genel başarı sayılmaz.
- Eksik PRD alanı kayıt hatası değildir; alan doluluk metriğine yansır.
- Geçersiz zorunlu alanlar kaydın kalıcı veri setinden çıkarılmasına neden olur.
- Schema ve kaynak değişiklikleri sürüm bilgisiyle görünür olur.

## Test Stratejisi

### Birim testleri

- BDDK katalog ayrıştırma ve registry farkları
- Her yeni banka için liste ve detay fixture'ları
- Türkçe oran, para, vade, taksit, tarih ve masraf kalıpları
- Ürün türü ve hedef kitle sınıflandırması
- Eksik, çelişkili ve bozuk metinler
- Şema serileştirme ve eski kayıtların okunması

### Entegrasyon testleri

- Fixture üzerinden BDDK -> kampanya -> doğrulama -> çıkarım -> çıktı zinciri
- Bir banka başarısızken diğer bankaların devam etmesi
- Kalite raporundaki banka ve alan doluluk metrikleri
- Mevcut 104 testin regresyonsuz çalışması

### Canlı doğrulama

Canlı testler varsayılan CI paketinden ayrı tutulur. Açıkça çağrılan smoke test:

- BDDK'dan en az bir ve güncel olarak beklenen banka kayıtlarını almalı
- registry kapsamını raporlamalı
- desteklenen her bankayı düşük limit ile çalıştırmalı
- ham, işlenmiş ve kalite raporu çıktıları üretmeli

Final veri çekimi banka başına yapılandırılabilir limite kadar çalışır ve PRD hedefi olan en az 100 kampanyayı hedefler. Kamuya açık kaynakların toplamı bu sayının altında kalırsa gerçek sayı ve banka bazlı gerekçe raporlanır; sahte veya çoğaltılmış kayıt üretilmez.

## Kabul Kriterleri

- Canlı BDDK kataloğundaki tüm bankalar kapsam raporunda görünür.
- Güncel katalog için 10/10 banka desteklenir veya kamuya açık veri kaynağı olmayan banka açık gerekçeyle raporlanır.
- Beş PRD ürün/kampanya türü aranır ve sınıflandırılır.
- PRD yapılandırılmış alanları şemada bulunur; eksik değerler `null` olur.
- Ham kaynak metin ve kaynak URL her kayıtta korunur.
- Banka ve alan bazlı kalite/doluluk raporu üretilir.
- Fixture tabanlı tüm testler ve mevcut regresyon testleri geçer.
- Gerçek uçtan uca smoke koşusu ham, işlenmiş ve rapor çıktılarıyla tamamlanır.
- Final canlı koşunun gerçek kayıt sayısı ve tüm başarısızlıkları açıkça raporlanır.

## Uygulama Sırası

1. Katalog/registry kapsam modeli ve testleri
2. PRD şeması ve çıkarım testleri
3. Eksik banka scraper fixture'ları ve implementasyonları
4. Uçtan uca CLI orkestrasyonu ve kalite metrikleri
5. Regresyon testleri
6. Canlı düşük limitli smoke testi
7. Final canlı veri çekimi ve sonuç raporu
