import logging
import os
import shutil
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

# Configure logging AT THE START
from .utils.helpers import setup_logging, Timer, sanitize_filename
logger = setup_logging(level_str=os.getenv("LOG_LEVEL", "INFO"))

# --- Calculate script's directory --- 
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# Import other components AFTER logging is set up
from .ingestion.file_router import process_file
from .indexing.vector_store import get_vector_store, BaseVectorStore
from .indexing.embedder import EMBEDDING_MODEL_NAME, get_embedding_dimension
from .qa.retriever import retrieve_chunks
from .qa.answer_generator import generate_answer
# Import visualizer functions (Placeholders)
from .visualizer import analyze_github_repo, analyze_pdf_visual

# Configuration (consider moving to a dedicated config file/module)
# --- Define paths relative to app.py location --- 
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(APP_DIR, "data", "uploads"))
VISUALIZER_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "visualizer_temp") # Subdir for temporary visualizer PDFs
PROCESSED_DIR = os.getenv("PROCESSED_DIR", os.path.join(APP_DIR, "data", "processed"))
VECTOR_DB_PATH = os.getenv("VECTOR_STORE_PATH", os.path.join(PROCESSED_DIR, "vector_store")) # Base name
# --- 

# Get dimension directly from the loaded embedder model
VECTOR_DIMENSION = get_embedding_dimension() # Get dimension after model loads
if VECTOR_DIMENSION is None:
    logger.error("Could not determine embedding dimension from model. Using fallback 768 for Gemini.")
    # Fallback or raise error if dimension is crucial and model failed
    VECTOR_DIMENSION = 768 # Fallback specifically for embedding-001

# Load optional MindPalace keys
GITHUB_ACCESS_TOKEN = os.getenv("GITHUB_ACCESS_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
if not GITHUB_ACCESS_TOKEN:
    logger.warning("GITHUB_ACCESS_TOKEN not found in .env - GitHub repo analysis might be rate-limited or fail for private repos.")
if not MISTRAL_API_KEY:
    logger.warning("MISTRAL_API_KEY not found in .env - Visualizer AI functions requiring Mistral may not work.")

app = FastAPI(title="NeuraParse - AI Document Q&A & Visualizer")

# --- Serve Static Frontend Files ---
# Define the path to the frontend directory relative to the backend app directory
# This assumes the frontend folder is sibling to the backend folder
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend") 

if os.path.exists(FRONTEND_DIR):
    logger.info(f"Attempting to serve static files from: {os.path.abspath(FRONTEND_DIR)}")
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/", response_class=FileResponse, include_in_schema=False)
    async def read_index():
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        if not os.path.exists(index_path):
            logger.error(f"Frontend index.html not found at: {index_path}")
            raise HTTPException(status_code=404, detail="Frontend not found. Cannot serve index.html.")
        logger.debug(f"Serving frontend index.html from: {index_path}")
        return FileResponse(index_path)
else:
    logger.warning(f"Frontend directory not found at expected location: {os.path.abspath(FRONTEND_DIR)}. Static file serving disabled.")
    @app.get("/", include_in_schema=False)
    async def read_root_fallback():
        # Provide a fallback message if frontend isn't found
        return {"message": "Backend is running, but frontend files are not configured or found."}
# -----------------------------------

logger.info("Application starting...")
# --- Log the absolute paths being used --- 
logger.info(f"Q&A Upload directory: {os.path.abspath(UPLOAD_DIR)}")
logger.info(f"Visualizer Temp Upload directory: {os.path.abspath(VISUALIZER_UPLOAD_DIR)}")
logger.info(f"Processed data directory: {os.path.abspath(PROCESSED_DIR)}")
logger.info(f"Vector store base path: {os.path.abspath(VECTOR_DB_PATH)}")
# --- 
logger.info(f"Using embedding model: {EMBEDDING_MODEL_NAME} (Expected Dim: {VECTOR_DIMENSION})")

# Ensure necessary directories exist
logger.info(f"Ensuring directory exists: {UPLOAD_DIR}")
os.makedirs(UPLOAD_DIR, exist_ok=True)
logger.info(f"Ensuring directory exists: {VISUALIZER_UPLOAD_DIR}") # Ensure visualizer temp dir exists
os.makedirs(VISUALIZER_UPLOAD_DIR, exist_ok=True)
logger.info(f"Ensuring directory exists: {PROCESSED_DIR}")
os.makedirs(PROCESSED_DIR, exist_ok=True)

# --- Vector Store Initialization ---
# Use BaseVectorStore for type hinting
vector_store: BaseVectorStore | None = None
try:
    logger.info(f"Attempting to initialize VectorStore (dim={VECTOR_DIMENSION}) with base path: {VECTOR_DB_PATH}")
    # --- Use the factory function --- 
    vector_store = get_vector_store(dimension=VECTOR_DIMENSION, path=VECTOR_DB_PATH)
    # --- 
    # vector_store = VectorStore(dimension=VECTOR_DIMENSION, index_path=VECTOR_DB_PATH) # <<< OLD INSTANTIATION
    logger.info(f"VectorStore initialized successfully using {type(vector_store).__name__}.")
except ImportError as import_err:
     logger.error(f"Failed to initialize VectorStore due to missing library: {import_err}", exc_info=False)
     vector_store = None
except Exception as e:
    logger.error(f"Failed to initialize VectorStore: {e}", exc_info=True)
    vector_store = None # Ensure it's None if initialization fails

# --- Pydantic Models ---
class QuestionRequest(BaseModel):
    question: str
    session_id: str | None = None

class AnswerResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]

