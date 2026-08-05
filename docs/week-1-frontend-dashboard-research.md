# Dashboard Teknolojisi Seçimi

## 1. Amaç

Bu dokümanın amacı, Katılım Bankacılığı NLP Projesi kapsamında geliştirilecek dashboard ve chatbot arayüzü için en uygun frontend teknolojisini belirlemektir.

Proje kapsamında değerlendirilen teknolojiler şunlardır:

- Streamlit
- Gradio
- React + Next.js

## 2. Proje Gereksinimleri

Seçilecek teknolojinin aşağıdaki gereksinimleri karşılaması beklenmektedir:

- Açık kaynak ve ücretsiz olması
- Ücretli API veya üçüncü taraf hizmet gerektirmemesi
- On-premise ortamda çalışabilmesi
- Python tabanlı NLP backend’i ile entegre olabilmesi
- Çok sayfalı dashboard yapısını desteklemesi
- Grafik, tablo, filtre ve özet kartları sunabilmesi
- Chatbot arayüzü geliştirmeye uygun olması
- Dört haftalık proje süresinde geliştirilebilir olması
- Modern ve kullanıcı dostu bir arayüz sunması

## 3. Streamlit

Streamlit, Python kullanılarak veri uygulamaları ve yapay zekâ arayüzleri geliştirmeye yarayan açık kaynaklı bir framework’tür.

Grafik, tablo, filtre, metrik kartı ve çok sayfalı uygulama gibi özelliklerin kısa sürede oluşturulmasını sağlar.

### Avantajları

- Python tabanlı olduğu için NLP modülleriyle kolay entegre olur.
- Az kodla hızlı prototip geliştirilebilir.
- Dashboard bileşenleri için hazır araçlar sunar.
- Çok sayfalı uygulama yapısını destekler.
- Yerel bilgisayarda veya kurum içi sunucuda çalıştırılabilir.
- Dört haftalık kısa geliştirme süresi için düşük risklidir.

### Dezavantajları

- Tasarım özgürlüğü React + Next.js’e göre daha sınırlıdır.
- Çok özel ve kurumsal arayüzler geliştirmek daha zordur.
- Büyük ölçekli frontend mimarilerinde esneklik sınırlı kalabilir.
- Kullanıcı etkileşimlerinde uygulamanın yeniden çalıştırılma mantığı dikkatli yönetilmelidir.

### Projeye Uygunluğu

Streamlit; özet kartları, kampanya tabloları, grafikler, filtreler ve karşılaştırma sayfaları için uygundur.

Projenin hızlı biçimde tamamlanması öncelikliyse güçlü bir seçenektir.

## 4. Gradio

Gradio, Python fonksiyonları ve makine öğrenmesi modelleri için kısa sürede web arayüzü oluşturmaya yarayan açık kaynaklı bir kütüphanedir.

Özellikle chatbot ve model demosu geliştirme alanında kullanışlıdır.

### Avantajları

- Python tabanlıdır.
- NLP ve LLM fonksiyonlarıyla kolay bağlantı kurar.
- Hazır chatbot bileşenleri sunar.
- Az kodla çalışan bir arayüz oluşturulabilir.
- Yerel ortamda çalıştırılabilir.
- Model çıktılarının hızlı biçimde test edilmesini sağlar.

### Dezavantajları

- Kapsamlı dashboard geliştirme konusunda Streamlit ve React + Next.js kadar güçlü değildir.
- Çok sayfalı ve kurumsal arayüzlerde daha sınırlıdır.
- Tasarım özgürlüğü düşüktür.
- Karşılaştırma tabloları, detay sayfaları ve gelişmiş navigasyon için daha fazla özelleştirme gerekir.

### Projeye Uygunluğu

Gradio, chatbot modülü veya NLP modelinin demosu için oldukça uygundur.

Ancak projenin bütün dashboard arayüzünü geliştirmek için tek başına yeterli esnekliği sunmayabilir.

