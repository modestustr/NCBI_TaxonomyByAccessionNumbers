# 🧬 eDNA Taxonomy Tool - TaxoByAccession Streamlit

NCBI accession numaralarına göre taksonomi bilgilerini otomatik olarak eşleştiren bir Streamlit uygulaması.

## 📋 İçindekiler

- [Özellikler](#özellikler)
- [Kurulum](#kurulum)
- [Kullanım](#kullanım)
- [Konfigürasyon](#konfigürasyon)
- [Dosya Yapısı](#dosya-yapısı)
- [Geliştirmeler](#geliştirmeler)

## ✨ Özellikler

- ✅ **Çift Yönlü Sorgu**: Accession numarası veya tür adı ile arama
- ✅ **Tam Taksonomi Bilgisi**: Kingdom'dan Species'e kadar tüm seviyeleri getiriyor
- ✅ **Performans**: In-memory caching ile duplicate sorguları ortadan kaldırıyor
- ✅ **Güvenilirlik**: Retry mekanizması (exponential backoff) ile hata toleransı
- ✅ **Detaylı Logging**: Tüm işlemler log dosyasında kaydediliyor
- ✅ **Paralel İşleme**: ThreadPoolExecutor ile hızlı batch processing
- ✅ **Hata Yönetimi**: Spesifik exception handling ile güvenli hata raporlama

## 🚀 Kurulum

### 1. Gereksinimler
- Python 3.10 veya üzeri
- pip (Python paket yöneticisi)

### 2. Adım Adım

```bash
# 1. Klasöre gir
cd d:\Uysal\TaxoByAccession_App

# 2. Sanal ortam oluştur (önerilen)
python -m venv venv
# Windows'ta
venv\Scripts\activate
# Linux/Mac'te
source venv/bin/activate

# 3. Bağımlılıkları yükle
pip install -r requirements.txt
```

### 3. NCBI API Anahtarı (İsteğe Bağlı)

API hızını artırmak için NCBI API anahtarı ekleyebilirsin:

1. [NCBI Account Settings](https://www.ncbi.nlm.nih.gov/account/settings/) sayfasına git
2. API Key oluştur
3. `ncbi_key.txt` dosyasına anahtarı yapıştır

```bash
echo "YOUR_API_KEY_HERE" > ncbi_key.txt
```

## 📖 Kullanım

### Uygulamayı Çalıştır

```bash
streamlit run TaxoByAccesion_Streamlit.py
```

Uygulama otomatik olarak `http://localhost:8501` adresinde açılacak.

### Adımlar

1. **Excel Dosyası Yükle**: Blast sonuç dosyanı seç (.xlsx)
2. **Sütunları Tanımla**: Accession ve Scientific Name sütunlarını seç
3. **Analizi Başlat**: "Analizi Başlat" butonuna tıkla
4. **Sonuçları İndir**: Excel dosyası olarak sonuçları indir

### Örnek Dosya Formatı

| Accession | scientific_name | ... |
|-----------|-----------------|-----|
| NZ_CP068... | Bacillus subtilis | ... |
| MW965... | Escherichia coli | ... |

## ⚙️ Konfigürasyon

`config_taxonomy.py` dosyasını düzenleyerek ayarları değiştirebilirsin:

```python
# --- API CONFIGURATION ---
NCBI_API_TIMEOUT = 15  # API isteği timeout'u (saniye)

# --- PROCESSING CONFIGURATION ---
MAX_WORKERS = 5  # Eşzamanlı çalışacak thread sayısı
RATE_LIMIT_DELAY = 0.2  # Sorgular arasında bekleme süresi (saniye)
REQUEST_RETRY_ATTEMPTS = 3  # Başarısız istek kaç kez denenir
REQUEST_RETRY_BACKOFF = 1.5  # Exponential backoff çarpanı

# --- LOGGING CONFIGURATION ---
LOG_LEVEL = "INFO"  # Logging seviyesi (DEBUG, INFO, WARNING, ERROR)

# --- CACHE CONFIGURATION ---
ENABLE_CACHE = True  # Caching aktif/pasif
CACHE_MAX_SIZE = 1000  # Maksimum cache boyutu
```

### Environment Variables

```bash
# API anahtarı path'i değiştir
set NCBI_KEY_PATH=C:\path\to\my\key.txt

# Logging seviyesini değiştir
set LOG_LEVEL=DEBUG
```

## 📁 Dosya Yapısı

```
TaxoByAccession_App/
├── TaxoByAccesion_Streamlit.py  # Ana Streamlit uygulaması
├── config_taxonomy.py           # Konfigürasyon dosyası
├── requirements.txt             # Python bağımlılıkları
├── README.md                    # Bu dosya
├── REFACTORING_SUMMARY.md       # Teknik geliştirmeler
├── ncbi_key.txt                 # NCBI API anahtarı (optional)
├── logs/                        # Log dosyaları
│   └── taxonomy_app.log         # Uygulama logları
└── .streamlit/                  # Streamlit config (optional)
    └── config.toml
```

## 📊 Çıktı Formatı

Sonuç Excel dosyası şu sütunları içerir:

| Sütun | Açıklama |
|-------|----------|
| Accession | NCBI accession numarası |
| scientific_name_original | Orijinal tür adı |
| kingdom | Krallık |
| phylum | Şube |
| class | Sınıf |
| order | Takım |
| family | Aile |
| genus | Cins |
| species | Tür |
| verification_method | "Accession" veya "Name_Fuzzy" |

## 🔍 Log Dosyaları

Hata ayıklama için `logs/taxonomy_app.log` dosyasını kontrol et:

```bash
# Son 20 satırı görüntüle
tail -n 20 logs\taxonomy_app.log

# İçinde grep ile ara
grep -i "error" logs\taxonomy_app.log

# Real-time monitoring (Windows)
Get-Content logs\taxonomy_app.log -Wait -Tail 10
```

## 🐛 Troubleshooting

### Problem: "NCBI Anahtarı bulunamadı"
**Çözüm**: `ncbi_key.txt` dosyasının yolu doğru mu kontrol et. Yoksa NCBI hız limitlerinde çalışacaksın.

### Problem: "Timeout hatası"
**Çözüm**: `config_taxonomy.py` içinde `NCBI_API_TIMEOUT` değerini artır (örn: 30)

### Problem: "Out of Memory"
**Çözüm**: 
- `CACHE_MAX_SIZE` değerini azalt
- `MAX_WORKERS` değerini azalt
- Daha küçük dosya ile test et

### Problem: "XML Parse Error"
**Çözüm**: NCBI API format değişmiş olabilir. Log dosyasını kontrol et ve hatayı raporla.

## 📈 Performance İpuçları

1. **Caching Kullan**: Duplicate kayıtları önle
2. **NCBI API Anahtarı**: Hız limitini 3 → 10 query/second'a çıkar
3. **Batch Size**: Büyük dosyaları parçala
4. **Workers**: Sisteme göre `MAX_WORKERS` ayarla (CPU cores sayısı)

## 📝 Geliştirmeler

Bu versionda yapılan teknik geliştirmeler:

- ✅ Type hints (100% coverage)
- ✅ Logging framework
- ✅ Caching mekanizması
- ✅ Retry logic (exponential backoff)
- ✅ Spesifik exception handling
- ✅ Configuration management
- ✅ Docstrings (tüm fonksiyonlar)

Detaylar için [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) dosyasını oku.

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
