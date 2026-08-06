# Katılım Bankacılığı Dashboard Tasarım Sistemi

## 1. Dokümanın Amacı

Bu doküman, Katılım Bankacılığı NLP Projesi kapsamında hazırlanan dashboard mockup tasarımlarının ortak görsel kararlarını tanımlar.

Tasarım sistemi aşağıdaki dört ekran esas alınarak hazırlanmıştır:

- Ana Sayfa
- Ürün Karşılaştırma Sayfası
- Kampanyalar Sayfası
- AI Asistan Sayfası

Bu dokümanda yalnızca mockup tasarımlarında görülen:

- renk paleti,
- tipografi,
- kart yapıları,
- butonlar,
- tablolar,
- grafikler,
- etiketler,
- form alanları,
- sohbet bileşenleri

açıklanmaktadır.

Mockuplarda bulunmayan ekstra özellikler bu dokümana eklenmemiştir.

---

## 2. Genel Tasarım Yaklaşımı

Dashboard arayüzünde katılım bankacılığının kurumsal ve güvenilir yapısı, yapay zekâ destekli modern analiz platformu görünümüyle birleştirilmiştir.

Tasarımın genel karakteri:

- Kurumsal
- Güvenilir
- Modern
- Sade
- Premium
- Teknolojik
- Kolay okunabilir

Bütün ekranlarda ortak olarak:

- üst navbar,
- açık renkli sayfa arka planı,
- beyaz kartlar,
- hafif kart gölgeleri,
- petrol mavisi ana renk,
- turkuaz teknoloji vurguları,
- sarı finansal vurgular

kullanılmaktadır.

---

## 3. Renk Paleti

Aşağıdaki renk kodları, mockup tasarımlarındaki renklerin kodlama aşamasında kullanılacak dijital karşılıklarıdır.

### 3.1 Petrol Mavisi

Petrol mavisi, uygulamanın ana kurumsal rengidir.

```text
Ana petrol mavisi: #002B3A
İkinci petrol tonu: #003D4F
```

Kullanıldığı alanlar:

- Navbar arka planı
- Büyük başlıklar
- Ana butonlar
- Tablo başlıkları
- Kart başlıkları
- Ana grafik veri serileri
- Önemli metinler
- Mesaj gönderme ikonu

Navbar yüzeyinde çok hafif bir renk geçişi kullanılabilir:

```css
background: linear-gradient(
  90deg,
  #002b3a 0%,
  #003d4f 100%
);
```

---

### 3.2 Turkuaz

Turkuaz renk, yapay zekâ, NLP ve teknolojik bileşenleri temsil eder.

```text
Ana turkuaz: #12B8B0
Açık turkuaz: #E3F8F6
```

Kullanıldığı alanlar:

- AI Asistan butonu
- AI ve NLP ikonları
- Kullanıcı mesaj balonları
- Finansman ve yatırım etiketleri
- Grafik sütunları
- Seçili veya avantajlı değerler
- Hazır soru ikonları
- Bilgi ikonları
- Gönder ikonu
- Küçük teknoloji vurguları

---

### 3.3 Sarı Vurgu Rengi

Sarı vurgu rengi, finansal değerleri ve dikkat çekmesi gereken alanları vurgulamak için kullanılır.

```text
Ana sarı vurgu: #E7AA2D
Açık sarı vurgu: #FFF4DD
```

Kullanıldığı alanlar:

- Aktif navbar bağlantısının alt çizgisi
- Toplam kampanya değeri
- Kart türü etiketi
- Masrafsız etiketi
- Esnek vade etiketi
- Masraf grafiğinin sütunları
- Seçili kampanya satırının sol çizgisi
- AI Asistana Sor butonunun kenarlığı
- AI Asistana Sor butonunun metni
- Grafiklerde yardımcı veri serileri

Sarı vurgu rengi büyük yüzeylerde kullanılmaz. Küçük ve kontrollü detaylarda kullanılır.

---

### 3.4 Arka Plan ve Yüzey Renkleri

```text
Ana sayfa arka planı: #F7F9FA
Kart arka planı: #FFFFFF
Açık yüzey rengi: #F4F7F8
Kenarlık rengi: #E3E9EB
Ana metin rengi: #102F3D
İkincil metin rengi: #62737B
```

