import fitz # PyMuPDF
from docx import Document
import pandas as pd
import json
import logging
import os
from typing import Dict, Any, List, Optional
import pdfplumber
import traceback # For detailed error logging

# Get the logger instance
logger = logging.getLogger(__name__)

# TODO: Add support for pptx (python-pptx), xlsx (openpyxl), html (BeautifulSoup)

# --- Helper for Profiling --- 
def _create_profile_text(df: pd.DataFrame, sheet_name: Optional[str] = None) -> str:
    """Generates a structured text profile from a DataFrame."""
    profile = []
    if sheet_name:
        profile.append(f"Sheet: {sheet_name}")
    else:
        profile.append("Data File Summary") # For CSV
    
    profile.append(f"Rows: {df.shape[0]}, Columns: {df.shape[1]}")
    profile.append("Columns:")
    # Limit number of columns profiled if extremely wide
    max_cols_to_profile = 50 
    cols_to_profile = df.columns[:max_cols_to_profile]
    profile.append(f"  - Names: {', '.join(cols_to_profile)}")
    if len(df.columns) > max_cols_to_profile:
         profile.append(f"  - ...(truncated, total {len(df.columns)} columns)")

    profile.append("Data Types:")
    dtypes_str = ', '.join([f'{col}:{dtype}' for col, dtype in df.dtypes[cols_to_profile].items()])
    profile.append(f"  - {dtypes_str}")

    profile.append("Null/Missing Values (Count per column):")
    try:
        null_counts = df.isnull().sum()
        # Only show columns with missing values, up to a limit
        missing_cols = null_counts[null_counts > 0]
        if not missing_cols.empty:
            missing_limit = 20
            missing_str = ', '.join([f'{col}:{count}' for col, count in missing_cols.items()][:missing_limit])
            profile.append(f"  - {missing_str}")
            if len(missing_cols) > missing_limit:
                 profile.append(f"  - ...(truncated, total {len(missing_cols)} columns with nulls)")
        else:
             profile.append("  - None found")
    except Exception as e:
         logger.warning(f"Could not compute null counts: {e}")
         profile.append("  - Error calculating null counts.")

    profile.append("Sample Rows (first 3):")
    try:
        # Convert head to string, handle potential formatting issues
        sample_str = df.head(3).to_string(index=False) 
        # Indent sample rows for clarity
        indented_sample = "\n".join([f"  {line}" for line in sample_str.split('\n')])
        profile.append(indented_sample)
    except Exception as e:
         logger.warning(f"Could not generate sample rows string: {e}")
         profile.append("  Error generating sample rows.")

    return "\n".join(profile)

# --- New Visual Extraction Function ---
def extract_pdf_visuals(file_path: str) -> List[Dict[str, Any]]:
    """Extracts images and tables from a PDF file."""
    visual_elements = []
    filename = os.path.basename(file_path)
    logger.info(f"Starting visual element extraction for: {filename}")

    # Extract Images using PyMuPDF
    try:
        doc = fitz.open(file_path)
        logger.debug(f"Processing {len(doc)} pages for images.")
        for page_num in range(len(doc)):
            try:
                page = doc.load_page(page_num)
                img_list = page.get_images(full=True)
                for img_index, img_info in enumerate(img_list):
                    xref = img_info[0]
                    base_image = doc.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]
                    # Basic filtering (optional): skip very small images
                    if len(image_bytes) < 2048: # e.g., skip images smaller than 2KB
                        # logger.debug(f"Skipping small image {img_index+1} on page {page_num+1}")
                        continue

                    visual_elements.append({
                        'type': 'image',
                        'data': image_bytes,
                        'page_number': page_num + 1, # 1-based page number
                        'original_source': filename
                    })
                    # logger.debug(f"Extracted image {img_index+1} (xref: {xref}, ext: {image_ext}) from page {page_num+1}")
            except Exception as page_img_err:
                 logger.error(f"Error extracting images from page {page_num + 1} of '{filename}': {page_img_err}", exc_info=True)
        doc.close()
        logger.info(f"Found {len([e for e in visual_elements if e['type'] == 'image'])} images in '{filename}' via PyMuPDF.")
    except Exception as e:
        logger.error(f"Error extracting images from PDF '{filename}' using PyMuPDF: {e}", exc_info=True)

    # Extract Tables using pdfplumber
    table_count = 0
    try:
        with pdfplumber.open(file_path) as pdf:
            logger.debug(f"Processing {len(pdf.pages)} pages for tables.")
            for page_num, page in enumerate(pdf.pages):
                try:
                    tables = page.extract_tables()
                    for table_index, table in enumerate(tables):
                        if not table: # Skip empty tables
                            continue
                        # Convert table to Markdown for better LLM processing
                        # Simple Markdown conversion - might need refinement for complex tables
                        header = " | ".join(str(cell) if cell is not None else '' for cell in table[0])
                        separator = " | ".join(["---"] * len(table[0]))
                        body = "\n".join([" | ".join(str(cell) if cell is not None else '' for cell in row) for row in table[1:]])
                        table_markdown = f"| {header} |\n| {separator} |\n{body}"

                        visual_elements.append({
                            'type': 'table',
                            'data': table_markdown,
                            'page_number': page_num + 1, # 1-based page number
                            'original_source': filename
                        })
                        table_count += 1
                        # logger.debug(f"Extracted table {table_index+1} from page {page_num+1}")
                except Exception as page_table_err:
                    logger.error(f"Error extracting tables from page {page_num + 1} of '{filename}': {page_table_err}", exc_info=True)
        logger.info(f"Found {table_count} tables in '{filename}' via pdfplumber.")
    except Exception as e:
        logger.error(f"Error extracting tables from PDF '{filename}' using pdfplumber: {e}", exc_info=True)

    logger.info(f"Finished visual element extraction for '{filename}'. Found {len(visual_elements)} total elements.")
    return visual_elements

