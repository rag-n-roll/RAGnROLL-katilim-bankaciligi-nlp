# 1. Hafta Veri Mühendisliği Tasarımı

## Kaynak araştırması sonucu

30 Temmuz 2026 kontrolünde BDDK'nın resmî Bankalar sayfasındaki “Katılım
Bankaları” grubu 10 faal kuruluş gösteriyor. Bu nedenle banka listesi sabit bir
Python dizisi değildir; her çalıştırmada BDDK HTML'inden çekilir. Görevdeki altı
banka kampanya toplama kapsamı olarak ayrı tutulur.

İncelenen birincil sayfalar:

- BDDK: <https://www.bddk.gov.tr/Kurulus/Liste/90>
- Kuveyt Türk: <https://www.kuveytturk.com.tr/kampanyalar/kendim-icin/kart-kampanyalari>
- Albaraka Türk: <https://www.albaraka.com.tr/tr/kampanyalar>
- Türkiye Finans: <https://www.turkiyefinans.com.tr/tr-tr/kampanyalar/sayfalar/default.aspx>
- Ziraat Katılım: <https://www.ziraatkatilim.com.tr/kart-kampanyalari>
- Vakıf Katılım: <https://www.vakifkatilim.com.tr/tr/kendim-icin/kampanyalar/mevcut-kampanyalar>
- Emlak Katılım: <https://www.emlakkatilim.com.tr/tr/bireysel/kampanyalar>

## Mimari kararlar

1. **Ortak taban, banka başına modül.** HTTP, tarih ayıklama, metin temizleme ve
   modelleme ortak tabandadır. URL desenleri ve CSS seçiciler banka modülünde
   bulunur. Böylece site değişikliği diğer bankaları etkilemez.
2. **Önce HTML.** Kampanyalar erişilebilir HTML'de bulunduğu için ağır tarayıcı
   otomasyonu üretim bağımlılığı yapılmadı. Gerçek tarayıcıyla görünür içerik ve
   “daha fazla” davranışı doğrulandı. Dinamik API kararsızsa sunucu taraflı
   bağlantılar güvenli geri dönüş olarak kullanılır.
3. **Kibar HTTP.** Tanımlı User-Agent, `robots.txt`, alan adı başına gecikme,
   zaman aşımı, 429/5xx tekrar denemesi ve `Retry-After` desteği vardır.
4. **Ham veri değişmezliği.** `content` korunur; temizlenmiş metin yeni alana
   yazılır. Çıktılar önce geçici dosyaya, sonra atomik olarak hedefe taşınır.
5. **Kısmi hata görünürlüğü.** Tek kampanyanın bozulması tüm koşuyu durdurmaz;
   URL ve hata `fetch_failures` içinde raporlanır.
6. **Tarih alanları nullable.** Sürekli kampanyalar ve farklı tarih yazımları
   nedeniyle eksik tarih hata değil uyarıdır. Türkçe ay adları ve sayısal tarih
   aralıkları desteklenir.

## Haftalık çalışma sırası

1. BDDK listesini üret ve beklenmedik adet değişimini incele.
2. Öncelikli üç bankayı düşük limit ile smoke-test et.
3. Kalite skoru ve çekme hatalarını kontrol et.
4. Altı bankalık koşuyu çalıştır.
5. İşlenmiş veri setini üret ve örnek kayıtları elle gözden geçir.

Üretim zamanlaması eklenirken günlük tek koşu çoğu kampanya kullanım senaryosu
için yeterlidir. Tam veri yerine kaynak URL kimliğiyle upsert yapılması ve önceki
snapshot'ın saklanması bir sonraki iterasyonun doğal adımıdır.
