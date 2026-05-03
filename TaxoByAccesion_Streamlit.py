import streamlit as st
import requests
import pandas as pd
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
import io
import logging
import os
from functools import wraps
from typing import Optional, Dict, List, Tuple, Any

# Import configuration
from config_taxonomy import (
    get_ncbi_api_key, MAX_WORKERS, RATE_LIMIT_DELAY, REQUEST_RETRY_ATTEMPTS,
    REQUEST_RETRY_BACKOFF, NCBI_ENDPOINTS, NCBI_API_TIMEOUT, TAXONOMY_RANKS,
    LOG_LEVEL, LOG_FILE, ENABLE_CACHE
)

# --- LOGGING SETUP ---
os.makedirs(os.path.dirname(LOG_FILE) if os.path.dirname(LOG_FILE) else ".", exist_ok=True)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- CACHING DECORATOR ---
def cache_result(func):
    """Simple in-memory cache decorator with max size limit."""
    cache = {}
    cache_stats = {"hits": 0, "misses": 0}
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not ENABLE_CACHE:
            return func(*args, **kwargs)
        
        key = (func.__name__, args, tuple(sorted(kwargs.items())))
        
        if key in cache:
            cache_stats["hits"] += 1
            logger.debug(f"Cache hit for {func.__name__} with args {args}")
            return cache[key]
        
        cache_stats["misses"] += 1
        result = func(*args, **kwargs)
        
        # Implement max cache size
        if len(cache) >= 1000:
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
        
        response = requests.get(
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
        
        response = requests.get(
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
        
        response = requests.get(
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
    
    logger.info(f"Processing entry {idx}/{total}: {accession}")
    
    # Try accession first
    taxid = get_taxid_from_accession(accession)
    method = "Accession"
    
    # Fall back to name search if accession fails
    if not taxid:
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
st.set_page_config(page_title="eDNA Taxonomy Tool", layout="wide")

st.title("🧬 eDNA Accession Numaralarına Göre Taksonomi Eşleştirici")
st.markdown("---")

# Log application start
logger.info("=== Streamlit application started ===")

# Show API key status
if NCBI_API_KEY:
    st.success(f"✅ NCBI API Anahtarı Aktif: {NCBI_API_KEY[:5]}***")
    logger.info("NCBI API key loaded successfully")
else:
    st.warning("⚠️ NCBI Anahtarı bulunamadı. Sorgu hızı kısıtlı olacaktır.")
    logger.warning("NCBI API key not found - rate limiting will apply")

# File upload
uploaded_file = st.file_uploader("Blast Sonuç Dosyasını Seçin (Excel .xlsx)", type=["xlsx"])

if uploaded_file:
    try:
        logger.info(f"File uploaded: {uploaded_file.name}")
        df_original = pd.read_excel(uploaded_file)
        
        # Clean column names
        df_original.columns = [str(col).strip() for col in df_original.columns]
        all_columns = df_original.columns.tolist()
        
        logger.info(f"File loaded: {len(df_original)} rows, {len(df_original.columns)} columns")
        
        with st.expander("📂 Yüklenen Dosya Önizlemesi ve Sütun Kontrolü", expanded=True):
            col_info1, col_info2 = st.columns([1, 2])
            with col_info1:
                st.write("**Veri Özeti:**")
                st.write(f"- Toplam Satır: `{len(df_original)}`")
                st.write(f"- Toplam Sütun: `{len(df_original.columns)}`")
            with col_info2:
                st.write("**Temizlenmiş Sütun İsimleri:**")
                st.code(", ".join(all_columns))
            
            st.dataframe(df_original.head(10), use_container_width=True)

        # --- COLUMN MAPPING SECTION ---
        st.subheader("🛠️ Sütunları Tanımlayın")
        st.info("Eğer sistem sütunlarınızı otomatik tanıyamadıysa, lütfen aşağıdan doğru sütunları seçin.")
        
        target_acc = "Accession"
        target_name = "scientific_name_original"
        
        col_sel1, col_sel2 = st.columns(2)
        
        # Find default indices
        def_acc_idx = all_columns.index(target_acc) if target_acc in all_columns else 0
        def_name_idx = all_columns.index(target_name) if target_name in all_columns else (1 if len(all_columns) > 1 else 0)
        
        with col_sel1:
            selected_acc_col = st.selectbox("Accession Numarası Sütunu:", options=all_columns, index=def_acc_idx)
        with col_sel2:
            selected_name_col = st.selectbox("Scientific Name (Tür Adı) Sütunu:", options=all_columns, index=def_name_idx)

        # Start processing
        if st.button("🚀 Analizi Başlat"):
            logger.info(f"Starting analysis with columns: {selected_acc_col}, {selected_name_col}")
            
            try:
                # Rename columns to standard names
                df_working = df_original.rename(columns={
                    selected_acc_col: "Accession",
                    selected_name_col: "scientific_name_original"
                })
                
                unique_entries = df_working[['Accession', 'scientific_name_original']].drop_duplicates()
                total_unique = len(unique_entries)
                
                logger.info(f"Processing {total_unique} unique entries")
                
                st.markdown("### 🔎 İşlem Durumu")
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                results: List[Dict[str, Any]] = []
                
                # Process entries with ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    tasks: List[Tuple[str, str, int, int]] = []
                    for i, (_, row) in enumerate(unique_entries.iterrows()):
                        tasks.append((
                            str(row['Accession']),
                            str(row['scientific_name_original']),
                            i + 1,
                            total_unique
                        ))
                    
                    counter = 0
                    for result in executor.map(process_entry, tasks):
                        results.append(result)
                        counter += 1
                        current_name = result.get('scientific_name_original', 'Bilinmiyor')
                        status_text.text(f"İşleniyor ({counter}/{total_unique}): {current_name}")
                        progress_bar.progress(counter / total_unique)
                
                logger.info(f"Successfully processed {counter} entries")
                
                # Merge results
                df_lookup = pd.DataFrame(results)
                df_final = pd.merge(
                    df_working,
                    df_lookup,
                    on=['Accession', 'scientific_name_original'],
                    how='left'
                )
                
                st.balloons()
                st.success("✅ Tüm veriler başarıyla eşleştirildi!")
                
                # Summary Report
                st.markdown("---")
                st.subheader("📊 Taksonomik Dağılım Özeti")
                summary_col1, summary_col2 = st.columns(2)
                
                with summary_col1:
                    if 'phylum' in df_final.columns:
                        phylum_counts = df_final['phylum'].value_counts()
                        st.write("**Phylum (Şube) Dağılımı:**")
                        st.dataframe(phylum_counts, use_container_width=True)
                
                with summary_col2:
                    if 'class' in df_final.columns:
                        class_counts = df_final['class'].value_counts()
                        st.write("**Class (Sınıf) Dağılımı:**")
                        st.dataframe(class_counts, use_container_width=True)

                st.subheader("🏁 Sonuç Tablosu (İlk 20 Satır)")
                st.dataframe(df_final.head(20), use_container_width=True)
                
                # Download results
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df_final.to_excel(writer, index=False, sheet_name='Taxonomy_Results')
                processed_data = output.getvalue()
                
                st.download_button(
                    label="📥 Sonuçları Excel Olarak İndir",
                    data=processed_data,
                    file_name="eDNA_Taxonomy_Result.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                
                logger.info("Analysis completed successfully")
                
            except Exception as e:
                logger.error(f"Error during analysis: {str(e)}", exc_info=True)
                st.error(f"❌ Hata oluştu: {str(e)}")
                st.error("Lütfen log dosyasını kontrol edin: logs/taxonomy_app.log")
    
    except pd.errors.ParserError as e:
        logger.error(f"Excel parse error: {str(e)}")
        st.error("❌ Excel dosyası okunamadı. Dosya formatını kontrol edin.")
    except Exception as e:
        logger.error(f"Unexpected error during file processing: {str(e)}", exc_info=True)
        st.error(f"❌ Beklenmeyen hata: {str(e)}")