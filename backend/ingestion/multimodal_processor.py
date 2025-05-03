import google.generativeai as genai
import logging
import os
from PIL import Image
import io
from typing import Dict, Any, Optional
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()
# Configure Gemini API Key at module level
# Assumes GEMINI_API_KEY is set in the environment where the app runs
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        logger.info("Gemini API Key configured successfully.")
    except Exception as e:
        logger.error(f"Error configuring Gemini API Key: {e}", exc_info=True)
        # Depending on strictness, might want to raise an error here
else:
    logger.warning("GEMINI_API_KEY environment variable not found. Multimodal processing will fail.")

# --- Constants for Multimodal Processing ---
# Consider making model names configurable via environment variables
MULTIMODAL_MODEL_NAME = "gemini-2.0-flash" # UPDATED User request
IMAGE_PROMPT = "Describe this image in detail. If it contains text, transcribe the text accurately. If it's a chart or diagram, explain what it shows. Focus on conveying the core information presented."
TABLE_PROMPT = """Summarize the key information presented in this table concisely:

{table_data}"""
MAX_RETRIES = 2
RETRY_DELAY = 5 # seconds - Consider exponential backoff

# Safety settings for Gemini (adjust as needed)
SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

def generate_summary_for_element(element: Dict[str, Any]) -> Optional[str]:
    """
    Generates a textual summary for a visual element (image or table) using Gemini.

    Args:
        element: A dictionary containing element details:
                 {'type': 'image'|'table', 'data': bytes|str, 'page_number': int|None, 'original_source': str}

    Returns:
        The generated text summary, or None if processing fails.
    """
    if not GEMINI_API_KEY:
        logger.error("Cannot generate summary: Gemini API key is not configured.")
        return None

    element_type = element.get("type")
    element_data = element.get("data")
    source_info = f"{element.get('original_source', 'Unknown')}, Page: {element.get('page_number', 'N/A')}, Type: {element_type}"

    if not element_type or not element_data:
        logger.warning(f"Missing type or data for element from {source_info}. Skipping summary generation.")
        return None

    try:
        model = genai.GenerativeModel(MULTIMODAL_MODEL_NAME)
        logger.info(f"Generating summary for {element_type} from {source_info} using model {MULTIMODAL_MODEL_NAME}...")

        if element_type == 'image':
            if not isinstance(element_data, bytes):
                logger.error(f"Invalid data type for image element: expected bytes, got {type(element_data)}. Source: {source_info}")
                return None
            try:
                img = Image.open(io.BytesIO(element_data))
                # Prepare parts for multimodal input: prompt first, then image
                parts = [IMAGE_PROMPT, img]
            except Exception as img_err:
                 logger.error(f"Failed to process image data before sending to Gemini: {img_err}. Source: {source_info}", exc_info=True)
                 return None

        elif element_type == 'table':
            if not isinstance(element_data, str):
                 logger.error(f"Invalid data type for table element: expected string, got {type(element_data)}. Source: {source_info}")
                 return None
            # Prepare parts for text-only input (multimodal model can handle text too)
            prompt = TABLE_PROMPT.format(table_data=element_data)
            parts = [prompt]
        else:
            logger.warning(f"Unsupported element type '{element_type}' for summary generation. Source: {source_info}")
            return None

        # Generate content using the Gemini API
        response = model.generate_content(parts, safety_settings=SAFETY_SETTINGS)

        # --- Basic Response Handling ---
        # More robust handling (retries, specific error checks) could be added here
        if response and response.parts:
             # Assuming the first part contains the text summary
             summary = response.text # Use .text accessor for simplicity
             char_count = len(summary) if summary else 0
             logger.info(f"Successfully generated summary ({char_count} chars) for {element_type} from {source_info}.")
             # Basic check for empty or placeholder responses
             if not summary or summary.strip().lower() == "none" or len(summary.strip()) < 10:
                 logger.warning(f"Generated summary seems empty or invalid for {source_info}. Summary: '{summary[:50]}...'")
                 return None # Or return a placeholder like "[Summary generation failed]"
             return summary.strip()
        else:
            # Log details if available - check response object structure
            block_reason = response.prompt_feedback.block_reason if response.prompt_feedback else "Unknown"
            safety_ratings = response.prompt_feedback.safety_ratings if response.prompt_feedback else "N/A"
            logger.warning(f"Gemini response was empty or invalid for {source_info}. Block Reason: {block_reason}, Safety Ratings: {safety_ratings}")
            return None

    except Exception as e:
        # Catch-all for API errors, configuration issues, etc.
        logger.error(f"Error generating summary using Gemini for {source_info}: {e}", exc_info=True)
        return None 