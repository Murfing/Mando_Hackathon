import requests
from bs4 import BeautifulSoup
import re
from urllib.parse import urljoin, urlparse
import logging
import time

# Get the logger instance
logger = logging.getLogger(__name__)

# TODO: Implement more robust link finding, filtering (avoid loops, respect robots.txt), error handling, and content extraction.
# TODO: Consider using a library like `scrapy` for more complex crawling needs.

MAX_DEPTH = 1       # Limit crawl depth to avoid infinite loops
MAX_LINKS = 10      # Limit number of links crawled per initial document
REQUEST_TIMEOUT = 10 # Seconds to wait for a response
USER_AGENT = 'Mozilla/5.0 (compatible; AIDocQABot/0.1; +http://example.com/botinfo)' # Be a good bot citizen

# --- Helper Functions ---

def is_valid_url(url, visited_urls):
    """Basic check for valid, crawlable URLs (HTTP/HTTPS, not visited)."""
    try:
        parsed = urlparse(url)
        # Ensure it's http/https, has a domain, and not already visited
        is_web_url = parsed.scheme in ["http", "https"] and parsed.netloc
        not_visited = url not in visited_urls
        return is_web_url and not_visited
    except Exception as e:
        logger.warning(f"Could not parse URL '{url}': {e}")
        return False

def extract_text_from_html(html_content: str) -> str:
    """Extracts text content from HTML, removing scripts and styles."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()

        # Get text, stripping leading/trailing whitespace
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        # Drop blank lines
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        content = '\n'.join(chunk for chunk in chunks if chunk)
        return content
    except Exception as e:
        logger.error(f"Error parsing HTML content: {e}", exc_info=True)
        return ""

# --- Main Crawling Logic ---

def crawl_url(url: str, visited_urls: set, depth: int = 0) -> str:
    """Fetches and extracts text content from a single URL."""
    if depth > MAX_DEPTH or not is_valid_url(url, visited_urls):
        if depth > MAX_DEPTH:
            logger.debug(f"Skipping crawl: Max depth ({MAX_DEPTH}) reached for URL: {url}")
        return ""

    visited_urls.add(url)
    logger.info(f"Crawling [Depth {depth}]: {url}")
    content = ""
    try:
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(url, timeout=REQUEST_TIMEOUT, headers=headers, allow_redirects=True)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        # Check content type - only parse HTML
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' in content_type:
            html_content = response.content
            logger.debug(f"Successfully fetched HTML content ({len(html_content)} bytes) from {url}")
            content = extract_text_from_html(html_content)
            logger.debug(f"Extracted {len(content)} characters of text from {url}")
            
            # Optional: Find and crawl further links (handle with care)
            # Consider doing this outside the recursive call for better control
            # soup = BeautifulSoup(html_content, 'html.parser')
            # for link in soup.find_all('a', href=True):
            #     next_url = urljoin(url, link['href'])
            #     content += crawl_url(next_url, visited_urls, depth + 1)
        else:
            logger.info(f"Skipping non-HTML content ('{content_type}') at: {url}")

    except requests.exceptions.Timeout:
         logger.warning(f"Timeout occurred while crawling {url} (>{REQUEST_TIMEOUT}s)")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to crawl {url}: {e}") # Log as warning, not error, as links can be dead
    except Exception as e:
        # Catch any other unexpected errors during processing
        logger.error(f"Unexpected error processing content from {url}: {e}", exc_info=True)
    
    # Add a small delay to be polite to servers
    time.sleep(0.5) 

    return content

def find_links_in_text(text: str, base_url: str = None) -> list[str]:
    """Extracts potential absolute URLs from text content."""
    # Regex for finding URLs - can be complex, this is a simplified version
    # It might find URLs within JavaScript or CSS if not properly cleaned
    url_pattern = re.compile(r'https?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
    found_urls = url_pattern.findall(text)
    
    absolute_urls = set()
    for url in found_urls:
        try:
            # Ensure the URL is absolute. If a base_url is provided, resolve relative URLs (though regex finds absolute).
            abs_url = urljoin(base_url, url) if base_url else url 
            # Basic filtering: avoid mailto, ftp, etc.
            if urlparse(abs_url).scheme in ['http', 'https']:
                absolute_urls.add(abs_url)
        except ValueError:
             logger.debug(f"Could not parse or resolve found URL fragment: {url}")
             
    logger.debug(f"Found {len(found_urls)} potential URL strings, resolved to {len(absolute_urls)} absolute HTTP/S URLs.")
    return list(absolute_urls)

def crawl_links(initial_content: str) -> str:
    """
    Finds links in the initial text and crawls them (up to MAX_DEPTH, MAX_LINKS).
    Returns the aggregated text content from crawled pages.
    Note: This is a basic implementation. Consider potential issues:
    - Robots.txt not checked.
    - Crawl traps (infinite links).
    - Performance for many links.
    """
    visited_urls = set() # Keep track of visited URLs *within this crawl operation*
    links_to_crawl = find_links_in_text(initial_content)
    
    if not links_to_crawl:
        logger.info("No links found in initial content to crawl.")
        return ""
        
    logger.info(f"Found {len(links_to_crawl)} potential links to crawl. Will crawl up to {MAX_LINKS} links.")
    
    aggregated_crawled_text = ""
    crawled_count = 0
    
    for link in links_to_crawl:
        if crawled_count >= MAX_LINKS:
             logger.info(f"Reached max links limit ({MAX_LINKS}). Stopping crawl.")
             break
             
        if is_valid_url(link, visited_urls):
            crawled_text = crawl_url(link, visited_urls, depth=0)
            if crawled_text:
                aggregated_crawled_text += f"\n\n--- Content from {link} ---\n\n" + crawled_text
                crawled_count += 1
        else:
             logger.debug(f"Skipping invalid or already visited link: {link}")
             
    logger.info(f"Finished crawling. Aggregated text length: {len(aggregated_crawled_text)} from {crawled_count} links.")
    return aggregated_crawled_text 