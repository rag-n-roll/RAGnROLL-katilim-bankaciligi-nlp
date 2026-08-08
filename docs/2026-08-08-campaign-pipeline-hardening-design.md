# Kampanya Veri Hattı Sağlamlaştırma Tasarımı

## Amaç

Mevcut scraper mimarisini, API sözleşmelerini, JSON şemasını ve Türkçe metin
işleme davranışını koruyarak katılım bankacılığı kampanya veri hattını daha
dayanıklı, gözlemlenebilir ve test edilebilir hale getirmek. İlk üç öncelikli
banka canlı smoke testlerle doğrulanacak; kalıcı veri çıktısı altı bankanın
tamamı için üretilecektir.

## Mevcut Durum

Repository hâlihazırda aşağıdaki bileşenlere sahiptir:

- FastAPI üzerinde `/health` ve placeholder `/chat` endpoint'leri;
- `BaseBankScraper` ve `ScraperConfig` tabanlı ortak scraper sözleşmesi;
- retry, timeout, robots.txt ve alan adı bazlı gecikme uygulayan `HttpClient`;
- sürümlü `Campaign` veri modeli;
- altı banka için scraper registry ve banka modülleri;
- atomik UTF-8 JSON storage;
- kampanya validation ve kalite raporu;
- Türkçe Unicode karakterlerini koruyan temizleme ve tokenizasyon pipeline'ı;
- pytest, flake8 ve Next.js doğrulama altyapısı.

Mevcut mimarinin yerine yeni bir framework, database, repository katmanı,
scheduler veya logging sistemi kurulmayacaktır.

## Kapsam

### Dahil

- BDDK katılım bankası çıktısının canlı olarak yenilenmesi;
- altı banka scraper'ının mevcut registry üzerinden çalıştırılması;
- ilk üç banka için fixture tabanlı integration testleri;
- düşük limitli, geçici canlı smoke testleri;
- banka ve kampanya seviyesinde hata izolasyonu;
- yapılandırılmış failure kayıtları;
- kaynak URL normalizasyonu;
- persistence öncesi normalize URL tabanlı duplicate kaldırma;
- zorunlu alan ve HTML kalıntısı validation'ı;
- mevcut logging olaylarının genişletilmesi;
- raw, processed ve quality report çıktılarının altı banka için yenilenmesi;
- README ve veri dokümantasyonunun mevcut yapıya ekleme yapılarak güncellenmesi.

### Hariç

- framework veya database değişikliği;
- yeni API endpoint'i;
- scheduler, cron veya background worker eklenmesi;
- frontend özelliği geliştirilmesi;
- browser automation dependency'si;
- mevcut kampanya JSON alanlarının kaldırılması veya yeniden adlandırılması;
- raw HTML arşivi oluşturulması;
- stop-word silme, stemming veya ağır NLP dependency'si.

## Seçilen Yaklaşım

Mevcut pipeline kontrollü biçimde sağlamlaştırılacaktır. Yeni paralel
abstraction'lar yerine aşağıdaki mevcut bileşenler genişletilecektir:

- `src/scraper/models.py`
- `src/scraper/base.py`
- `src/scraper/scraper.py`
- `src/scraper/validation.py`
- `src/scraper/storage.py`
- `src/preprocessing/clean_text.py`
- `src/scraper/registry.py`
- `src/scraper/banks/*`

Banka modülleri yalnızca canlı HTML doğrulaması gerçek bir seçici sorunu
gösterirse değiştirilecektir.

## Mimari ve Sorumluluklar

```text
BDDK parser
    ↓
Mevcut banka registry
    ↓
BaseBankScraper + banka konfigürasyonları
    ↓
Campaign modeli
    ↓
Normalization + validation + deduplication
    ├──→ Quality report
    └──→ Raw JSON
            ↓
        Mevcut Türkçe preprocessing
            ↓
        Processed JSON
```

### Model

`Campaign` mevcut alanlarını ve `1.0.0` şema sürümünü korur. Kaynak URL'nin
fragment ve bilinen tracking parametrelerinden arındırılmış hali kararlı kayıt
kimliği ve duplicate anahtarı için kullanılır. Bu davranış mevcut tüketiciler
için alan kaldırmaz; yalnızca yeni üretilen URL ve kimlikleri kararlı hale
getirir.

### Scraper tabanı

`BaseBankScraper`, liste keşfi ve kampanya detaylarının işlenmesinde mevcut
banka konfigürasyonlarını kullanmaya devam eder. Tek kampanya hatası diğer
kampanyaları durdurmaz. Liste keşfi seviyesindeki hata ilgili bankaya ait bir
failure kaydına dönüştürülür ve üst seviye runner diğer bankalara geçer.

### Runner

CLI runner her banka çalışmasını bağımsız bir sınır içinde yürütür. Bir scraper
beklenmedik istisna üretirse başarılı banka kayıtları korunur, hata kalite
raporuna eklenir ve sıradaki banka çalıştırılır.

### Validation ve duplicate yönetimi

Validation aşağıdaki alanları kontrol eder:

- `bank_slug` ve `bank_name` boş olamaz;
- `title` en az mevcut minimum uzunlukta olmalıdır;
- `content` mevcut minimum içerik uzunluğunu karşılamalıdır;
- `source_url` geçerli bir HTTPS URL olmalıdır;
- başlangıç tarihi bitiş tarihinden sonra olamaz;
- içerikte kalan HTML etiketleri kalite problemi olarak görünmelidir;
- eksik tarih ve özet warning olarak kalmalıdır.

Duplicate kaldırma anahtarı `bank_slug + normalized source_url` olacaktır.
Başlık benzerliği otomatik silme ölçütü yapılmayacaktır; farklı kampanyaların
aynı başlığa sahip olma ihtimali nedeniyle bu yaklaşım yanlış pozitif üretir.
Kaldırılan kayıt sayısı quality report içinde görünür olacaktır.

