# RAGnROLL — Katılım Bankacılığı NLP

TEKNOFEST 2026 Yapay Zekâ Dil Ajanları Yarışması için katılım bankacılığı
kampanyalarını toplayan ve Türkçe NLP işlemine hazırlayan veri hattı.

## 1. hafta veri mühendisliği kapsamı

- BDDK'nın resmî kuruluş sayfasından güncel katılım bankası listesi
- Altı yerleşik banka için bağımsız scraper modülleri
- İlk öncelik: Kuveyt Türk, Albaraka Türk ve Türkiye Finans
- Sürümlü ortak JSON şeması ve atomik dosya yazımı
- Kayıt, tarih, URL, tekrar ve çekme hatası kalite kontrolleri
- Unicode/Türkçe uyumlu temizleme ve hafif tokenizasyon

BDDK listesi Temmuz 2026 itibarıyla 10 banka içerir. Kampanya kapsamındaki altı
banka ise Albaraka Türk, Kuveyt Türk, Türkiye Finans, Ziraat Katılım, Vakıf
Katılım ve Emlak Katılım'dır. Yeni/dijital bankalar BDDK çıktısında korunur;
kampanya scraper kaydına gereksinim oldukça ayrıca eklenebilir.

## Kurulum

Python 3.11 veya üstü önerilir.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Kullanım

BDDK listesini çekin:

```bash
python -m src.scraper.scraper banks
```

Öncelikli üç bankadan banka başına en fazla 10 kampanya çekin ve kalite
raporunu üretin:

```bash
python -m src.scraper.scraper --verbose campaigns \
  --banks priority \
  --max-per-bank 10
```

Altı bankanın tümünü çalıştırın:

```bash
python -m src.scraper.scraper campaigns --banks all --max-per-bank 20
```

`--banks priority` ile düşük `--max-per-bank` sınırı kullanan çalıştırmalar
geçici smoke kontrolleri içindir. Kalıcı veri seti yenilenirken altı bankayı
kapsayan `--banks all` komutu kullanılmalıdır.

Bir bankadaki hata diğer bankaların taramasını durdurmaz; başarılı kayıtlar
yazılır ve kısmi başarı durumunda komut `2` çıkış koduyla tamamlanır. Banka,
aşama, URL, hata türü/mesajı, HTTP durumu ve UTC zamanı içeren ayrıntılar kalite
raporunun `fetch_failures` alanında tutulur. Hiç kayıt alınamayan toplam
kesintide son bilinen iyi kampanya dosyası korunur. Kampanya çıktısı ile kalite
raporu için aynı dosya yolu verilmesi de veri kaybını önlemek üzere reddedilir.

Ham metinleri temizleyip tokenize edin:

```bash
python -m src.scraper.scraper preprocess data/raw/campaigns.json \
  --output data/processed/campaigns.json
```

Mevcut bir veri setini yeniden doğrulayın:

```bash
python -m src.scraper.scraper validate data/raw/campaigns.json
```

Testler:

```bash
python -m pytest
```

## Çıktılar

- `data/raw/participation_banks.json`: BDDK kuruluş listesi
- `data/raw/campaigns.json`: ortak şemadaki ham kampanyalar
- `data/processed/campaigns.json`: temiz metin ve tokenlar
- `outputs/quality_report.json`: kayıt ve çekme hata raporu

Alan tanımları, kalite ölçütleri, veri kökeni ve kullanım notları için
[`data/README.md`](data/README.md), teknik kararlar için
[`docs/week-1-data-engineering.md`](docs/week-1-data-engineering.md) dosyasına
bakın.

## Sorumlu tarama

İstemci tanımlı bir User-Agent kullanır, `robots.txt` kurallarını varsayılan
olarak uygular, aynı alan adına istekler arasında bekler ve geçici hatalarda
kontrollü tekrar dener. `--ignore-robots` yalnızca site sahibinden açık izin
alındığında kullanılmalıdır. Üretilen verinin yeniden yayımlanmasından önce
ilgili sitelerin kullanım şartları ve içerik hakları ayrıca kontrol edilmelidir.

Kaynak URL'lerdeki `utm_*`, `gclid`, `fbclid` gibi izleme parametreleri kararlı
kayıt kimliği üretilmeden önce kaldırılır. Kayıtlar kalıcı depolamadan önce
`bank_slug + normalize edilmiş source_url` anahtarıyla tekilleştirilir;
çıkarılan kayıtların ayrıntıları kalite raporunun `duplicates` alanına yazılır.

