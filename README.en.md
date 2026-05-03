# 🧬 eDNA Taxonomy Tool - TaxoByAccession Streamlit

A Streamlit application that automatically matches taxonomy information by NCBI accession numbers.

## 📋 Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [File Structure](#file-structure)
- [Improvements](#improvements)

## ✨ Features

- ✅ **Bidirectional Query**: Search by accession number or species name
- ✅ **Complete Taxonomy Info**: Retrieves all levels from Kingdom to Species
- ✅ **Performance**: In-memory caching eliminates duplicate queries
- ✅ **Reliability**: Retry mechanism (exponential backoff) for fault tolerance
- ✅ **Detailed Logging**: All operations are recorded in log files
- ✅ **Parallel Processing**: Fast batch processing with ThreadPoolExecutor
- ✅ **Error Management**: Safe error reporting with specific exception handling

## 🚀 Installation

### 1. Requirements
- Python 3.10 or higher
- pip (Python package manager)

### 2. Step by Step

```bash
# 1. Enter the directory
cd d:\Uysal\TaxoByAccession_App

# 2. Create virtual environment (recommended)
python -m venv venv
# On Windows
venv\Scripts\activate
# On Linux/Mac
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### 3. NCBI API Key (Optional)

Add an NCBI API key to increase query speed:

1. Go to [NCBI Account Settings](https://www.ncbi.nlm.nih.gov/account/settings/)
2. Generate an API Key
3. Paste the key into `ncbi_key.txt` file

```bash
echo "YOUR_API_KEY_HERE" > ncbi_key.txt
```

## 📖 Usage

### Run the Application

```bash
streamlit run TaxoByAccesion_Streamlit.py
```

The application will automatically open at `http://localhost:8501`.

### Steps

1. **Upload Excel File**: Select your BLAST result file (.xlsx)
2. **Define Columns**: Select Accession and Scientific Name columns
3. **Start Analysis**: Click the "Start Analysis" button
4. **Download Results**: Download results as Excel file

### Example File Format

| Accession | scientific_name | ... |
|-----------|-----------------|-----|
| NZ_CP068... | Bacillus subtilis | ... |
| MW965... | Escherichia coli | ... |

## ⚙️ Configuration

Edit `config_taxonomy.py` to change settings:

```python
# --- API CONFIGURATION ---
NCBI_API_TIMEOUT = 15  # API request timeout (seconds)

# --- PROCESSING CONFIGURATION ---
MAX_WORKERS = 5  # Number of concurrent threads
RATE_LIMIT_DELAY = 0.2  # Wait time between queries (seconds)
REQUEST_RETRY_ATTEMPTS = 3  # Number of retries for failed requests
REQUEST_RETRY_BACKOFF = 1.5  # Exponential backoff multiplier

# --- LOGGING CONFIGURATION ---
LOG_LEVEL = "INFO"  # Logging level (DEBUG, INFO, WARNING, ERROR)

# --- CACHE CONFIGURATION ---
ENABLE_CACHE = True  # Enable/disable caching
CACHE_MAX_SIZE = 1000  # Maximum cache size
```

### Environment Variables

```bash
# Change API key path
set NCBI_KEY_PATH=C:\path\to\my\key.txt

# Change logging level
set LOG_LEVEL=DEBUG
```

## 📁 File Structure

```
TaxoByAccession_App/
├── TaxoByAccesion_Streamlit.py  # Main Streamlit application
├── config_taxonomy.py           # Configuration file
├── translations.py              # Multi-language system
├── translations_tr.json         # Turkish translations
├── translations_en.json         # English translations
├── requirements.txt             # Python dependencies
├── README.md                    # This file (English)
├── README.tr.md                 # Turkish version
├── REFACTORING_SUMMARY.md       # Technical improvements
├── ncbi_key.txt                 # NCBI API key (optional)
├── logs/                        # Log files
│   └── taxonomy_app.log         # Application logs
└── .streamlit/                  # Streamlit config (optional)
    └── config.toml
```

## 📊 Output Format

The result Excel file contains the following columns:

| Column | Description |
|--------|-------------|
| Accession | NCBI accession number |
| scientific_name_original | Original species name |
| kingdom | Kingdom |
| phylum | Phylum |
| class | Class |
| order | Order |
| family | Family |
| genus | Genus |
| species | Species |
| verification_method | "Accession" or "Name_Fuzzy" |

## 🔍 Log Files

Check `logs/taxonomy_app.log` for debugging:

```bash
# View last 20 lines
tail -n 20 logs\taxonomy_app.log

# Search with grep
grep -i "error" logs\taxonomy_app.log

# Real-time monitoring (Windows)
Get-Content logs\taxonomy_app.log -Wait -Tail 10
```

## 🐛 Troubleshooting

### Problem: "NCBI Key not found"
**Solution**: Check if `ncbi_key.txt` path is correct. Otherwise, the app will work with NCBI rate limits.

### Problem: "Timeout error"
**Solution**: Increase `NCBI_API_TIMEOUT` in `config_taxonomy.py` (e.g., 30)

### Problem: "Out of Memory"
**Solution**: 
- Reduce `CACHE_MAX_SIZE`
- Reduce `MAX_WORKERS`
- Test with smaller file

### Problem: "XML Parse Error"
**Solution**: NCBI API format may have changed. Check log file and report the error.

## 📈 Performance Tips

1. **Use Caching**: Avoid duplicate records
2. **NCBI API Key**: Increases rate limit from 3 to 10 queries/second
3. **Batch Size**: Split large files into chunks
4. **Workers**: Set `MAX_WORKERS` based on CPU cores

## 🌐 Multi-Language Support

The application supports multiple languages:
- 🇹🇷 Turkish (Türkçe)
- 🇬🇧 English (English)

Switch languages using the selector in the sidebar.

## 📝 Improvements

Technical improvements in this version:

- ✅ Type hints (100% coverage)
- ✅ Logging framework
- ✅ Caching mechanism
- ✅ Retry logic (exponential backoff)
- ✅ Specific exception handling
- ✅ Configuration management
- ✅ Docstrings (all functions)
- ✅ Multi-language support (TR/EN)

For details, see [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md).

## 📄 Related Files

- [README.tr.md](README.tr.md) - Turkish version
- [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md) - Technical details
- [PUSH_INSTRUCTIONS.md](PUSH_INSTRUCTIONS.md) - Git push guide
