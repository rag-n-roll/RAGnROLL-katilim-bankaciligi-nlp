# DSPy + GEPA sistem promptu optimizasyonu

Bu deney mevcut RAG cevap promptunu, onaylı sınıflandırma ve hibrit NER
etiketlerinden türetilen kanıta dayalı soru-cevap örnekleriyle optimize eder.

## Deney tasarımı

- Sınıflandırma ve NER kayıtları kampanya kimliğiyle birleştirilir.
- Bir kampanyanın tüm görevleri aynı kümede tutulur; görevler arası veri sızıntısı
  engellenir.
- One-shot (`k=1`) ve few-shot (`k=4`) adayları ayrı ayrı oluşturulur.
- Her adayın talimatı GEPA ile yalnızca train ve validation kullanılarak optimize
  edilir.
- Aday seçimi validation skoruyla yapılır.
- Test kümesi yalnızca seçilen adaya bir kez uygulanır.
- Metrik; zorunlu bilgi kapsaması, token F1, desteklenmeyen sayı/kod ve gereksiz
  uzunluğu birlikte değerlendirir. GEPA'ya eksik veya uydurulmuş bilgiler için
  metinsel geri bildirim verir.

Üretilen veri dosyası `data/model_training_data/dspy_prompt_examples.jsonl`
içinde 934 örnek barındırır: 654 train, 133 validation ve 147 test. Bunun 465'i
sınıflandırma özeti, 469'u entity ayrıntısı görevidir.

## Çalıştırma

```powershell
& '.\.venv-training\Scripts\python.exe' -m src.prompt_optimization.dataset
& '.\.venv-training\Scripts\python.exe' -m src.prompt_optimization.optimize_gepa `
  --student-model 'ollama_chat/gemma4:e4b' `
  --reflection-model 'ollama_chat/gemma4:e4b' `
  --shots 1 4 `
  --auto light
```

Ollama'nın `http://localhost:11434` adresinde çalışması ve iki model argümanında
belirtilen modellerin kurulu olması gerekir. Küçük bir maliyet/süre pilotu için
`--max-train 120 --max-validation 40` kullanılabilir. Nihai deneyde bu iki
argüman verilmez; böylece bütün train ve validation örnekleri kullanılır.

## Çıktılar ve RAG entegrasyonu

Deney tamamlandığında `models/dspy_gepa/` altında şunlar oluşur:

- `one_shot.json`: GEPA ile optimize edilmiş one-shot DSPy programı,
- `few_shot_4.json`: GEPA ile optimize edilmiş four-shot DSPy programı,
- `experiment_report.json`: validation karşılaştırması ve seçilen adayın test
  skoru,
- `selected_prompt.json`: kazanan sistem talimatı ve demonstrasyonlar.

`src/chatbot/rag_langchain.py`, `selected_prompt.json` varsa kazanan talimat ve
örnekleri otomatik yükler. Dosya henüz yoksa güvenli yerleşik promptla çalışmaya
devam eder.

## Tekrarlanabilirlik notu

Varsayılan seed 42'dir. Test verisi GEPA'ya veya demo seçimine verilmez. Gerçek
GEPA sonucu oluşmadan bir test skoru raporlanmamalıdır.
