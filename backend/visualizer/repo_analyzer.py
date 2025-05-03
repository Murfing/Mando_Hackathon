# Backend analyzer for GitHub Repos using MindPalace logic adapters
print("Importing visualizer.repo_analyzer") # DEBUG
import logging
import os
import requests
import base64
import json
from typing import Dict, Any, List, Optional, Tuple
import google.generativeai as genai

# Import the refactored adapters

from .utils import call_gemini_json, generate_mermaid_flowchart # Use shared utils

# logger = logging.getLogger(__name__) # REMOVE - We will use the passed logger

# Get API keys from environment (loaded in app.py)
GITHUB_TOKEN = os.getenv("GITHUB_ACCESS_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY") # Not needed for repo summary/relations

# --- Constants --- 
EXCLUDED_FILE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp", ".pdf", ".zip", ".tar", ".gz", ".mp4", ".mp3", ".avi"}
MAX_FILES_TO_FETCH = 50 # Limit number of files fetched to avoid excessive API calls

REPO_SUMMARY_INSTRUCTION = """Analyze the provided repository structure and README (if included). Your goal is to identify the core components, technologies, and the overall purpose/workflow.

Your response MUST be a valid JSON object containing ONLY the following structure:
{
  "topics": [
    {
      "topic": "<A concise name for a key area, technology, functional component, or significant file/module>",
      "summary": "<A DETAILED (3-5 sentence) summary explaining this topic's role, key responsibilities, main technologies/libraries used within it, and its primary interactions OR purpose within the repository.>"
    },
    ...
  ]
}

Identify **more granular topics** where appropriate (e.g., distinct backend modules, frontend components, key utility classes/files). 
Focus on providing substantial detail in each summary. 
Do NOT include raw file contents or large code snippets. Ensure the output strictly adheres to the JSON schema provided."""

RELATIONSHIP_INSTRUCTION = """Based on the following list of topics and their DETAILED summaries, identify ALL key relationships, dependencies, and interactions between them.

Consider relationships like: 'uses function/class from', 'imports', 'provides data to', 'configures', 'manages state for', 'renders UI for', 'handles requests for', 'depends on', 'part of', 'interacts with'. Be specific.

Your response MUST be a valid JSON object containing ONLY the following structure:
{
  "relationships": [
    {
      "from": "<Topic Name A>",
      "to": "<Topic Name B>",
      "relationship": "<Specific description of the relationship (e.g., 'imports utility functions from', 'renders data managed by')>"
    },
    ...
  ]
}

Ensure the 'from' and 'to' fields exactly match topic names from the input summaries. Identify as many direct relationships as are clearly implied by the summaries. Be elaborate and specific in the relationship descriptions. If no clear relationships are found, return an empty list: {"relationships": []}."""

# --- GitHub API Interaction --- 
def _fetch_github_api(url: str, headers: Dict[str, str], current_logger: Optional[logging.Logger] = None) -> Any:
    """Helper to fetch data from GitHub API with error handling."""
    effective_logger = current_logger if current_logger else logging.getLogger(__name__)
    try:
        response = requests.get(url, headers=headers, timeout=15) # Add timeout
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        effective_logger.error(f"GitHub API request timed out for {url}")
        raise TimeoutError(f"GitHub API request timed out")
    except requests.exceptions.RequestException as e:
        effective_logger.error(f"Error fetching GitHub API {url}: {e}")
        status_code = e.response.status_code if e.response is not None else 500
        detail = f"Failed to fetch repository data ({status_code})"
        if status_code == 404:
            detail = "Repository not found or access denied."
        elif status_code == 403: # Rate limit or permission issue
            detail = "GitHub API rate limit likely exceeded or insufficient permissions."
        raise ConnectionError(detail) from e

def _get_file_content(file_info: Dict[str, Any], headers: Dict[str, str], current_logger: Optional[logging.Logger] = None) -> Optional[str]:
    """Fetches and decodes file content from GitHub API."""
    effective_logger = current_logger if current_logger else logging.getLogger(__name__)
    if "content" in file_info: # Content might be included in initial listing if small
        try:
            return base64.b64decode(file_info["content"]).decode("utf-8", errors="ignore")
        except Exception as e:
            effective_logger.warning(f"Error decoding inline content for {file_info.get('path', 'unknown file')}: {e}")
            return None
    elif "download_url" in file_info:
        # For larger files, fetch the download URL (raw content)
        try:
            response = requests.get(file_info["download_url"], headers=headers, timeout=10)
            response.raise_for_status()
            # Decode explicitly, assuming utf-8 but handling errors
            return response.content.decode('utf-8', errors='ignore')
        except requests.exceptions.RequestException as e:
            effective_logger.warning(f"Could not download file content from {file_info['download_url']}: {e}")
            return None
        except Exception as e:
            effective_logger.warning(f"Error decoding downloaded content for {file_info.get('path', 'unknown file')}: {e}")
            return None
    else:
        effective_logger.warning(f"Could not find content or download_url for file: {file_info.get('path')}")
        return None

