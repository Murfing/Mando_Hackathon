import os
import logging
from typing import List, Dict, Any, Tuple
import numpy as np

# Get the logger instance
logger = logging.getLogger(__name__)

# --- Choose and import your vector store library ---
# Option 1: FAISS (CPU version recommended for broader compatibility initially)
try:
    import faiss
    FAISS_AVAILABLE = True
    logger.info("FAISS library found.")
except ImportError:
    FAISS_AVAILABLE = False
    logger.warning("FAISS library not found. FAISSVectorStore will not be usable.")
    faiss = None # Define faiss as None if not available

# Option 2: ChromaDB
# try:
#     import chromadb
#     from chromadb.utils import embedding_functions
#     CHROMA_AVAILABLE = True
#     logger.info("ChromaDB library found.")
# except ImportError:
#     CHROMA_AVAILABLE = False
#     logger.warning("ChromaDB library not found. ChromaVectorStore will not be usable.")
#     chromadb = None

# --- Base Class (Optional but good practice) ---
class BaseVectorStore:
    def add_documents(self, texts: List[str], embeddings: List[List[float]], metadatas: List[Dict[str, Any]], ids: List[str]):
        raise NotImplementedError

    def search(self, query_embedding: List[float], top_k: int = 5, filter_dict: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError
        
    def save(self):
         # May not be needed for all stores (like cloud-based or auto-persisting)
         logger.info(f"Save operation called on {self.__class__.__name__}")
         pass
         
    def load(self):
         # May not be needed for all stores
         logger.info(f"Load operation called on {self.__class__.__name__}")
         pass

# --- FAISS Implementation ---
class FAISSVectorStore(BaseVectorStore):
    """
    A Vector Store implementation using FAISS.
    Manages an index and associated metadata.
    NOTE: This basic implementation stores metadata in memory. For large datasets,
    consider a separate persistent store (DB, file) for metadata, keyed by FAISS index ID.
    """
    def __init__(self, dimension: int, index_path: str = "vector_store.faiss", metadata_path: str = "vector_store_meta.json"):
        if not FAISS_AVAILABLE:
            raise ImportError("FAISS library is required to use FAISSVectorStore but it's not installed.")
            
        self.dimension = dimension
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.index = None
        # Use a dictionary for metadata mapping: {faiss_index_id: {metadata..., text:...}}
        self.doc_metadata_map: Dict[int, Dict[str, Any]] = {}
        self._initialize_or_load()

    def _initialize_or_load(self):
        if os.path.exists(self.index_path) and os.path.exists(self.metadata_path):
            try:
                self.load()
            except Exception as e:
                logger.warning(f"Failed to load existing FAISS index/metadata from '{self.index_path}'/'{self.metadata_path}': {e}. Creating new index.", exc_info=True)
                self._create_new_index()
        else:
            logger.info("No existing FAISS index/metadata found. Creating new ones.")
            self._create_new_index()

    def _create_new_index(self):
        logger.info(f"Creating new FAISS base index (IndexFlatL2) with dimension {self.dimension}")
        base_index = faiss.IndexFlatL2(self.dimension)
        logger.info("Wrapping base index with IndexIDMap.")
        # Assign the wrapped index directly
        new_index = faiss.IndexIDMap(base_index)
        self.index = new_index # Be explicit about assignment
        logger.info(f"Successfully created index of type: {type(self.index)}")
        self.doc_metadata_map = {}

    def add_documents(self, texts: List[str], embeddings: List[List[float]], metadatas: List[Dict[str, Any]], ids: List[str]):
        if not self.index:
            logger.error("FAISS index is not initialized. Cannot add documents.")
            raise RuntimeError("FAISS index not initialized.")

        # --- Add assertion to check index type --- 
        assert isinstance(self.index, faiss.IndexIDMap), f"Index type mismatch! Expected IndexIDMap, got {type(self.index)}"
        # --- 

        if not (len(texts) == len(embeddings) == len(metadatas) == len(ids)):
            raise ValueError("Mismatch in lengths of texts, embeddings, metadatas, or ids.")

        if not embeddings:
            logger.warning("Received empty list of embeddings. Nothing to add.")
            return

        embeddings_np = np.array(embeddings, dtype='float32')
        if embeddings_np.shape[1] != self.dimension:
            logger.error(f"Embedding dimension mismatch. Index expects {self.dimension}, got {embeddings_np.shape[1]}")
            raise ValueError(f"Embedding dimension mismatch: expected {self.dimension}, got {embeddings_np.shape[1]}")

        start_id = self.index.ntotal
        # --- Ensure IDs are np.int64 --- 
        faiss_ids = np.arange(start_id, start_id + len(texts), dtype=np.int64)
        # --- 

        logger.info(f"Adding {len(texts)} documents to FAISS index (Start ID: {start_id}) using IDs of type {faiss_ids.dtype}...")
        
        try:
             # This is the call that previously failed
             self.index.add_with_ids(embeddings_np, faiss_ids)
        except RuntimeError as e:
             logger.error(f"FAISS add_with_ids failed: {e}")
             logger.error(f"Index type at time of error: {type(self.index)}") # Log type if error occurs
             raise # Re-raise the error
        except Exception as e:
             logger.error(f"Unexpected error during FAISS add_with_ids: {e}", exc_info=True)
             raise

        # Store metadata mapped by the FAISS ID
        for i, faiss_id in enumerate(faiss_ids):
            doc_id = int(faiss_id) # Ensure key is int
            self.doc_metadata_map[doc_id] = {
                "content": texts[i],
                "metadata": metadatas[i],
                "internal_id": ids[i]
            }
        logger.info(f"Added {len(texts)} documents. Index size now: {self.index.ntotal}")

    def search(self, query_embedding: List[float], top_k: int = 5, filter_dict: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        if not self.index:
            logger.error("FAISS index is not initialized. Cannot perform search.")
            return []
        if self.index.ntotal == 0:
             logger.warning("Search attempted on an empty FAISS index.")
             return []
             
        query_np = np.array([query_embedding], dtype='float32')
        if query_np.shape[1] != self.dimension:
            logger.error(f"Query embedding dimension mismatch. Index expects {self.dimension}, got {query_np.shape[1]}")
            return []
            
        # TODO: Implement filtering for FAISS. This is complex.
        # Requires either searching more results (k * factor) and filtering afterwards,
        # or using more advanced FAISS indexing strategies with metadata support if available,
        # or integrating with a metadata store that can pre-filter IDs.
        if filter_dict:
            logger.warning("FAISS filtering is not implemented in this basic example. Filter will be ignored.")
            # Example: Increase k and filter post-search (inefficient for large k)
            # search_k = top_k * 5 
        else:
            search_k = top_k

        logger.debug(f"Searching FAISS index for top {search_k} results.")
        distances, faiss_ids = self.index.search(query_np, search_k)
        
        results = []
        if faiss_ids.size == 0:
            logger.info("FAISS search returned no results.")
            return []
            
        # faiss_ids[0] contains the array of result IDs
        logger.debug(f"FAISS search raw results - Distances: {distances[0]}, IDs: {faiss_ids[0]}")
        for i, doc_id in enumerate(faiss_ids[0]):
            if doc_id != -1: # FAISS returns -1 if fewer than k results are found
                 doc_info = self.doc_metadata_map.get(int(doc_id))
                 if doc_info:
                     # TODO: Apply post-search filtering here if filter_dict was provided
                     results.append({
                         "content": doc_info['content'], 
                         "metadata": doc_info['metadata'], 
                         "score": float(distances[0][i]), # Lower L2 distance is better
                         "internal_id": doc_info.get('internal_id') # Retrieve original ID
                     })
                 else:
                     logger.warning(f"FAISS returned ID {doc_id} but it was not found in the metadata map.")
                     
        logger.info(f"FAISS search completed. Found {len(results)} matching results after processing.")
        return results[:top_k] # Ensure we only return top_k after potential filtering

    def save(self):
        import json # Local import
        if not self.index:
            logger.error("Cannot save: FAISS index not initialized.")
            return
            
        logger.info(f"Saving FAISS index to: {self.index_path}")
        faiss.write_index(self.index, self.index_path)
        
        logger.info(f"Saving metadata map ({len(self.doc_metadata_map)} items) to: {self.metadata_path}")
        try:
            with open(self.metadata_path, 'w', encoding='utf-8') as f:
                json.dump(self.doc_metadata_map, f, ensure_ascii=False, indent=2)
            logger.info("FAISS index and metadata saved successfully.")
        except TypeError as e:
             logger.error(f"Failed to serialize metadata to JSON: {e}. Ensure metadata is JSON serializable.", exc_info=True)
             # Consider deleting the potentially partially saved JSON or index file?
        except Exception as e:
             logger.error(f"Failed to save metadata map: {e}", exc_info=True)

    def load(self):
        import json # Local import
        if not os.path.exists(self.index_path):
             logger.error(f"Cannot load FAISS index: File not found at '{self.index_path}'")
             raise FileNotFoundError(f"FAISS index file not found: {self.index_path}")
        if not os.path.exists(self.metadata_path):
             logger.error(f"Cannot load metadata: File not found at '{self.metadata_path}'")
             raise FileNotFoundError(f"FAISS metadata file not found: {self.metadata_path}")
             
        logger.info(f"Loading FAISS index from: {self.index_path}")
        self.index = faiss.read_index(self.index_path)
        logger.info(f"FAISS index loaded. Index size: {self.index.ntotal}, Dimension: {self.index.d}")
        if self.index.d != self.dimension:
             logger.warning(f"Loaded FAISS index dimension ({self.index.d}) differs from configured dimension ({self.dimension}).")
             # Decide how to handle: error out, reconfigure, etc. For now, log warning.
             self.dimension = self.index.d # Use loaded dimension

        logger.info(f"Loading metadata map from: {self.metadata_path}")
        with open(self.metadata_path, 'r', encoding='utf-8') as f:
             # Convert string keys back to integers after loading from JSON
             loaded_map = json.load(f)
             self.doc_metadata_map = {int(k): v for k, v in loaded_map.items()}
        logger.info(f"Metadata map loaded successfully ({len(self.doc_metadata_map)} items).")
        
        # Sanity check
        if self.index.ntotal != len(self.doc_metadata_map):
             logger.warning(f"Loaded index size ({self.index.ntotal}) does not match metadata count ({len(self.doc_metadata_map)}). Metadata might be incomplete or corrupt.")

# --- ChromaDB Implementation (Placeholder) ---
# class ChromaVectorStore(BaseVectorStore):
#     def __init__(self, dimension: int, collection_name: str = "documents", persist_path: str = "./chroma_db"):
#         if not CHROMA_AVAILABLE:
#             raise ImportError("ChromaDB library is required to use ChromaVectorStore but it's not installed.")
#         
#         self.dimension = dimension # Store expected dimension for validation
#         self.persist_path = persist_path
#         self.collection_name = collection_name
#         
#         logger.info(f"Initializing ChromaDB client. Persistence path: {os.path.abspath(persist_path)}")
#         self.client = chromadb.PersistentClient(path=self.persist_path)
#         
#         # Get or create the collection
#         # TODO: How to handle embedding function if model changes? Store model name in metadata?
#         # For now, assume the global embedder.MODEL_NAME is consistent.
#         from ..indexing.embedder import MODEL_NAME as embedder_model_name
#         self.st_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=embedder_model_name)
#         
#         logger.info(f"Getting or creating ChromaDB collection: '{collection_name}'")
#         # Note: ChromaDB calculates embeddings if not provided AND an embedding function is set.
#         # If we provide embeddings calculated externally (as we do), we might not need to set embedding_function here,
#         # but it's needed for querying by text later if desired.
#         self.collection = self.client.get_or_create_collection(
#             name=self.collection_name,
#             embedding_function=self.st_ef, 
#             metadata={"hnsw:space": "cosine"} # Example: Use cosine distance
#         )
#         logger.info(f"ChromaDB collection '{collection_name}' ready. Item count: {self.collection.count()}")
# 
#     def add_documents(self, texts: List[str], embeddings: List[List[float]], metadatas: List[Dict[str, Any]], ids: List[str]):
#         if not (len(texts) == len(embeddings) == len(metadatas) == len(ids)):
#             raise ValueError("Mismatch in lengths of texts, embeddings, metadatas, or ids.")
#         if not embeddings:
#              logger.warning("Received empty list of embeddings for ChromaDB. Nothing to add.")
#              return
#              
#         # Validate embedding dimension (optional but recommended)
#         first_embedding_dim = len(embeddings[0])
#         if first_embedding_dim != self.dimension:
#              logger.error(f"Embedding dimension mismatch for ChromaDB. Configured for {self.dimension}, got {first_embedding_dim}")
#              raise ValueError(f"Embedding dimension mismatch: expected {self.dimension}, got {first_embedding_dim}")
#              
#         logger.info(f"Adding {len(ids)} documents to ChromaDB collection '{self.collection_name}'")
#         try:
#             # Chroma handles batching internally
#             self.collection.add(
#                 embeddings=embeddings, 
#                 documents=texts,
#                 metadatas=metadatas,
#                 ids=ids
#             )
#             logger.info(f"Successfully added {len(ids)} documents. Collection count now: {self.collection.count()}")
#             # Persist changes (though PersistentClient often handles this automatically)
#             # self.save()
#         except Exception as e:
#             # TODO: ChromaDB might have more specific exceptions to catch
#             logger.error(f"Error adding documents to ChromaDB collection '{self.collection_name}': {e}", exc_info=True)
#             raise
# 
#     def search(self, query_embedding: List[float], top_k: int = 5, filter_dict: Dict[str, Any] = None) -> List[Dict[str, Any]]:
#         logger.debug(f"Searching ChromaDB collection '{self.collection_name}' for top {top_k} results.")
#         
#         # Construct the 'where' filter if provided
#         # See ChromaDB docs for filter operators: $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin
#         # Example: filter_dict = {"source": "some_document.pdf"} -> where={"source": "some_document.pdf"}
#         # Example: filter_dict = {"year": {"$gte": 2022}} -> where={"year": {"$gte": 2022}}
#         where_filter = filter_dict if filter_dict else None
#         if where_filter:
#              logger.debug(f"Applying search filter: {where_filter}")
#         
#         try:
#             query_results = self.collection.query(
#                 query_embeddings=[query_embedding], # Must be a list of embeddings
#                 n_results=top_k,
#                 where=where_filter, # Apply metadata filter
#                 include=["documents", "metadatas", "distances"] # Request needed fields
#             )
#         except Exception as e:
#              # TODO: Catch more specific ChromaDB exceptions
#              logger.error(f"Error querying ChromaDB collection '{self.collection_name}': {e}", exc_info=True)
#              return []
# 
#         results = []
#         # ChromaDB returns results for each query embedding (we only have one)
#         if query_results and query_results.get('ids') and query_results['ids'][0]:
#             num_results = len(query_results['ids'][0])
#             logger.info(f"ChromaDB search returned {num_results} raw results.")
#             for i in range(num_results):
#                 # Handle potential None values if fields are missing in results
#                 doc_id = query_results['ids'][0][i]
#                 doc_content = query_results['documents'][0][i] if query_results.get('documents') else None
#                 doc_meta = query_results['metadatas'][0][i] if query_results.get('metadatas') else None
#                 doc_dist = query_results['distances'][0][i] if query_results.get('distances') else None
#                     
#                 results.append({
#                     "internal_id": doc_id,
#                     "content": doc_content,
#                     "metadata": doc_meta,
#                     "score": float(doc_dist) if doc_dist is not None else None # Lower distance is better for cosine/L2
#                 })
#         else:
#             logger.info("ChromaDB search returned no results.")
#             
#         return results
# 
#     def save(self):
#         # For PersistentClient, changes are often saved automatically.
#         # Explicitly calling persist can ensure data is written.
#         logger.info(f"Explicitly persisting ChromaDB client for path: {self.persist_path}")
#         try:
#              self.client.persist()
#              logger.info(f"ChromaDB data persisted successfully.")
#         except Exception as e:
#              logger.error(f"Error persisting ChromaDB data: {e}", exc_info=True)
# 
#     def load(self):
#         # Loading happens implicitly during __init__ with PersistentClient
#         logger.info("ChromaDB PersistentClient loads data on initialization.")
#         pass

# --- Selector Function (Example) ---
# Choose which vector store implementation to use
# Could be based on environment variable or configuration

VECTOR_STORE_TYPE = os.getenv("VECTOR_STORE_TYPE", "FAISS").upper()

def get_vector_store(dimension: int, path: str, **kwargs) -> BaseVectorStore:
    logger.info(f"Attempting to get vector store of type: {VECTOR_STORE_TYPE}")
    if VECTOR_STORE_TYPE == "FAISS":
        if not FAISS_AVAILABLE:
             raise ImportError("FAISS vector store requested but library is not available.")
        # Construct paths for FAISS data and metadata
        base_path = path.replace(".faiss", "") # Allow passing base name
        index_path = base_path + ".faiss"
        metadata_path = base_path + "_meta.json"
        logger.info(f"Initializing FAISSVectorStore with index='{index_path}', meta='{metadata_path}'")
        return FAISSVectorStore(dimension=dimension, index_path=index_path, metadata_path=metadata_path)
    # elif VECTOR_STORE_TYPE == "CHROMA":
    #     if not CHROMA_AVAILABLE:
    #         raise ImportError("ChromaDB vector store requested but library is not available.")
    #     collection_name = kwargs.get("collection_name", "documents")
    #     # Chroma uses a directory path for persistence
    #     persist_directory = path if os.path.isdir(path) else os.path.dirname(path)
    #     logger.info(f"Initializing ChromaVectorStore with persist_path='{persist_directory}', collection='{collection_name}'")
    #     return ChromaVectorStore(dimension=dimension, persist_path=persist_directory, collection_name=collection_name)
    else:
        raise ValueError(f"Unsupported VECTOR_STORE_TYPE: {VECTOR_STORE_TYPE}. Choose FAISS or CHROMA (if enabled)." )

# Replace the placeholder VectorStore in app.py with a call to this function:
# from .indexing.vector_store import get_vector_store
# vector_store = get_vector_store(dimension=VECTOR_DIMENSION, path=VECTOR_DB_PATH)

# --- Old Placeholder Class (Remove or keep for reference) ---
# class VectorStore:
#     ...