# --- Existing Text Extraction Functions (Modified PDF one slightly) ---

def extract_text_from_pdf(file_path: str) -> Dict[str, Any]:
    """Extracts text from a PDF file. (OCR logic removed, handled separately)"""
    logger.debug(f"Starting standard PDF text extraction for: {file_path}")
    text = ""
    # needs_ocr = False # REMOVED - No longer used here
    try:
        doc = fitz.open(file_path)
        if not doc.is_pdf:
            logger.warning(f"File is not a valid PDF: {file_path}")
            return {"text": "", "error": "Invalid PDF file"}

        num_pages = len(doc)
        logger.debug(f"PDF has {num_pages} pages.")
        total_text_len = 0
        # image_pages = 0 # REMOVED - Not needed for this check anymore

        for page_num in range(num_pages):
            page = doc.load_page(page_num)
            page_text = page.get_text().strip()
            total_text_len += len(page_text)
            text += page_text + "\n" # Add newline between pages
        doc.close()

        logger.debug(f"Finished standard PDF text extraction for '{os.path.basename(file_path)}'. Length: {total_text_len}")

    except Exception as e:
        logger.error(f"Error extracting standard text from PDF '{file_path}': {e}", exc_info=True)
        return {"text": text, "error": str(e)}

    return {"text": text.strip()} # Return only text and potential error

def extract_text_from_docx(file_path: str) -> Dict[str, Any]:
    """Extracts text from a DOCX file."""
    logger.debug(f"Starting DOCX extraction for: {file_path}")
    text = ""
    try:
        doc = Document(file_path)
        for para in doc.paragraphs:
            text += para.text + "\n"
        # TODO: Consider extracting text from tables within DOCX if needed
        logger.debug(f"Finished DOCX extraction for '{os.path.basename(file_path)}'. Length: {len(text)}")
    except Exception as e:
        logger.error(f"Error extracting text from DOCX '{file_path}': {e}", exc_info=True)
        return {"text": text, "error": str(e)}
    return {"text": text.strip()}

def extract_text_from_txt(file_path: str) -> Dict[str, Any]:
    """Extracts text from a TXT or MD file."""
    logger.debug(f"Starting TXT/MD extraction for: {file_path}")
    text = ""
    try:
        # Try common encodings
        encodings_to_try = ['utf-8', 'latin-1', 'windows-1252']
        for enc in encodings_to_try:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    text = f.read()
                logger.debug(f"Successfully read '{os.path.basename(file_path)}' with encoding '{enc}'. Length: {len(text)}")
                break # Stop after successful read
            except UnicodeDecodeError:
                logger.debug(f"Failed to decode '{os.path.basename(file_path)}' with '{enc}'")
                continue
            except Exception as file_err:
                # Catch other file reading errors for the specific encoding attempt
                logger.warning(f"Could not read file '{file_path}' with encoding '{enc}': {file_err}")
                continue # Try next encoding
        else: # If loop completes without break
            logger.error(f"Could not decode file '{file_path}' with any attempted encoding.")
            return {"text": "", "error": "Could not decode file"}

    except Exception as e:
        logger.error(f"Error extracting text from TXT/MD '{file_path}': {e}", exc_info=True)
        return {"text": text, "error": str(e)}
    return {"text": text.strip()}