def _fetch_repo_recursive(api_base_url: str, path: str, headers: Dict[str, str], file_contents: Dict[str, str], structure_list: List[str], level: int, files_fetched: int, current_logger: Optional[logging.Logger] = None) -> int:
    """Recursively fetches repo structure and file contents."""
    effective_logger = current_logger if current_logger else logging.getLogger(__name__)
    if files_fetched >= MAX_FILES_TO_FETCH:
        effective_logger.warning(f"Reached maximum file fetch limit ({MAX_FILES_TO_FETCH}). Stopping recursion.")
        return files_fetched

    effective_logger.debug(f"Fetching contents for path: {path if path else 'root'}")
    url = f"{api_base_url}/{path}"
    items = _fetch_github_api(url, headers, effective_logger)
    indent = "  " * level

    for item in items:
        if files_fetched >= MAX_FILES_TO_FETCH:
            break
            
        item_path = item["path"]
        item_name = item["name"]
        
        if item["type"] == "dir":
            structure_list.append(f"{indent}- {item_name}/")
            # Recurse into subdirectory
            files_fetched = _fetch_repo_recursive(api_base_url, item_path, headers, file_contents, structure_list, level + 1, files_fetched, effective_logger)
        elif item["type"] == "file":
            structure_list.append(f"{indent}- {item_name}")
            file_extension = os.path.splitext(item_name)[1].lower()
            if file_extension not in EXCLUDED_FILE_TYPES:
                # Fetch full file info to potentially get content/download_url
                file_info = _fetch_github_api(item["url"], headers, effective_logger)
                if file_info:
                    content = _get_file_content(file_info, headers, effective_logger)
                    if content:
                        file_contents[item_path] = content
                        files_fetched += 1
                        effective_logger.debug(f"Fetched content for: {item_path} ({files_fetched}/{MAX_FILES_TO_FETCH})")
                    else:
                        effective_logger.warning(f"Skipping file with no content: {item_path}")
                else:
                     effective_logger.warning(f"Could not get file info for: {item_path}")
            else:
                effective_logger.debug(f"Skipping excluded file type: {item_path}")
                
    return files_fetched

def fetch_and_structure_repo_text(repo_url: str, github_token: Optional[str], current_logger: Optional[logging.Logger] = None) -> Tuple[str, Dict[str, str]]:
    """Fetches repo structure and relevant file contents recursively.
    Returns a tuple: (repository_structure_string, file_contents_dictionary)
    """
    effective_logger = current_logger if current_logger else logging.getLogger(__name__)
    try:
        parts = repo_url.strip("/").split("/")
        owner = parts[-2]
        repo = parts[-1]
        if not owner or not repo or parts[-3].lower() != "github.com":
            raise ValueError("Invalid GitHub URL format")
    except Exception as e:
         raise ValueError(f"Could not parse owner/repo from GitHub URL: {repo_url}. Error: {e}")

    effective_logger.info(f"Fetching repo: {owner}/{repo}")
    api_base_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if github_token:
        headers['Authorization'] = f'token {github_token}'
    else:
        effective_logger.warning("No GitHub token provided. API calls will be rate-limited.")

    file_contents: Dict[str, str] = {}
    structure_list: List[str] = []
    files_fetched = 0

    try:
        # Pass effective_logger down
        _fetch_repo_recursive(api_base_url, "", headers, file_contents, structure_list, 0, files_fetched, effective_logger)

        # Combine structure into a single string
        structure_str = "Repository Structure:\n---\n" + "\n".join(structure_list) + "\n---"

        # Return structure string and file contents dictionary separately
        return structure_str, file_contents

    except ConnectionError as e: # Catch errors raised by _fetch_github_api
        effective_logger.error(f"ConnectionError fetching repo {owner}/{repo}: {e}")
        raise RuntimeError(f"Could not fetch repository data: {e}")
    except Exception as e:
        effective_logger.error(f"Unexpected error fetching full repo content for {owner}/{repo}: {e}", exc_info=True)
        raise RuntimeError(f"Unexpected error fetching repository data: {e}")

