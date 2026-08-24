# Model eğitim verileri

Bu dizin sınıflandırma, NER, bilgi çıkarımı ve prompt deneyi için hazırlanmış
JSON/JSONL veri sözleşmelerini içerir. Dosya adında `test` veya `golden` geçmesi,
tek başına bağımsız insan doğrulaması anlamına gelmez.

## Güncel sınıflandırma ve NER dosyaları

| Dosya | Rol |
| --- | --- |
| `classifier_campaigns_review.jsonl` | Gerçek kampanyaların insan/otomatik/excluded etiket kuyruğu |
| `ner_dataset_approved.jsonl` | Gerçek kampanyaların insan veya otomatik NER etiketleri |
| `classifier_dataset_final.jsonl` | Ortak split uygulanmış gerçek ve kontrollü sentetik sınıflandırma verisi |
| `ner_dataset_final.jsonl` | Ortak split uygulanmış gerçek ve kontrollü sentetik NER verisi |
| `campaign_nlp_output_schema.json` | Kampanya NLP çıktı sözleşmesi |
| `dspy_prompt_examples.jsonl` | Yukarıdaki etiketlerden türetilen prompt proxy örnekleri |
| `training_dataset_manifest.json` | Eğitim dosyalarının digest, split ve provenance özeti |
| `dspy_prompt_examples.manifest.json` | Prompt verisinin input/output ve split-assignment digestleri |

`classifier_dataset_final.jsonl` zaten kontrollü sentetik varyantları içerir;
byte-identical ikinci bir tuning kopyası tutulmaz. NER için de aynı final veriyle
aynı rolü üstlenen ayrı bir tuning kopyası tutulmaz.

## Provenance ve metrik sözleşmesi

- `human`: Gerçek kayıt üzerinde insan tarafından doğrulanmış referans.
- `auto`: Kural/model tarafından otomatik üretilmiş referans.
- `synthetic`: Kontrollü şablon üretimi. Kaydın eski alanlarında
  `human_verified: true` bulunsa bile insan etiketi sayılmaz.
- `excluded`: Eğitime uygun olmayan veya reddedilmiş kayıt.

Otomatik ve sentetik referanslardan hesaplanan sonuçlar yalnız `proxy` metriktir.
Prompt örneklerinin yanıtları da classifier/NER etiketlerinin deterministik
projeksiyonudur; bağımsız soru-cevap gold'u değildir. Bu repoda bağımsız olarak
yazılmış ve gözden geçirilmiş bir holdout bulunmadığı manifestlerde
`independent_gold.status: not_provided` olarak kaydedilir.

Eski `golden_evaluation_set.jsonl`, mevcut kural sözleşmesinin dondurulmuş regresyon
verisidir. İnsan doğrulama/lineage manifesti olmadığı için yarışma veya bağımsız
genelleme metriği olarak sunulmamalıdır.

## Doğrulama

```bash
python -m src.training.dataset_contract --check
python -m src.training.create_unified_splits validate \
  --classifier data/model_training_data/classifier_dataset_final.jsonl \
  --ner data/model_training_data/ner_dataset_final.jsonl
python -m src.prompt_optimization.dataset --check
```

Gerçek kayıtlar canonical `source_url` ailesiyle gruplanır. Host case, fragment,
tracking parametreleri, query sırası ve root dışı trailing slash normalize edilir;
işlevsel query değerleri korunur. Aynı aile classifier ve NER boyunca yalnız tek
split'te bulunabilir. Gerçek kayıtta URL eksikliği hatadır; sentetik kayıtlar ise
`source_id` taşır ve yalnız train split'inde yer alır.
