# Kurulum

## Python Sürümü — ÖNEMLİ
Bu proje Python 3.13 ile çalışmıyor (bağımlılık hatası veriyor).
Python 3.11.9 kullanmanız gerekiyor.

1. Python 3.11.9'u indirin: https://www.python.org/downloads/release/python-3119/
2. Proje kök dizininde sanal ortam oluşturun:
   py -3.11 -m venv venv311
3. Aktif edin (Windows):
   venv311\Scripts\activate
4. Bağımlılıkları kurun:
   pip install -r requirements.txt

Kampanya sınıflandırıcı ve NER artefaktları yalnız requirements dosyasındaki tam
spaCy, scikit-learn ve joblib sürümleriyle yüklenir. Hash veya sürüm farkında
çalışma zamanı modeli deserialize etmeden durur.

## Yerel Model Servisi

Apple Silicon üzerinde Gemma cevap yazım modeli vLLM-Metal ile çalışır:

```bash
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm-metal/main/install.sh | bash
python -m scripts.serve_local_llm
```

## Embedding İndeksi

Qwen embedding modeli ve Chroma indeksi ilk çalıştırmada bir kez hazırlanır:

```bash
python -m scripts.ingest_chroma --batch-size 64
```

Sonraki çalıştırmalarda yalnız değişen kampanya veya terminoloji parçaları embed
edilir. Uzun kayıtlar kaynak konumunu koruyan semantik parçalara ayrılır; silinen
kayıtların eski parçaları indeksten temizlenir.

## Çalıştırma
Proje kök dizininde API'yi başlatın:

```bash
python -m uvicorn src.main:app --reload
```

Dashboard için ayrı terminalde `src/dashboard` dizininde `npm run dev` çalıştırın.
İlk indekslemede Qwen3-Embedding modeli otomatik iner.

## Bilinen Durum
Embedding cihazı otomatik seçilir. Apple Silicon üzerinde gerekirse
`RAGNROLL_EMBEDDING_DEVICE=mps` ayarlanabilir. vLLM veya Chroma erişilemezse
uygulama kaynaklı yerel fallback yanıtıyla çalışmaya devam eder.