# --- Main Analysis Function --- 
def analyze_github_repo(repo_url: str, logger_instance: Optional[logging.Logger] = None) -> dict:
    print("ENTERING analyze_github_repo") # DEBUG
    """Analyzes a GitHub repo using reimplemented logic."""
    
    effective_logger = logger_instance if logger_instance else logging.getLogger(__name__)
    
    effective_logger.info(f"Starting analysis for repo URL: {repo_url}")
    github_token = os.getenv("GITHUB_ACCESS_TOKEN")
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        effective_logger.error("GEMINI_API_KEY not found in environment.")
        raise ValueError("GEMINI_API_KEY not found in environment.")

    try:
        # 1. Fetch Repo Content (Structure and File Contents separated)
        effective_logger.info("Fetching repository structure and content...")
        repo_structure, file_contents = fetch_and_structure_repo_text(repo_url, github_token, effective_logger)

        if not repo_structure:
            effective_logger.error("Could not fetch repository structure.")
            raise ValueError("Could not fetch repository structure.")
        effective_logger.info(f"Fetched repository structure ({len(repo_structure)} chars) and content for {len(file_contents)} files.")

        # --- Prepare input for Summary Generation --- 
        # Start with just the structure. Optionally add README if found.
        summary_input_text = repo_structure
        readme_content = None
        for path, content in file_contents.items():
            # Find README (case-insensitive)
             if path.lower() == 'readme.md': # Simple check, might need refinement for subdirs
                 readme_content = content
                 effective_logger.info("Found README.md, adding to summary input.")
                 summary_input_text += f"\n\nFile: {path}\n---\n{content}\n---"
                 break # Assume only one top-level README is needed for summary
        
        effective_logger.debug(f"Input text for summary generation length: {len(summary_input_text)}")
        
        # --- TODO: Review REPO_SUMMARY_INSTRUCTION --- 
        # Ensure the prompt clearly asks for high-level topics and summaries, 
        # and explicitly discourages returning full file contents in the summary response.
        # REPO_SUMMARY_INSTRUCTION = "... updated prompt ..."

        # 2. Generate Summaries (Using Gemini with potentially reduced input)
        effective_logger.info("Generating repository summary via Gemini...")
        summary_json = call_gemini_json(summary_input_text, REPO_SUMMARY_INSTRUCTION, gemini_api_key, effective_logger)
        if not summary_json or "topics" not in summary_json:
            effective_logger.error("Failed to generate repository summary from Gemini.")
            raise ValueError("Failed to generate repository summary from Gemini.")
        effective_logger.info(f"Generated summary for {len(summary_json['topics'])} topics.")

        # 3. Format Explanation & Prepare text for Relationship Extraction
        explanation = f"Analysis for {repo_url}:\n\n"
        summary_text_for_relations = ""
        for topic in summary_json.get('topics', []):
            topic_name = topic.get('topic', 'Unknown Topic')
            topic_summary = topic.get('summary', 'No summary.')
            explanation += f"**{topic_name}**\n{topic_summary}\n\n"
            summary_text_for_relations += f"Topic: {topic_name}\nSummary: {topic_summary}\n\n"

        # --- TODO: Review RELATIONSHIP_INSTRUCTION ---
        # Ensure this prompt works well with the generated summaries.
        # RELATIONSHIP_INSTRUCTION = "..."

        # 4. Extract Relationships (Using Gemini based on generated summaries)
        effective_logger.info("Extracting relationships via Gemini...")
        relationships_json = call_gemini_json(summary_text_for_relations, RELATIONSHIP_INSTRUCTION, gemini_api_key, effective_logger)
        if not relationships_json or "relationships" not in relationships_json:
             effective_logger.warning("Failed to extract relationships from Gemini, flowchart might be basic.")
             relationships_data = None
        else:
            relationships_data = relationships_json # Use the full dict
            effective_logger.info(f"Extracted {len(relationships_json.get('relationships',[]))} relationships.")

        # 5. Generate Mermaid Flowchart (UPDATED)
        effective_logger.info("Generating Mermaid flowchart...")
        mermaid_code = generate_mermaid_flowchart(relationships_data, effective_logger)
        
        effective_logger.info(f"Finished analysis for repo URL: {repo_url}")
        return {
            "explanation": explanation.strip(),
            "mindmap_markdown": mermaid_code,
            "repo_structure_text": repo_structure
        }

    except (ValueError, ConnectionError, RuntimeError, TimeoutError) as e:
         effective_logger.error(f"Analysis failed for {repo_url}: {e}")
         raise e
    except Exception as e:
        effective_logger.error(f"Unexpected error during GitHub repo analysis for {repo_url}: {e}", exc_info=True)
        raise RuntimeError(f"Unexpected analysis error: {e}") 