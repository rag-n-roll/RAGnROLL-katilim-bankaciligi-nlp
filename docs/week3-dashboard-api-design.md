# Week 3 - Dashboard Backend API Integration Design

## Amaç

Bu doküman, Next.js ile geliştirilen dashboard arayüzünün FastAPI tabanlı backend servisi ile nasıl haberleşeceğini tanımlar.

Frontend tarafında şu anda kullanılan mock veriler, backend servisleri ile entegrasyon tamamlandığında gerçek API verileri ile değiştirilecektir.

---

## API Base URL

Backend servisinin varsayılan adresi:

`http://localhost:8000`

API endpointleri `/api/v1` prefix'i altında çalışmaktadır.

Frontend tarafında kullanılacak base URL:

```ts
const API_BASE_URL = "http://localhost:8000/api/v1";
```

---

## Frontend - Backend Endpoint Eşleşmesi

### Ana Sayfa

Ana sayfadaki dashboard özet verileri için:

`GET /api/v1/dashboard/summary`

endpointi kullanılacaktır.

Bu endpoint ile dashboard sayaçları, kampanya özetleri ve son scraper koşusuna ait bilgiler frontend tarafına aktarılacaktır.

---

### Banka Verileri

Banka bazlı kampanya ve ürün bilgilerinin alınması için:

`GET /api/v1/banks`

endpointi kullanılacaktır.

Bu veri özellikle banka filtrelerinin dinamik olarak oluşturulmasında kullanılabilir.

---

### Kampanyalar Sayfası

Kampanya listesinin alınması için:

`GET /api/v1/campaigns`

endpointi kullanılacaktır.

Desteklenen filtre parametreleri:

- `bank_slug`
- `product_type`
- `currency`
- `search`
- `limit`
- `offset`

Örnek:

`GET /api/v1/campaigns?bank_slug=kuveyt-turk&product_type=financing&limit=20&offset=0`

Filtreleme ve sayfalama backend tarafında SQLite üzerinden yapılmaktadır.

Seçilen kampanyanın detayını almak için:

`GET /api/v1/campaigns/{id}`

endpointi kullanılacaktır.

Bu endpointten alınan detaylar kampanya metni ve çıkarılan finansal bilgiler alanlarında gösterilecektir.

---

### Karşılaştırma Sayfası

Kampanyaların karşılaştırılması için:

`POST /api/v1/comparisons`

endpointi kullanılacaktır.

Örnek istek:

```json
{
  "product_type": "financing",
  "currency": "TRY",
  "amount": 100000
}
```

Backend tarafından döndürülen karşılaştırma sonuçları:

- Karşılaştırma tablosunda
- Kâr payı grafiğinde
- Vade grafiğinde
- Masraf grafiğinde

kullanılacaktır.

Karşılaştırma servisi en fazla 500 aday kabul etmektedir. Daha geniş sonuç kümelerinde kullanıcıdan banka veya ürün filtresini daraltması istenecektir.

---

### Veri Yenileme

Yeni kampanya verilerinin toplanması için:

`POST /api/v1/data-refresh`

endpointi kullanılacaktır.

Başlatılan scraper işleminin durumunu kontrol etmek için:

`GET /api/v1/data-refresh/{id}`

endpointi kullanılacaktır.

Backend aynı anda yalnızca bir veri toplama işlemi çalıştırmaktadır. İkinci bir veri yenileme isteği gönderilirse API `409 Conflict` yanıtı döndürebilir.

---

### API Sağlık Kontrolü

Backend ve SQLite servislerinin hazır olup olmadığını kontrol etmek için:

`GET /api/v1/health`

endpointi kullanılabilir.

Bu endpoint frontend açılışında veya bağlantı problemi yaşandığında backend durumunu kontrol etmek amacıyla kullanılabilir.

---

## Genel Veri Akışı

```text
Kullanıcı
   ↓
Next.js Dashboard
   ↓
Frontend API Service
   ↓
FastAPI Backend
   ↓
SQLite / NLP / Scraper
   ↓
JSON Response
   ↓
Kartlar / Tablolar / Plotly Grafikler
```

---

## Frontend API Servis Katmanı

API isteklerinin doğrudan sayfa bileşenleri içerisinde yazılması yerine ortak bir servis katmanında tutulması planlanmaktadır.

Önerilen yapı:

```text
src/dashboard/
├── app/
├── components/
└── services/
    └── api.ts
```

Örnek:

```ts
const API_BASE_URL = "http://localhost:8000/api/v1";

export async function getDashboardSummary() {
  const response = await fetch(`${API_BASE_URL}/dashboard/summary`);

  if (!response.ok) {
    throw new Error("Dashboard verileri alınamadı.");
  }

  return response.json();
}

export async function getBanks() {
  const response = await fetch(`${API_BASE_URL}/banks`);

  if (!response.ok) {
    throw new Error("Banka verileri alınamadı.");
  }

  return response.json();
}

export async function getCampaigns() {
  const response = await fetch(`${API_BASE_URL}/campaigns`);

  if (!response.ok) {
    throw new Error("Kampanya verileri alınamadı.");
  }

  return response.json();
}
```

---

## AI Asistan

Mevcut backend API dokümanında AI Asistan için ayrı bir chatbot endpointi bulunmamaktadır.

Chatbot servisi hazırlandığında AI Asistan sayfası ilgili backend endpointi ile entegre edilecektir.

---

## Hata Yönetimi

Frontend aşağıdaki durumları ele alacaktır:

- Backend servisinin çalışmaması
- API isteğinin başarısız olması
- Boş veri dönmesi
- `409 Conflict` gibi backend hata yanıtları
- Filtre sonucunda kampanya bulunamaması
- Karşılaştırma sonucunun izin verilen aday sayısını aşması

Bu durumlarda kullanıcıya uygun hata veya bilgilendirme mesajı gösterilecektir.

---

## Sonuç

Dashboard ile backend arasındaki entegrasyon yapısı mevcut FastAPI endpointleri dikkate alınarak tasarlanmıştır.

Bir sonraki aşamada dashboard içerisinde kullanılan mock veriler kaldırılarak gerçek API servislerine geçilecek ve kartlar, tablolar, filtreler ve Plotly grafikler dinamik verilerle çalışacaktır.