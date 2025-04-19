// --- Configuration ---
// API_BASE_URL is now relative to the frontend's origin since it's served by the same server
// We just need the /api prefix
const API_PREFIX = '/api';

// --- DOM Elements ---
const uploadForm = document.getElementById('upload-form');
const fileInput = document.getElementById('file-input');
const uploadButton = document.getElementById('upload-button');
const uploadStatusDiv = document.getElementById('upload-status');
const selectedFilesContainer = document.getElementById('selected-files-container');
const fileInputLabel = document.querySelector('.file-input-label');
const originalFileInputLabelText = fileInputLabel ? fileInputLabel.textContent : 'Choose files...';

const queryForm = document.getElementById('query-form');
const questionInput = document.getElementById('question-input');
const queryButton = document.getElementById('query-button');
const queryStatusDiv = document.getElementById('query-status');
const answerContainer = document.getElementById('answer-container');
const answerTextP = document.getElementById('answer-text');
const sourcesListUl = document.getElementById('sources-list');

// --- Helper Functions ---
function showStatus(element, message, type = 'loading') {
    element.textContent = message;
    element.className = `status ${type}`; // Add type class (loading, success, error)
}

function hideStatus(element) {
    element.textContent = '';
    element.className = 'status'; // Remove type classes
}

function disableForm(form, disable = true) {
    const elements = form.elements;
    for (let i = 0; i < elements.length; i++) {
        elements[i].disabled = disable;
    }
}

// --- Event Listeners ---

// NEW: Display selected file names
if (fileInput && selectedFilesContainer && fileInputLabel) {
    fileInput.addEventListener('change', () => {
        selectedFilesContainer.innerHTML = '';
        
        const files = fileInput.files;
        if (files && files.length > 0) {
            const list = document.createElement('ul');
            list.className = 'selected-files-list';
            
            Array.from(files).forEach(file => {
                const listItem = document.createElement('li');
                listItem.textContent = file.name; 
                list.appendChild(listItem);
            });
            
            selectedFilesContainer.appendChild(list);
            fileInputLabel.textContent = `${files.length} file(s) selected`;
        } else {
            fileInputLabel.textContent = originalFileInputLabelText; 
        }
        hideStatus(uploadStatusDiv);
    });
} else {
    console.error('Could not find necessary elements for file list display (fileInput, selectedFilesContainer, or fileInputLabel).');
}

// File Upload Form Submission
uploadForm.addEventListener('submit', async (event) => {
    event.preventDefault(); // Prevent default form submission

    const files = fileInput.files;
    if (!files || files.length === 0) {
        showStatus(uploadStatusDiv, 'Please select at least one file.', 'error');
        return;
    }

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
        formData.append('files', files[i]);
    }

    showStatus(uploadStatusDiv, `Uploading ${files.length} file(s)...`, 'loading');
    disableForm(uploadForm, true);
    answerContainer.classList.add('hidden'); // Hide previous answer
    hideStatus(queryStatusDiv);

    try {
        const response = await fetch(`${API_PREFIX}/upload/`, {
            method: 'POST',
            body: formData,
            // 'Content-Type': 'multipart/form-data' is set automatically by browser for FormData
        });

        const result = await response.json();

        if (!response.ok) {
            // Handle HTTP errors (like 4xx, 5xx)
            console.error('Upload Error Response:', result);
            throw new Error(result.detail || `HTTP error ${response.status}`);
        }

        console.log('Upload Success Response:', result);
        showStatus(uploadStatusDiv, result.message || 'Upload successful!', 'success');
        // Optionally display more details from result.results
        uploadForm.reset(); // Clear the form
        

    } catch (error) {
        console.error('Upload Fetch Error:', error);
        showStatus(uploadStatusDiv, `Upload failed: ${error.message}`, 'error');
    } finally {
        disableForm(uploadForm, false);
    }
});

// Query Form Submission
queryForm.addEventListener('submit', async (event) => {
    event.preventDefault();

    const question = questionInput.value.trim();
    if (!question) {
        showStatus(queryStatusDiv, 'Please enter a question.', 'error');
        return;
    }

    showStatus(queryStatusDiv, 'Asking AI...', 'loading');
    disableForm(queryForm, true);
    answerContainer.classList.add('hidden'); // Hide previous answer while loading
    answerTextP.textContent = '';
    sourcesListUl.innerHTML = '';

    try {
        const response = await fetch(`${API_PREFIX}/query/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ question: question }),
        });

        const result = await response.json();

        if (!response.ok) {
            console.error('Query Error Response:', result);
            throw new Error(result.detail || `HTTP error ${response.status}`);
        }

        console.log('Query Success Response:', result);
        hideStatus(queryStatusDiv); // Hide loading status

        // Display Answer
        answerTextP.textContent = result.answer || 'No answer provided.';

        // Display Sources
        sourcesListUl.innerHTML = ''; // Clear previous sources
        if (result.sources && result.sources.length > 0) {
            result.sources.forEach(source => {
                const li = document.createElement('li');

                const sourceInfo = document.createElement('strong');
                sourceInfo.textContent = `Source: ${source.metadata?.source || 'Unknown'}`;
                if (source.metadata?.chunk_index !== undefined) {
                    sourceInfo.textContent += ` (Chunk ${source.metadata.chunk_index})`;
                }
                 if (source.score !== undefined && source.score !== null) {
                    sourceInfo.textContent += ` | Score: ${source.score.toFixed(4)}`;
                }
                li.appendChild(sourceInfo);

                const snippet = document.createElement('blockquote');
                snippet.textContent = `"${source.content_snippet}"`;
                li.appendChild(snippet);

                sourcesListUl.appendChild(li);
            });
        } else {
            const li = document.createElement('li');
            li.textContent = 'No sources provided.';
            sourcesListUl.appendChild(li);
        }

        answerContainer.classList.remove('hidden'); // Show the answer section

    } catch (error) {
        console.error('Query Fetch Error:', error);
        showStatus(queryStatusDiv, `Query failed: ${error.message}`, 'error');
        answerContainer.classList.add('hidden'); // Ensure answer is hidden on error
    } finally {
        disableForm(queryForm, false);
    }
}); 