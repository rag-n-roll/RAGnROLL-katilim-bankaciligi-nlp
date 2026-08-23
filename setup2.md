# Setup 2 - RAG Chatbot Notlari

Bu dosya, hafta 3 sonunda RAG chatbot tarafinda yapilanlari ve kaptanin projeye nasil birlestirebilecegini ozetlemek icin hazirlandi.

## Yapilanlar

- RAG chatbot icin ayri bir demo arayuzu hazirlandi: `src/chatbot/standalone_ui.py`
- Demo arayuzu `http://127.0.0.1:8501` adresinden calisiyor.
- Chatbot cevaplari mevcut RAG pipeline'i uzerinden aliniyor.
- Sohbet icinde basit memory eklendi:
  - Son sorulan banka hatirlaniyor.
  - Kullanici once genel kampanya sorup sonra alan belirtirse baglam korunuyor.
  - Banka degisince yeni banka baglami kullaniliyor.
- Yeni sohbet butonu eklendi:
  - Memory sifirlaniyor.
  - Ekran ilk acilistaki temiz sohbet haline donuyor.
- Cevap uretilirken gonder butonu durdurma butonuna donusuyor.
  - Kullanici cevabi durdurursa RAG'a yeni istek gondermeden ekranda durduruldu mesaji gosteriliyor.
- Tanim sorularinda metadata, es anlamli ve Ingilizce ceviri gibi kullaniciya gereksiz gelen alanlar cevapta gosterilmeyecek sekilde duzenlendi.
- Katilim bankalarini listeleme sorusunda sistemin eksik liste vermemesi icin bankalar katalog baglami daha net kullandirildi.

## Degisen Dosyalar

- `src/chatbot/rag_langchain.py`
  - RAG prompt ve cevap temizleme davranislari iyilestirildi.
  - Aktif Chroma collection ayari korunuyor.(karsilastirma icin veriler hala eksik data bitince tekrar embedding yapilmali )
  - Banka listeleme ve tanim cevaplari daha kontrollu hale getirildi.

- `src/chatbot/standalone_ui.py`
  - Tek dosyalik chatbot demo arayuzu.
  - 8501 portunda calisir.
  - Yeni sohbet, memory reset, cevap durdurma ve stream cevap gosterimi burada bulunur.

## Kullanilan Ortamlar

### `venv`

Projede eski/ana Python sanal ortami olarak duruyor. Bazi onceki calistirmalar veya ekip uyelerinin yerel kurulumu buna bagli olabilir.

### `venv311`

Bu calismada aktif kullanilan Python ortami bu 3.11.9'dur. RAG, ChromaDB, Ollama baglantisi ve standalone chatbot UI bu ortamla calistirildi.

Calistirma komutu:

```powershell
cd C:\Users\ASUS\Desktop\proje\RAGnROLL-katilim-bankaciligi-nlp
.\venv311\Scripts\python.exe -u -m src.chatbot.standalone_ui
```

Acildiktan sonra tarayicida:

```text
http://127.0.0.1:8501
```

## Portlar

### `8000`

Backend/API icin kullanilan ana portlardan biri. Daha once FastAPI tarafinda bu port kullanildi.

### `8001`

Dashboard entegrasyonu denenirken API base URL olarak kullanildi. Dashboard tarafinda chatbot API'sine baglanma denemelerinde gecici olarak kullanildi.

### `8501`

Su an calisan tek dosyalik standalone chatbot demo arayuzunun portu.

Demo icin en stabil yol:

```text
http://127.0.0.1:8501
```

## Aktif Embedding Bilgisi

Aktif Chroma klasoru:

```text
chroma_db/
```

Aktif collection:

```text
katilim_bankaciligi_qwen3_v2
```

Embedding modeli:

```text
Qwen/Qwen3-Embedding-0.6B
```

LLM:

```text
gemma4:e4b
```

## Drive Linki

Embedding zip dosyasi Drive'a yuklendikten sonra link buraya eklenecek:

```text
https://drive.google.com/file/d/1MWQxvKnx_AXvjrgYO4EXvFtAddC47NF4/view?usp=sharing
```

Not: Su an repo icinde `chroma_db.zip` dosyasi da gorunuyor. Paylasmadan once bunun guncel aktif `chroma_db/` klasorunden alinmis zip oldugu kontrol edilmeli.

## Bilinen Durumlar

- Mevcut cihazda Ollama CPU uzerinden calistigi icin cevaplar yavas gelebiliyor.
- GPU/Ollama destegi daha iyi olan bir bilgisayarda cevap suresi belirgin sekilde kisalabilir.
- Takim veri etiketleme, NER ve classification islerini bitirdikten sonra final embedding'in tekrar uretilmesi gerekecek.
- Su anki embedding, mevcut data snapshot'i icin calisiyor; final proje teslimi oncesi guncel data ile tekrar ingest edilmesi daha dogru olur.

## Demo Akisi

1. Terminalde proje ana klasorune girilir.
2. `venv311` ile standalone UI baslatilir.
3. Tarayicida `http://127.0.0.1:8501` acilir.
4. Ornek sorular:
   - `Türkiye'deki katılım bankalarını sayar mısın?`
   - `Murabaha nedir?`
   - `Kuveyt Türk kampanyalarında hangi avantajlar var?`
   - `Türkiye Finans ihtiyaç finansmanı avantajları nelerdir?`
5. Gerekirse yeni sohbet butonu ile memory sifirlanir.
