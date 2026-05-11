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


def _ncbi_request(url: str, *, params: Dict[str, Any], timeout: int):
    """Serialize NCBI requests so concurrent workers do not exceed API limits."""
    global NCBI_LAST_REQUEST_AT

    with NCBI_REQUEST_LOCK:
        now = time.monotonic()
        next_allowed_at = max(NCBI_LAST_REQUEST_AT + NCBI_CURRENT_INTERVAL, NCBI_THROTTLE_COOLDOWN_UNTIL)
        if now < next_allowed_at:
            time.sleep(next_allowed_at - now)

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

# Set page title and main title
st.title(t.t("app.title"))
st.markdown("---")

# Log application start
logger.info(t.t("app.log_started"))

# Show API key status
if NCBI_API_KEY:
    st.success(t.t("app.api_key_found", NCBI_API_KEY[:5]))
    logger.info("NCBI API key loaded successfully")
else:
    st.warning(t.t("app.api_key_not_found"))
    logger.warning("NCBI API key not found - rate limiting will apply")

    uploaded_key_file = st.file_uploader(
        "NCBI API key dosyası yükle",
        type=None,
        help="Dosya adı önemli değil. İçerik proje klasörüne ncbi_key.txt olarak kaydedilir.",
    )
    if uploaded_key_file is not None:
        try:
            saved_path = save_ncbi_api_key_file(uploaded_key_file.getvalue(), uploaded_key_file.name)
            st.success(f"API key kaydedildi: {saved_path}")
            logger.info(f"NCBI API key uploaded and saved as {saved_path}")
            st.rerun()
        except Exception as exc:
            logger.error(f"Failed to save uploaded NCBI API key: {exc}", exc_info=True)
            st.error(f"API key kaydedilemedi: {exc}")

# File upload
uploaded_file = st.file_uploader(t.t("upload.label"), type=["xlsx"])

if uploaded_file:
    try:
        logger.info(f"File uploaded: {uploaded_file.name}")
        df_original = pd.read_excel(uploaded_file)
        
        # Clean column names
        df_original.columns = [str(col).strip() for col in df_original.columns]
        all_columns = df_original.columns.tolist()
        
        logger.info(f"File loaded: {len(df_original)} rows, {len(df_original.columns)} columns")
        
        with st.expander(t.t("upload.preview"), expanded=True):
            col_info1, col_info2 = st.columns([1, 2])
            with col_info1:
                st.write(f"**{t.t('upload.file_info_title')}**")
                st.write(t.t("upload.total_rows", len(df_original)))
                st.write(t.t("upload.total_columns", len(df_original.columns)))
            with col_info2:
                st.write(f"**{t.t('upload.column_names')}**")
                st.code(", ".join(all_columns))
            
            st.dataframe(df_original.head(10), width='stretch')

        # --- COLUMN MAPPING SECTION ---
        st.subheader(t.t("column_mapping.title"))
        st.info(t.t("column_mapping.info"))
        
        target_acc = "Accession"
        target_name = "scientific_name_original"
        
        col_sel1, col_sel2 = st.columns(2)
        
        # Find default indices
        def_acc_idx = all_columns.index(target_acc) if target_acc in all_columns else 0
        def_name_idx = all_columns.index(target_name) if target_name in all_columns else (1 if len(all_columns) > 1 else 0)
        
        with col_sel1:
            selected_acc_col = st.selectbox(t.t("column_mapping.accession_label"), options=all_columns, index=def_acc_idx)
        with col_sel2:
            selected_name_col = st.selectbox(t.t("column_mapping.name_label"), options=all_columns, index=def_name_idx)

        # Start processing
        if st.button(t.t("processing.start_button")):
            logger.info(f"Starting analysis with columns: {selected_acc_col}, {selected_name_col}")
            
            try:
                # Rename columns to standard names
                df_working = df_original.rename(columns={
                    selected_acc_col: "Accession",
                    selected_name_col: "scientific_name_original"
                })
                
                unique_entries = df_working[['Accession', 'scientific_name_original']].drop_duplicates()
                total_unique = len(unique_entries)
                
                logger.info(t.t("processing.unique_entries", total_unique))
                
                st.markdown(f"### {t.t('processing.status_title')}")
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                results: List[Dict[str, Any]] = []
                
                # Process entries with ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    tasks: List[Tuple[str, str, int, int]] = []
                    for i, (_, row) in enumerate(unique_entries.iterrows()):
                        tasks.append((
                            row['Accession'],
                            row['scientific_name_original'],
                            i + 1,
                            total_unique
                        ))
                    
                    counter = 0
                    for result in executor.map(process_entry, tasks):
                        results.append(result)
                        counter += 1
                        current_name = result.get('scientific_name_original', 'Bilinmiyor')
                        status_text.text(t.t("processing.processing_text", counter, total_unique, current_name))
                        progress_bar.progress(counter / total_unique)
                
                logger.info(t.t("processing.success_log"))
                
                # Merge results
                df_lookup = pd.DataFrame(results)
                df_final = pd.merge(
                    df_working,
                    df_lookup,
                    on=['Accession', 'scientific_name_original'],
                    how='left'
                )
                
                st.balloons()
                st.success(t.t("processing.completed"))
                
                # Summary Report
                st.markdown("---")
                st.subheader(t.t("summary.title"))
                summary_col1, summary_col2 = st.columns(2)
                
                with summary_col1:
                    if 'phylum' in df_final.columns:
                        phylum_counts = df_final['phylum'].value_counts()
                        st.write(t.t("summary.phylum_distribution"))
                        st.dataframe(phylum_counts, width='stretch')
                
                with summary_col2:
                    if 'class' in df_final.columns:
                        class_counts = df_final['class'].value_counts()
                        st.write(t.t("summary.class_distribution"))
                        st.dataframe(class_counts, width='stretch')

                st.subheader(t.t("results.results_table"))
                st.dataframe(df_final.head(20), width='stretch')
                
                # Download results
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Taxonomy_Results')
                processed_data = output.getvalue()
                
                st.download_button(
                    label=t.t("results.download_button"),
                    data=processed_data,
                    file_name=t.t("results.download_filename"),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                logger.info("Analysis completed successfully")
                
            except Exception as e:
                logger.error(f"Error during analysis: {str(e)}", exc_info=True)
                st.error(t.t("errors.analysis_error", str(e)))
                st.error(t.t("errors.check_logs"))
    
    except pd.errors.ParserError as e:
        logger.error(f"Excel parse error: {str(e)}")
        st.error(t.t("errors.parse_error"))
    except Exception as e:
        logger.error(f"Unexpected error during file processing: {str(e)}", exc_info=True)
        st.error(t.t("errors.unexpected_error", str(e)))