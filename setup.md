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

## Ollama Kurulumu
1. Model cmd'den indirin: ollama pull gemma4:e4b
2. Sunucuyu başlatın (ayrı bir terminalde açık kalmalı): ollama serve(ollama arka planda açık olsa da olur)

## Embedding Verisi (chroma_db)
Hazır embed edilmiş veri (1712 doküman) burada: https://drive.google.com/file/d/1-zaOWe9jHeeFECAcIRVdqWP0piRV42_T/view?usp=drive_link
İndirip zip'i açın, `chroma_db` klasörünü proje kök dizinine (data klasörüyle
aynı seviyeye) koyun. Bu sayede embedding'i sıfırdan yapmanıza gerek kalmaz
(RAM yoğun bir işlem, 1-2 saat sürebilir).

## Çalıştırma
Proje kök dizininde:
python -m src.chatbot.rag_langchain

İlk çalıştırmada Qwen3-Embedding modeli otomatik iner (~1-2GB).
"Chatbot hazır" yazısını görünce kullanıma hazırdır.

## Bilinen Durum
CPU'da (GPU desteklenmiyorsa) cevap süresi 50-100sn arası sürebilir.
GPU'lu makinede çok daha hızlı olması beklenir.