Mockuplardaki yüzey yapısı:

- Sayfa arka planı açık gri-beyazdır.
- Kart yüzeyleri beyazdır.
- Kartlarda renkli arka plan kullanılmaz.
- Kartlar hafif gölge ve ince kenarlıkla arka plandan ayrılır.
- Turkuaz ve sarı renkler yalnızca vurgu alanlarında kullanılır.

---

## 4. Tipografi

Mockuplarda iki farklı yazı tipi yaklaşımı görülmektedir:

- Büyük başlıklarda serif yazı tipi
- Arayüz metinlerinde sans-serif yazı tipi

### 4.1 Başlık Yazı Tipi

Büyük başlıklar klasik, kurumsal ve premium bir serif görünümüne sahiptir.

Kodlama aşamasında bu görünüme yakın bir serif font kullanılacaktır.

Önerilen font:

```text
Playfair Display
```

Kullanıldığı alanlar:

- Katılım Bankacılığı proje adı
- Ana sayfa hero başlığı
- Ürün Karşılaştırma başlığı
- Kampanya Merkezi başlığı
- AI Asistanı başlığı
- Hazır Sorular başlığı
- AI Asistan tanıtım kartı başlığı

---

### 4.2 Arayüz Yazı Tipi

Navbar bağlantılarında, tablolarda, açıklamalarda, butonlarda ve sohbet metinlerinde sade bir sans-serif font kullanılacaktır.

Önerilen font:

```text
Geist
```

Kullanıldığı alanlar:

- Navbar bağlantıları
- Açıklama metinleri
- Buton yazıları
- Tablo içerikleri
- Kart içerikleri
- Form alanları
- Finansal değerler
- Sohbet mesajları
- Etiketler
- Grafik açıklamaları

---

### 4.3 Yazı Hiyerarşisi

| Kullanım | Yaklaşık Boyut | Kalınlık |
|---|---:|---:|
| Ana sayfa hero başlığı | 48–52 px | 700 |
| Sayfa başlığı | 40–44 px | 700 |
| Büyük panel başlığı | 28–34 px | 700 |
| Bölüm başlığı | 18–22 px | 600 |
| Kart başlığı | 16–18 px | 600 |
| Ana metin | 15–16 px | 400 |
| Navbar bağlantısı | 15–16 px | 500 |
| Buton metni | 15–16 px | 600 |
| Yardımcı metin | 13–14 px | 400 |
| Etiket metni | 12–13 px | 500 |

---

## 5. Navbar

Navbar bütün sayfalarda aynı yapıda kullanılmaktadır.

### 5.1 Navbar İçeriği

- Katılım Bankacılığı
- Ana Sayfa
- Karşılaştırma
- Kampanyalar
- AI Asistan

### 5.2 Navbar Görünümü

- Petrol mavisi arka plan
- Sol tarafta beyaz proje adı
- Sağ tarafta navigasyon bağlantıları
- Beyaz navigasyon metinleri
- Aktif sayfanın altında sarı çizgi
- AI Asistan bağlantısında turkuaz kenarlık
- AI Asistan bağlantısında turkuaz ikon
- Hafif yuvarlatılmış AI Asistan butonu

Navbar içerisinde proje adının yanında ayrı bir logo kullanılmamaktadır.

---

## 6. Ortak Kart Yapısı

Bütün ana içerikler beyaz kartlar içerisinde gösterilir.

Kartların ortak özellikleri:

- Beyaz arka plan
- İnce açık gri kenarlık
- Hafif ve yumuşak gölge
- Yuvarlatılmış köşeler
- Geniş iç boşluk
- Düzenli içerik hiyerarşisi
- Kartlar arasında yeterli boşluk

Yaklaşık köşe yuvarlaklığı:

```text
14–18 px
```

Mockuplardaki gölge yapısına uygun önerilen gölge:

```css
box-shadow: 0 8px 24px rgba(15, 54, 68, 0.09);
```

Daha küçük kartlarda daha hafif gölge kullanılabilir:

```css
box-shadow: 0 4px 14px rgba(15, 54, 68, 0.07);
```

