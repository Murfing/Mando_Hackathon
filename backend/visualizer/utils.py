# backend/visualizer/utils.py
print("Importing visualizer.utils") # DEBUG
import logging
import json
import google.generativeai as genai
from typing import Dict, Any, Optional
import string # Import string for letter generation

# logger = logging.getLogger(__name__) # REMOVE - Use passed logger

# --- Gemini Interaction --- 
def _configure_gemini(gemini_api_key: str | None, current_logger: Optional[logging.Logger] = None):
    """Configures the Gemini client. Should ideally happen once."""
    effective_logger = current_logger if current_logger else logging.getLogger(__name__)
    if not gemini_api_key:
        # Log before raising
        effective_logger.error("Gemini API Key is required but not provided.")
        raise ValueError("Gemini API Key is required.")
    try:
        # This configuration is global. Be mindful if called multiple times.
        # Consider a check if it's already configured or use a shared client instance.
        genai.configure(api_key=gemini_api_key)
        effective_logger.debug("Gemini API configured.")
    except Exception as e:
        effective_logger.error(f"Failed to configure Gemini: {e}")
        raise RuntimeError(f"Gemini configuration failed: {e}") from e

def call_gemini_json(prompt_text: str, system_instruction: str, gemini_api_key: str | None, 
                     current_logger: Optional[logging.Logger] = None, model_name="gemini-2.0-flash") -> Optional[Dict[str, Any]]:
    """Calls the Gemini API, expecting a JSON response."""
    effective_logger = current_logger if current_logger else logging.getLogger(__name__)

    _configure_gemini(gemini_api_key, effective_logger)
    try:
        effective_logger.debug(f"Calling Gemini model {model_name} with system instruction... Input length: {len(prompt_text)}")
        # Small part of the input prompt for context
        prompt_snippet = prompt_text[:100] + ("..." if len(prompt_text) > 100 else "")
        effective_logger.debug(f"Prompt snippet: {prompt_snippet}")
        
        generation_config = {
            "temperature": 0.5,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 8192,
            "response_mime_type": "application/json",
        }
        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=generation_config,
            system_instruction=system_instruction
        )
        response = model.generate_content(prompt_text)

        # --- LOGGING & VALIDATION --- 
        raw_text = ""
        try:
            # Attempt to access parts safely
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                raw_text = "".join(part.text for part in response.candidates[0].content.parts)
                effective_logger.info(f"Gemini Raw Response Received (Length: {len(raw_text)}). Attempting to parse JSON.")
                # Log the raw response text BEFORE parsing - crucial for debugging
                effective_logger.debug(f"Gemini Raw Text:\n---\n{raw_text}\n---") 
            else:
                # Log detailed failure info if parts are missing
                block_reason = response.prompt_feedback.block_reason if hasattr(response, 'prompt_feedback') and response.prompt_feedback else "Unknown Block Reason"
                finish_reason = response.candidates[0].finish_reason if response.candidates and hasattr(response.candidates[0], 'finish_reason') else "Unknown Finish Reason"
                safety_ratings = response.candidates[0].safety_ratings if response.candidates and hasattr(response.candidates[0], 'safety_ratings') else "No Safety Ratings"
                effective_logger.error(f"Gemini call failed or returned empty content. Finish: {finish_reason}, Block: {block_reason}, Safety: {safety_ratings}")
                # Explicitly log the full response object for deep inspection if possible
                try:
                    effective_logger.error(f"Full Gemini Response Object (on failure): {response}")
                except Exception as log_err:
                    effective_logger.error(f"Could not log full response object: {log_err}")
                raise RuntimeError(f"Gemini API call failed or returned empty (Reason: {finish_reason}, Block: {block_reason})")
        except AttributeError as ae:
             effective_logger.error(f"Error accessing Gemini response attributes: {ae}. Response: {response}", exc_info=True)
             raise RuntimeError(f"Error processing Gemini response structure: {ae}") from ae
        except Exception as e:
            # Catch any other unexpected errors during raw text extraction
            effective_logger.error(f"Unexpected error extracting raw text from Gemini response: {e}. Response: {response}", exc_info=True)
            raise RuntimeError(f"Unexpected error processing Gemini response: {e}") from e
        
        # --- JSON Parsing --- 
        # Basic cleaning for markdown code blocks (applied AFTER logging raw)
        cleaned_text = raw_text.strip()
        if cleaned_text.startswith("```json"):
             cleaned_text = cleaned_text[7:-3].strip()
        elif cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:-3].strip()

        try:
            # Additional checks for common non-JSON prefixes/suffixes
            json_start = cleaned_text.find('{')
            json_end = cleaned_text.rfind('}')
            if json_start != -1 and json_end != -1:
                json_candidate = cleaned_text[json_start : json_end + 1]
                parsed_json = json.loads(json_candidate)
                effective_logger.info("Successfully parsed JSON response from Gemini.")
                return parsed_json
            else:
                 effective_logger.error("Cleaned text did not contain valid JSON object markers ('{' and '}').")
                 raise json.JSONDecodeError("No valid JSON object markers found", cleaned_text, 0)

        except json.JSONDecodeError as json_err:
             effective_logger.error(f"Failed to decode Gemini JSON response: {json_err}")
             # Log the cleaned text that failed parsing
             effective_logger.error(f"Cleaned Text that failed JSON parsing:\n---\n{cleaned_text}\n---")
             # Re-raise as ValueError for the calling function to handle
             raise ValueError(f"AI model returned invalid JSON: {json_err}")

    except Exception as e:
        # Catch errors from _configure_gemini or the main API call
        effective_logger.error(f"Error during Gemini API call or setup for model {model_name}: {e}", exc_info=True)
        # Ensure this re-raises to be caught by the endpoint handler
        raise RuntimeError(f"AI analysis call failed: {e}") from e

