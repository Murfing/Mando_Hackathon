import fitz # PyMuPDF
from docx import Document
import pandas as pd
import json
import logging
import os
from typing import Dict, Any

# Get the logger instance
logger = logging.getLogger(__name__)

# TODO: Add support for pptx (python-pptx), xlsx (openpyxl), html (BeautifulSoup)

def extract_text_from_pdf(file_path: str) -> Dict[str, Any]:
    """Extracts text from a PDF file. Checks if OCR might be needed."""
    logger.debug(f"Starting PDF extraction for: {file_path}")
    text = ""
    needs_ocr = False
    try:
        doc = fitz.open(file_path)
        if not doc.is_pdf:
            logger.warning(f"File is not a valid PDF: {file_path}")
            return {"text": "", "needs_ocr": False, "error": "Invalid PDF file"}
            
        num_pages = len(doc)
        logger.debug(f"PDF has {num_pages} pages.")
        total_text_len = 0
        image_pages = 0

        for page_num in range(num_pages):
            page = doc.load_page(page_num)
            page_text = page.get_text().strip()
            if not page_text:
                 # Check more robustly if it contains images that might have text
                 if page.get_images(full=True):
                     logger.debug(f"Page {page_num + 1} has no text but contains images. Potential OCR needed.")
                     image_pages += 1
                 else:
                     logger.debug(f"Page {page_num + 1} appears to be empty (no text, no images).")
            else:
                 total_text_len += len(page_text)
            text += page_text + "\n" # Add newline between pages
        doc.close()

        # Decide if OCR is needed
        # If total text is very short compared to page count, or many pages had images but no text
        if num_pages > 0 and (total_text_len < num_pages * 20 or image_pages > num_pages // 2):
            logger.info(f"Low text content ({total_text_len} chars) or high image count ({image_pages}/{num_pages} pages) suggests OCR might be beneficial for '{os.path.basename(file_path)}'.")
            needs_ocr = True
        else:
             logger.debug(f"Extracted {total_text_len} characters. OCR likely not needed.")
             
    except Exception as e:
        logger.error(f"Error extracting text from PDF '{file_path}': {e}", exc_info=True)
        # Decide if failure implies needing OCR
        needs_ocr = True # Assume OCR might help if standard extraction fails
        return {"text": text, "needs_ocr": needs_ocr, "error": str(e)}
        
    logger.debug(f"Finished PDF extraction for '{file_path}'. Length: {len(text)}, Needs OCR: {needs_ocr}")
    return {"text": text.strip(), "needs_ocr": needs_ocr}

def extract_text_from_docx(file_path: str) -> Dict[str, Any]:
    """Extracts text from a DOCX file."""
    logger.debug(f"Starting DOCX extraction for: {file_path}")
    text = ""
    try:
        doc = Document(file_path)
        num_paras = len(doc.paragraphs)
        logger.debug(f"DOCX has {num_paras} paragraphs.")
        for i, para in enumerate(doc.paragraphs):
            text += para.text + "\n"
        # TODO: Extract text from tables as well
        # TODO: Extract text from headers/footers if needed
    except Exception as e:
        logger.error(f"Error extracting text from DOCX '{file_path}': {e}", exc_info=True)
        return {"text": "", "needs_ocr": False, "error": str(e)}
        
    logger.debug(f"Finished DOCX extraction for '{file_path}'. Length: {len(text)}")
    return {"text": text.strip(), "needs_ocr": False}

def extract_text_from_txt(file_path: str) -> Dict[str, Any]:
    """Extracts text from a TXT file."""
    logger.debug(f"Starting TXT extraction for: {file_path}")
    text = ""
    try:
        # Try common encodings
        encodings_to_try = ['utf-8', 'latin-1', 'cp1252']
        for enc in encodings_to_try:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    text = f.read()
                logger.debug(f"Successfully read TXT file with encoding: {enc}")
                break # Stop if successful
            except UnicodeDecodeError:
                logger.debug(f"Failed to decode TXT with {enc}, trying next...")
                continue
        else: # If loop finishes without break
            raise ValueError(f"Could not decode TXT file with tried encodings: {encodings_to_try}")

    except FileNotFoundError:
         logger.error(f"TXT file not found: '{file_path}'")
         return {"text": "", "needs_ocr": False, "error": "File not found"}
    except Exception as e:
        logger.error(f"Error reading TXT file '{file_path}': {e}", exc_info=True)
        return {"text": "", "needs_ocr": False, "error": str(e)}
        
    logger.debug(f"Finished TXT extraction for '{file_path}'. Length: {len(text)}")
    return {"text": text.strip(), "needs_ocr": False}

def extract_text_from_csv(file_path: str) -> Dict[str, Any]:
    """Extracts text content from a CSV file by concatenating rows."""
    logger.debug(f"Starting CSV extraction for: {file_path}")
    text = ""
    try:
        # Attempt to detect encoding, falling back to utf-8
        df = pd.read_csv(file_path, encoding_errors='ignore')
        logger.debug(f"CSV read successfully. Shape: {df.shape}")
        # Convert entire DataFrame to string, could be improved (e.g., row by row)
        # Consider handling large CSVs more efficiently
        text = df.to_string(index=False) # Avoid writing row index
    except FileNotFoundError:
         logger.error(f"CSV file not found: '{file_path}'")
         return {"text": "", "needs_ocr": False, "error": "File not found"}
    except Exception as e:
        logger.error(f"Error reading CSV file '{file_path}': {e}", exc_info=True)
        return {"text": "", "needs_ocr": False, "error": str(e)}
        
    logger.debug(f"Finished CSV extraction for '{file_path}'. Length: {len(text)}")
    return {"text": text.strip(), "needs_ocr": False}

def extract_text_from_json(file_path: str) -> Dict[str, Any]:
    """Extracts text content from a JSON file by pretty-printing."""
    logger.debug(f"Starting JSON extraction for: {file_path}")
    text = ""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Convert JSON object to a string representation
        # Consider alternative representations if structure is important (e.g., key-value pairs)
        text = json.dumps(data, indent=2)
    except FileNotFoundError:
         logger.error(f"JSON file not found: '{file_path}'")
         return {"text": "", "needs_ocr": False, "error": "File not found"}
    except json.JSONDecodeError as e:
         logger.error(f"Invalid JSON format in file '{file_path}': {e}")
         return {"text": "", "needs_ocr": False, "error": f"Invalid JSON: {e}"}
    except Exception as e:
        logger.error(f"Error reading JSON file '{file_path}': {e}", exc_info=True)
        return {"text": "", "needs_ocr": False, "error": str(e)}
        
    logger.debug(f"Finished JSON extraction for '{file_path}'. Length: {len(text)}")
    return {"text": text.strip(), "needs_ocr": False}

# --- Add extractors for other types (pptx, xlsx, html) here ---
# def extract_text_from_pptx(file_path: str) -> Dict[str, Any]: ...
# def extract_text_from_xlsx(file_path: str) -> Dict[str, Any]: ...
# def extract_text_from_html(file_path: str) -> Dict[str, Any]: ...

def extract_text(file_path: str, file_type: str) -> Dict[str, Any]:
    """Main extraction dispatcher based on file type."""
    logger.info(f"Dispatching extractor for file type '{file_type}' on file: {os.path.basename(file_path)}")
    
    extractor_map = {
        'pdf': extract_text_from_pdf,
        'docx': extract_text_from_docx,
        'text': extract_text_from_txt, # Handles .txt, .md
        'csv': extract_text_from_csv,
        'json': extract_text_from_json,
        # --- Add mappings for other types here --- #
        # 'pptx': extract_text_from_pptx,
        # 'xlsx': extract_text_from_xlsx,
        # 'html': extract_text_from_html,
    }

    extractor_func = extractor_map.get(file_type)
    
    if extractor_func:
        try:
            result = extractor_func(file_path)
            if "error" in result:
                 logger.warning(f"Extractor '{extractor_func.__name__}' reported error for '{file_path}': {result['error']}")
            return result
        except Exception as e:
             # Catch unexpected errors within the specific extractor call itself
             logger.error(f"Unexpected error in extractor '{extractor_func.__name__}' for '{file_path}': {e}", exc_info=True)
             return {"text": "", "needs_ocr": False, "error": f"Unexpected extractor error: {e}"}
    else:
        # This case should ideally not be reached if called from file_router with supported types
        logger.error(f"No extractor function mapped for supported type: '{file_type}' ('{file_path}')")
        return {"text": "", "needs_ocr": False, "error": f"Internal mapping error for type {file_type}"} 