# 🚀 GitHub'a Push Etme Talimatları

## Adım 1: GitHub'da Repository Oluştur

1. GitHub.com'a git
2. **New repository** butonuna tıkla
3. Repository adı: `NCBI_TaxonomyByAccessionNumbers`
4. Description: `NCBI accession numbers ile taksonomi eşleştirme Streamlit uygulaması`
5. Public veya Private seç
6. **Create repository** butonuna tıkla

## Adım 2: Local Repository'yi GitHub'a Bağla

```bash
# Klasöre gir
cd d:\Uysal\TaxoByAccession_App

# Remote URL'sini ekle (USERNAME'ini kendi hesap adın ile değiştir)
git remote add origin https://github.com/USERNAME/NCBI_TaxonomyByAccessionNumbers.git

# Branch'i yeniden adlandır (opsiyonel, main tercih edilen)
git branch -M main

# Push et
git push -u origin main
```

## Adım 3: SSH Anahtarı ile Push (İsteğe Bağlı, Daha Güvenli)

Eğer SSH anahtarın varsa:

```bash
git remote set-url origin git@github.com:USERNAME/NCBI_TaxonomyByAccessionNumbers.git
git push -u origin main
```

## Mevcut Durum

```
Repository: NCBI_TaxonomyByAccessionNumbers
Location: d:\Uysal\TaxoByAccession_App
Branch: master (local)
Status: ✅ Tüm dosyalar committed

Son Commit:
- Hash: 48db0e1
- Mesaj: "Initial commit: TaxoByAccession Streamlit app with refactored code"
- Tarih: 2026-05-03
```

## Dosya Listesi (Committed)

```
✅ TaxoByAccesion_Streamlit.py     - Ana Streamlit uygulaması
✅ config_taxonomy.py              - Konfigürasyon dosyası  
✅ requirements.txt                - Python bağımlılıkları
✅ README.md                       - Kullanıcı rehberi
✅ REFACTORING_SUMMARY.md          - Teknik geliştirmeler dokümantasyonu
✅ .gitignore                      - Git ignore kuralları
✅ ncbi_key.txt                    - NCBI API anahtarı
📁 logs/                           - Uygulama logları (empty)
```

## Kontrol Komutları

```bash
# Geçerli durumu kontrol et
cd d:\Uysal\TaxoByAccession_App
git status

# Remote'ları göster
git remote -v

# Commit geçmişini göster
git log --oneline -5

# Dosyaları staged olarak ekle
git add .

# Commit et (değişiklik varsa)
git commit -m "Commit mesajı"

# Push et
git push origin main
```

## Sık Karşılaşılan Sorunlar

### "Authentication failed"
- GitHub token kur: https://github.com/settings/tokens
- Veya SSH key oluştur: https://docs.github.com/en/authentication/connecting-to-github-with-ssh

### "Permission denied (publickey)"
- SSH key'ini GitHub'a ekle: https://github.com/settings/keys

### "fatal: 'origin' does not appear to be a 'git' repository"
- `git remote add origin URL` komutunu çalıştır

## ✅ Başarılı Push Belirtileri

```
Enumerating objects: X, done.
Counting objects: 100% (X/X), done.
Writing objects: 100% (X/X), X bytes | X bytes/s, done.
Total X (delta 0), reused 0 (delta 0)
To https://github.com/USERNAME/NCBI_TaxonomyByAccessionNumbers.git
 * [new branch]      main -> main
Branch 'main' set up to track remote branch 'main' from 'origin'.
```

---

**Local Repository**: ✅ HAZIR  
**GitHub Repository**: ⏳ BEKLENIYOR  
**Push Durumu**: ⏳ HAZIR
