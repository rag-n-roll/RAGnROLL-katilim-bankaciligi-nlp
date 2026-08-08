# RAGnROLL — Katılım Bankacılığı NLP

TEKNOFEST 2026 Yapay Zekâ Dil Ajanları Yarışması için katılım bankacılığı
kampanyalarını toplayan ve Türkçe NLP işlemine hazırlayan veri hattı.

## 1. hafta veri mühendisliği kapsamı

- BDDK'nın resmî Türkçe `/Kurulus/Liste/77` sayfasından güncel katılım bankası listesi
- BDDK kataloğundaki 10 banka için bağımsız ürün/kampanya scraper adaptörleri
- İlk öncelik: Kuveyt Türk, Albaraka Türk ve Türkiye Finans
- Sürümlü ortak JSON şeması ve atomik dosya yazımı
- Kayıt, tarih, URL, tekrar ve çekme hatası kalite kontrolleri
- Unicode/Türkçe uyumlu temizleme ve hafif tokenizasyon

BDDK listesi Ağustos 2026 itibarıyla 10 banka içerir. Veri hattı bu katalogdaki
hiçbir bankayı sessizce atlamaz. Adil Katılım'ın kamuya açık ürün/hizmet metni,
Dünya Katılım, Hayat Finans ve T.O.M. Katılım dahil diğer bankaların resmî
kampanya metinleri ortak ham şemada saklanır.

## Kurulum

Python 3.11 veya üstü önerilir.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Kullanım

BDDK kataloğundan başlayarak tüm veri hattını tek komutla çalıştırın:

```bash
python -m src.scraper.scraper --verbose collect \
  --max-per-bank 20 \
  --banks-output data/raw/participation_banks.json \
  --raw-output data/raw/campaigns.json \
  --processed-output data/processed/campaigns.json \
  --quality-report outputs/quality_report.json
```

Komut BDDK kapsam raporunu, ham kayıtları, PRD alanları çıkarılmış işlenmiş
veriyi ve banka/alan doluluk metriklerini birlikte üretir. Eksik banka, sıfır
kayıtlı banka, ağ/ayrıştırma hatası veya doğrulama hatası varsa `2` ile çıkar.

BDDK listesini çekin:

```bash
python -m src.scraper.scraper banks
```

Öncelikli üç bankadan banka başına en fazla 10 kampanya çekin ve kalite
raporunu üretin:

```bash
python -m src.scraper.scraper --verbose campaigns \
  --banks priority \
  --max-per-bank 10 \
  --output outputs/smoke_campaigns.json \
  --quality-report outputs/smoke_quality_report.json
```

Registry'deki bankaların tümünü yalnızca ham toplama modunda çalıştırın:

```bash
python -m src.scraper.scraper campaigns \
  --banks all \
  --max-per-bank 20 \
  --output data/raw/campaigns.json \
  --quality-report outputs/quality_report.json
```

`--banks priority` ile düşük `--max-per-bank` sınırı kullanan çalıştırmalar
geçici smoke kontrolleri içindir; `outputs/smoke_*.json` dosyaları Git tarafından
yok sayılır ve kanonik veri setinin üzerine yazmaz. Kalıcı yenilemede BDDK
güdümlü `collect` komutu kullanılmalıdır. `campaigns` ve `preprocess` alt
komutları tanılama ve kısmi yeniden çalıştırma için korunur.

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
python -m src.scraper.scraper validate data/raw/campaigns.json \
  --output outputs/validation_report.json
```

Bu ayrı doğrulama raporu, tarama sırasında üretilen tekrar ve `fetch_failures`
ayrıntılarını içeren kanonik `outputs/quality_report.json` dosyasını korur.

Testler:

```bash
python -m pytest
```

## Çıktılar

- `data/raw/participation_banks.json`: BDDK kuruluş listesi
- `data/raw/campaigns.json`: ortak şemadaki ham kampanyalar
- `data/processed/campaigns.json`: temiz metin, tokenlar ve PRD `structured` alanları
- `outputs/quality_report.json`: kapsam, alan doluluğu, kayıt ve çekme hata raporu

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