Kart gölgeleri koyu, sert veya yoğun olmayacaktır.

---

## 7. Butonlar

### 7.1 Ana Buton

Kullanıldığı alanlar:

- Kampanyaları Keşfet
- Karşılaştır

Görünümü:

- Petrol mavisi arka plan
- Beyaz metin
- Sol tarafta ikon
- Yuvarlatılmış köşeler
- Hafif gölge
- Orta veya geniş yatay yapı

---

### 7.2 İkincil Buton

Kullanıldığı alan:

- AI Asistana Sor

Görünümü:

- Beyaz arka plan
- Sarı kenarlık
- Sarı metin
- Sol tarafta ikon
- Yuvarlatılmış köşeler

---

### 7.3 AI Asistan Navbar Butonu

Görünümü:

- Navbar ile uyumlu petrol mavisi arka plan
- Turkuaz kenarlık
- Turkuaz ikon
- Turkuaz metin
- Yuvarlatılmış köşeler

---

## 8. Etiketler

Etiketler ürün türlerini ve avantaj bilgilerini kısa biçimde göstermek için kullanılır.

### 8.1 Turkuaz Etiketler

Örnekler:

- Finansman
- Yatırım
- En Düşük
- Düşük oran
- Uzun vade
- Yapay Zekâ Destekli

Görünümü:

- Açık turkuaz arka plan
- Turkuaz veya petrol mavisi metin
- Küçük yuvarlatılmış köşeler
- Kısa yatay yapı

---

### 8.2 Sarı Etiketler

Örnekler:

- Kart
- Masrafsız
- Esnek vade

Görünümü:

- Açık sarı arka plan
- Sarı veya koyu sarı metin
- Küçük yuvarlatılmış köşeler
- Kısa yatay yapı

---

# 9. Ana Sayfa UI Bileşenleri

## 9.1 Hero Alanı

Ana sayfanın üst bölümünde geniş bir hero kartı bulunmaktadır.

Hero alanında:

- Büyük serif başlık
- Kısa açıklama metni
- Kampanyaları Keşfet butonu
- AI Asistana Sor butonu
- Sağ tarafta finans ve AI temalı görsel
- Hafif kart gölgesi
- Yuvarlatılmış köşeler

bulunmaktadır.

Başlık:

> Katılım bankacılığı kampanyalarını tek ekranda analiz edin.

Açıklama:

> Finansman, kart ve yatırım kampanyalarını yapay zekâ desteğiyle karşılaştırın, en uygun fırsatları kolayca keşfedin.

---

## 9.2 Özet Kartları

Hero alanının altında, sol tarafta üç özet kartı alt alta gösterilir:

- Toplam Banka
- Toplam Kampanya
- Ortalama Kâr Payı

Her kartta:

- Sol tarafta dairesel ikon alanı
- Sağ tarafta başlık
- Büyük sayısal değer
- Beyaz kart yüzeyi
- Hafif gölge
- Yuvarlatılmış köşeler

bulunmaktadır.

Renk kullanımı:

- Toplam Banka: petrol mavisi
- Toplam Kampanya: sarı vurgu
- Ortalama Kâr Payı: turkuaz

---

## 9.3 Kampanya Dağılım Grafiği

Özet kartlarının sağında geniş bir grafik kartı bulunmaktadır.

Başlık:

> Bankalara Göre Kampanya Dağılımı

Kart içerisinde:

- Donut grafik
- Banka adları
- Kampanya adetleri
- Yüzde oranları

gösterilmektedir.

Grafik renkleri:

- Petrol mavisi
- Turkuaz
- Sarı
- Açık turkuaz tonları

Grafik kartında beyaz yüzey ve hafif gölge kullanılır.

---

## 9.4 Güncel Kampanyalar Tablosu

Ana sayfanın alt bölümünde geniş bir tablo kartı bulunmaktadır.

Başlık:

> Güncel Kampanyalar

Tablo sütunları:

- Banka
- Kampanya Adı
- Tür
- Tarih

Kaynak sütunu bulunmamaktadır.

Ürün türleri turkuaz veya sarı etiketlerle gösterilir.

---

