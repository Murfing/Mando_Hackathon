import google.generativeai as genai
import logging
import time
import os
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional

# --- Import Timer --- 
from ..utils.helpers import Timer
# --- 

# Get the logger instance
logger = logging.getLogger(__name__)

# --- Load API Key (Ensure it's loaded, though app.py/answer_generator might also load it) ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

# --- Configuration ---
# Use the standard Gemini embedding model
# Other options might exist, check Gemini documentation
EMBEDDING_MODEL_NAME = "models/embedding-001"
# Dimension for models/embedding-001 is 768
EMBEDDING_DIMENSION = 768
CHUNK_SIZE = 500  # Max characters per chunk (tune based on content)
CHUNK_OVERLAP = 50 # Characters overlap between chunks (helps context)
# Gemini API has limits on requests per minute, batching might need delays or careful handling
# For simplicity, embedding one by one initially, but batching is possible.
# Batch size limit for embed_content is often 100.
EMBEDDING_BATCH_SIZE = 100

# --- Configure Gemini API Client --- 
# This happens globally when the module loads.
# Consider passing a configured client instance if preferred.
gemini_initialized = False
if not API_KEY:
    logger.error(f"GEMINI_API_KEY not found. {EMBEDDING_MODEL_NAME} embedding will not work.")
else:
    try:
        genai.configure(api_key=API_KEY)
        logger.info(f"Gemini API configured successfully for embeddings.")
        gemini_initialized = True
    except Exception as e:
        logger.error(f"Error configuring Gemini API: {e}", exc_info=True)

