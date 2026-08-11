# Hafta 2 - NLP modelleri ve değerlendirme

Bu çalışma kural tabanlı bilgi çıkarımı, NER, metin sınıflandırma ve ortak KPI
raporunu tamamen lokal çalışacak şekilde tamamlar.

## Veri güvenilirliği

`data/model_training_data/ner_dataset.jsonl` ve
`classifier_dataset.jsonl` sentetik şablonlarla oluşturulmuştur. Bu veriler smoke
test ve baseline geliştirmek için kullanılabilir; bu verilerden alınan skorlar
yarışma performansı olarak raporlanmamalıdır. Nihai metrikler, resmi banka
sayfalarından gelen ve ekip tarafından doğrulanmış, eğitim verisinden kaynak ve
kampanya bazında ayrılmış test kümesinde hesaplanmalıdır.

## 1. NER verisini doğrulama

```bash
python -m src.ner.train validate data/model_training_data/ner_dataset.jsonl
```

Komut; bozuk JSON, hatalı span, örtüşen entity ve `entity.text`/ofset
uyuşmazlıklarında başarısız olur. Mevcut etiketler: `BANK`, `PRODUCT`, `MATURITY`,
`PROFIT_RATE`, `FINANCING_AMOUNT`, `APPLICATION_CHANNEL`, `CAMPAIGN`, `END_DATE`,
`CONDITION`, `CAMPAIGN_BENEFIT`, `TRADE_FINANCE_TERM`, `DOCUMENT`.

## 2. spaCy NER eğitimi

```bash
python -m src.ner.train train \
  data/model_training_data/ner_dataset.jsonl \
  models/trained/ner-spacy \
  --epochs 20 --batch-size 32 --seed 42
```

Model ile birlikte `models/trained/ner-spacy/evaluation.json` üretilir. Raporda
entity-level strict Precision, Recall, F1 ve entity türü bazlı skorlar bulunur.

Bağımsız test kümesi eklendiğinde:

```bash
python -m src.ner.train evaluate models/trained/ner-spacy \
  data/annotations/ner_gold.jsonl --split test
```

## 3. Kampanya türü etiketleme

Gerçek kampanyaları ön etiketleme kuyruğuna dönüştürmek için:

```bash
python -m src.classifier.prepare_campaign_data \
  data/processed/campaigns.json \
  data/annotations/campaign_type_review.jsonl
```

Kurallar çok boyutlu bir `annotations` nesnesi önerir. Her kayıt başlangıçta
`human_verified: false` durumundadır. Ekip tüm alanları kontrol etmeli ve ardından
kampanya/banka sızıntısını önleyecek biçimde `train`, `validation`, `test`
değerlerinden birini `split` alanına yazmalıdır. Final eğitiminde
`--require-verified` kullanılmalıdır.

Etiket yapısı repodaki ontology ile uyumludur:

- `product_category`: Tek ana ürün; kart, konut/taşıt/ihtiyaç/alışveriş/eğitim,
  tarım, ticari, dijital veya sürdürülebilir finansman, yatırım, katılma hesabı vb.
- `campaign_mechanics`: Taksit, indirim, nakit iade, puan, referans, promosyon
  kodu, hediye çeki veya çekiliş.
- `target_segments`: Yeni/mevcut/maaş müşterisi, genç/öğrenci, KOBİ, çiftçi,
  kart sahibi veya dijital müşteri.
- `channels`: Mobil, internet şubesi, fiziksel şube, kart/POS, e-ticaret, ATM
  veya çağrı merkezi.
- `benefits`: `%0`/avantajlı kâr payı, ücret muafiyeti, ücretsiz sigorta,
  erteleme, ek taksit veya ücretsiz hizmet.
- `requirements`: Minimum harcama, başvuru, promosyon kodu, otomatik ödeme,
  ilk işlem, tarih/stok, belirli işyeri veya kart koşulu.

Ana ürün tek seçimlidir; diğer boyutlar çoklu seçimdir. Örneğin bir kayıt aynı
anda kart ürünü, nakit iade mekaniği, yeni müşteri segmenti ve mobil kanal
etiketlerini taşıyabilir.

`needs_review` nihai bir sınıf değildir; belirsiz kaydı ekip üyesine yönlendirir.

### Streamlit etiketleme ekranı

JSONL dosyasını elle değiştirmek yerine ekip arayüzü kullanılmalıdır:

```bash
python -m streamlit run src/annotation/app.py
```

Farklı bir annotation dosyasını açmak için tarayıcı adresine query parametresi
eklenebilir:

```text
http://localhost:8501/?dataset=data/annotations/campaign_type_review.jsonl
```

İş akışı:

1. İlk ekip üyesi adını girer, `Etiketleyici` rolünü seçer, ürün kategorisini,
   çoklu özellikleri ve split'i belirleyerek kaydeder.
2. Farklı bir ekip üyesi `Reviewer` rolünü seçer ve `awaiting_review`
   kayıtlarını filtreler.
3. Reviewer doğru kaydı onaylar veya gerekçeli değişiklik isteği gönderir.
4. Yalnızca reviewer onayından sonra `human_verified: true` yazılır.

Aynı kişi kendi kaydını onaylayamaz ve `needs_review` etiketi çözülmeden kayıt
onaylanamaz. Her işlem UTC zamanıyla `annotation_history` alanında tutulur. Dosya
başka biri tarafından değiştirildiyse arayüz kaydetmeyi reddeder ve yeniden
yükleme ister.

## 4. Sınıflandırıcı eğitimi

İnsan doğrulamalı kampanya verisiyle:

```bash
python -m src.classifier.multilabel train \
  data/annotations/campaign_type_review.jsonl \
  models/trained/campaign-classifier.joblib \
  --train-split train --evaluation-split validation
```

Çıktıdaki `.metrics.json` ana ürün kategorisi Accuracy değerini; her çok etiketli
boyut için micro/macro F1 ve subset accuracy değerlerini içerir. Bağımsız test:

```bash
python -m src.classifier.multilabel evaluate \
  models/trained/campaign-classifier.joblib \
  data/annotations/campaign_type_review.jsonl --split test
```

Mevcut sentetik intent verisiyle yalnızca smoke baseline çalıştırmak için:

```bash
python -m src.classifier.main train \
  data/model_training_data/classifier_dataset.jsonl \
  models/trained/intent-baseline.joblib --label-field intent
```

## 5. Hibrit çıkarım

`HybridExtractor` deterministik ve normalize edilmiş kural çıktılarını korur;
spaCy modeli verilirse modelin bağlamsal entity span'larını ekler:

```python
from src.extraction.hybrid import HybridExtractor

extractor = HybridExtractor("models/trained/ner-spacy")
result = extractor.extract(campaign_text)
```

## 6. PRD KPI raporu

```bash
python -m src.evaluation.report \
  models/trained/ner-spacy/evaluation.json \
  models/trained/campaign-classifier.metrics.json \
  --output outputs/model_kpi_report.json
```

Hedefler: NER Precision `>=0.85`, Recall `>=0.80`, F1 `>=0.82` ve
sınıflandırma Accuracy `>=0.85`. Sentetik veri içeren raporlar otomatik olarak
`competition_metric_eligible: false` işaretlenir.