# 10. Ürün Karşılaştırma Sayfası UI Bileşenleri

## 10.1 Sayfa Başlığı

Başlık:

> Ürün Karşılaştırma

Açıklama:

> Katılım bankalarının benzer ürünlerini tek ekranda karşılaştırın.

Başlığın sağ tarafında turkuaz ve sarı çizgilerden oluşan dekoratif desen bulunmaktadır.

---

## 10.2 Filtre Kartı

Sayfa başlığının altında geniş bir filtre kartı bulunmaktadır.

Filtre kartında:

- Banka Seçimi
- Ürün Türü
- Karşılaştır butonu

yer almaktadır.

### Banka Seçimi

- Geniş select alanı
- Sol tarafta banka ikonu
- Sağ tarafta aşağı ok
- Birden fazla banka adı gösterimi

### Ürün Türü

- Geniş select alanı
- Sol tarafta taşıt veya ürün ikonu
- Sağ tarafta aşağı ok

### Karşılaştır Butonu

- Petrol mavisi arka plan
- Turkuaz terazi ikonu
- Beyaz metin
- Yuvarlatılmış köşeler

Filtre kartında beyaz yüzey ve hafif gölge kullanılmaktadır.

---

## 10.3 Karşılaştırma Tablosu

Filtre kartının altında karşılaştırma tablosu bulunmaktadır.

Tablo sütunları:

- Banka
- Kampanya
- Kâr Payı Oranı
- Vade
- Taksit
- Masraf
- Avantaj

En düşük kâr payı:

- Turkuaz metinle
- “En Düşük” etiketiyle

vurgulanmaktadır.

Avantaj alanında:

- Düşük oran
- Masrafsız
- Uzun vade
- Esnek vade

etiketleri kullanılmaktadır.

---

## 10.4 Kâr Payı Oranı Karşılaştırma Grafiği

Sayfanın sol alt bölümünde bulunmaktadır.

Başlık:

> Kâr Payı Oranı Karşılaştırması

Özellikleri:

- Her banka ayrı sütunla gösterilir.
- Sütunların üzerinde oran değerleri bulunur.
- En düşük oran turkuaz etiketle belirtilir.
- Petrol mavisi, turkuaz ve sarı sütunlar kullanılır.
- Alt bölümde banka logoları ve adları bulunur.

---

## 10.5 Vade ve Masraf Karşılaştırması

Sayfanın sağ alt bölümünde geniş bir kart içerisinde gösterilmektedir.

Kart iki bölüme ayrılır:

- Vade (Ay)
- Masraf (TL)

Vade bölümünde turkuaz sütunlar kullanılır.

Masraf bölümünde sarı sütunlar kullanılır.

İki bölüm ince dikey çizgiyle ayrılır.

---

# 11. Kampanyalar Sayfası UI Bileşenleri

## 11.1 Sayfa Başlığı

Başlık:

> Kampanya Merkezi

Açıklama:

> Bankaların güncel kampanyalarını, kampanya metinlerini ve çıkarılan finansal bilgileri tek ekranda inceleyin.

Başlığın sağ tarafında turkuaz ve sarı dekoratif çizgiler bulunur.

---

## 11.2 Banka Bazlı Tüm Kampanyalar Kartı

Sol tarafta banka bazlı kampanya listesi bulunmaktadır.

Kart başlığı:

> Banka Bazlı Tüm Kampanyalar

Sağ üstte kampanya sayısı gösterilir:

```text
25 kampanya
```

Her kampanya satırında:

- Banka logosu
- Banka adı
- Kampanya adı
- Ürün türü etiketi

bulunur.

Seçili kampanya satırında:

- Çok açık sarı arka plan
- Sol tarafta ince sarı çizgi

kullanılır.

Kartın altında:

> Tümünü Görüntüle

bağlantısı bulunmaktadır.

---

## 11.3 Kampanya Metni Kartı

Orta bölümde seçili kampanyanın orijinal metni gösterilir.

Kartta:

- Belge ikonu
- Kampanya Metni başlığı
- Kampanya açıklama paragrafları
- Alt bölümde bilgi kutusu

bulunmaktadır.

Bilgi kutusu metni:

