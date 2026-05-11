# 🧬 eDNA Taxonomy Tool - TaxoByAccession Streamlit

**Language / Dil:**
- 🇬🇧 [English](README.en.md)
- 🇹🇷 [Türkçe](README.tr.md)

---

A Streamlit application that automatically matches taxonomy information by NCBI accession numbers.

NCBI accession numaralarına göre taksonomi bilgilerini otomatik olarak eşleştiren bir Streamlit uygulaması.

The UI is organized into tabs: the accession workflow comes first, API key handling lives in its own tab, and the Advanced tab now starts from an Excel accession column preview before running the batch.

Arayüz sekmeli çalışır: accession akışı ilk sekmededir, API key kendi sekmesindedir ve Advanced sekmesi Excel accession önizlemesini batch işlemine hazırlar.

## 📋 Quick Start / Hızlı Başlangıç

### Installation / Kurulum

```bash
# 1. Enter directory / Klasöre gir
cd d:\Python Edna\TaxoByAccession

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
- ✅ Tabbed UI / Sekmeli arayüz: accession, API key, advanced
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

API key durumu ana akışta tekrar edilmez; yalnızca API Key sekmesinde gösterilir.

Advanced sekmesinde Excel'den seçilen accession sütunu önce önizlenir, sonra batch olarak işlenir. Yapıştırmalı liste alanı hâlâ alternatif olarak durur.

Ana sekme de artık mümkün olan yerde batch-hibrit çalışır: accession değerleri toplu çözülür, lineage toplu alınır, yalnızca scientific name fallback gereken satırlar satır bazlı devam eder.

429 ve bekleme davranışı hâlâ mümkün olabilir, ama artık ana darboğaz değildir; istek sayısı ciddi biçimde azaldı.

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

**Versiyon**: 2.1 (Batch-first update)  
**Son Güncelleme**: May 11, 2026  
**Python**: 3.10+