class AnalyzeRepoRequest(BaseModel):
    github_url: str

class VisualizationResponse(BaseModel):
    explanation: str
    mindmap_markdown: Optional[str] = None
    repo_structure_text: Optional[str] = None

class QueryRequest(BaseModel):
    question: str

# --- Exception Handling ---
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception during request to {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": f"An internal server error occurred: {exc}"},
    )

# --- API Endpoints ---

# Existing Q&A Endpoints
@app.post("/api/upload/", summary="Upload and process files for Q&A", tags=["Q&A API"])
async def upload_files_qa(files: List[UploadFile] = File(...)):
    # Renamed function slightly for clarity
    global vector_store
    # ... (keep existing implementation of upload logic) ...
    processed_files_info = []
    filenames = [sanitize_filename(file.filename or f"file_{i}") for i, file in enumerate(files)]
    logger.info(f"[Q&A] Received {len(filenames)} files for upload: {filenames}")

    if vector_store is None:
        logger.error("[Q&A] Upload rejected: Vector store is not available.")
        raise HTTPException(status_code=503, detail="Vector store not initialized. Cannot process uploads.")

    with Timer(logger, name=f"[Q&A] Total upload processing for {len(filenames)} files"):
        for i, file in enumerate(files):
            sanitized_name = filenames[i]
            file_path = os.path.join(UPLOAD_DIR, sanitized_name)
            logger.debug(f"[Q&A] Processing file {i+1}/{len(filenames)}: '{sanitized_name}'")

            try:
                logger.debug(f"[Q&A] Saving '{sanitized_name}' to '{file_path}'")
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
                logger.info(f"[Q&A] Successfully saved uploaded file: {file_path}")

                logger.info(f"[Q&A] Starting ingestion process for: {file_path}")
                with Timer(logger, name=f"[Q&A] Ingestion for {sanitized_name}"):
                    metadata = process_file(file_path, vector_store)
                
                logger.info(f"[Q&A] Finished ingestion for '{sanitized_name}'. Metadata: {metadata}")
                processed_files_info.append({"filename": sanitized_name, "status": metadata.get("status", "unknown"), "details": metadata})

            except HTTPException as http_exc:
                raise http_exc
            except Exception as e:
                logger.error(f"[Q&A] Error processing file '{sanitized_name}': {e}", exc_info=True)
                # Clean up file if processing failed during ingestion step
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                        logger.info(f"[Q&A] Cleaned up temporary file due to error: {file_path}")
                    except OSError as remove_err:
                        logger.warning(f"[Q&A] Could not remove temporary file '{file_path}' after error: {remove_err}")
                processed_files_info.append({"filename": sanitized_name, "status": "failed", "error": str(e)})
            finally:
                # Ensure the file object is closed even if errors occur
                if hasattr(file, 'file') and hasattr(file.file, 'close'):
                    file.file.close()
    
    successful_uploads = sum(1 for f in processed_files_info if f['status'] not in ['failed', 'skipped'])
    logger.info(f"[Q&A] Upload processing complete. Successfully processed {successful_uploads}/{len(filenames)} files.")
    
    try:
        if vector_store and hasattr(vector_store, 'save'):
             logger.info("[Q&A] Attempting to save vector store index after updates...")
             with Timer(logger, name="[Q&A] Vector store save"):
                 vector_store.save()
    except Exception as save_err:
        logger.error(f"[Q&A] Failed to save vector store index: {save_err}", exc_info=True)

    return {
        "message": f"Upload request processed for {len(filenames)} files. {successful_uploads} processed successfully.",
        "results": processed_files_info
    }


