import os
import logging
from typing import Dict, Any
import io # ADDED for BytesIO
from PIL import Image # ADDED for reading image bytes

# Get the logger instance from the root logger configured in app.py
logger = logging.getLogger(__name__)

# Placeholder imports - replace with actual implementations
from .extractor import extract_text, extract_pdf_visuals
from .multimodal_processor import generate_summary_for_element
from .crawler import crawl_links
from ..indexing.embedder import embed_and_index_chunks, get_embeddings
from ..utils.helpers import Timer
from ..indexing.vector_store import BaseVectorStore

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

def process_file(file_path: str, vector_store: BaseVectorStore) -> Dict[str, Any]:
    """
    Routes the file for processing.
    - Extracts standard text and indexes it.
    - For PDFs, extracts images/tables, gets summaries via Gemini, and indexes summaries.
    - For Images, gets summary via Gemini and indexes it.

    Args:
        file_path: Path to the file to process.
        vector_store: The initialized vector store instance.

    Returns:
        A dictionary containing metadata about the processing (e.g., chunks count).
    """
    _, file_extension = os.path.splitext(file_path)
    file_type = SUPPORTED_EXTENSIONS.get(file_extension.lower())
    filename = os.path.basename(file_path)
    total_chunks_added = 0
    visual_elements_processed = 0
    visual_elements_failed = 0

    logger.info(f"Processing file: '{filename}' (Detected type: {file_type})")

    result_metadata = {"filename": filename, "file_type": file_type}

    if not file_type:
        logger.warning(f"Unsupported file type '{file_extension}' for file '{filename}'. Skipping.")
        return {"status": "skipped", "reason": f"Unsupported file type: {file_extension}", **result_metadata}

    try:
        extracted_content = None
        extraction_error = None

        # 1. Standard Text Extraction (for relevant types)
        if file_type in ['pdf', 'docx', 'csv', 'json', 'text', 'html']: # Exclude image type here
            logger.debug(f"Attempting standard text extraction for '{filename}' (type: {file_type}).")
            with Timer(logger, name=f"Standard text extraction for {filename}"):
                extracted_data = extract_text(file_path, file_type)
                extracted_content = extracted_data.get("text", "")
                extraction_error = extracted_data.get("error")
                char_count = len(extracted_content) if extracted_content else 0
                if extraction_error:
                    logger.warning(f"Standard extraction failed for '{filename}': {extraction_error}")
                else:
                    logger.info(f"Standard extraction complete for '{filename}'. Chars: {char_count}")

            # --- NEW 1.5: Optional Link Crawling ---
            ENABLE_LINK_CRAWLING = True # Set to False or getenv to disable
            crawled_content = "" # Initialize
            if ENABLE_LINK_CRAWLING and extracted_content and file_type in ['pdf', 'text', 'docx']: # Add other types like html if needed
                logger.info(f"Attempting link crawling within content of '{filename}'...")
                with Timer(logger, name=f"Link crawling for {filename}"):
                    try:
                        # Assuming crawl_links takes the text and returns crawled text
                        crawled_content = crawl_links(extracted_content)
                    except Exception as crawl_err:
                        logger.error(f"Link crawling failed for '{filename}': {crawl_err}", exc_info=True)
                        # Don't stop processing, just log the error

                if crawled_content:
                    logger.info(f"Adding {len(crawled_content)} chars from crawled links for '{filename}'.")
                    # Append crawled content to the original extracted content
                    extracted_content += "\n\n--- Crawled Link Content ---\n\n" + crawled_content
                else:
                    logger.info(f"No content retrieved from link crawling for '{filename}'.")
            # --- END Link Crawling ---

            # 2. Index Standard Text Chunks (if content exists)
            if extracted_content and extracted_content.strip():
                logger.info(f"Indexing standard text content for '{filename}'")
                with Timer(logger, name=f"Standard text indexing for {filename}"):
                    # Assuming embed_and_index_chunks handles chunking, embedding, and adding to store
                    # It needs to return the count of chunks added.
                    # We pass standard metadata here.
                    chunk_metadata = {'source': filename}
                    # ADDED: Inject content_type for tabular profiles
                    if file_type in ['csv', 'xlsx', 'xls']:
                        chunk_metadata['content_type'] = 'tabular_profile'
                        
                    indexing_result = embed_and_index_chunks(extracted_content, vector_store, chunk_metadata)
                    added_count = indexing_result.get('chunk_count', 0) # Extract the count, default to 0
                    total_chunks_added += added_count
                    logger.info(f"Indexed {added_count} standard text chunks for '{filename}'.")
            elif not extraction_error:
                logger.info(f"No standard text content extracted from '{filename}'. Skipping text indexing.")

        # 3. Visual Element Processing (PDFs and Images)
        visual_elements_to_process = []
        if file_type == 'pdf':
            logger.info(f"Extracting visual elements (images/tables) from PDF: '{filename}'")
            with Timer(logger, name=f"Visual element extraction for {filename}"):
                visual_elements_to_process = extract_pdf_visuals(file_path)
        elif file_type == 'image':
            logger.info(f"Preparing standalone image for processing: '{filename}'")
            try:
                with open(file_path, "rb") as f:
                    image_bytes = f.read()
                if image_bytes:
                    visual_elements_to_process = [{
                        'type': 'image',
                        'data': image_bytes,
                        'page_number': None,
                        'original_source': filename
                    }]
                else:
                    logger.warning(f"Could not read bytes from image file: '{filename}'")
            except Exception as img_read_err:
                logger.error(f"Error reading image file '{filename}': {img_read_err}", exc_info=True)

        # 4. Summarize and Index Visual Elements
        if visual_elements_to_process:
            logger.info(f"Processing {len(visual_elements_to_process)} visual elements for '{filename}'...")
            for element in visual_elements_to_process:
                with Timer(logger, name=f"Gemini summary for {element.get('type')} element ({filename} Pg:{element.get('page_number')})"):
                    summary = generate_summary_for_element(element)

                if summary:
                    visual_elements_processed += 1
                    # Embed and index the summary
                    try:
                        logger.debug(f"Embedding summary for visual element: {element['original_source']} ({element['type']}) Page: {element.get('page_number')}")
                        # Ensure embedding is a list of floats
                        embedding_list = get_embeddings([summary])[0]
                        if not isinstance(embedding_list, list):
                            embedding_list = embedding_list.tolist() # Convert numpy array if necessary

                        # Prepare metadata for the visual element's summary
                        metadata = {
                            'summary': summary, # Store the summary itself in metadata for potential display
                            'source_type': element['type'], # 'image' or 'table'
                            'original_source': element['original_source'],
                            'page_number': element.get('page_number') # Can be None for standalone images
                        }
                        
                        # Generate a unique ID for this visual summary chunk
                        unique_id = f"{element['original_source']}__{element['type']}__{element.get('page_number', 'None')}__summary"
                        
                        # Use add_documents with single-item lists
                        vector_store.add_documents(
                            texts=[summary], 
                            embeddings=[embedding_list], 
                            metadatas=[metadata], # Pass the prepared metadata dict within a list
                            ids=[unique_id]
                        )
                        total_chunks_added += 1 # Count each summary as one 'chunk'
                        logger.debug(f"Indexed summary for visual element: {metadata['original_source']} ({metadata['source_type']}) Page: {metadata.get('page_number')}")
                    except Exception as index_err:
                        visual_elements_failed += 1
                        logger.error(f"Failed to embed or index summary for visual element ({element['original_source']} - {element['type']}): {index_err}", exc_info=True)
                else:
                    visual_elements_failed += 1
                    logger.warning(f"Failed to generate summary for visual element ({element['original_source']} - {element['type']}). Skipping indexing.")
            logger.info(f"Finished processing visual elements for '{filename}'. Processed: {visual_elements_processed}, Failed: {visual_elements_failed}")

        # 5. Final Status Check
        if total_chunks_added == 0 and not extraction_error:
            # If standard extraction didn't fail but no text or visual summaries were indexed
            logger.warning(f"Completed processing for '{filename}', but no content was indexed (standard text or visual summaries). Check file content and Gemini processing logs.")
            return {"status": "skipped", "reason": "No content indexed", **result_metadata, "chunks_added": 0}
        elif extraction_error and total_chunks_added == 0:
            # If standard extraction failed AND no visual summaries were indexed
            logger.error(f"Processing failed entirely for '{filename}'. Extraction Error: {extraction_error}. No visual content indexed.")
            return {"status": "failed", "reason": f"Extraction failed: {extraction_error}", **result_metadata, "chunks_added": 0}

        # If *any* content was indexed (standard text or visual summaries)
        logger.info(f"Successfully finished processing '{filename}'. Total items indexed: {total_chunks_added}")
        return {"status": "processed", "chunks_added": total_chunks_added, **result_metadata}

    except Exception as e:
        logger.error(f"Unhandled error during processing of file '{filename}': {e}", exc_info=True)
        return {"status": "failed", "reason": f"Unhandled processing error: {e}", **result_metadata, "chunks_added": total_chunks_added} 