## 5. React + Next.js

React, bileşen tabanlı kullanıcı arayüzleri geliştirmek için kullanılan açık kaynaklı bir JavaScript kütüphanesidir.

Next.js ise React üzerine kurulu, sayfa yönlendirme, proje yapısı, sunucu tarafı özellikleri ve optimizasyonlar sağlayan bir framework’tür.

Bu nedenle projede React ve Next.js birlikte tek bir teknoloji seçeneği olarak değerlendirilmiştir.

### Avantajları

- Modern ve profesyonel arayüzler geliştirilebilir.
- Tasarım özgürlüğü çok yüksektir.
- Tekrar kullanılabilir bileşen yapısı sunar.
- Çok sayfalı dashboard ve navigasyon için uygundur.
- Responsive tasarım geliştirmek kolaydır.
- Dashboard ve chatbot aynı uygulama içinde ayrı sayfalar olarak geliştirilebilir.
- Uzun vadede genişletilebilir ve sürdürülebilir bir yapı sağlar.
- Docker veya Node.js sunucusu üzerinden on-premise çalıştırılabilir.

### Dezavantajları

- Streamlit ve Gradio’ya göre öğrenme ve geliştirme süresi daha uzundur.
- JavaScript veya TypeScript bilgisi gerektirir.
- Python tabanlı NLP sistemiyle doğrudan değil, API üzerinden iletişim kurar.
- Backend ekibinin FastAPI benzeri bir REST API hazırlaması gerekir.
- Dört haftalık sürede takım içi koordinasyon gerektirir.

### Projeye Uygunluğu

React + Next.js; ana sayfa, karşılaştırma sayfası, detay sayfası, filtreleme, grafikler, tablolar ve chatbot ekranı içeren kapsamlı bir kullanıcı arayüzü için en esnek seçenektir.

## 6. Karşılaştırma Tablosu

| Kriter | Streamlit | Gradio | React + Next.js |
|---|---|---|---|
| Açık kaynak | Evet | Evet | Evet |
| Ücretsiz kullanım | Evet | Evet | Evet |
| On-premise çalışma | Evet | Evet | Evet |
| Temel dil | Python | Python | JavaScript / TypeScript |
| Python NLP entegrasyonu | Doğrudan | Doğrudan | API üzerinden |
| Dashboard yeteneği | Çok iyi | Orta | Çok iyi |
| Chatbot yeteneği | İyi | Çok iyi | Çok iyi |
| Çok sayfalı yapı | İyi | Sınırlı | Çok güçlü |
| Tasarım özgürlüğü | Orta | Düşük | Çok yüksek |
| Geliştirme hızı | Çok hızlı | Çok hızlı | Orta |
| Profesyonel görünüm | Orta-İyi | Orta | Çok yüksek |
| Öğrenme kolaylığı | Kolay | Kolay | Orta-Zor |
| Uzun vadeli genişletilebilirlik | Orta | Düşük-Orta | Çok yüksek |
| Dört haftalık projeye uygunluk | Çok yüksek | Orta | Ekip bilgisine bağlı |

## 7. Sonuç ve Teknoloji Kararı

Gradio, chatbot ve model demosu oluşturmak için güçlü olsa da projenin kapsamlı dashboard gereksinimleri nedeniyle ana frontend teknolojisi olarak yeterli görülmemiştir.

Streamlit, Python tabanlı yapısı ve hızlı geliştirme avantajı sayesinde düşük riskli bir seçenektir. Ancak tasarım özgürlüğü ve uzun vadeli genişletilebilirlik bakımından React + Next.js’in gerisinde kalmaktadır.

Projenin ana sayfa, karşılaştırma, detay, grafik, filtreleme ve chatbot gibi birden fazla arayüz bileşeni içermesi nedeniyle ana frontend teknolojisi olarak React + Next.js seçilmiştir.




