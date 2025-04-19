import logging
import sys
import time # Added for Timer
import re # Added for sanitize_filename

# --- Logging Setup ---
# It's generally recommended to get specific loggers rather than configuring the root logger directly,
# especially in library code, but for application-level setup, basicConfig is often sufficient.

log_levels = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL
}

def setup_logging(level_str: str = "INFO"):
    """Configures basic stream logging for the application.
    Call this once at the beginning of your application (e.g., in app.py).
    """
    level = log_levels.get(level_str.lower(), logging.INFO)
    log_format = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    logging.basicConfig(level=level, format=log_format, stream=sys.stdout)
    
    # Optionally reduce noise from verbose libraries
    logging.getLogger("httpx").setLevel(logging.WARNING) # httpx used by fastapi test client and potentially others
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING) # Pillow library used by PIL
    logging.getLogger("pytesseract").setLevel(logging.INFO) # Keep tesseract info for debugging

    # Get the root logger instance
    logger = logging.getLogger()
    logger.info(f"Logging configured with level: {logging.getLevelName(level)}")
    return logger

# --- Common Utility Functions ---

def sanitize_filename(filename: str) -> str:
    """Remove potentially problematic characters from a filename."""
    # Remove or replace characters like / \ : * ? " < > |
    sanitized = re.sub(r'[/\\:*?"<>|]', '_', filename)
    # Optional: Limit length, remove leading/trailing dots or spaces
    sanitized = sanitized.strip('. ')
    # Ensure it's not empty after sanitization
    if not sanitized:
        sanitized = "sanitized_empty_filename"
    return sanitized[:200] # Limit length

class Timer:
    """Context manager for timing code blocks."""
    def __init__(self, logger: logging.Logger = None, name: str = "Code block"):
        self.logger = logger
        self.name = name

    def __enter__(self):
        self.start = time.perf_counter()
        if self.logger:
            self.logger.debug(f"Starting timer for: {self.name}")
        return self

    def __exit__(self, *args):
        self.end = time.perf_counter()
        self.interval = self.end - self.start
        message = f"{self.name} executed in: {self.interval:.4f} seconds"
        if self.logger:
            self.logger.info(message)
        else:
            print(message)

# Example: Function to sanitize filenames (useful before saving uploads)
# import re
# def sanitize_filename(filename: str) -> str:
#     """Remove potentially problematic characters from a filename."""
#     # Remove or replace characters like / \ : * ? " < > |
#     sanitized = re.sub(r'[/\\:*?"<>|]', '_', filename)
#     # Optional: Limit length, remove leading/trailing dots or spaces
#     sanitized = sanitized.strip('. ')
#     return sanitized[:200] # Limit length

# Example: Timer utility
# import time
# class Timer:
#     def __enter__(self):
#         self.start = time.perf_counter()
#         return self
#     def __exit__(self, *args):
#         self.end = time.perf_counter()
#         self.interval = self.end - self.start
#         print(f"Code block executed in: {self.interval:.4f} seconds") 