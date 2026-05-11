# 🧬 eDNA Taxonomy Tool - TaxoByAccession Streamlit

**Language / Dil:**
- 🇬🇧 [English](README.en.md)
- 🇹🇷 [Türkçe](README.tr.md)

---

A Streamlit application that automatically matches taxonomy information by NCBI accession numbers.

NCBI accession numaralarına göre taksonomi bilgilerini otomatik olarak eşleştiren bir Streamlit uygulaması.

## 📋 Quick Start / Hızlı Başlangıç

### Installation / Kurulum

```bash
# 1. Enter directory / Klasöre gir
cd d:\Uysal\TaxoByAccession_App

# 2. Create virtual environment / Sanal ortam oluştur
python -m venv venv
venv\Scripts\activate

# 3. Install dependencies / Bağımlılıkları yükle
pip install -r requirements.txt
```

### Run / Çalıştır

```bash
streamlit run TaxoByAccesion_Streamlit.py
```

## ✨ Features / Özellikler

- ✅ Bidirectional Query / Çift Yönlü Sorgu
- ✅ Complete Taxonomy Info / Tam Taksonomi Bilgisi
- ✅ Performance Caching / Performans İçin Caching
- ✅ Error Handling & Retry / Hata Yönetimi
- ✅ Detailed Logging / Detaylı Kayıt
- ✅ Parallel Processing / Paralel İşleme
- ✅ Multi-Language Support / Çoklu Dil Desteği (TR/EN)
- ✅ NCBI API Key Upload / Arayüzden API key yükleme ve `ncbi_key.txt` olarak kaydetme
- ✅ Adaptive NCBI Throttling / `429` gelince otomatik yavaşlama
- ✅ Persistent Cache / Çalışmalar arasında cache'i koruma

## 📁 Documentation / Belgeler

- [Full English Guide](README.en.md) - Complete documentation
- [Türkçe Rehber](README.tr.md) - Tam dokümantasyon
- [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) - Technical details
- [PUSH_INSTRUCTIONS.md](PUSH_INSTRUCTIONS.md) - Git guide

## 🌐 Language Support / Dil Desteği

The application supports Turkish and English. Switch languages using the sidebar selector.

Uygulama Türkçe ve İngilizceyi destekliyor. Sidebar'dan dil seçerek değiştirebilirsin.

## 🔑 NCBI API Key / NCBI API Anahtarı

If `ncbi_key.txt` does not exist, the Streamlit UI shows an upload field. Any file name is accepted; the content is saved as `ncbi_key.txt` in the project folder and the app reloads automatically.

`ncbi_key.txt` dosyası yoksa Streamlit arayüzünde yükleme alanı görünür. Dosya adı önemli değildir; içerik proje klasöründe `ncbi_key.txt` olarak kaydedilir ve uygulama otomatik yeniden başlar.

## 🔗 Faydalı Linkler

- [NCBI Entrez API](https://www.ncbi.nlm.nih.gov/books/NBK25499/)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [Pandas Documentation](https://pandas.pydata.org/docs/)
- [Requests Library](https://requests.readthedocs.io/)

## 📧 Sorunlar ve Öneriler

Hata bulursan veya iyileştirme önerisi varsa log dosyasını kontrol et ve hata mesajını kaydetti.

## 📄 Lisans

Bu proje akademik amaçlar için geliştirilmiştir.

---

**Versiyon**: 2.0 (Refactored)  
**Son Güncelleme**: May 3, 2026  
**Python**: 3.10+
