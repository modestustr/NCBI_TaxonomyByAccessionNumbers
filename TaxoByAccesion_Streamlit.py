import streamlit as st
import atexit
import json
import requests
import pandas as pd
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
import io
import logging
import os
import sys
import threading
from functools import wraps
from typing import Optional, Dict, List, Tuple, Any

# Import configuration
from config_taxonomy import (
    get_ncbi_api_key, MAX_WORKERS, RATE_LIMIT_DELAY, REQUEST_RETRY_ATTEMPTS,
    REQUEST_RETRY_BACKOFF, NCBI_ENDPOINTS, NCBI_API_TIMEOUT, TAXONOMY_RANKS,
    LOG_LEVEL, LOG_FILE, ENABLE_CACHE, CACHE_MAX_SIZE, ENABLE_PERSISTENT_CACHE,
    PERSISTENT_CACHE_FILE, NCBI_BASE_INTERVAL_WITH_KEY, NCBI_BASE_INTERVAL_NO_KEY,
    NCBI_MAX_INTERVAL, NCBI_THROTTLE_GROWTH, NCBI_THROTTLE_DECAY,
    NCBI_429_COOLDOWN_MULTIPLIER, save_ncbi_api_key_file
)

# Import translation system
from translations import initialize_translator, get_translator, set_language

# --- LOGGING SETUP ---
os.makedirs(os.path.dirname(LOG_FILE) if os.path.dirname(LOG_FILE) else ".", exist_ok=True)


PERSISTENT_CACHE_PATH = os.path.join(os.path.dirname(__file__), PERSISTENT_CACHE_FILE)


def _load_persistent_cache() -> Dict[str, Dict[str, Any]]:
    if not ENABLE_CACHE or not ENABLE_PERSISTENT_CACHE:
        return {}

    try:
        if not os.path.exists(PERSISTENT_CACHE_PATH):
            return {}

        with open(PERSISTENT_CACHE_PATH, "r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)

        if isinstance(data, dict):
            return {
                str(func_name): value if isinstance(value, dict) else {}
                for func_name, value in data.items()
            }
    except Exception as exc:
        logger.debug(f"Failed to load persistent cache: {exc}")

    return {}


def _save_persistent_cache() -> None:
    if not ENABLE_CACHE or not ENABLE_PERSISTENT_CACHE:
        return

    try:
        os.makedirs(os.path.dirname(PERSISTENT_CACHE_PATH), exist_ok=True)
        with open(PERSISTENT_CACHE_PATH, "w", encoding="utf-8") as file_handle:
            json.dump(PERSISTENT_CACHE, file_handle, ensure_ascii=False)
    except Exception as exc:
        logger.debug(f"Failed to save persistent cache: {exc}")


PERSISTENT_CACHE: Dict[str, Dict[str, Any]] = _load_persistent_cache()
atexit.register(_save_persistent_cache)


def _utf8_stream(stream):
    """Return a text stream that can safely emit UTF-8 log messages on Windows."""
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
        return stream
    except Exception:
        try:
            return io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace", line_buffering=True)
        except Exception:
            return stream


logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(_utf8_stream(sys.stderr))
    ]
)
logger = logging.getLogger(__name__)

NCBI_REQUEST_LOCK = threading.Lock()
NCBI_LAST_REQUEST_AT = 0.0
NCBI_CURRENT_INTERVAL = NCBI_BASE_INTERVAL_WITH_KEY if get_ncbi_api_key() else NCBI_BASE_INTERVAL_NO_KEY
NCBI_THROTTLE_COOLDOWN_UNTIL = 0.0


def _normalize_value(value: Any) -> Optional[str]:
    if pd.isna(value):
        return None

    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None

    return text