def extract_text_from_csv(file_path: str) -> Dict[str, Any]:
    """Extracts a profile and sample from a CSV file using pandas."""
    logger.debug(f"Starting CSV profiling for: {file_path}")
    try:
        # Try reading with common parameters, add error handling
        try:
            df = pd.read_csv(file_path)
        except pd.errors.ParserError as pe:
            logger.warning(f"Pandas ParserError for '{file_path}': {pe}. Trying different settings.")
            try:
                df = pd.read_csv(file_path, on_bad_lines='skip')
            except Exception as fallback_err:
                 logger.error(f"Failed to parse CSV '{file_path}' even with fallback: {fallback_err}", exc_info=True)
                 return {"text": "", "error": f"Failed to parse CSV: {fallback_err}"}
        except Exception as read_err:
            logger.error(f"Error reading CSV '{file_path}' with pandas: {read_err}", exc_info=True)
            return {"text": "", "error": str(read_err)}

        # Generate profile text
        profile_text = _create_profile_text(df)
        logger.debug(f"Finished CSV profiling for '{os.path.basename(file_path)}'. Profile length: {len(profile_text)}")
        return {"text": profile_text}

    except Exception as e:
        logger.error(f"Error profiling CSV '{file_path}': {e}\n{traceback.format_exc()}") # Log full traceback
        return {"text": "", "error": f"Error profiling CSV: {e}"}

def extract_text_from_json(file_path: str) -> Dict[str, Any]:
    """Extracts text content from a JSON file by pretty-printing."""
    logger.debug(f"Starting JSON extraction for: {file_path}")
    text = ""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        text = json.dumps(data, indent=2) # Pretty print
        logger.debug(f"Finished JSON extraction for '{os.path.basename(file_path)}'. Length: {len(text)}")
    except json.JSONDecodeError as json_err:
         logger.error(f"Invalid JSON file: '{file_path}': {json_err}", exc_info=False)
         return {"text": "", "error": f"Invalid JSON format: {json_err}"}
    except Exception as e:
        logger.error(f"Error extracting text from JSON '{file_path}': {e}", exc_info=True)
        return {"text": text, "error": str(e)}
    return {"text": text.strip()}

# --- NEW: Add Excel Extractor --- 
def extract_text_from_xlsx(file_path: str) -> Dict[str, Any]:
    """Extracts a profile and sample from each sheet of an Excel file."""
    logger.debug(f"Starting Excel profiling for: {file_path}")
    combined_profiles = []
    try:
        # Read all sheets
        excel_data = pd.read_excel(file_path, sheet_name=None) # Returns dict {sheet_name: df}
        if not excel_data:
            logger.warning(f"No sheets found in Excel file: {file_path}")
            return {"text": "", "error": "No sheets found in file"}
        
        logger.info(f"Found {len(excel_data)} sheets in '{os.path.basename(file_path)}': {list(excel_data.keys())}")
        # Generate profile for each sheet
        for sheet_name, df in excel_data.items():
            logger.debug(f"Profiling sheet: '{sheet_name}'")
            sheet_profile = _create_profile_text(df, sheet_name)
            combined_profiles.append(sheet_profile)
        
        final_profile_text = "\n\n---\n\n".join(combined_profiles) # Join profiles with separator
        logger.debug(f"Finished Excel profiling for '{os.path.basename(file_path)}'. Total profile length: {len(final_profile_text)}")
        return {"text": final_profile_text}

    except Exception as e:
        logger.error(f"Error profiling Excel file '{file_path}': {e}\n{traceback.format_exc()}")
        return {"text": "", "error": f"Error profiling Excel file: {e}"}

# --- Main Extraction Dispatcher (Modified) ---
def extract_text(file_path: str, file_type: str) -> Dict[str, Any]:
    """Main extraction dispatcher based on file type."""
    logger.info(f"Dispatching extractor for file type '{file_type}' on file: {os.path.basename(file_path)}")

    extractor_map = {
        'pdf': extract_text_from_pdf,
        'docx': extract_text_from_docx,
        'text': extract_text_from_txt, # Handles .txt, .md
        'csv': extract_text_from_csv, # Uses new profiling function
        'json': extract_text_from_json,
        'xlsx': extract_text_from_xlsx, # ADDED mapping
        # 'xls': extract_text_from_xlsx, # Optional: Map older .xls if needed
        # --- Add mappings for other types here --- #
        # 'pptx': extract_text_from_pptx,
        # 'html': extract_text_from_html,
    }

    extractor_func = extractor_map.get(file_type)

    if extractor_func:
        try:
            result = extractor_func(file_path)
            # Log error here if extractor reported it
            if result.get("error"):
                 logger.warning(f"Extractor '{extractor_func.__name__}' reported error for '{file_path}': {result['error']}")
            # Ensure a 'text' key exists, even if empty on error
            if "text" not in result:
                 result["text"] = ""
            return result
        except Exception as e:
             # Catch unexpected errors within the specific extractor call itself
             logger.error(f"Unexpected error in extractor '{extractor_func.__name__}' for '{file_path}': {e}", exc_info=True)
             return {"text": "", "error": f"Unexpected extractor error: {e}"}
    else:
        # This case should ideally not be reached if called from file_router with supported types
        logger.error(f"No extractor function mapped for supported type: '{file_type}' ('{file_path}')")
        return {"text": "", "error": f"Internal mapping error for type {file_type}"} 