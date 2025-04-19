import os
import logging
from typing import Dict, Any

# Get the logger instance from the root logger configured in app.py
logger = logging.getLogger(__name__)

# Placeholder imports - replace with actual implementations
from .extractor import extract_text
from .ocr_handler import handle_ocr
from .crawler import crawl_links
from ..indexing.embedder import embed_and_index_chunks # Assuming this function handles chunking, embedding, and indexing
from ..utils.helpers import Timer

SUPPORTED_EXTENSIONS = {
    '.pdf': 'pdf',
    '.docx': 'docx',
    '.pptx': 'pptx',
    '.xlsx': 'xlsx',
    '.csv': 'csv',
    '.json': 'json',
    '.txt': 'text',
    '.md': 'text', # Added markdown as text
    '.html': 'html',
    '.jpg': 'image',
    '.jpeg': 'image',
    '.png': 'image',
    '.tiff': 'image',
    '.bmp': 'image',
    '.gif': 'image',
    # Add more as needed
}

def process_file(file_path: str, vector_store: Any) -> Dict[str, Any]:
    """
    Routes the file to the appropriate processing module based on its extension.
    Orchestrates extraction, OCR (if needed), chunking, embedding, and indexing.

    Args:
        file_path: Path to the file to process.
        vector_store: The initialized vector store instance.

    Returns:
        A dictionary containing metadata about the processing (e.g., chunks count).
    """
    _, file_extension = os.path.splitext(file_path)
    file_type = SUPPORTED_EXTENSIONS.get(file_extension.lower())
    filename = os.path.basename(file_path)

    logger.info(f"Processing file: '{filename}' (Detected type: {file_type})")

    extracted_content = None
    needs_ocr = False
    result_metadata = {"filename": filename, "file_type": file_type}

    if not file_type:
        logger.warning(f"Unsupported file type '{file_extension}' for file '{filename}'. Skipping.")
        return {"status": "skipped", "reason": f"Unsupported file type: {file_extension}"}

    try:
        # 1. Extraction
        logger.debug(f"Attempting extraction for '{filename}' (type: {file_type}).")
        with Timer(logger, name=f"Extraction for {filename}"):
            if file_type in ['pdf', 'docx', 'pptx', 'xlsx', 'csv', 'json', 'text', 'html']:
                extracted_data = extract_text(file_path, file_type)
                extracted_content = extracted_data.get("text", "")
                needs_ocr = extracted_data.get("needs_ocr", False)
                char_count = len(extracted_content) if extracted_content else 0
                logger.info(f"Extraction complete for '{filename}'. Chars: {char_count}, Needs OCR: {needs_ocr}")
                # TODO: Handle extracted tables, images separately if needed

            elif file_type == 'image':
                needs_ocr = True # Images always need OCR
                logger.info(f"File '{filename}' identified as image, requires OCR.")
            else:
                 # This case should not be reached due to the initial check, but good practice
                 logger.error(f"No extractor available for file type: {file_type} ('{filename}'). This should not happen.")
                 return {"status": "skipped", "reason": f"Internal error: No extractor for supported type {file_type}"}

        # 2. OCR (if needed)
        if needs_ocr:
            logger.info(f"Performing OCR on: '{filename}'")
            with Timer(logger, name=f"OCR for {filename}"):
                ocr_text = handle_ocr(file_path, file_type) # Pass file_type for context
            ocr_char_count = len(ocr_text) if ocr_text else 0
            logger.info(f"OCR complete for '{filename}'. Added Chars: {ocr_char_count}")
            # Combine OCR text with any previously extracted text (e.g., from PDF metadata)
            if extracted_content and ocr_text:
                extracted_content = extracted_content + "\n\n--- OCR Text ---\n\n" + ocr_text
            elif ocr_text:
                extracted_content = ocr_text
            else:
                 logger.warning(f"OCR was flagged for '{filename}' but returned no text.")
                 # Content might still exist from initial extraction, proceed if so

        if not extracted_content or not extracted_content.strip():
             logger.warning(f"No content could be extracted or generated via OCR from '{filename}'. Skipping indexing.")
             return {"status": "skipped", "reason": "No content extracted", **result_metadata}

        # 3. Link Crawling (Optional)
        # Be cautious enabling this - can significantly increase processing time and complexity.
        should_crawl = False # Set to True to enable
        if should_crawl and file_type in ['text', 'html', 'pdf']: # Only crawl links in text-based formats
            logger.info(f"Attempting link crawling within content of '{filename}'")
            with Timer(logger, name=f"Crawling links in {filename}"):
                crawled_content = crawl_links(extracted_content)
            if crawled_content:
                logger.info(f"Adding {len(crawled_content)} chars from crawled links for '{filename}'")
                extracted_content += "\n\n--- Crawled Content ---\n\n" + crawled_content

        # 4. Chunking, Embedding & Indexing
        logger.info(f"Starting indexing process for content from: '{filename}'")
        if vector_store is None:
             # This check is also in app.py, but good to have defence in depth
             logger.error("Vector store not available during processing of '{filename}'. Skipping indexing.")
             return {"status": "processed_no_index", "reason": "Vector store not available", **result_metadata}

        # Metadata for chunks
        # Ensure metadata is serializable if needed by the vector store
        base_metadata = {"source": filename, "original_path": file_path, "file_type": file_type}

        # This function should handle chunking, embedding, and adding to the store
        with Timer(logger, name=f"Embedding and Indexing for {filename}"):
             indexing_result = embed_and_index_chunks(extracted_content, vector_store, base_metadata)

        chunk_count = indexing_result.get("chunk_count", 0)
        if chunk_count > 0:
            logger.info(f"Successfully indexed {chunk_count} chunks for: '{filename}'")
            final_status = "indexed"
        else:
            logger.warning(f"Indexing process completed but added 0 chunks for: '{filename}'. Result: {indexing_result}")
            final_status = indexing_result.get("status", "indexing_failed") # Use status from embedder if available
        
        # Merge results
        result_metadata.update(indexing_result)
        result_metadata["status"] = final_status
        return result_metadata

    except Exception as e:
        logger.error(f"Unhandled exception during processing of file '{filename}': {e}", exc_info=True)
        # Ensure a consistent return format on failure
        result_metadata["status"] = "failed"
        result_metadata["error"] = str(e)
        return result_metadata 