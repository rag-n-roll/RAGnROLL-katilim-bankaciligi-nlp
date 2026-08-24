# Eğitim verisi ve proxy değerlendirme sözleşmesi

## Split birimi

Classifier ve NER kayıtları kampanya kimliğiyle değil canonical kaynak URL ailesiyle
ayrılır. URL normalizasyonu host büyük/küçük harfini, fragment ve tracking
parametrelerini, query sırasını ve root dışı trailing slash farkını giderir;
işlevsel query anahtar/değerleri korunur. Böylece aynı sayfanın farklı kayıt
kimlikleri train, validation ve test arasında dağılamaz.

Gerçek kayıtta `source_url` zorunludur ve eksikse üretim/validasyon durur. Kontrollü
sentetik kayıtlar URL yerine `source_id` taşır, yalnız train split'inde bulunur ve
hiçbir zaman insan doğrulamalı sayılmaz.

## Manifestler

`training_dataset_manifest.json` her eğitim dosyasının SHA-256 digestini, byte ve
satır sayısını, split/task dağılımını, real/synthetic ile
human/auto/synthetic/excluded sayılarını kaydeder. Aynı manifest final classifier ve
NER dosyalarında source-family cross-split bulunmadığını da doğrular.

`dspy_prompt_examples.manifest.json` iki kaynak dosyanın digestini, üretilen prompt
verisinin digestini, family-assignment digestini ve split/task/provenance sayılarını
tutar. Üretimde zaman damgası veya worktree'ye özgü mutlak yol kullanılmadığı için
aynı girdiler byte-identical çıktı verir.

## Değerlendirme sınırı

Prompt yanıtları classifier/NER etiketlerinden türetildiği için
`reference_kind=derived_label_projection` taşır. Sonuçlar yalnız proxy olarak;
`overall`, `human`, `auto` ve varsa `synthetic` dilimlerinde örnek sayısıyla (`n`)
raporlanır. Boş dilimin skoru `null` olur.

Repoda bağımsız yazılmış ve ikinci bir insan incelemesinden geçmiş QA holdout'u
bulunmamaktadır. Bu nedenle manifestler `independent_gold.status=not_provided`
yazar ve bağımsız gold skoru üretmez.