def get_embedding_dimension() -> int | None:
    """Returns the dimension of the configured Gemini embedding model."""
    # Currently hardcoded based on model name
    if EMBEDDING_MODEL_NAME == "models/embedding-004":
        return 768
    logger.warning(f"Unknown embedding dimension for model: {EMBEDDING_MODEL_NAME}")
    return None # Or raise an error

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Splits text into overlapping chunks."""
    if not isinstance(text, str) or not text.strip():
        logger.warning(f"Input to chunk_text is not a non-empty string (type: {type(text)}). Returning empty list.")
        return []
    
    logger.debug(f"Chunking text of length {len(text)} with chunk_size={chunk_size}, overlap={chunk_overlap}")
    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        next_start = start + chunk_size - chunk_overlap
        if next_start <= start:
            logger.warning(f"Chunk overlap ({chunk_overlap}) >= chunk size ({chunk_size}). Stopping chunking.")
            break
        if next_start >= text_len:
            break
        start = next_start
        
    logger.debug(f"Generated {len(chunks)} chunks.")
    return chunks

def get_embeddings(texts: List[str], task_type: str = "RETRIEVAL_DOCUMENT", batch_size: int = EMBEDDING_BATCH_SIZE) -> Optional[List[List[float]]]:
    """Generates embeddings for a list of text chunks using Gemini API.

    Args:
        texts: A list of strings to embed.
        task_type: The task type for the embedding (e.g., "RETRIEVAL_DOCUMENT", "RETRIEVAL_QUERY").
        batch_size: How many texts to send in each API request.

    Returns:
        A list of embeddings (each a list of floats), or None if an error occurs.
    """
    if not gemini_initialized:
        logger.error("Cannot generate embeddings: Gemini API not initialized.")
        return None
    if not texts:
        logger.warning("Input to get_embeddings is an empty list.")
        return []
    if not all(isinstance(t, str) for t in texts):
        logger.error("Invalid input to get_embeddings: List must contain only strings.")
        return None

    logger.info(f"Generating Gemini embeddings for {len(texts)} text chunks (task: {task_type}, batch size: {batch_size})...")
    all_embeddings = []
    num_batches = (len(texts) + batch_size - 1) // batch_size

    try:
        for i in range(num_batches):
            batch_start = i * batch_size
            batch_end = batch_start + batch_size
            batch_texts = texts[batch_start:batch_end]
            
            if not batch_texts: # Should not happen with calculation above, but safety check
                continue
                
            logger.debug(f"Processing batch {i+1}/{num_batches} ({len(batch_texts)} texts)")
            # Make the Gemini API call for the batch
            # Handle potential titles if your data includes them, otherwise just use content
            # For simplicity, we use the text directly as content here.
            response = genai.embed_content(
                model=EMBEDDING_MODEL_NAME,
                content=batch_texts,
                task_type=task_type
            )
            
            batch_embeddings = response.get('embedding')
            if not batch_embeddings or len(batch_embeddings) != len(batch_texts):
                logger.error(f"Gemini embedding API returned unexpected result for batch {i+1}. Expected {len(batch_texts)} embeddings, got {len(batch_embeddings) if batch_embeddings else 'None'}. Response: {response}")
                # Decide whether to fail all or just skip batch
                return None # Fail all for now
                
            all_embeddings.extend(batch_embeddings)
            
            # Optional: Add a small delay between batches if hitting rate limits
            # if i < num_batches - 1:
            #     time.sleep(0.5) 
            
        logger.info(f"Successfully generated {len(all_embeddings)} Gemini embeddings.")
        return all_embeddings

    except Exception as e:
        logger.error(f"Error generating Gemini embeddings: {e}", exc_info=True)
        # Handle specific Gemini API errors if possible
        return None

def embed_and_index_chunks(text: str, vector_store: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Chunks text, generates Gemini embeddings (document type), and adds them to the vector store.
    Returns metadata about the process, including chunk count or errors.
    """
    filename = metadata.get("source", "unknown_file")
    logger.info(f"Starting Gemini embedding and indexing for '{filename}'")
    result = {"status": "started", "chunk_count": 0}

    if not vector_store:
        logger.error(f"Vector store is not initialized. Cannot index '{filename}'")
        result["status"] = "failed"
        result["error"] = "Vector store not initialized"
        return result
        
    if not gemini_initialized:
        logger.error(f"Gemini API not initialized. Cannot index '{filename}'")
        result["status"] = "failed"
        result["error"] = "Gemini API not initialized"
        return result

    try:
        # 1. Chunk the text
        with Timer(logger, name=f"Chunking for {filename}"):
            list_of_text_chunks = chunk_text(text)
        result["text_length"] = len(text)
        result["chunk_count"] = len(list_of_text_chunks)
        
        if not list_of_text_chunks:
            logger.warning(f"No text chunks generated for '{filename}'. Nothing to index.")
            result["status"] = "skipped_no_chunks"
            return result
        
        logger.info(f"Generated {len(list_of_text_chunks)} chunks for '{filename}'. Proceeding with embedding.")

        # 2. Generate embeddings (use RETRIEVAL_DOCUMENT task type)
        with Timer(logger, name=f"Gemini embedding {len(list_of_text_chunks)} chunks for {filename}"):
            embeddings = get_embeddings(list_of_text_chunks, task_type="RETRIEVAL_DOCUMENT", batch_size=EMBEDDING_BATCH_SIZE)
        
        if embeddings is None or len(embeddings) != len(list_of_text_chunks):
            logger.error(f"Failed to generate Gemini embeddings for '{filename}'. Expected {len(list_of_text_chunks)}, got {len(embeddings) if embeddings else 'None'}.")
            result["status"] = "failed_embedding"
            result["error"] = "Gemini embedding generation failed or produced incorrect count"
            return result
        logger.debug(f"Successfully generated {len(embeddings)} Gemini embeddings for '{filename}'.")

        # 3. Prepare data for vector store (IDs and metadata)
        prepared_metadatas = []
        prepared_ids = []
        for i, chunk_content in enumerate(list_of_text_chunks):
            chunk_meta = metadata.copy()
            chunk_meta['chunk_index'] = i
            chunk_meta['chunk_length'] = len(chunk_content)
            prepared_metadatas.append(chunk_meta)
            prepared_ids.append(f"{filename}_chunk_{i}")

        logger.debug(f"Prepared {len(prepared_ids)} IDs and metadata objects for vector store.")

        # 4. Add to vector store
        logger.info(f"Adding {len(list_of_text_chunks)} chunks with Gemini embeddings to vector store for '{filename}'")
        with Timer(logger, name=f"Vector store add_documents for {filename}"):
            vector_store.add_documents(texts=list_of_text_chunks, embeddings=embeddings, metadatas=prepared_metadatas, ids=prepared_ids)
            
        logger.info(f"Successfully added {len(list_of_text_chunks)} chunks to vector store for '{filename}'")
        result["status"] = "indexed"
        # chunk_count already set

    except Exception as e:
        logger.error(f"Error during Gemini embedding or indexing process for '{filename}': {e}", exc_info=True)
        result["status"] = "failed"
        result["error"] = f"Error during indexing: {e}"
        # chunk_count might be partially set, keep it for info

    logger.info(f"Finished embedding and indexing for '{filename}'. Final status: {result['status']}, Chunks indexed: {result.get('chunk_count', 0)}")
    return result

# TODO: Consider adding functions for handling different embedding models (OpenAI, etc.)
# TODO: Explore more sophisticated chunking strategies (e.g., sentence splitting, semantic chunking) 