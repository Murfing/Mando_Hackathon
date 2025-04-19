import pytesseract
from PIL import Image, UnidentifiedImageError
import fitz # PyMuPDF for PDF image extraction
import io
import os
import logging

# Get the logger instance
logger = logging.getLogger(__name__)

# --- Configuration ---
# Attempt to get Tesseract path from environment variable first
TESSERACT_PATH = os.getenv("TESSERACT_CMD")
if TESSERACT_PATH:
    logger.info(f"Using Tesseract path from environment variable: {TESSERACT_PATH}")
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
else:
    logger.info("TESSERACT_CMD environment variable not set. Relying on system PATH for Tesseract.")
    # Add platform-specific checks or common paths if needed
    # Example for Windows default:
    # if os.name == 'nt' and not shutil.which('tesseract'): # Check if not in PATH
    #     default_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    #     if os.path.exists(default_path):
    #         logger.info(f"Tesseract not found in PATH, using default: {default_path}")
    #         pytesseract.pytesseract.tesseract_cmd = default_path


def ocr_image_object(image: Image.Image, image_description: str) -> str:
    """Performs OCR on a PIL Image object."""
    try:
        # Consider adding language options: lang='eng'
        text = pytesseract.image_to_string(image)
        logger.debug(f"OCR successful for {image_description}. Found {len(text)} chars.")
        return text
    except pytesseract.TesseractNotFoundError:
        logger.error("Tesseract command not found. Please install Tesseract and ensure it's in your PATH or set TESSERACT_CMD environment variable.", exc_info=False) # Only log error once potentially
        raise # Re-raise the error to stop processing
    except Exception as e:
        logger.error(f"Error performing OCR on {image_description}: {e}", exc_info=True)
        return ""

def ocr_image_file(image_path: str) -> str:
    """Performs OCR on a single image file path."""
    logger.debug(f"Performing OCR on image file: {image_path}")
    try:
        with Image.open(image_path) as img:
            return ocr_image_object(img, f"image file '{image_path}'")
    except FileNotFoundError:
        logger.error(f"Image file not found for OCR: {image_path}")
        return ""
    except UnidentifiedImageError:
        logger.error(f"Cannot identify image file (may be corrupt or unsupported format): {image_path}")
        return ""
    except Exception as e:
         logger.error(f"Error opening image file '{image_path}' for OCR: {e}", exc_info=True)
         return ""

def ocr_pdf(file_path: str) -> str:
    """Performs OCR on each page of a PDF, extracting images first."""
    logger.info(f"Performing page-by-page OCR on PDF: {file_path}")
    text = ""
    try:
        doc = fitz.open(file_path)
        num_pages = len(doc)
        logger.debug(f"Processing {num_pages} pages in PDF for OCR.")
        for page_num in range(num_pages):
            page_text = ""
            try:
                page = doc.load_page(page_num)
                # Render page to an image (pixmap)
                # Increase DPI for better OCR quality, but higher memory usage
                # Default is 96 DPI. Try 150 or 200 if needed.
                zoom = 2 # zoom factor (2 = 192 DPI)
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png") # Convert to PNG bytes
                
                with Image.open(io.BytesIO(img_bytes)) as img:
                    page_description = f"page {page_num + 1} of PDF '{os.path.basename(file_path)}'"
                    page_text = ocr_image_object(img, page_description)
                    
                text += page_text + "\n\n" # Add page break
            except Exception as page_err:
                logger.error(f"Error during OCR on page {page_num + 1} of PDF '{file_path}': {page_err}", exc_info=True)
                text += f"[OCR Error on Page {page_num + 1}]\n\n"
        doc.close()
    except Exception as e:
        logger.error(f"Error opening or processing PDF '{file_path}' for OCR: {e}", exc_info=True)
        return f"[OCR Failed for entire PDF: {e}]"
        
    logger.info(f"Finished PDF OCR for '{file_path}'. Total chars: {len(text)}")
    return text.strip()

def handle_ocr(file_path: str, file_type: str) -> str:
    """
    Determines the file type and calls the appropriate OCR function.
    This is typically called when initial extraction yields little/no text or for image types.
    """
    logger.info(f"OCR handler called for file: '{os.path.basename(file_path)}' (type: {file_type})")
    
    if file_type == 'image':
        return ocr_image_file(file_path)
    elif file_type == 'pdf':
        # This function is called when the extractor determined OCR is likely needed for the PDF
        return ocr_pdf(file_path)
    else:
        # This case should generally not be reached if called correctly from file_router
        logger.warning(f"OCR handler called for unexpected file type: '{file_type}' ('{file_path}'). No OCR performed.")
        return ""

# TODO: Add integration with cloud OCR services (Google Vision, AWS Textract) as alternatives or fallbacks. 