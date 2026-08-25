# Cross-platform installation and verification design

## Amaç

README, yalnızca macOS komutlarına dayanmadan Windows ve Linux kullanıcılarının
projeyi kurup çalıştırabilmesini açıklayacak. Windows ortamında temel servisler,
Docker Compose, embedding/retrieval, GEPA ve varsa yerel LLM yolu doğrulanacak.

## Kapsam

- README içinde Windows PowerShell, Linux ve macOS kurulum yolları.
- Python 3.11, sanal ortam, bağımlılık ve Node.js/dashboard kurulumları.
- Docker Desktop/Linux Docker Compose kurulumu ve smoke akışı.
- API, dashboard, backend test/lint, frontend test/lint/build doğrulaması.
- Chroma/Qwen embedding ve GEPA sözleşme kontrolü.
- Gemma/vLLM desteğinin platform ve donanım sınırlarının açıkça belirtilmesi.

## Yaklaşım

Platform komutları ortak proje adımlarından ayrılacak; Windows için PowerShell
komutları, Linux/macOS için POSIX komutları kullanılacak. Docker Compose, yerel
Python/Node kurulumuna alternatif ve tüm servisleri birlikte doğrulayan yol olarak
belirtilecek. Donanım veya harici model endpoint'i gerektiren adımlar temel sağlık
kontrollerinden ayrı, opsiyonel fakat doğrulama sonuçlarıyla birlikte raporlanacak.

## Doğrulama ölçütleri

- `.venv` Python 3.11 ile bağımlılıklar kurulabilir.
- Backend testleri ve flake8 başarılı olur.
- Dashboard bağımlılık kurulumu, test, lint ve build başarılı olur.
- API health ve dashboard HTTP smoke kontrolleri başarılı olur.
- Compose config/build/start ve API-dashboard smoke başarılı olur.
- Chroma/Qwen ile embedding/index akışı mümkünse çalışır; değilse kesin hata ve
  gereksinim README’de belirtilir.
- GEPA bağımlılıkları ve `--check` sözleşmesi doğrulanır.
- Gemma/vLLM doğrulaması platform kısıtları nedeniyle yapılamıyorsa bu durum
  başarı gibi sunulmaz.

## Değiştirilecek dosyalar

- `README.md`: platform bazlı kurulum, tam doğrulama ve sorun giderme yönergeleri.
- Bu tasarım belgesi: onaylanan kapsamın kaydı.

Kod davranışı değiştirilmez; yalnız kurulum belgeleri ve doğrulama kanıtları
güncellenir.