@app.post("/api/query/", response_model=AnswerResponse, summary="Ask a question (Q&A)", tags=["Q&A API"])
async def ask_question_qa(request: QuestionRequest):
    # Renamed function slightly for clarity
    # ... (keep existing implementation of query logic) ...
    logger.info(f"[Q&A] Received query: '{request.question[:100]}...' (Session: {request.session_id or 'N/A'})")

    if vector_store is None:
        logger.error("[Q&A] Query rejected: Vector store is not available.")
        raise HTTPException(status_code=503, detail="Vector store not initialized. Cannot process queries.")

    with Timer(logger, name=f"[Q&A] Query processing for '{request.question[:50]}...'"):
        try:
            logger.debug(f"[Q&A] Retrieving chunks for query: '{request.question}'")
            with Timer(logger, name="[Q&A] Chunk retrieval"):
                relevant_chunks = retrieve_chunks(request.question, vector_store, top_k=10) # TODO: Make top_k configurable?
            logger.info(f"[Q&A] Retrieved {len(relevant_chunks)} chunks for query.")

            if not relevant_chunks:
                logger.warning(f"[Q&A] No relevant chunks found for query: '{request.question}'")
                return AnswerResponse(answer="Sorry, I couldn't find relevant information in the uploaded documents.", sources=[])

            context = "\n---\n".join([chunk.get('content', '') for chunk in relevant_chunks])
            logger.debug(f"[Q&A] Generating answer using context (approx {len(context)} chars)...")
            with Timer(logger, name="[Q&A] Answer generation"):
                answer_text = generate_answer(request.question, context)
            logger.info(f"[Q&A] Generated answer (snippet): '{answer_text[:100]}...'")

            # Format sources nicely, including visual element info
            sources = []
            for chunk in relevant_chunks:
                metadata = chunk.get('metadata', {})
                source_type = metadata.get('source_type') # Check if it's a visual summary
                original_source = metadata.get('original_source', metadata.get('source', 'Unknown')) # Use original if available
                page_number = metadata.get('page_number')

                # Use summary as snippet for visual elements, content for text chunks
                content_snippet = metadata.get('summary', chunk.get('content', ''))[:150] + "..."

                source_entry = {
                    "source": original_source, # Always show the original document name
                    "content_snippet": content_snippet,
                    "score": chunk.get('score', None),
                    "metadata": { # Pass specific metadata needed by frontend
                        "original_source": original_source,
                        "source_type": source_type, # 'image', 'table', or None
                        "page_number": page_number, # Page number if available
                        "chunk_index": metadata.get('chunk_index') # Chunk index for standard text
                    }
                }
                sources.append(source_entry)

            logger.debug(f"[Q&A] Formatted {len(sources)} sources for response.")

            return AnswerResponse(answer=answer_text, sources=sources)

        except HTTPException as http_exc:
            # Re-raise HTTP exceptions directly
            raise http_exc
        except Exception as e:
            logger.error(f"[Q&A] Error during query processing for '{request.question}': {e}", exc_info=True)
            # Return a generic 500 error for other exceptions
            raise HTTPException(status_code=500, detail=f"An error occurred while processing the question.")


# --- New Visualizer Endpoints ---

@app.post("/api/analyze_repo", response_model=VisualizationResponse, summary="Analyze GitHub Repo for Visualization", tags=["Visualizer API"])
async def analyze_repo_endpoint(request: AnalyzeRepoRequest):
    # print("ENTERING analyze_repo_endpoint") # Can remove debug print
    logger.info(f"Received request to analyze repo: {request.github_url}")
    if not request.github_url or not request.github_url.startswith("https://github.com/"):
        raise HTTPException(status_code=400, detail="Invalid GitHub repository URL provided.")
    
    try:
        # Pass the existing global logger instance to the analysis function
        result = analyze_github_repo(request.github_url, logger_instance=logger)
        return result
    except (ValueError, ConnectionError, RuntimeError, TimeoutError) as e:
        # Log the specific error before raising HTTPException
        logger.error(f"Analysis failed for repo {request.github_url}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze repository: {e}")
    except Exception as e:
        logger.error(f"Unexpected error analyzing GitHub repo '{request.github_url}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected analysis error occurred.") # Generic message to user

@app.post("/api/analyze_pdf", response_model=VisualizationResponse, summary="Analyze PDF for Visualization", tags=["Visualizer API"])
async def analyze_pdf_endpoint(file: UploadFile = File(...)):
    logger.info(f"Received request to analyze PDF: {file.filename}")
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF files are accepted for visualization.")

    sanitized_name = sanitize_filename(file.filename)
    temp_file_path = os.path.join(VISUALIZER_UPLOAD_DIR, f"visual_{sanitized_name}")
    
    try:
        # Save temp file
        logger.debug(f"Saving visualizer PDF temporarily to '{temp_file_path}'")
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Successfully saved visualizer PDF: {temp_file_path}")

        # Pass the existing global logger instance
        result = analyze_pdf_visual(temp_file_path, logger_instance=logger)
        return result

    except (ValueError, ConnectionError, RuntimeError, TimeoutError) as e:
        logger.error(f"Analysis failed for PDF {sanitized_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze PDF: {e}")
    except Exception as e:
        logger.error(f"Error analyzing PDF file '{sanitized_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error analyzing PDF.") # Generic message
    finally:
        # Clean up temp file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"Cleaned up temporary visualizer file: {temp_file_path}")
            except OSError as remove_err:
                logger.warning(f"Could not remove temporary visualizer file '{temp_file_path}': {remove_err}")
        # Close file handle
        if hasattr(file, 'file') and hasattr(file.file, 'close'):
             file.file.close()

# --- Optional System Endpoints ---
@app.get("/api/health", summary="Health check", tags=["System"])
async def health_check():
    logger.info("Health check requested.")
    health_status = {
        "status": "ok", 
        "vector_store_initialized": vector_store is not None,
        "vector_store_type": type(vector_store).__name__ if vector_store else None
    }
    return health_status


# --- Run Instructions (for local development) ---
# Use uvicorn: uvicorn backend.app:app --reload --port 8000

logger.info("Application setup complete. Ready to accept requests.") 