> Bu metin yapay zekâ ile analiz edilerek finansal bilgiler çıkarılmıştır.

Bilgi kutusunda açık yüzey ve turkuaz bilgi ikonu kullanılır.

---

## 11.4 Çıkarılan Bilgiler Kartı

Sağ tarafta NLP ile çıkarılan bilgiler gösterilir.

Kart başlığı:

> Çıkarılan Bilgiler

Gösterilen alanlar:

- Banka
- Ürün Türü
- Kâr Payı
- Vade
- Masraf
- Başvuru Koşulu
- Geçerlilik Tarihi

Her satırda:

- Sol tarafta dairesel ikon
- Ortada alan adı
- Sağ tarafta değer

bulunmaktadır.

Ürün türü bilgisi etiket içerisinde gösterilir.

---

## 11.5 Yapılandırılmış Veri Tablosu

Sayfanın alt bölümünde geniş bir tablo kartı bulunmaktadır.

Başlık:

> Yapılandırılmış Veri Tablosu

Tablo sütunları:

- Banka
- Kampanya Adı
- Tür
- Kâr Payı
- Vade
- Masraf
- Geçerlilik

Tabloda:

- Banka logoları
- Ürün türü etiketleri
- En düşük oran etiketi
- İnce yatay ayırıcılar

kullanılmaktadır.

---

# 12. AI Asistan Sayfası UI Bileşenleri

AI Asistan sayfası iki ana sütundan oluşmaktadır:

- Sol tarafta büyük sohbet paneli
- Sağ tarafta iki kart

---

## 12.1 Sol Sohbet Paneli

Sohbet panelinin üst bölümünde:

- Küçük robot görseli
- AI Asistanı başlığı
- Turkuaz ve sarı dekoratif çizgiler

bulunmaktadır.

Başlığın altında ayrı bir açıklama metni bulunmamaktadır.

Panelin geri kalanında sohbet mesajları gösterilir.

---

## 12.2 Kullanıcı Mesajları

Kullanıcı mesajları:

- Sağ tarafta gösterilir.
- Açık turkuaz arka plana sahiptir.
- Yuvarlatılmış köşelidir.
- Sağ alt bölümünde mesaj saati bulunur.
- Turkuaz onay işareti içerir.

---

## 12.3 AI Mesajları

AI mesajları:

- Sol tarafta gösterilir.
- Beyaz veya çok açık gri arka plana sahiptir.
- Sol yanında küçük robot avatarı bulunur.
- Yuvarlatılmış köşelidir.
- Madde işaretli finansal bilgiler içerebilir.
- Sağ alt bölümünde mesaj saati bulunur.

---

## 12.4 Mesaj Giriş Alanı

Sohbet panelinin alt kısmında bulunmaktadır.

Bileşenler:

- Sol tarafta dairesel artı butonu
- Ortada geniş mesaj giriş alanı
- Sağ tarafta turkuaz gönder ikonu

Mesaj giriş alanının altında bilgilendirme metni bulunur:

> Yanıtlar bilgilendirme amaçlıdır. Detaylı bilgi için lütfen bankanızla iletişime geçiniz.

---

## 12.5 AI Asistan Tanıtım Kartı

Sağ üst bölümde bulunmaktadır.

Kartta:

- AI Asistanı başlığı
- Yapay Zekâ Destekli etiketi
- Kısa açıklama
- Büyük robot görseli
- Turkuaz ve sarı dekoratif çizgiler
- Üç özellik satırı

bulunmaktadır.

Özellikler:

- 7/24 Akıllı Destek
- Güvenilir ve Güncel Bilgi
- Size Özel Öneriler

Her özellik satırının yanında turkuaz ikon kullanılır.

---

## 12.6 Hazır Sorular Kartı

Sağ alt bölümde bulunmaktadır.

Başlık:

> Hazır Sorular

Hazır soru örnekleri:

- En yüksek kâr payı hangi bankada?
- Taşıt finansmanında en uygun seçenek hangisi?
- Masrafsız kart kampanyaları neler?
- Yatırım kampanyalarını karşılaştır

Her soru:

