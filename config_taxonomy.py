"""
Configuration file for TaxoByAccession Streamlit application
"""
import os
from typing import Optional

# --- API CONFIGURATION ---
# NCBI API key file path (in same directory as this config file)
NCBI_API_KEY_PATH: str = os.path.join(os.path.dirname(__file__), "ncbi_key.txt")
NCBI_API_TIMEOUT: int = 15
NCBI_ENDPOINTS: dict = {
    "esearch": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
    "esummary": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
    "efetch": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
}

# --- PROCESSING CONFIGURATION ---
MAX_WORKERS: int = 2
RATE_LIMIT_DELAY: float = 0.0  # global NCBI throttle handles request pacing
REQUEST_RETRY_ATTEMPTS: int = 3
REQUEST_RETRY_BACKOFF: float = 1.5  # exponential backoff multiplier
NCBI_BASE_INTERVAL_WITH_KEY: float = 0.12
NCBI_BASE_INTERVAL_NO_KEY: float = 0.35
NCBI_MAX_INTERVAL: float = 4.0
NCBI_THROTTLE_GROWTH: float = 1.6
NCBI_THROTTLE_DECAY: float = 0.995
NCBI_429_COOLDOWN_MULTIPLIER: float = 2.0

# --- TAXONOMY RANKS ---
TAXONOMY_RANKS: list = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

# --- LOGGING CONFIGURATION ---
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = "logs/taxonomy_app.log"

# --- CACHE CONFIGURATION ---
ENABLE_CACHE: bool = True
CACHE_MAX_SIZE: int = 1000
PERSISTENT_CACHE_FILE: str = "logs/ncbi_cache.json"
ENABLE_PERSISTENT_CACHE: bool = True


def get_ncbi_api_key() -> Optional[str]:
    """Load NCBI API key from ncbi_key.txt file."""
    try:
        with open(NCBI_API_KEY_PATH, "r") as f:
            key = f.read().strip()
            return key if key else None
    except (IOError, OSError) as e:
        print(f"Warning: Could not read NCBI API key from {NCBI_API_KEY_PATH}: {e}")
        return None


def save_ncbi_api_key_file(file_bytes: bytes, source_name: str | None = None) -> str:
    """Persist an uploaded API key file as ncbi_key.txt in the project folder."""
    os.makedirs(os.path.dirname(NCBI_API_KEY_PATH), exist_ok=True)
    with open(NCBI_API_KEY_PATH, "wb") as file_handle:
        file_handle.write(file_bytes)
    return NCBI_API_KEY_PATH
