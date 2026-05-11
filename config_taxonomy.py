"""
Configuration file for TaxoByAccession Streamlit application
"""
import os
from pathlib import Path
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

# --- TAXONOMY RANKS ---
TAXONOMY_RANKS: list = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

# --- LOGGING CONFIGURATION ---
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = "logs/taxonomy_app.log"

# --- CACHE CONFIGURATION ---
ENABLE_CACHE: bool = True
CACHE_MAX_SIZE: int = 1000


def get_ncbi_api_key() -> Optional[str]:
    """Load NCBI API key from ncbi_key.txt file."""
    try:
        with open(NCBI_API_KEY_PATH, "r") as f:
            key = f.read().strip()
            return key if key else None
    except (IOError, OSError) as e:
        print(f"Warning: Could not read NCBI API key from {NCBI_API_KEY_PATH}: {e}")
        return None
