# Backend analyzer for PDFs using MindPalace logic adapters
import logging
import os
import base64
import json
from mistralai import Mistral
from typing import Optional

# Use shared utils for AI calls and flowchart generation
from .utils import call_gemini_json, generate_mermaid_flowchart

# logger = logging.getLogger(__name__)

# Get API keys from environment (loaded in app.py)
# GITHUB_TOKEN = os.getenv("GITHUB_ACCESS_TOKEN") # Not needed for PDF
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

# --- Constants --- 
PDF_SUMMARY_INSTRUCTION = """Analyze the provided text extracted from a PDF document. Your goal is to identify and summarize the main sections, key concepts, arguments, and conclusions presented.

Your response MUST be a valid JSON object containing ONLY the following structure:
{
  "topics": [
    {
      "topic": "<A concise name for a key section, concept, or argument>",
      "summary": "<A DETAILED (3-5 sentence) summary explaining this topic's main points, significance, and any key sub-points or examples mentioned in the text.>"
    },
    ...
  ]
}

Break down the document into logical, **granular topics**. Ensure each summary captures the essence and important details of its corresponding topic based SOLELY on the provided text. Ensure the output strictly adheres to the JSON schema provided."""

RELATIONSHIP_INSTRUCTION = """Based on the following list of topics and their DETAILED summaries extracted from a PDF, identify ALL key logical connections, dependencies, and flow between them.

Consider relationships like: 'introduces', 'explains', 'references', 'contrasts with', 'builds upon', 'provides evidence for', 'leads to', 'is a part of'. Be specific.

Your response MUST be a valid JSON object containing ONLY the following structure:
{
  "relationships": [
    {
      "from": "<Topic Name A>",
      "to": "<Topic Name B>",
      "relationship": "<Specific description of the relationship (e.g., 'provides background for', 'contrasts findings with')>"
    },
    ...
  ]
}

Ensure the 'from' and 'to' fields exactly match topic names from the input summaries. Identify as many direct relationships as are clearly implied by the summaries. Be elaborate and specific in the relationship descriptions. If no clear relationships are found, return an empty list: {"relationships": []}."""

# --- Mistral OCR Interaction --- 
def extract_text_from_pdf_mistral(file_path: str, mistral_api_key: str, current_logger: Optional[logging.Logger] = None) -> str:
    """Extracts text from PDF using Mistral OCR API."""
    effective_logger = current_logger if current_logger else logging.getLogger(__name__)
    try:
        client = Mistral(api_key=mistral_api_key)
        with open(file_path, "rb") as pdf_file:
            pdf_bytes = pdf_file.read()
        
        encoded_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        document = {"type": "document_url", "document_url": f"data:application/pdf;base64,{encoded_pdf}"}
        
        effective_logger.info(f"Sending PDF {os.path.basename(file_path)} to Mistral OCR...")
        # Note: Check Mistral API docs for latest model name and parameters
        ocr_response = client.ocr.process(model="mistral-ocr-latest", document=document)
        
        pages = getattr(ocr_response, "pages", [])
        result_text = "\n\n".join(page.markdown for page in pages)
        
        if not result_text:
            effective_logger.warning(f"Mistral OCR returned no text for {os.path.basename(file_path)}.")
            return "(OCR returned no text)" # Return indicator string
            
        effective_logger.info(f"Mistral OCR successful, extracted {len(result_text)} chars.")
        return result_text
        
    except Exception as e:
        effective_logger.error(f"Error during Mistral OCR API call for {os.path.basename(file_path)}: {e}", exc_info=True)
        # Raise a more specific error or return None/empty string?
        raise RuntimeError(f"Mistral OCR failed: {e}") from e

# --- Main Analysis Function --- 
def analyze_pdf_visual(file_path: str, logger_instance: Optional[logging.Logger] = None) -> dict:
    """Analyzes a PDF using reimplemented logic (Mistral OCR + Gemini)."""
    # Use the passed logger if available, otherwise get a default one
    effective_logger = logger_instance if logger_instance else logging.getLogger(__name__)
    
    filename = os.path.basename(file_path)
    effective_logger.info(f"Starting visual analysis for PDF: {filename}")

    mistral_api_key = os.getenv("MISTRAL_API_KEY")
    gemini_api_key = os.getenv("GEMINI_API_KEY")

    if not mistral_api_key:
        effective_logger.error("MISTRAL_API_KEY is required for PDF analysis but not found in environment.")
        raise ValueError("MISTRAL_API_KEY is required for PDF analysis but not found in environment.")
    if not gemini_api_key:
        effective_logger.error("GEMINI_API_KEY is required for PDF analysis but not found in environment.")
        raise ValueError("GEMINI_API_KEY is required for PDF analysis but not found in environment.")

    try:
        # 1. Extract Text using Mistral OCR
        effective_logger.info("Extracting PDF text using Mistral OCR...")
        pdf_text = extract_text_from_pdf_mistral(file_path, mistral_api_key, effective_logger)
        if not pdf_text or pdf_text == "(OCR returned no text)":
            effective_logger.error("Could not extract text from PDF using OCR.")
            raise ValueError("Could not extract text from PDF using OCR.")
        effective_logger.info(f"Extracted {len(pdf_text)} characters from PDF.")

        # 2. Generate Summaries (Using Gemini)
        effective_logger.info("Generating PDF summary via Gemini...")
        summary_json = call_gemini_json(pdf_text, PDF_SUMMARY_INSTRUCTION, gemini_api_key, effective_logger)
        if not summary_json or "topics" not in summary_json:
            effective_logger.error("Failed to generate PDF summary from Gemini.")
            raise ValueError("Failed to generate PDF summary from Gemini.")
        effective_logger.info(f"Generated summary for {len(summary_json['topics'])} topics.")

        # 3. Format Explanation & Prepare text for Relationship Extraction
        explanation = f"Analysis for {filename}:\n\n"
        summary_text_for_relations = ""
        for topic in summary_json.get('topics', []):
            topic_name = topic.get('topic', 'Unknown Topic')
            topic_summary = topic.get('summary', 'No summary.')
            explanation += f"**{topic_name}**\n{topic_summary}\n\n"
            summary_text_for_relations += f"Topic: {topic_name}\nSummary: {topic_summary}\n\n"

        # 4. Extract Relationships (Using Gemini)
        effective_logger.info("Extracting relationships via Gemini...")
        relationships_json = call_gemini_json(summary_text_for_relations, RELATIONSHIP_INSTRUCTION, gemini_api_key, effective_logger)
        if not relationships_json or "relationships" not in relationships_json:
            effective_logger.warning("Failed to extract relationships from Gemini, mind map might be basic.")
            relationships_data = None
        else:
            relationships_data = relationships_json
            effective_logger.info(f"Extracted {len(relationships_json.get('relationships', []))} relationships.")

        # 5. Generate Mermaid Flowchart
        effective_logger.info("Generating Mermaid flowchart...")
        mermaid_code = generate_mermaid_flowchart(relationships_data, effective_logger)

        effective_logger.info(f"Finished visual analysis for PDF: {filename}")
        return {
            "explanation": explanation.strip(),
            "mindmap_markdown": mermaid_code
        }

    except (ValueError, ConnectionError, RuntimeError, TimeoutError) as e: # Catch specific errors + TimeoutError
         effective_logger.error(f"Analysis failed for PDF {filename}: {e}")
         raise e # Re-raise to be handled by API
    except Exception as e:
        effective_logger.error(f"Unexpected error during PDF visual analysis for {filename}: {e}", exc_info=True)
        raise RuntimeError(f"Unexpected analysis error: {e}")