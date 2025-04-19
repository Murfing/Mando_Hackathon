import google.generativeai as genai
import os
import logging
from dotenv import load_dotenv
from typing import Optional

# Get the logger instance
logger = logging.getLogger(__name__)

# --- Load API Key ---
# It's better practice to load this once at application startup (e.g., in app.py)
# and pass the configured client/model instance, but loading here is also common.
load_dotenv() # Load environment variables from .env file
API_KEY = os.getenv("GEMINI_API_KEY")
gemini_model_instance: Optional[genai.GenerativeModel] = None

# --- Configuration ---
# Choose a suitable Gemini model (e.g., 'gemini-1.5-flash', 'gemini-pro')
MODEL_NAME = "gemini-2.0-flash" # Use a recent, available model
# Adjust generation parameters as needed
GENERATION_CONFIG = {
    "temperature": 0.3, # Slightly increased temperature for a bit more creativity/verbosity
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 2048, # Increased further to allow for longer answers
}
# Configure safety settings to be less restrictive if needed, or handle blocked responses
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

# --- Model Initialization ---
def initialize_gemini_model():
    global gemini_model_instance
    if gemini_model_instance:
        # logger.debug("Gemini model already initialized.")
        return

    if not API_KEY:
        logger.error("GEMINI_API_KEY not found in environment variables. Cannot initialize Gemini model.")
        gemini_model_instance = None # Ensure it's None
        return

    try:
        logger.info("Configuring Google Generative AI...")
        genai.configure(api_key=API_KEY)
        logger.info(f"Initializing Gemini Model: {MODEL_NAME}")
        gemini_model_instance = genai.GenerativeModel(
            MODEL_NAME,
            generation_config=GENERATION_CONFIG,
            safety_settings=SAFETY_SETTINGS
        )
        logger.info("Gemini model initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing Google Generative AI model '{MODEL_NAME}': {e}", exc_info=True)
        gemini_model_instance = None

# Initialize the model when the module is loaded
initialize_gemini_model()


def generate_answer(query: str, context: str) -> str:
    """
    Generates an answer to the query using the provided context with a Gemini model.

    Args:
        query: The user's question.
        context: The relevant text chunks retrieved from documents.

    Returns:
        The generated answer string, or an error message.
    """
    if gemini_model_instance is None:
        logger.error("Answer generation failed: Gemini model is not initialized.")
        # Attempt re-initialization? Or rely on startup initialization.
        # initialize_gemini_model() # Optional: Try to re-initialize
        # if gemini_model_instance is None: # Check again
        return "Error: AI model not configured or API key missing."

    if not context or not context.strip():
        logger.warning(f"Attempted answer generation for query '{query[:50]}...' with empty context.")
        return "Sorry, I could not find relevant context to answer the question."

    # Construct the prompt asking for more detail and length
    prompt = f"""You are a helpful AI assistant tasked with answering questions based ONLY on the provided context snippets below. Your goal is to provide a thorough, descriptive, and well-synthesized answer.

**Context Snippets:**
---
{context}
---

**Instructions:**
1.  Carefully read and understand the user's question.
2.  Thoroughly analyze all provided context snippets. Identify all pieces of information relevant to the question.
3.  Synthesize a comprehensive and descriptive answer. Do not just list facts; explain the information and connect relevant details found across different snippets.
4.  Aim for a detailed response that fully addresses the user's question based *exclusively* on the provided text. Use multiple sentences and structure the answer clearly.
5.  If the context snippets do not contain sufficient information to provide a detailed answer to the question, state clearly: \"Based on the provided documents, I cannot answer this question in detail.\" followed by any partial answer the context *does* support.
6.  Crucially, do NOT add any information that is not present in the context snippets. Do not make assumptions or use prior knowledge.

**Question:** {query}

**Detailed and Descriptive Answer:**
"""

    logger.debug(f"Generating detailed answer for query: '{query[:50]}...'")
    logger.debug(f"Using context length: {len(context)} chars.")
    # logger.debug(f"Prompt: {prompt}") # Avoid logging potentially large/sensitive prompts unless debugging

    try:
        # Use the initialized model instance
        response = gemini_model_instance.generate_content(prompt)

        # More robust check for response content
        if not response.candidates or not hasattr(response.candidates[0], 'content') or not hasattr(response.candidates[0].content, 'parts') or not response.candidates[0].content.parts:
            block_reason = "Unknown"
            finish_reason = "Unknown"
            safety_ratings = []
            if response.prompt_feedback:
                 block_reason = response.prompt_feedback.block_reason
                 safety_ratings = response.prompt_feedback.safety_ratings
            if response.candidates and hasattr(response.candidates[0], 'finish_reason'):
                 finish_reason = response.candidates[0].finish_reason

            logger.warning(f"Answer generation potentially failed or blocked. Finish Reason: {finish_reason}, Block Reason: {block_reason}, Safety Ratings: {safety_ratings}")

            # Provide a more informative message based on the reason
            if finish_reason == 'SAFETY':
                 return f"Sorry, the response could not be generated due to safety filters (Reason: {block_reason})."
            elif finish_reason == 'RECITATION':
                 return "Sorry, the response could not be generated due to potential recitation issues."
            elif finish_reason == 'MAX_TOKENS':
                 return "Sorry, the generated answer exceeded the maximum length limit."
            else:
                 return f"Sorry, I couldn't generate a complete answer (Reason: {finish_reason}, Block: {block_reason}). Please try rephrasing your question."

        # Extract text - primary way for gemini-pro and similar
        answer = "".join(part.text for part in response.candidates[0].content.parts)

        logger.info(f"Successfully generated answer. Length: {len(answer)} chars.")
        # logger.debug(f"Generated answer: '{answer}'") # Log full answer only if necessary
        return answer.strip()

    except Exception as e:
        logger.error(f"Exception during Gemini API call for query '{query[:50]}...': {e}", exc_info=True)
        # More specific error handling might be needed based on genai library exceptions
        # e.g., handle google.api_core.exceptions.PermissionDenied, ResourceExhausted, etc.
        return f"Sorry, an error occurred while communicating with the AI model: {e}"

# TODO: Consider adding chat history management for conversational context
# TODO: Explore different prompting strategies for better results (e.g., few-shot)
# TODO: Implement context length checks and truncation based on model limits (e.g., using tiktoken)