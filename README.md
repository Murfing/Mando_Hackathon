<div align="center">
  <img src="frontend/assets/logo.png" alt="NeuraParse Logo" width="200"/>
  <h1>NeuraParse</h1>
</div>

# NeuraParse - AI Document Q&A & Visualizer

This project implements a system for answering questions based on uploaded documents (Document Q&A) and for generating visual mind maps and explanations for GitHub repositories or PDF documents (Visualizer), leveraging Retrieval-Augmented Generation (RAG) with Google's Gemini AI and incorporating concepts from MindPalace.

---

## ✨ Features

*   **Document Q&A:**
    *   Upload multiple documents (`.pdf`, `.docx`, `.txt`, etc.).
    *   Ask questions about the content.
    *   Receive AI-generated answers based *only* on document context.
    *   View source snippets used for the answer.
*   **Visualizer (MindPalace Integration):**
    *   Analyze a public GitHub repository via URL.
    *   Analyze an uploaded PDF document.
    *   Generates a text explanation/summary.
    *   Generates an interactive mind map visualizing the structure/content (using Markmap.js).
*   **Common Features:**
    *   Wide file type support including OCR for images and scanned PDFs.
    *   Vector indexing (FAISS) for efficient semantic search in Q&A.
    *   Modern web interface with separate sections for Q&A and Visualizer.

---

## 🛠️ Tech Stack

*   **Backend:** Python, FastAPI, Uvicorn
*   **AI:** Google Generative AI (Gemini), MistralAI (Optional, for Visualizer)
*   **Vector Store:** FAISS (`faiss-cpu`)
*   **File Processing:** PyMuPDF, python-docx, etc., pytesseract (for OCR)
*   **Web Scraping (Visualizer):** Requests, BeautifulSoup4
*   **Frontend:** HTML, CSS, JavaScript
*   **Mind Map Rendering:** Markmap.js (via CDN)
*   **Environment:** python-dotenv

---

## 🚀 Getting Started

### Prerequisites

*   Python 3.9+
*   Pip & Venv
*   Git
*   Tesseract OCR (See Step 4 below)
*   Google Gemini API Key (Required)
*   GitHub Access Token (Recommended for Visualizer)
*   Mistral API Key (Optional, if Visualizer implementation uses it)

### Setup Instructions

1.  **Clone:** `git clone <url>` and `cd ai-doc-qa-system`
2.  **Create & Activate Venv:** (See previous README version for specific commands)
3.  **Install Dependencies:** `pip install -r requirements.txt`
4.  **Install Tesseract OCR:** Follow OS-specific instructions from [Tesseract Docs](https://tesseract-ocr.github.io/tessdoc/Installation.html) and ensure it's in PATH.
5.  **Configure Environment Variables (`.env` file):**
      ```dotenv
      # --- Required --- 
      GEMINI_API_KEY="YOUR_ACTUAL_GEMINI_API_KEY"

      # --- Optional / Recommended --- 
      # Visualizer Specific Keys
      GITHUB_ACCESS_TOKEN="YOUR_GITHUB_PAT_OR_LEAVE_BLANK" # For higher rate limits / private repos
      MISTRAL_API_KEY="YOUR_MISTRAL_API_KEY_OR_LEAVE_BLANK" # If visualizer logic needs it

      # Q&A / General Configuration
      UPLOAD_DIR="backend/data/uploads"
      PROCESSED_DIR="backend/data/processed"
      VECTOR_STORE_PATH="backend/data/processed/vector_store"
      LOG_LEVEL="INFO"
      TESSERACT_CMD="" # Optional: Path if tesseract not in system PATH
      ```

### Running the Application

1.  **Start Backend:** `uvicorn backend.app:app --reload --port 8000` (from project root, venv active)
2.  **Access Frontend:** Open `http://localhost:8000/` in your browser.

---

## 📝 Usage

*   Use the **Document Q&A** / **Visualizer** buttons at the top to switch modes.
*   **Document Q&A:** Upload files, wait for processing, ask questions.
*   **Visualizer:** Enter a GitHub URL *or* upload a PDF, click "Generate Visualization", view explanation and mind map.

---

## 🔮 Future Improvements (TODO)

- [ ] **Asynchronous Processing:** Implement background tasks for uploads and analysis.
- [ ] **Error Handling & UI Feedback:** Improve reporting for processing errors.
- [ ] **Search/Retrieval:** Hybrid search, metadata filtering.
- [ ] **Deployment:** Containerize (Docker).
- [ ] **Multi-User:** Authentication/sessions.
- [ ] **Context Management:** Token limits.
- [ ] **UI Polish:** Loading indicators, source distinction.

---

## 📊 What is happening

<div align="center">
  <img src="frontend/assets/image.png" alt="Application screenshot" width="800"/>
</div> 