- Ayrı beyaz satır kartı içerisinde
- Sol tarafta turkuaz ikonla
- Sağ tarafta turkuaz yön oku ile
- Hafif gölgeyle
- Yuvarlatılmış köşelerle

gösterilmektedir.

AI Asistan sayfasında aşağıdaki alanlar bulunmamaktadır:

- Filtreler
- Hızlı işlemler
- Günlük özet
- İçgörü paneli
- İstatistik kartları

---

## 13. İkon Kararları

Mockuplarda sade ve çizgisel ikonlar kullanılmaktadır.

İkon renkleri:

- Petrol mavisi
- Turkuaz
- Sarı vurgu rengi

Kullanılan ikon türleri:

- Banka
- Kampanya
- Finansman
- Kart
- Yatırım
- Kâr payı
- Vade
- Masraf
- Karşılaştırma
- Yapay zekâ
- Mesaj
- Gönder
- Bilgi
- Belge
- Takvim

İkonların çizgi kalınlıkları ve görsel stilleri ekranlar arasında tutarlı olmalıdır.

---

## 14. Tablo Kararları

Mockuplardaki tabloların ortak özellikleri:

- Beyaz arka plan
- İnce gri yatay çizgiler
- Açık tablo başlık alanı
- Sol hizalı metin
- Düzenli sayısal değerler
- Ürün türlerinde etiket kullanımı
- Banka adlarının yanında logo kullanımı
- Yuvarlatılmış dış kart
- Hafif gölge

Tablolarda yoğun dikey çizgiler kullanılmamaktadır.

---

## 15. Form Alanları

Karşılaştırma sayfasında kullanılan select alanlarının özellikleri:

- Beyaz arka plan
- İnce gri kenarlık
- Yuvarlatılmış köşeler
- Sol tarafta ikon
- Sağ tarafta aşağı ok
- Yeterli yatay boşluk
- Geniş ve kolay okunabilir yapı

Form alanları ayrı bir beyaz kart içerisinde gösterilmektedir.

---

## 16. Grafik Kararları

Kullanılan grafik türleri:

- Donut grafik
- Dikey sütun grafik

Grafiklerde kullanılan renkler:

- Petrol mavisi
- Turkuaz
- Sarı
- Açık turkuaz tonları

Grafiklerde:

- Başlık
- Sayısal değer
- Banka adı veya banka logosu
- Açıklayıcı etiketler

bulunmaktadır.

Grafik kartları beyaz yüzeye, yuvarlatılmış köşelere ve hafif gölgeye sahiptir.

---

## 17. Ortak Yerleşim Kararları

- Bütün sayfalarda aynı navbar kullanılacaktır.
- İçerikler geniş ve ortalanmış bir alanda gösterilecektir.
- Kartlar arasında düzenli boşluk bırakılacaktır.
- Sayfalar masaüstü dashboard düzeninde hazırlanacaktır.
- Beyaz alan kullanımı korunacaktır.
- Petrol mavisi ana kurumsal renk olacaktır.
- Turkuaz teknoloji ve AI vurgusu olacaktır.
- Sarı renk finansal ve dikkat çekici vurgu olacaktır.
- Kartlar beyaz yüzeyli olacaktır.
- Kartlara hafif gölge uygulanacaktır.
- Ağır, koyu veya keskin gölgeler kullanılmayacaktır.
- Gereksiz renk ve bileşen kalabalığından kaçınılacaktır.

---

## 18. Sonuç

Dashboard için alınan temel tasarım kararları:

```text
Başlık yazı tipi yaklaşımı: Serif
Arayüz yazı tipi yaklaşımı: Sans-serif
Önerilen başlık fontu: Playfair Display
Önerilen arayüz fontu: Geist

Ana renk: Petrol mavisi
AI ve NLP vurgu rengi: Turkuaz
Finansal vurgu rengi: Sarı
Sayfa arka planı: Açık gri-beyaz
Kart arka planı: Beyaz
Kart görünümü: Hafif gölgeli ve yuvarlatılmış
Navigasyon yapısı: Üst navbar
```

Bu tasarım sistemi, hazırlanan dört dashboard mockup’ının React ve Next.js kullanılarak geliştirilmesi sırasında temel alınacaktır.