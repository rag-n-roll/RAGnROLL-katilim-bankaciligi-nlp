# Final NLP model eğitimi

Bu çalışma kampanya sınıflandırması ile entity çıkarımını tek, kampanya bazlı
train/validation/test politikası altında birleştirir. Ortak 468 gerçek kampanyada
sınıflandırma ve NER split uyuşmazlığı sıfırdır. Sentetik örnekler yalnız train
kümesinde tutulur.

## Seçilen modeller

- Sınıflandırma: karakter TF-IDF (3–5 gram) + Linear SVM; ürün kategorisi ve beş
  çok etiketli kampanya boyutu için ayrı başlıklar.
- Entity çıkarımı: spaCy Türkçe NER + denetlenmiş finansal regex kuralları.
- BERTurk denemeleri validation skorlarında bu modellerin gerisinde kaldığı için
  üretim modeli olarak seçilmedi.

## Bağımsız test sonuçları

- Ürün kategorisi doğruluğu: **%93,26** (89 kampanya)
- Hibrit NER exact-span precision: **%90,34**
- Hibrit NER exact-span recall: **%91,58**
- Hibrit NER exact-span F1: **%90,96** (90 kampanya)
- Birleşik sistem proxy skoru: **%90,31**
- Aynı 89 kampanyada bütün sınıflandırma etiketleri ve bütün NER span'leri aynı
  anda eksiksiz doğru olduğunda katı doküman doğruluğu: **%35,96**

Özet skorların tamamı `models/final_training/training_manifest.json` ve
`models/final_training/model_manifest.json` dosyalarındadır.

## Yeniden üretim

```powershell
.\.venv-training\Scripts\python.exe -m src.training.create_unified_splits `
  --classifier-input data/model_training_data/classifier_dataset_tuning_augmented.jsonl `
  --ner-input data/model_training_data/ner_dataset_tuning_augmented.jsonl `
  --classifier-output data/model_training_data/classifier_dataset_final.jsonl `
  --ner-output data/model_training_data/ner_dataset_final.jsonl `
  --manifest-output data/model_training_data/unified_split_manifest.json

.\.venv-training\Scripts\python.exe -m src.training.run_final_training
```

## RAG entegrasyonu

Kutay'ın Qwen3 embedding + Chroma/BM25/knowledge-graph retrieval katmanına
girdi üretmek için özgün kampanya dosyasını değiştirmeden şu komut çalıştırılır:

```powershell
.\.venv-training\Scripts\python.exe -m src.extraction.enrich_campaigns_for_rag `
  data/processed/campaigns.json `
  data/processed/campaigns_nlp_enriched.json
```

Çıktıda her kampanyanın `structured` alanına ürün sınıfı, sınıflandırma
boyutları, normalize entity'ler, güven/uyarılar ve model provenance bilgisi
eklenir. Böylece retrieval metadata filtreleri ve LLM kanıt paketi aynı
doğrulanmış NLP çıktısını kullanabilir.