# --- Mermaid Generation (Replaces Markmap) --- 

def _sanitize_mermaid_label(text: str) -> str:
    """Sanitizes text for use within Mermaid node labels or edge labels.
       Removes characters that could break Mermaid syntax, especially quotes.
    """
    # Replace quotes and characters that might interfere with Mermaid string definitions
    sanitized = text.replace("\"", "'").replace("`", "'").replace("[\n\r]", " ") # Replace various quotes and newlines
    # Remove any remaining characters that aren't letters, numbers, spaces, or basic punctuation
    # This is quite aggressive, might need adjustment
    # sanitized = re.sub(r'[^a-zA-Z0-9\s.,;!?\-_\(\)']', '', sanitized)
    return sanitized.strip()

def generate_mermaid_flowchart(relationships_json: Optional[Dict[str, Any]], 
                               current_logger: Optional[logging.Logger] = None) -> str:
    """Generates Mermaid flowchart code from relationship data, similar to MindPalace."""
    effective_logger = current_logger if current_logger else logging.getLogger(__name__)
    
    # --- Basic Validation --- 
    if not relationships_json or "relationships" not in relationships_json:
        # Return LR for error too
        return "graph LR\nError[\"No relationship data found\"]"
    relationships = relationships_json["relationships"]
    if not relationships:
         # Return LR for empty too
         return "graph LR\nEmpty[\"No relationships extracted to build graph\"]"
    
    # --- Mermaid Header & Theme --- 
    mermaid_code = """%%{
  init: {
    'theme': 'base',
    'themeVariables': {
      'primaryColor': '#e66b22',
      'primaryTextColor': '#efefef',
      'primaryBorderColor': '#d9d9d9',
      'lineColor': '#8d8d8d',
      'secondaryColor': '#212121',
      'tertiaryColor': '#fff'
    }
  }
}%%
flowchart LR;
""" # CHANGED TD to LR

    # --- Node and Edge Generation --- 
    unique_nodes: Dict[str, str] = {}
    letters = string.ascii_uppercase
    node_index = 0
    nodes_defined = set()
    edges_defined = set()
    for relation in relationships:
        for node_name_raw in [relation.get("from"), relation.get("to")]:
            if node_name_raw and isinstance(node_name_raw, str):
                node_name = _sanitize_mermaid_label(node_name_raw)
                if node_name and node_name not in unique_nodes:
                    if node_index < len(letters):
                        unique_nodes[node_name] = letters[node_index]
                        node_index += 1
                    else:
                        fallback_id = f"N{node_index}"
                        unique_nodes[node_name] = fallback_id
                        node_index += 1
                        if node_index == 26:
                            effective_logger.warning("Exceeded letters...")
            elif node_name_raw:
                 effective_logger.warning(f"Skipping non-string node: {node_name_raw}")

    for relation in relationships:
        from_topic_raw = relation.get("from")
        to_topic_raw = relation.get("to")
        rel_text_raw = relation.get("relationship", "")
        if not from_topic_raw or not to_topic_raw or not isinstance(from_topic_raw, str) or not isinstance(to_topic_raw, str):
            continue
        from_topic = _sanitize_mermaid_label(from_topic_raw)
        to_topic = _sanitize_mermaid_label(to_topic_raw)
        rel_text = _sanitize_mermaid_label(rel_text_raw) if rel_text_raw else ""
        from_id = unique_nodes.get(from_topic)
        to_id = unique_nodes.get(to_topic)
        if not from_id or not to_id:
            continue
        if from_id not in nodes_defined:
            mermaid_code += f'  {from_id}["{from_topic}"];\n'
            nodes_defined.add(from_id)
        if to_id not in nodes_defined:
            mermaid_code += f'  {to_id}["{to_topic}"];\n'
            nodes_defined.add(to_id)
        edge_str = f'  {from_id} -->|"{rel_text}"| {to_id};\n'
        if edge_str not in edges_defined:
             mermaid_code += edge_str
             edges_defined.add(edge_str)
             
    for node_name, node_id in unique_nodes.items():
         if node_id not in nodes_defined:
             mermaid_code += f'  {node_id}["{node_name}"];\n'
             nodes_defined.add(node_id)

    # --- Styling --- 
    mermaid_code += "\nclassDef customStyle stroke:#e66b22,stroke-width:2px,rx:10px,ry:10px,font-size:16px;\n"
    for node_id in unique_nodes.values():
        mermaid_code += f'  class {node_id} customStyle;\n'
        
    effective_logger.info("Generated Mermaid flowchart code (LR).")
    return mermaid_code.strip()

# --- Remove Old Markmap Functions --- 
# def generate_markdown_mindmap(...): # REMOVED
# def _build_markdown_recursive(...): # REMOVED
# def _sanitize_markdown(...): # REMOVED (replaced by _sanitize_mermaid_label) 