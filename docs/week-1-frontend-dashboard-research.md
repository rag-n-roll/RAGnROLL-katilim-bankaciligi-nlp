# 1. Hafta Dashboard Teknolojisi Araştırması

## Araştırmanın Amacı

Bu çalışmanın amacı, TEKNOFEST 2026 Katılım Bankacılığı NLP Projesi kapsamında geliştirilecek kullanıcı arayüzü (dashboard) için en uygun teknolojiyi belirlemektir.

Bu araştırmada Streamlit ve Gradio frameworkleri incelenip proje ihtiyaçları doğrultusunda teknik açıdan değerlendirilecektir.

---

# Proje Gereksinimleri

Dashboard teknolojisinin aşağıdaki gereksinimleri karşılaması beklenmektedir.

- Ana Sayfa
- Karşılaştırma Sayfası
- Detay Sayfası
- Chatbot Arayüzü
- Grafikler
- Filtreleme
- Veri Tabloları
- Çok Sayfalı Yapı
- Açık Kaynak Olması
- Python ile Uyumlu Olması
- On-Premise Çalışabilmesi

---

# İncelenen Dashboard Teknolojileri

Proje kapsamında dashboard geliştirme teknolojisi olarak iki farklı açık kaynak framework incelenmiştir.

- Streamlit
- Gradio

Her iki teknoloji de Python tabanlı uygulama geliştirmeye olanak sağlamaktadır. Ancak geliştirilme amaçları, sundukları bileşenler ve kullanım alanları farklılık göstermektedir.

Bu nedenle her iki framework proje gereksinimleri açısından ayrı ayrı değerlendirilmiştir.

---

## Streamlit

### Genel Bilgiler

Streamlit, veri bilimi, makine öğrenmesi ve yapay zekâ projeleri için etkileşimli web uygulamaları geliştirmeyi kolaylaştıran açık kaynaklı bir Python framework'üdür.

İlk olarak 2019 yılında geliştirilmiş olup günümüzde veri analizi, dashboard ve makine öğrenmesi uygulamalarında yaygın olarak kullanılmaktadır.

HTML, CSS veya JavaScript bilgisi gerektirmeden yalnızca Python kodu ile modern web arayüzleri oluşturulabilmektedir.

### Temel Özellikleri

- Açık kaynaklıdır.
- Ücretsiz olarak kullanılabilir.
- Python tabanlıdır.
- Dashboard geliştirmeye uygundur.
- Çok sayfalı uygulamaları destekler.
- Grafik oluşturma kütüphaneleri ile uyumludur.
- Veri tablolarını kolay şekilde gösterebilir.
- Form bileşenleri içerir.
- Yerel (On-Premise) olarak çalıştırılabilir.
- Docker ile kolayca dağıtılabilir.

### Avantajları

- Öğrenme süresi oldukça kısadır.
- Geliştirme hızı yüksektir.
- Veri görselleştirme desteği güçlüdür.
- Pandas, Plotly ve Matplotlib ile uyumludur.
- Filtreleme ve kullanıcı etkileşimi kolayca oluşturulabilir.
- Python ekosistemi ile tam uyumludur.

### Dezavantajları

- React tabanlı uygulamalar kadar özelleştirilebilir değildir.
- Büyük ölçekli kurumsal web uygulamaları için bazı sınırlamalar bulunmaktadır.
- Karmaşık kullanıcı arayüzlerinde ek geliştirmeler gerekebilir.

---

## Gradio

### Genel Bilgiler

Gradio, makine öğrenmesi modellerini ve büyük dil modellerini (LLM) hızlı bir şekilde kullanıcı arayüzüne dönüştürmek amacıyla geliştirilmiş açık kaynaklı bir framework'tür.

Özellikle model demoları, chatbot uygulamaları ve yapay zekâ prototipleri geliştirmek için tercih edilmektedir.

### Temel Özellikleri

- Açık kaynaklıdır.
- Python tabanlıdır.
- Ücretsizdir.
- Chatbot geliştirmeye uygundur.
- Makine öğrenmesi modelleri ile kolay entegre olur.
- Yerel olarak çalıştırılabilir.

### Avantajları

- Yapay zekâ uygulamalarını hızlı şekilde yayınlamaya olanak sağlar.
- Chatbot geliştirme sürecini kolaylaştırır.
- Basit kullanıcı arayüzleri kısa sürede oluşturulabilir.
- Python ile tamamen uyumludur.

### Dezavantajları

- Dashboard geliştirme amacıyla tasarlanmamıştır.
- Çok sayfalı uygulamalarda sınırlıdır.
- Geniş kapsamlı veri tabloları için yeterli esnekliği sunmaz.
- Karmaşık kullanıcı arayüzleri oluşturmak Streamlit'e göre daha zordur.

---

# Teknik Karşılaştırma

Aşağıdaki tabloda proje gereksinimleri doğrultusunda Streamlit ve Gradio frameworkleri karşılaştırılmıştır.

| Özellik | Streamlit | Gradio |
|----------|-----------|---------|
| Açık Kaynak | ✅ | ✅ |
| Ücretsiz | ✅ | ✅ |
| Python Desteği | ✅ | ✅ |
| Dashboard Geliştirme | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| Grafik Desteği | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Veri Tabloları | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| Çok Sayfalı Yapı | ⭐⭐⭐⭐ | ⭐⭐ |
| Chatbot Entegrasyonu | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Öğrenme Kolaylığı | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| On-Premise Çalışma | ✅ | ✅ |

Tablo incelendiğinde her iki frameworkün de açık kaynaklı ve Python tabanlı olduğu görülmektedir. Ancak geliştirilme amaçları farklıdır.

Streamlit, veri analizi ve dashboard geliştirme amacıyla tasarlanmış olup veri görselleştirme, tablo gösterimi ve çok sayfalı kullanıcı arayüzleri konusunda daha güçlü özellikler sunmaktadır.

Gradio ise özellikle yapay zekâ modellerinin ve chatbot uygulamalarının hızlı bir şekilde son kullanıcıya sunulması amacıyla geliştirilmiştir. Dashboard geliştirme konusunda Streamlit kadar kapsamlı değildir.

---

# Sonuç

Yapılan araştırma sonucunda Streamlit ve Gradio frameworkleri proje gereksinimleri doğrultusunda teknik açıdan değerlendirilmiştir.

Her iki framework de açık kaynaklı, ücretsiz ve Python tabanlı çözümler sunmaktadır. Ancak proje kapsamında geliştirilecek sistem yalnızca bir chatbot uygulaması değil; kullanıcıların bankaları karşılaştırabileceği, kampanyaları inceleyebileceği, filtreleme yapabileceği ve NLP analiz sonuçlarını görüntüleyebileceği kapsamlı bir dashboard içermektedir.

Bu ihtiyaçlar doğrultusunda Streamlit; güçlü dashboard bileşenleri, veri görselleştirme desteği, çok sayfalı uygulama geliştirme imkânı ve Python ekosistemiyle uyumu sayesinde proje için daha uygun bir seçenek olarak değerlendirilmiştir.

İlerleyen haftalarda dashboard iskeletinin oluşturulması, kullanıcı arayüzü tasarımı, mockup geliştirme ve chatbot entegrasyonu çalışmalarının Streamlit altyapısı kullanılarak gerçekleştirilmesi planlanmaktadır.


