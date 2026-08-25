# Prompt optimizasyon sözleşmesi

Canlı `GroundedPromptBuilder` varsayılan olarak committed sistem promptunu ve
görev talimatını aynen kullanır. GEPA yalnız alt düzey görev talimatı için deney
adayı üretir; sistemdeki kanıt güvenliği, prompt-injection savunması ve `[K#]`
atıf kuralları artifact tarafından değiştirilemez.

## Çevrimdışı kontrol

```bash
pip install -r requirements-prompt-optimization.txt
python -m src.prompt_optimization.optimize_gepa --check
```

Bu komut ağ çağrısı yapmadan exact DSPy/GEPA sürümlerini, 934 satırlık datasetin
deterministik yeniden üretimini, manifest digestini, committed splitleri ve
artifact şemasını doğrular. Mevcut bir artifact ayrıca denetlenecekse
`--artifact runtime/prompt-optimization/selected_prompt.json` verilir.
Dataset ve manifest digestleri çalışma zamanı kodundaki immutable contract'a da
bağlıdır; artifact ile haricî manifesti birlikte değiştirerek kontrol geçilemez.

## Deney ve etkinleştirme

```bash
python -m src.prompt_optimization.optimize_gepa \
  --runtime-dir runtime \
  --student-model gemma4:e4b-mlx \
  --reflection-model gemma4:e4b-mlx \
  --max-metric-calls 24
```

Deney önce `/models` ve küçük bir chat isteğiyle endpoint preflight yapar. Cache,
loglar, rapor ve aday artifact yalnız açıkça verilen runtime dizinine yazılır;
JSON çıktılar atomik olarak değiştirilir. Train ile GEPA çalışır, validation aday
seçer, test ise seçilmiş adayı bir kez ölçer.

Referanslar bağımsız insan-gold cevaplar değil, sınıflandırma ve NER etiketlerinden
türetilmiş projeksiyonlardır. Bu nedenle bütün skorlar provenance dilimleriyle
birlikte `proxy` olarak yazılır; artifact ve rapor
`independent_gold:not_provided` taşır. Bu repoda yeni bir deney sonucu veya skor
committed değildir.

İncelenmiş adayı canlı serviste açmak için:

```bash
export RAGNROLL_PROMPT_MODE=gepa
export RAGNROLL_PROMPT_ARTIFACT=runtime/prompt-optimization/selected_prompt.json
```

Artifact yoksa, şeması geçersizse ya da dataset/manifest SHA değerleri uyuşmazsa
sessiz fallback yapılmaz; `GroundedPromptBuilder` oluşturulamaz ve asistan isteği
fail-closed sonuçlanır. `default` modu artifact'e bakmadan mevcut committed prompt
davranışını korur.
