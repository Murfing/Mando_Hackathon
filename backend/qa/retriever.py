import logging
from typing import List, Dict, Any

# Get the logger instance
logger = logging.getLogger(__name__)

# Assuming embedder.py handles model loading and embedding generation
from ..indexing.embedder import get_embeddings
# --- Import the Base class --- 
from ..indexing.vector_store import BaseVectorStore # Use BaseVectorStore for type hinting
# ---
# from ..indexing.vector_store import VectorStore # Using the placeholder for now
from ..utils.helpers import Timer

# TODO: Implement hybrid search (combining vector search with keyword matching)
# TODO: Add filtering capabilities based on metadata (e.g., document source)

# Update type hint to use BaseVectorStore
def retrieve_chunks(query: str, vector_store: BaseVectorStore, top_k: int = 5, filter_dict: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Retrieves the top_k most relevant document chunks for a given query,
    optionally applying metadata filters.

    Args:
        query: The user's question.
        vector_store: The initialized vector store instance (must implement BaseVectorStore methods).
        top_k: The number of chunks to retrieve.
        filter_dict: Optional dictionary for metadata filtering (e.g., {"source": "doc.pdf"}).
                     Support depends on the vector store implementation.

    Returns:
        A list of dictionaries, each representing a relevant chunk
        (including content, metadata, and score).
    """
    logger.info(f"Retrieving top {top_k} chunks for query: '{query[:50]}...'")
    if filter_dict:
         logger.info(f"Applying filter: {filter_dict}")

    # Check if a valid vector store object was passed
    if not isinstance(vector_store, BaseVectorStore):
         logger.error("Retrieval failed: Invalid or uninitialized vector store object provided.")
         return []
         
    if not query:
        logger.warning("Retrieval attempted with empty query.")
        return []

    # 1. Generate embedding for the query
    logger.debug(f"Generating embedding for query: '{query}'")
    with Timer(logger, name="Query embedding generation"):
        try:
            query_embedding_list = get_embeddings([query], task_type="RETRIEVAL_QUERY")
        except Exception as e:
            logger.error(f"Exception during query embedding generation: {e}", exc_info=True)
            query_embedding_list = None

    if query_embedding_list is None or not query_embedding_list:
        logger.error("Failed to generate query embedding. Cannot perform retrieval.")
        return []
    query_embedding = query_embedding_list[0]
    logger.debug(f"Generated query embedding with dimension: {len(query_embedding)}")

    # 2. Search the vector store
    logger.debug(f"Searching vector store for query '{query[:50]}...'")
    try:
        with Timer(logger, name="Vector store search"):
            # Pass the filter dictionary to the vector store's search method
            # The actual implementation (e.g., FAISSVectorStore) handles the search.
            results = vector_store.search(query_embedding, top_k=top_k, filter_dict=filter_dict)

        logger.info(f"Vector store search completed. Found {len(results)} candidate chunks.")
        # Optional: Add re-ranking logic here if needed
        return results
    except NotImplementedError:
         logger.error("The current vector store implementation does not support the 'search' method.", exc_info=False)
         return []
    except Exception as e:
        logger.error(f"Error during vector store search for query '{query[:50]}...': {e}", exc_info=True)
        return []

# --- Optional: Keyword Search Implementation (Placeholder) ---
# def keyword_search(query: str, documents: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
#     """ Placeholder for a simple keyword search (e.g., using BM25 or TF-IDF). """
#     # TODO: Implement keyword search logic
#     logger.debug("Keyword search not implemented.")
#     return []

# --- Optional: Hybrid Search Implementation (Placeholder) ---
# def hybrid_retrieve(query: str, vector_store: BaseVectorStore, top_k: int = 5, filter_dict: Dict[str, Any] = None) -> List[Dict[str, Any]]:
#     """ Combines vector search and keyword search results. """
#     logger.info(f"Performing hybrid retrieval for query: '{query[:50]}...'")
#     # Keyword search needs access to the text/metadata, potentially from the vector store or a separate source
#     # all_docs = vector_store.get_all_documents() # Hypothetical method
#
#     vector_results = retrieve_chunks(query, vector_store, top_k, filter_dict)
#     # keyword_results = keyword_search(query, all_docs, top_k) # Pass documents if available
#     keyword_results = [] # Placeholder
#
#     # TODO: Implement a strategy to combine and re-rank results (e.g., Reciprocal Rank Fusion)
#     logger.debug("Hybrid search combination logic not implemented.")
#     # Simple combination for now (may have duplicates)
#     combined = vector_results + keyword_results
#     # Deduplicate based on content or a unique ID
#     # Example using internal_id if available from vector store results
#     unique_results_dict = {}
#     for res in combined:
#         key = res.get('internal_id') or res.get('content', '') # Use ID or content as key
#         if key not in unique_results_dict:
#              unique_results_dict[key] = res
#     unique_results = list(unique_results_dict.values())
#
#     # TODO: Re-sort combined results based on a fusion score
#     logger.info(f"Hybrid search returning {len(unique_results)} unique results (combination/ranking not fully implemented).")
#     return unique_results[:top_k] # Return only top_k unique results for now