### Storage ve preprocessing

Mevcut atomik UTF-8 JSON yazımı korunur. Raw `content` alanı değiştirilmez.
Processed çıktı raw kaydı kopyalar ve yalnızca `clean_text`, `tokens` ve
`token_count` alanlarını ekler. Türkçe büyük/küçük harf davranışı ve NFC
normalizasyonu korunur.

## Veri Üretim Politikası

### Geçici smoke doğrulaması

İlk üç öncelikli banka düşük limit ile repository dışındaki geçici bir dizine
yazılır:

```text
Kuveyt Türk
Albaraka Türk
Türkiye Finans
```

Smoke çıktıları kalıcı veri dosyalarının üzerine yazmaz.

### Kalıcı altı banka çıktısı

Testler ve smoke doğrulaması geçtikten sonra mevcut CLI ile altı banka için
kalıcı üretim yapılır:

```text
BDDK
→ data/raw/participation_banks.json

6 banka scraper'ı
→ normalization
→ validation
→ deduplication
├──→ outputs/quality_report.json
└──→ data/raw/campaigns.json
        ↓
    preprocessing
        ↓
    data/processed/campaigns.json
```

Çıktılar canlı kaynağın gerçek durumunu yansıtır. Bir banka başarısız olursa
başarılı bankaların kayıtları yine yazılır; başarısız banka final raporda ve
quality report içinde açıkça gösterilir.

## Hata Modeli ve Logging

Failure kayıtları mümkün olduğunda şu alanları taşır:

```json
{
  "bank_slug": "bank-name",
  "stage": "discovery_or_fetch_or_parse",
  "url": "https://example.invalid",
  "error_type": "Timeout",
  "error": "Hata açıklaması",
  "http_status": null,
  "timestamp": "2026-08-08T12:00:00+00:00"
}
```

Mevcut Python logging sistemi aşağıdaki olayları görünür kılar:

- scraper başlangıcı;
- banka seçimi;
- keşfedilen kampanya sayısı;
- kampanya parse başarısı veya hatası;
- validation sonucu;
- kaldırılan duplicate sayısı;
- persistence sonucu;
- scraper tamamlanması veya başarısızlığı.

Yeni logging dependency'si eklenmez.

## Test Tasarımı

Tüm davranış değişiklikleri test-first uygulanır. Eklenecek veya genişletilecek
testler şunları kapsar:

- tracking parametresi ve fragment temizleyen URL normalizasyonu;
- normalize URL tabanlı duplicate kaldırma;
- zorunlu banka alanları;
- HTML kalıntısı validation'ı;
- yapılandırılmış fetch/parse/discovery failure kayıtları;
- bir banka çöktüğünde diğer bankaların devam etmesi;
- Kuveyt Türk, Albaraka Türk ve Türkiye Finans için listing fixture'dan URL
  keşfi, detail fixture'dan `Campaign` üretimi ve validation.

Unit ve fixture testleri ağ erişimi kullanmaz. Canlı kontroller normal pytest
paketinden ayrı tutulur.

## Regression Kontrolü

Final doğrulama aşağıdakileri içerir:

- tüm pytest testleri;
- izlenen Python dosyalarında flake8;
- FastAPI `/health` ve `/chat` testleri;
- dashboard ESLint;
- Next.js production build;
- ilk üç banka düşük limitli canlı smoke run;
- BDDK canlı banka listesi;
- altı banka kalıcı veri üretimi;
- raw veri validation komutu;
- processed/raw alan ve kayıt sayısı tutarlılığı;
- JSON parse ve UTF-8/Türkçe karakter kontrolü;
- Git diff üzerinden API, frontend ve kullanıcıya ait önceden var olan
  `src/dashboard/package-lock.json` değişikliğinin korunması.

## Dokümantasyon

Kök README ve `data/README.md` tamamen yeniden yazılmayacaktır. Mevcut
bölümlere aşağıdaki bilgiler eklenecektir:

- öncelikli üç banka smoke doğrulaması;
- altı bankalık final üretim komutları;
- URL normalizasyonu ve duplicate politikası;
- yapılandırılmış failure alanları;
- raw ve processed veri ayrımı;
- gerçek scraper durumları ve bilinen riskler.

## Başarı Ölçütleri

- Mevcut API sözleşmeleri ve frontend build'i korunur.
- Altı banka mevcut registry üzerinden desteklenir.
- İlk üç banka fixture ve canlı smoke doğrulamasını geçer.
- Bir bankanın hatası diğer bankaların verisini kaybettirmez.
- Duplicate kampanyalar normalize URL üzerinden persistence öncesi kaldırılır.
- Raw kampanya içeriği processed çıktı üretiminde korunur.
- Quality report validation, duplicate ve failure sonuçlarını içerir.
- Kalıcı BDDK, raw, processed ve quality report dosyaları güncel kodla üretilir.
- Yeni ve mevcut otomatik kontroller başarıyla tamamlanır veya dış kaynaklı
  başarısızlıklar gerçek nedenleriyle raporlanır.

## Riskler

- Banka HTML yapıları haber vermeden değişebilir.
- robots.txt veya site erişim politikaları canlı üretimi kısıtlayabilir.
- Altı bankalık canlı crawl sırasında geçici ağ hataları görülebilir.
- URL normalizasyonunda yalnızca açıkça tracking amacı taşıyan parametreler
  kaldırılmalıdır; işlevsel query parametreleri korunmalıdır.
- Repository'deki kullanıcıya ait mevcut `package-lock.json` değişikliği bu
  çalışma kapsamında değildir ve korunmalıdır.