def _make_cache_key(func_name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    return json.dumps(
        {
            "func": func_name,
            "args": args,
            "kwargs": sorted(kwargs.items()),
        },
        default=str,
        ensure_ascii=False,
        sort_keys=True,
    )


def _register_throttle_success() -> None:
    global NCBI_CURRENT_INTERVAL
    NCBI_CURRENT_INTERVAL = max(
        NCBI_BASE_INTERVAL_WITH_KEY if NCBI_API_KEY else NCBI_BASE_INTERVAL_NO_KEY,
        NCBI_CURRENT_INTERVAL * NCBI_THROTTLE_DECAY,
    )


def _register_throttle_429(wait_hint: float | None = None) -> float:
    global NCBI_CURRENT_INTERVAL, NCBI_THROTTLE_COOLDOWN_UNTIL

    wait_time = wait_hint or 0.0
    NCBI_CURRENT_INTERVAL = min(NCBI_MAX_INTERVAL, max(NCBI_CURRENT_INTERVAL * NCBI_THROTTLE_GROWTH, wait_time))
    NCBI_THROTTLE_COOLDOWN_UNTIL = max(
        NCBI_THROTTLE_COOLDOWN_UNTIL,
        time.monotonic() + max(wait_time, NCBI_CURRENT_INTERVAL * NCBI_429_COOLDOWN_MULTIPLIER),
    )
    return NCBI_CURRENT_INTERVAL


def _ncbi_request(url: str, *, params: Dict[str, Any], timeout: int, method: str = "get"):
    """Serialize NCBI requests so concurrent workers do not exceed API limits."""
    global NCBI_LAST_REQUEST_AT

    with NCBI_REQUEST_LOCK:
        now = time.monotonic()
        next_allowed_at = max(NCBI_LAST_REQUEST_AT + NCBI_CURRENT_INTERVAL, NCBI_THROTTLE_COOLDOWN_UNTIL)
        if now < next_allowed_at:
            time.sleep(next_allowed_at - now)

        if method.lower() == "post":
            response = requests.post(url, data=params, timeout=timeout)
        else:
            response = requests.get(url, params=params, timeout=timeout)
        NCBI_LAST_REQUEST_AT = time.monotonic()
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            retry_after_seconds = 0.0
            if retry_after is not None:
                try:
                    retry_after_seconds = float(retry_after)
                except ValueError:
                    retry_after_seconds = 0.0
            _register_throttle_429(retry_after_seconds)
        else:
            _register_throttle_success()

        return response

# --- CACHING DECORATOR ---
def cache_result(func):
    """Simple in-memory cache decorator with max size limit."""
    cache = PERSISTENT_CACHE.setdefault(func.__name__, {})
    cache_stats = {"hits": 0, "misses": 0}
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not ENABLE_CACHE:
            return func(*args, **kwargs)
        
        key = _make_cache_key(func.__name__, args, kwargs)
        
        if key in cache:
            cache_stats["hits"] += 1
            logger.debug(f"Cache hit for {func.__name__} with args {args}")
            return cache[key]
        
        cache_stats["misses"] += 1
        result = func(*args, **kwargs)
        
        # Implement max cache size
        if len(cache) >= CACHE_MAX_SIZE:
            first_key = next(iter(cache))
            del cache[first_key]
        
        cache[key] = result
        return result
    
    wrapper.cache_stats = cache_stats
    wrapper.cache_clear = lambda: cache.clear()
    return wrapper

# --- RETRY DECORATOR ---
def retry_with_backoff(max_attempts: int = REQUEST_RETRY_ATTEMPTS, backoff: float = REQUEST_RETRY_BACKOFF):
    """Decorator for retry logic with exponential backoff."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            last_exception = None
            
            while attempt < max_attempts:
                try:
                    return func(*args, **kwargs)
                except (requests.RequestException, requests.Timeout) as e:
                    last_exception = e
                    attempt += 1
                    if attempt < max_attempts:
                        wait_time = backoff ** (attempt - 1)
                        status_code = getattr(getattr(e, "response", None), "status_code", None)
                        if status_code == 429:
                            retry_after = getattr(getattr(e, "response", None), "headers", {}).get("Retry-After")
                            try:
                                retry_after_seconds = float(retry_after) if retry_after is not None else 0.0
                            except ValueError:
                                retry_after_seconds = 0.0
                            wait_time = max(wait_time, retry_after_seconds, _register_throttle_429(retry_after_seconds))
                        logger.warning(
                            f"{func.__name__} failed (attempt {attempt}/{max_attempts}). "
                            f"Retrying in {wait_time:.1f}s. Error: {str(e)[:100]}"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(f"{func.__name__} failed after {max_attempts} attempts")
                except Exception as e:
                    logger.error(f"{func.__name__} failed with unexpected error: {str(e)}", exc_info=True)
                    return None
            
            if last_exception:
                logger.error(f"Max retries exceeded for {func.__name__}: {str(last_exception)}")
            return None
        
        return wrapper
    return decorator

# --- CONFIGURATION ---
NCBI_API_KEY: Optional[str] = get_ncbi_api_key()

# --- TAXONOMY API FUNCTIONS ---

@retry_with_backoff()
@cache_result
def get_taxonomy_by_name(name: str) -> Optional[str]:
    """
    Get taxonomy ID from species name using NCBI taxonomy search.
    
    Args:
        name: Scientific name to search for
        
    Returns:
        Taxonomy ID if found, None otherwise
    """
    if pd.isna(name) or str(name).strip() == "":
        return None
    
    try:
        words = str(name).split()
        clean_name = " ".join(words[:2]) if len(words) > 1 else words[0]
        
        params = {
            "db": "taxonomy",
            "term": clean_name,
            "retmode": "json"
        }
        if NCBI_API_KEY:
            params["api_key"] = NCBI_API_KEY
        
        response = _ncbi_request(
            NCBI_ENDPOINTS["esearch"],
            params=params,
            timeout=NCBI_API_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        ids = data.get("esearchresult", {}).get("idlist", [])
        
        if ids:
            logger.debug(f"Found taxonomy ID for name '{clean_name}': {ids[0]}")
            return ids[0]
        else:
            logger.debug(f"No taxonomy ID found for name '{clean_name}'")
            return None
            
    except requests.RequestException as e:
        logger.error(f"Request error in get_taxonomy_by_name('{name}'): {str(e)}")
        return None
    except (KeyError, ValueError) as e:
        logger.error(f"Parse error in get_taxonomy_by_name('{name}'): {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_taxonomy_by_name('{name}'): {str(e)}", exc_info=True)
        return None


@retry_with_backoff()
@cache_result
def get_taxid_from_accession(accession: str) -> Optional[str]:
    """
    Get taxonomy ID from NCBI accession number.
    
    Args:
        accession: NCBI accession number
        
    Returns:
        Taxonomy ID if found, None otherwise
    """
    if pd.isna(accession) or str(accession).strip() == "":
        return None
    
    try:
        clean_accession = str(accession).split('.')[0]
        
        params = {
            "db": "nucleotide",
            "id": clean_accession,
            "retmode": "json"
        }
        if NCBI_API_KEY:
            params["api_key"] = NCBI_API_KEY
        
        response = _ncbi_request(
            NCBI_ENDPOINTS["esummary"],
            params=params,
            timeout=NCBI_API_TIMEOUT
        )
        response.raise_for_status()
        
        data = response.json()
        
        if "result" not in data or not data["result"].get("uids"):
            logger.debug(f"No results for accession '{accession}'")
            return None
        
        uid = data["result"]["uids"][0]
        taxid = data["result"].get(uid, {}).get("taxid")
        
        if taxid:
            logger.debug(f"Found taxonomy ID for accession '{accession}': {taxid}")
            return str(taxid)
        else:
            logger.debug(f"No taxid found for accession '{accession}'")
            return None
            
    except requests.RequestException as e:
        logger.error(f"Request error in get_taxid_from_accession('{accession}'): {str(e)}")
        return None
    except (KeyError, IndexError) as e:
        logger.error(f"Parse error in get_taxid_from_accession('{accession}'): {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_taxid_from_accession('{accession}'): {str(e)}", exc_info=True)
        return None


@retry_with_backoff()
@cache_result
def get_lineage(taxid: str) -> Optional[Dict[str, Optional[str]]]:
    """
    Get full taxonomy lineage from taxonomy ID.
    
    Args:
        taxid: NCBI taxonomy ID
        
    Returns:
        Dictionary with taxonomy ranks and their names, or None if error
    """
    if not taxid:
        return None
    
    try:
        params = {
            "db": "taxonomy",
            "id": taxid,
            "retmode": "xml"
        }
        if NCBI_API_KEY:
            params["api_key"] = NCBI_API_KEY
        
        response = _ncbi_request(
            NCBI_ENDPOINTS["efetch"],
            params=params,
            timeout=NCBI_API_TIMEOUT
        )
        response.raise_for_status()
        
        root = ET.fromstring(response.text)
        taxon = root.find(".//Taxon")
        
        if taxon is None:
            logger.warning(f"No taxon found for taxid '{taxid}'")
            return None
        
        # Initialize result with all ranks
        result: Dict[str, Optional[str]] = {rank: None for rank in TAXONOMY_RANKS}
        
        # Extract lineage information
        for node in taxon.findall(".//LineageEx/Taxon"):
            rank = node.findtext("Rank")
            scientific_name = node.findtext("ScientificName")
            if rank in result and scientific_name:
                result[rank] = scientific_name
        
        # Add species from main taxon
        species_name = taxon.findtext("ScientificName")
        if species_name:
            result["species"] = species_name
        
        logger.debug(f"Retrieved lineage for taxid '{taxid}'")
        return result
        
    except ET.ParseError as e:
        logger.error(f"XML parse error in get_lineage('{taxid}'): {str(e)}")
        return None
    except requests.RequestException as e:
        logger.error(f"Request error in get_lineage('{taxid}'): {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in get_lineage('{taxid}'): {str(e)}", exc_info=True)
        return None


def process_entry(entry: Tuple[str, str, int, int]) -> Dict[str, Any]:
    """
    Process a single accession/name entry to retrieve taxonomy information.
    
    Args:
        entry: Tuple of (accession, scientific_name, current_index, total_entries)
        
    Returns:
        Dictionary with accession, name, lineage info, and verification method
    """
    accession, scientific_name, idx, total = entry
    accession = _normalize_value(accession)
    scientific_name = _normalize_value(scientific_name)
    display_value = accession or scientific_name or "Bilinmiyor"
    
    logger.info(f"Processing entry {idx}/{total}: {display_value}")
    
    # Try accession first
    taxid = get_taxid_from_accession(accession) if accession else None
    method = "Accession"
    
    # Fall back to name search if accession fails
    if not taxid and scientific_name:
        taxid = get_taxonomy_by_name(scientific_name)
        method = "Name_Fuzzy"
        logger.debug(f"Fell back to name search for {accession}")
    
    # Get full lineage if taxid found
    lineage = get_lineage(taxid) if taxid else None
    
    # Rate limiting
    time.sleep(RATE_LIMIT_DELAY)
    
    # Build result
    result: Dict[str, Any] = {
        "Accession": accession,
        "scientific_name_original": scientific_name,
        "verification_method": method
    }
    
    if lineage:
        result.update(lineage)
    else:
        # Ensure all taxonomy ranks are present even if lookup failed
        for rank in TAXONOMY_RANKS:
            if rank not in result:
                result[rank] = None
    
    return result


def _classify_bulk_value(raw_value: str) -> Tuple[str, str]:
    normalized_value = raw_value.strip().split()[0].strip().rstrip(",;|")
    if normalized_value.isdigit():
        return normalized_value, "taxid"

    if any(character.isdigit() for character in normalized_value) and any(character.isalpha() for character in normalized_value):
        return normalized_value, "accession"

    return normalized_value, "name"


def _detect_column_index(columns: List[str], preferred_names: List[str], fallback_index: int = 0) -> int:
    normalized_columns = {str(column).strip().lower(): index for index, column in enumerate(columns)}

    for preferred_name in preferred_names:
        preferred_index = normalized_columns.get(preferred_name.lower())
        if preferred_index is not None:
            return preferred_index

    for index, column_name in enumerate(columns):
        lowered_name = str(column_name).strip().lower()
        if any(preferred_name.lower() in lowered_name for preferred_name in preferred_names):
            return index

    return fallback_index


def _chunked(values: List[str], size: int) -> List[List[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def get_taxids_from_accessions(accessions: List[str]) -> Dict[str, Optional[str]]:
    lookup: Dict[str, Optional[str]] = {}
    cleaned_accessions = []

    for accession in accessions:
        normalized_accession = _normalize_value(accession)
        if normalized_accession:
            cleaned_accessions.append(normalized_accession)

    if not cleaned_accessions:
        return lookup

    for batch in _chunked(list(dict.fromkeys(cleaned_accessions)), 200):
        params = {
            "db": "nucleotide",
            "id": ",".join(batch),
            "retmode": "json",
        }
        if NCBI_API_KEY:
            params["api_key"] = NCBI_API_KEY

        response = _ncbi_request(
            NCBI_ENDPOINTS["esummary"],
            params=params,
            timeout=NCBI_API_TIMEOUT,
            method="post" if len(batch) > 100 else "get",
        )
        response.raise_for_status()

        data = response.json().get("result", {})
        for uid in data.get("uids", []):
            record = data.get(uid, {})
            taxid = record.get("taxid")
            taxid_text = str(taxid) if taxid else None
            caption = _normalize_value(record.get("caption"))
            accession_version = _normalize_value(record.get("accessionversion"))

            for key in {caption, accession_version, caption.split(".")[0] if caption else None, accession_version.split(".")[0] if accession_version else None}:
                if key:
                    lookup[key] = taxid_text

    return lookup


def get_lineages_from_taxids(taxids: List[str]) -> Dict[str, Dict[str, Optional[str]]]:
    lookup: Dict[str, Dict[str, Optional[str]]] = {}
    cleaned_taxids = []

    for taxid in taxids:
        normalized_taxid = _normalize_value(taxid)
        if normalized_taxid:
            cleaned_taxids.append(normalized_taxid)

    if not cleaned_taxids:
        return lookup

    for batch in _chunked(list(dict.fromkeys(cleaned_taxids)), 200):
        params = {
            "db": "taxonomy",
            "id": ",".join(batch),
            "retmode": "xml",
        }
        if NCBI_API_KEY:
            params["api_key"] = NCBI_API_KEY

        response = _ncbi_request(
            NCBI_ENDPOINTS["efetch"],
            params=params,
            timeout=NCBI_API_TIMEOUT,
            method="post" if len(batch) > 100 else "get",
        )
        response.raise_for_status()

        root = ET.fromstring(response.text)
        for taxon in root.findall(".//Taxon"):
            taxid_value = _normalize_value(taxon.findtext("TaxId"))
            if not taxid_value:
                continue

            lineage_result: Dict[str, Optional[str]] = {rank: None for rank in TAXONOMY_RANKS}
            for node in taxon.findall(".//LineageEx/Taxon"):
                rank = node.findtext("Rank")
                scientific_name = node.findtext("ScientificName")
                if rank in lineage_result and scientific_name:
                    lineage_result[rank] = scientific_name

            species_name = taxon.findtext("ScientificName")
            if species_name:
                lineage_result["species"] = species_name

            lookup[taxid_value] = lineage_result

    return lookup


def build_bulk_preview_rows(bulk_input: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for index, raw_line in enumerate(bulk_input.splitlines(), start=1):
        stripped_line = raw_line.strip()
        if not stripped_line:
            continue

        normalized_value, entry_type = _classify_bulk_value(stripped_line)
        rows.append(
            {
                t.t("advanced_tab.preview_column_index"): str(index),
                t.t("advanced_tab.preview_column_raw"): stripped_line,
                t.t("advanced_tab.preview_column_normalized"): normalized_value,
                t.t("advanced_tab.preview_column_type"): t.t(f"advanced_tab.entry_type_{entry_type}"),
            }
        )

    return rows


def build_bulk_preview_rows_from_values(values: List[Any]) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for index, raw_value in enumerate(values, start=1):
        if pd.isna(raw_value):
            continue

        stripped_line = str(raw_value).strip()
        if not stripped_line or stripped_line.lower() == "nan":
            continue

        normalized_value, entry_type = _classify_bulk_value(stripped_line)
        rows.append(
            {
                t.t("advanced_tab.preview_column_index"): str(index),
                t.t("advanced_tab.preview_column_raw"): stripped_line,
                t.t("advanced_tab.preview_column_normalized"): normalized_value,
                t.t("advanced_tab.preview_column_type"): t.t(f"advanced_tab.entry_type_{entry_type}"),
            }
        )

    return rows


def process_bulk_preview_row(row: Dict[str, str], idx: int, total: int) -> Dict[str, Any]:
    normalized_value = row.get(t.t("advanced_tab.preview_column_normalized"), "")
    entry_type = row.get(t.t("advanced_tab.preview_column_type"), "")
    display_value = normalized_value or row.get(t.t("advanced_tab.preview_column_raw"), "") or "Bilinmiyor"

    logger.info(f"Processing bulk entry {idx}/{total}: {display_value}")

    accession_value: Optional[str] = None
    scientific_name_value: Optional[str] = None
    taxid_value: Optional[str] = None
    verification_method = entry_type

    if entry_type == t.t("advanced_tab.entry_type_taxid"):
        taxid_value = normalized_value
        verification_method = "Taxid"
    elif entry_type == t.t("advanced_tab.entry_type_accession"):
        accession_value = normalized_value
        taxid_value = get_taxid_from_accession(accession_value) if accession_value else None
        verification_method = "Accession"
    else:
        scientific_name_value = normalized_value
        taxid_value = get_taxonomy_by_name(scientific_name_value) if scientific_name_value else None
        verification_method = "Name_Fuzzy"

    lineage = get_lineage(taxid_value) if taxid_value else None
    time.sleep(RATE_LIMIT_DELAY)

    result: Dict[str, Any] = {
        t.t("advanced_tab.preview_column_index"): row.get(t.t("advanced_tab.preview_column_index"), str(idx)),
        "Accession": accession_value,
        "scientific_name_original": scientific_name_value,
        "taxid": taxid_value,
        "verification_method": verification_method,
        "bulk_input_raw": row.get(t.t("advanced_tab.preview_column_raw"), ""),
        "bulk_input_normalized": normalized_value,
        "bulk_input_type": entry_type,
    }

    if lineage:
        result.update(lineage)
    else:
        for rank in TAXONOMY_RANKS:
            result.setdefault(rank, None)

    return result

# --- STREAMLIT UI ---
# Initialize translator
translator = initialize_translator()

# Set up Streamlit page config
st.set_page_config(page_title="eDNA Taxonomy Tool", layout="wide")

# Initialize language in session state
if "language" not in st.session_state:
    st.session_state.language = "tr"

# Language selector in sidebar
with st.sidebar:
    st.markdown("### 🌐 Dil / Language")
    language_options = translator.get_all_languages()
    selected_lang = st.selectbox(
        "Select Language / Dili Seçin",
        options=list(language_options.keys()),
        format_func=lambda x: language_options[x],
        index=0 if st.session_state.language == "tr" else 1,
        key="lang_selector"
    )
    
    # Update language if changed
    if selected_lang != st.session_state.language:
        st.session_state.language = selected_lang
        set_language(selected_lang)
        st.rerun()
    else:
        set_language(st.session_state.language)

# Get translator for easier access
t = get_translator()

def render_analysis_tab() -> None:
    st.subheader(t.t("processing.status_title"))

    if not NCBI_API_KEY:
        st.warning(t.t("app.api_key_not_found"))
        st.info(t.t("analysis.api_key_hint"))

    uploaded_file = st.file_uploader(t.t("upload.label"), type=["xlsx"], key="analysis_upload")
    if not uploaded_file:
        st.info(t.t("analysis.no_file_prompt"))
        return

    try:
        logger.info(f"File uploaded: {uploaded_file.name}")
        df_original = pd.read_excel(uploaded_file)
        df_original.columns = [str(col).strip() for col in df_original.columns]
        all_columns = df_original.columns.tolist()

        st.session_state["analysis_uploaded_df"] = df_original
        st.session_state["analysis_uploaded_columns"] = all_columns
        st.session_state["analysis_uploaded_name"] = uploaded_file.name

        with st.expander(t.t("upload.preview"), expanded=True):
            left, right = st.columns([1, 2])
            with left:
                st.write(f"**{t.t('upload.file_info_title')}**")
                st.write(t.t("upload.total_rows", len(df_original)))
                st.write(t.t("upload.total_columns", len(df_original.columns)))
            with right:
                st.write(f"**{t.t('upload.column_names')}**")
                st.code(", ".join(all_columns))
            st.dataframe(df_original.head(10), width="stretch")

        st.subheader(t.t("column_mapping.title"))
        st.info(t.t("column_mapping.info"))
        accession_only_mode = st.checkbox(
            t.t("analysis.accession_only_mode"),
            value=True,
            key="analysis_accession_only_mode",
        )
        if accession_only_mode:
            st.caption(t.t("analysis.accession_only_hint"))

        col_sel1, col_sel2 = st.columns(2)
        def_acc_idx = _detect_column_index(all_columns, ["Accession", "accession", "acc", "accession number"], 0)
        def_name_idx = _detect_column_index(all_columns, ["scientific_name_original", "scientific name", "scientific_name", "name"], 1 if len(all_columns) > 1 else 0)

        with col_sel1:
            selected_acc_col = st.selectbox(t.t("column_mapping.accession_label"), options=all_columns, index=def_acc_idx, key="analysis_acc_col")
        if not accession_only_mode:
            with col_sel2:
                selected_name_col = st.selectbox(t.t("column_mapping.name_label"), options=all_columns, index=def_name_idx, key="analysis_name_col")
        else:
            selected_name_col = None

        if st.button(t.t("processing.start_button"), key="analysis_start_button"):
            if accession_only_mode:
                df_working = df_original.rename(columns={selected_acc_col: "Accession"})
                if "Accession" not in df_working.columns:
                    raise KeyError("Accession column could not be created from the selected Excel column")
                unique_entries = df_working[["Accession"]].drop_duplicates()
            else:
                df_working = df_original.rename(columns={
                    selected_acc_col: "Accession",
                    selected_name_col: "scientific_name_original",
                })
                unique_entries = df_working[["Accession", "scientific_name_original"]].drop_duplicates()

            total_unique = len(unique_entries)

            progress_bar = st.progress(0)
            status_text = st.empty()
            accession_values = unique_entries["Accession"].tolist()

            status_text.text(t.t("processing.processing_text", 1, total_unique, t.t("advanced_tab.excel_accession_preview_button")))
            taxid_lookup = get_taxids_from_accessions(accession_values)
            progress_bar.progress(0.5)

            if accession_only_mode:
                lineage_lookup = get_lineages_from_taxids(list(dict.fromkeys(taxid for taxid in taxid_lookup.values() if taxid)))
                progress_bar.progress(1.0)

                results: List[Dict[str, Any]] = []
                for accession_value in accession_values:
                    normalized_accession = _normalize_value(accession_value)
                    if not normalized_accession:
                        continue

                    taxid_value = taxid_lookup.get(normalized_accession) or taxid_lookup.get(normalized_accession.split(".")[0])
                    lineage = lineage_lookup.get(taxid_value) if taxid_value else None

                    result: Dict[str, Any] = {
                        "Accession": normalized_accession,
                        "scientific_name_original": None,
                        "verification_method": "Accession",
                    }

                    if lineage:
                        result.update(lineage)
                    else:
                        for rank in TAXONOMY_RANKS:
                            result[rank] = None

                    results.append(result)

                df_lookup = pd.DataFrame(results)
                df_final = pd.merge(df_working, df_lookup, on=["Accession"], how="left")
            else:
                lookup_rows: List[Dict[str, Any]] = []
                missing_rows: List[Tuple[str, str, int, int]] = []

                for idx, (_, row) in enumerate(unique_entries.iterrows(), start=1):
                    normalized_accession = _normalize_value(row["Accession"])
                    scientific_name_original = _normalize_value(row["scientific_name_original"])
                    if not normalized_accession:
                        continue

                    taxid_value = taxid_lookup.get(normalized_accession) or taxid_lookup.get(normalized_accession.split(".")[0])
                    if taxid_value:
                        lookup_rows.append({
                            "Accession": normalized_accession,
                            "scientific_name_original": scientific_name_original,
                            "taxid": taxid_value,
                            "verification_method": "Accession",
                        })
                    elif scientific_name_original:
                        missing_rows.append((normalized_accession, scientific_name_original, idx, total_unique))

                missing_results: List[Dict[str, Any]] = []
                if missing_rows:
                    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                        for idx, result in enumerate(executor.map(process_entry, missing_rows), start=1):
                            missing_results.append(result)
                            status_text.text(t.t("processing.processing_text", idx, len(missing_rows), result.get("scientific_name_original", "Bilinmiyor")))
                            progress_bar.progress(0.5 + (idx / max(len(missing_rows), 1)) * 0.5)

                if lookup_rows or missing_results:
                    df_lookup = pd.DataFrame(lookup_rows + missing_results)
                else:
                    df_lookup = pd.DataFrame(columns=["Accession", "scientific_name_original", "taxid", "verification_method"])

                if not df_lookup.empty:
                    lineage_lookup = get_lineages_from_taxids(list(dict.fromkeys(taxid for taxid in df_lookup["taxid"].tolist() if taxid)))
                    for row_index, row in df_lookup.iterrows():
                        taxid_value = row.get("taxid")
                        lineage = lineage_lookup.get(taxid_value) if taxid_value else None
                        if lineage:
                            for rank, value in lineage.items():
                                df_lookup.at[row_index, rank] = value
                        else:
                            for rank in TAXONOMY_RANKS:
                                if rank not in df_lookup.columns:
                                    df_lookup[rank] = None

                df_final = pd.merge(df_working, df_lookup, on=["Accession", "scientific_name_original"], how="left")

            st.balloons()
            st.success(t.t("processing.completed"))

            st.markdown("---")
            st.subheader(t.t("summary.title"))
            summary_col1, summary_col2 = st.columns(2)
            with summary_col1:
                if "phylum" in df_final.columns:
                    st.write(t.t("summary.phylum_distribution"))
                    st.dataframe(df_final["phylum"].value_counts(), width="stretch")
            with summary_col2:
                if "class" in df_final.columns:
                    st.write(t.t("summary.class_distribution"))
                    st.dataframe(df_final["class"].value_counts(), width="stretch")

            st.subheader(t.t("results.results_table"))
            st.dataframe(df_final.head(20), width="stretch")

            if accession_only_mode:
                st.caption(t.t("analysis.accession_only_result_note"))

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                df_final.to_excel(writer, index=False, sheet_name="Taxonomy_Results")
            st.download_button(
                label=t.t("results.download_button"),
                data=output.getvalue(),
                file_name=t.t("results.download_filename"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="analysis_download_button",
            )

    except pd.errors.ParserError as exc:
        logger.error(f"Excel parse error: {exc}")
        st.error(t.t("errors.parse_error"))
    except Exception as exc:
        logger.error(f"Unexpected error during file processing: {exc}", exc_info=True)
        st.error(t.t("errors.unexpected_error", str(exc)))


def render_api_key_tab() -> None:
    st.subheader(t.t("api_key_tab.title"))
    st.write(t.t("api_key_tab.description"))

    if NCBI_API_KEY:
        st.success(t.t("app.api_key_found", NCBI_API_KEY[:5]))
    else:
        st.warning(t.t("app.api_key_not_found"))

    uploaded_key_file = st.file_uploader(
        t.t("api_key_tab.upload_label"),
        type=None,
        help=t.t("api_key_tab.upload_help"),
        key="api_key_upload",
    )
    if uploaded_key_file is not None:
        saved_path = save_ncbi_api_key_file(uploaded_key_file.getvalue(), uploaded_key_file.name)
        st.success(t.t("api_key_tab.saved", saved_path))
        st.rerun()


def render_advanced_tab() -> None:
    st.subheader(t.t("advanced_tab.title"))
    st.markdown(t.t("advanced_tab.description"))
    st.info(
        t.t(
            "advanced_tab.settings",
            MAX_WORKERS,
            RATE_LIMIT_DELAY,
            NCBI_BASE_INTERVAL_WITH_KEY,
            NCBI_BASE_INTERVAL_NO_KEY,
        )
    )

    uploaded_df = st.session_state.get("analysis_uploaded_df")
    uploaded_columns = st.session_state.get("analysis_uploaded_columns", [])

    with st.expander(t.t("advanced_tab.excel_accession_title"), expanded=True):
        if uploaded_df is None or not uploaded_columns:
            st.info(t.t("advanced_tab.excel_accession_no_source"))
        else:
            st.write(t.t("advanced_tab.excel_accession_description", st.session_state.get("analysis_uploaded_name", "")))
            accession_columns = uploaded_columns
            default_acc_index = _detect_column_index(accession_columns, ["Accession", "accession", "acc", "accession number"], 0)
            selected_acc_col = st.selectbox(
                t.t("advanced_tab.excel_accession_column_label"),
                options=accession_columns,
                index=default_acc_index,
                key="advanced_excel_accession_column",
            )

            preview_state_key = "advanced_excel_accession_preview_rows"
            preview_ready_key = "advanced_excel_accession_preview_ready"

            if st.button(t.t("advanced_tab.excel_accession_preview_button"), key="advanced_excel_accession_preview_button"):
                preview_values = uploaded_df[selected_acc_col].drop_duplicates().tolist()
                preview_rows = build_bulk_preview_rows_from_values(preview_values)
                st.session_state[preview_state_key] = preview_rows
                st.session_state[preview_ready_key] = True

                if not preview_rows:
                    st.warning(t.t("advanced_tab.excel_accession_empty"))
                else:
                    st.success(t.t("advanced_tab.excel_accession_preview_result", len(preview_rows)))
                    st.dataframe(pd.DataFrame(preview_rows), width="stretch")
                    st.caption(t.t("advanced_tab.excel_accession_preview_caption"))

            preview_rows = st.session_state.get(preview_state_key, [])
            preview_ready = st.session_state.get(preview_ready_key, False)

            if preview_ready and preview_rows:
                if st.button(t.t("advanced_tab.bulk_run_button"), key="advanced_excel_accession_bulk_run_button"):
                    total = len(preview_rows)
                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    accession_values = [row.get(t.t("advanced_tab.preview_column_raw"), "") for row in preview_rows]
                    status_text.text(t.t("advanced_tab.bulk_run_status", 1, total))
                    taxid_lookup = get_taxids_from_accessions(accession_values)
                    progress_bar.progress(0.5)

                    unique_taxids = list(dict.fromkeys(taxid for taxid in taxid_lookup.values() if taxid))
                    lineage_lookup = get_lineages_from_taxids(unique_taxids)

                    results: List[Dict[str, Any]] = []
                    for idx, row in enumerate(preview_rows, start=1):
                        raw_accession = _normalize_value(row.get(t.t("advanced_tab.preview_column_raw"), ""))
                        if not raw_accession:
                            continue

                        taxid_value = taxid_lookup.get(raw_accession) or taxid_lookup.get(raw_accession.split(".")[0])
                        lineage = lineage_lookup.get(taxid_value) if taxid_value else None

                        result: Dict[str, Any] = {
                            t.t("advanced_tab.preview_column_index"): row.get(t.t("advanced_tab.preview_column_index"), str(idx)),
                            "Accession": raw_accession,
                            "scientific_name_original": None,
                            "taxid": taxid_value,
                            "verification_method": "Accession",
                            "bulk_input_raw": row.get(t.t("advanced_tab.preview_column_raw"), ""),
                            "bulk_input_normalized": raw_accession,
                            "bulk_input_type": t.t("advanced_tab.entry_type_accession"),
                        }

                        if lineage:
                            result.update(lineage)
                        else:
                            for rank in TAXONOMY_RANKS:
                                result.setdefault(rank, None)

                        results.append(result)
                        status_text.text(t.t("advanced_tab.bulk_run_status", idx, total))
                        progress_bar.progress(idx / total)

                    df_final = pd.DataFrame(results)
                    st.success(t.t("advanced_tab.bulk_run_completed", total))
                    st.dataframe(df_final.head(50), width="stretch")

                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                        df_final.to_excel(writer, index=False, sheet_name="Accession_Results")

                    st.download_button(
                        label=t.t("advanced_tab.bulk_download_button"),
                        data=output.getvalue(),
                        file_name=t.t("advanced_tab.bulk_download_filename"),
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key="advanced_excel_accession_bulk_download_button",
                    )

            st.caption(t.t("advanced_tab.excel_accession_fallback_note"))

    with st.expander(t.t("advanced_tab.bulk_preview_title"), expanded=False):
        st.write(t.t("advanced_tab.bulk_preview_description"))
        bulk_input = st.text_area(
            t.t("advanced_tab.bulk_input_label"),
            placeholder=t.t("advanced_tab.bulk_input_placeholder"),
            height=160,
            key="advanced_bulk_preview_input",
        )

        if st.button(t.t("advanced_tab.bulk_preview_button"), key="advanced_bulk_preview_button"):
            preview_rows = build_bulk_preview_rows(bulk_input)
            st.session_state["advanced_bulk_preview_rows"] = preview_rows
            st.session_state["advanced_bulk_preview_ready"] = True

            if not preview_rows:
                st.warning(t.t("advanced_tab.bulk_preview_empty"))
            else:
                st.success(t.t("advanced_tab.bulk_preview_result", len(preview_rows)))
                st.dataframe(pd.DataFrame(preview_rows), width="stretch")
                st.caption(t.t("advanced_tab.bulk_preview_caption"))

        preview_rows = st.session_state.get("advanced_bulk_preview_rows", [])
        preview_ready = st.session_state.get("advanced_bulk_preview_ready", False)

        if preview_ready and preview_rows:
            if st.button(t.t("advanced_tab.bulk_run_button"), key="advanced_bulk_run_button"):
                total = len(preview_rows)
                progress_bar = st.progress(0)
                status_text = st.empty()
                results: List[Dict[str, Any]] = []

                for idx, row in enumerate(preview_rows, start=1):
                    results.append(process_bulk_preview_row(row, idx, total))
                    status_text.text(t.t("advanced_tab.bulk_run_status", idx, total))
                    progress_bar.progress(idx / total)

                result_df = pd.DataFrame(results)
                st.success(t.t("advanced_tab.bulk_run_completed", total))
                st.dataframe(result_df, width="stretch")

                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                    result_df.to_excel(writer, index=False, sheet_name="Bulk_Taxonomy_Results")

                st.download_button(
                    label=t.t("advanced_tab.bulk_download_button"),
                    data=output.getvalue(),
                    file_name=t.t("advanced_tab.bulk_download_filename"),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="advanced_bulk_download_button",
                )


st.title(t.t("app.title"))
st.markdown("---")
logger.info(t.t("app.log_started"))

tabs = st.tabs([t.t("tabs.analysis"), t.t("tabs.api_key"), t.t("tabs.advanced")])

with tabs[0]:
    render_analysis_tab()

with tabs[1]:
    render_api_key_tab()

with tabs[2]:
    render_advanced_tab()