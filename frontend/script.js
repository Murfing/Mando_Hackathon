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

// Navigation Elements
const navQaButton = document.getElementById('nav-qa');
const navVisualizerButton = document.getElementById('nav-visualizer');

// Page Containers
const qaPage = document.getElementById('qa-page');
const visualizerPage = document.getElementById('visualizer-page');

// Visualizer Page Elements (Get references for later)
const visualizerForm = document.getElementById('visualizer-form');
const githubUrlInput = document.getElementById('github-url');
const pdfVisualInput = document.getElementById('pdf-visual-input');
const visualPdfList = document.getElementById('visual-pdf-list');
const visualizeButton = document.getElementById('visualize-button');
const visualizerStatusDiv = document.getElementById('visualizer-status');
const visualizerOutputCard = document.querySelector('.visualizer-output-card');
const visualizerMindmapContainer = document.getElementById('visualizer-mindmap-container');
const visualizerExplanationDiv = document.getElementById('visualizer-explanation');
const visualizerMindmapDiv = document.getElementById('visualizer-mindmap');

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

// --- Page Navigation Logic ---
function setActivePage(pageId) {
    console.log(`Switching to page: ${pageId}`); // Add logging for debugging
    
    // Hide all pages
    [qaPage, visualizerPage].forEach(page => {
        if (page) {
            page.classList.remove('active-page');
            console.log(`Removed active-page from ${page.id}`);
        }
    });
    
    // Deactivate all nav buttons
    [navQaButton, navVisualizerButton].forEach(button => {
        if (button) {
            button.classList.remove('active');
            console.log(`Removed active from nav button`);
        }
    });

    // Activate the selected page and button
    if (pageId === 'qa') {
        if (qaPage) {
            qaPage.classList.add('active-page');
            console.log('Activated QA page');
        }
        if (navQaButton) {
            navQaButton.classList.add('active');
            console.log('Activated QA nav button');
        }
    } else if (pageId === 'visualizer') {
        if (visualizerPage) {
            visualizerPage.classList.add('active-page');
            console.log('Activated Visualizer page');
        }
        if (navVisualizerButton) {
            navVisualizerButton.classList.add('active');
            console.log('Activated Visualizer nav button');
        }
    }
}

if (navQaButton) {
    navQaButton.addEventListener('click', () => {
        console.log('QA nav button clicked');
        setActivePage('qa');
    });
}

if (navVisualizerButton) {
    navVisualizerButton.addEventListener('click', () => {
        console.log('Visualizer nav button clicked');
        setActivePage('visualizer');
    });
}

// Initialize the default page (Q&A) when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, initializing default page');
    setActivePage('qa');
});

// --- Event Listeners (Existing Q&A + New Placeholders) ---

// ADDED: Trigger file input click when the custom label is clicked (for Q&A)
if (fileInput && fileInputLabel) {
    fileInputLabel.addEventListener('click', () => {
        fileInput.click(); // Programmatically click the hidden file input
    });
}

// Q&A: Display selected file names
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
    console.error('Could not find necessary elements for Q&A file list display.');
}

// Q&A: File Upload Form Submission
if (uploadForm) {
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
            });

            const result = await response.json();

            if (!response.ok) {
                console.error('Upload Error Response:', result);
                throw new Error(result.detail || `HTTP error ${response.status}`);
            }
            
            console.log('Upload Success Response:', result);
            showStatus(uploadStatusDiv, result.message || 'Upload successful!', 'success');
            uploadForm.reset(); // Clear the form
            if (selectedFilesContainer) selectedFilesContainer.innerHTML = ''; 
            if (fileInputLabel) fileInputLabel.textContent = originalFileInputLabelText;
            
        } catch (error) {
            console.error('Upload Fetch Error:', error);
            showStatus(uploadStatusDiv, `Upload failed: ${error.message}`, 'error');
        } finally {
            disableForm(uploadForm, false);
        }
    });
} else {
    console.error("Could not find upload form element.");
}

// Q&A: Query Form Submission
if(queryForm) {
    queryForm.addEventListener('submit', async (event) => {
        event.preventDefault();

        const question = questionInput.value.trim();
        if (!question) {
            showStatus(queryStatusDiv, 'Please enter a question.', 'error');
            return;
        }

        showStatus(queryStatusDiv, 'Asking AI...', 'loading');
        disableForm(queryForm, true);
        answerContainer.classList.add('hidden');
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
            hideStatus(queryStatusDiv);

            answerTextP.textContent = result.answer || 'No answer provided.';

            sourcesListUl.innerHTML = '';
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

            answerContainer.classList.remove('hidden');

        } catch (error) {
            console.error('Query Fetch Error:', error);
            showStatus(queryStatusDiv, `Query failed: ${error.message}`, 'error');
            answerContainer.classList.add('hidden');
        } finally {
            disableForm(queryForm, false);
        }
    });
} else {
    console.error("Could not find query form element.");
}

// --- Visualizer Page Listeners ---

// ADDED: Trigger file input click when the custom label is clicked (for Visualizer)
if (pdfVisualInput) {
    const visualFileInputLabel = pdfVisualInput.nextElementSibling; // Assumes label is next sibling span
    if (visualFileInputLabel && visualFileInputLabel.classList.contains('file-input-label')) {
        visualFileInputLabel.addEventListener('click', () => {
             pdfVisualInput.click(); // Programmatically click the hidden file input
        });
    } else {
        console.error('Could not find the custom file input label for the visualizer PDF input, or it lacks the expected class.');
    }
}

// Visualizer: Display selected PDF filename
if (pdfVisualInput && visualPdfList) {
    const visualFileInputLabel = pdfVisualInput.nextElementSibling; // Assumes label is sibling
    const originalVisualLabel = visualFileInputLabel ? visualFileInputLabel.textContent : 'Choose PDF file...';

    pdfVisualInput.addEventListener('change', () => {
        visualPdfList.innerHTML = '';
        const file = pdfVisualInput.files[0];
        if (file) {
            const listItem = document.createElement('div');
            listItem.textContent = `Selected: ${file.name}`;
            visualPdfList.appendChild(listItem);
            if (visualFileInputLabel) visualFileInputLabel.textContent = '1 PDF selected';
            // Clear the URL input if a PDF is chosen
            if (githubUrlInput) githubUrlInput.value = '';
            hideStatus(visualizerStatusDiv);
        } else {
            if (visualFileInputLabel) visualFileInputLabel.textContent = originalVisualLabel;
        }
    });
} else {
    console.error('Could not find necessary elements for Visualizer PDF list display.');
}

// Visualizer: Clear PDF input if URL is typed
if (githubUrlInput && pdfVisualInput) {
    githubUrlInput.addEventListener('input', () => {
        if (githubUrlInput.value.trim() !== '') {
            pdfVisualInput.value = ''; // Clear the file input
            if (visualPdfList) visualPdfList.innerHTML = ''; // Clear the displayed list
            const visualFileInputLabel = pdfVisualInput.nextElementSibling;
            const originalVisualLabel = visualFileInputLabel ? visualFileInputLabel.dataset.originalText || 'Choose PDF file...' : 'Choose PDF file...';
             if (visualFileInputLabel) {
                 visualFileInputLabel.textContent = originalVisualLabel; // Reset label text
                 if(!visualFileInputLabel.dataset.originalText) visualFileInputLabel.dataset.originalText = originalVisualLabel; // Store original if not done yet
             }
        }
    });
}

// Visualizer: Form Submission
if (visualizerForm && githubUrlInput && pdfVisualInput && visualizerStatusDiv && visualizerOutputCard && visualizerMindmapContainer && visualizerExplanationDiv && visualizerMindmapDiv) {
    visualizerForm.addEventListener('submit', async (event) => {
        event.preventDefault();

        const githubUrl = githubUrlInput.value.trim();
        const pdfFile = pdfVisualInput.files[0];

        if (!githubUrl && !pdfFile) {
            showStatus(visualizerStatusDiv, 'Please enter a GitHub URL or select a PDF file.', 'error');
            return;
        }
        if (githubUrl && pdfFile) {
            showStatus(visualizerStatusDiv, 'Please provide either a GitHub URL or a PDF, not both.', 'error');
            return;
        }

        showStatus(visualizerStatusDiv, 'Analyzing and generating visualization...', 'loading');
        disableForm(visualizerForm, true);
        visualizerOutputCard.classList.add('hidden');
        visualizerMindmapContainer.classList.add('hidden');
        visualizerExplanationDiv.innerHTML = '';
        visualizerMindmapDiv.innerHTML = ''; // Clear previous content

        let endpoint = '';
        let body = null;
        let headers = {};

        try {
            if (githubUrl) {
                endpoint = `${API_PREFIX}/analyze_repo`;
                body = JSON.stringify({ github_url: githubUrl });
                headers = { 'Content-Type': 'application/json' };
            } else if (pdfFile) {
                endpoint = `${API_PREFIX}/analyze_pdf`;
                const formData = new FormData();
                formData.append('file', pdfFile);
                body = formData;
                // No Content-Type header needed for FormData, browser sets it
            }

            const response = await fetch(endpoint, {
                method: 'POST',
                headers: headers,
                body: body,
            });

            const result = await response.json();

            if (!response.ok) {
                console.error('Visualizer Error Response:', result);
                throw new Error(result.detail || `Analysis failed (HTTP ${response.status})`);
            }

            console.log('Visualizer Success Response:', result);
            hideStatus(visualizerStatusDiv);

            visualizerExplanationDiv.textContent = result.explanation || 'No explanation provided.';
            visualizerMindmapDiv.innerHTML = ''; // Clear previous content
            const mermaidCode = result.mindmap_markdown;

            if (mermaidCode && typeof mermaid !== 'undefined') {
                console.log("Received Mermaid code:", mermaidCode);
                const mermaidContainerId = 'mermaid-temp-render-' + Date.now(); 

                try {
                    console.log(`Attempting to render Mermaid code for temporary ID: ${mermaidContainerId}`);
                    const { svg, bindFunctions } = await mermaid.render(mermaidContainerId, mermaidCode);
                    console.log(`Mermaid rendering returned SVG (length: ${svg?.length}).`);

                    if (svg) {
                        // Clear existing content first
                        visualizerMindmapDiv.innerHTML = '';
                        
                        // Create a zoom wrapper div with proper class
                        const zoomWrapper = document.createElement('div');
                        zoomWrapper.className = 'zoom-content';
                        zoomWrapper.style.transformOrigin = 'top left';
                        zoomWrapper.style.position = 'relative';
                        zoomWrapper.style.width = 'fit-content';
                        zoomWrapper.style.minWidth = '100%';
                        
                        // Add wrapper to container
                        visualizerMindmapDiv.appendChild(zoomWrapper);
                        
                        // Set SVG inside the zoom wrapper
                        zoomWrapper.innerHTML = svg;
                        console.log("Mermaid flowchart SVG injected into zoom wrapper inside #visualizer-mindmap.");
                        
                        // Initialize panning immediately after rendering
                        setTimeout(() => {
                            console.log("Attempting to initialize panning...");
                            if (typeof initPanControls === 'function') {
                                initPanControls();
                                console.log("Pan controls initialized");
                            }
                        }, 500);
                    } else {
                        throw new Error("Mermaid.render() did not return SVG content.");
                    }
                    
                } catch (renderError) {
                    console.error("Error rendering Mermaid flowchart:", renderError);
                    visualizerMindmapDiv.innerHTML = 
                        `<p class="error">Error rendering flowchart:</p><p class="error-message">${renderError.message || 'Unknown error'}</p><p>Raw Mermaid Code:</p><pre><code>${mermaidCode || 'No Mermaid code available'}</code></pre>`;
                    showStatus(visualizerStatusDiv, 'Analysis complete, but flowchart rendering failed.', 'error');
                }
            } else {
                visualizerMindmapDiv.textContent = 'No flowchart data available or Mermaid library not loaded.';
                if (typeof mermaid === 'undefined') console.error("Mermaid library (mermaid) not found!");
                if (!mermaidCode) console.log("No Mermaid code string received from backend.");
            }

            visualizerOutputCard.classList.remove('hidden');
            visualizerMindmapContainer.classList.remove('hidden');

        } catch (error) {
            console.error('Visualizer Fetch/Processing Error:', error);
            showStatus(visualizerStatusDiv, `Visualization failed: ${error.message}`, 'error');
            visualizerOutputCard.classList.add('hidden');
            visualizerMindmapContainer.classList.add('hidden');
        } finally {
            disableForm(visualizerForm, false);
        }
    });
} else {
    console.error('Could not find all necessary elements for Visualizer form submission.');
}

// --- Visualization Enhancement Features ---
// Define global variables accessible to form handler
let initPanControls; // Will be defined in the DOMContentLoaded handler

// Update the zoom and fullscreen functionality
document.addEventListener('DOMContentLoaded', function() {
    const mindmapContainer = document.getElementById('visualizer-mindmap');
    const zoomInBtn = document.getElementById('zoom-in');
    const zoomOutBtn = document.getElementById('zoom-out');
    const resetZoomBtn = document.getElementById('reset-zoom');
    const fullscreenToggle = document.getElementById('fullscreen-toggle');
    
    // Initialize zoom level
    let currentZoom = 1.0;
    const zoomStep = 0.2;
    const minZoom = 0.5;
    const maxZoom = 3.0;
    
    // Initialize pan state
    let isPanning = false;
    let startX, startY;
    let translateX = 0, translateY = 0;
    
    // Function to update zoom and position
    function updateTransform() {
        if (mindmapContainer) {
            // Find the zoom wrapper inside the container
            const zoomWrapper = mindmapContainer.querySelector('.zoom-content');
            if (zoomWrapper) {
                zoomWrapper.style.transition = isPanning ? 'none' : 'transform 0.3s ease';
                zoomWrapper.style.transform = `translate(${translateX}px, ${translateY}px) scale(${currentZoom})`;
                console.log(`Transform updated: scale=${currentZoom}, translate(${translateX}px, ${translateY}px)`);
            } else {
                console.warn('Zoom wrapper not found in mindmap container');
            }
        }
    }
    
    // Define initPanControls globally so it can be called after rendering
    initPanControls = function() {
        console.log("initPanControls called");
        
        // Remove any existing listeners to prevent duplicates
        mindmapContainer.removeEventListener('mousedown', startPan);
        document.removeEventListener('mousemove', pan);
        document.removeEventListener('mouseup', endPan);
        
        // Set cursor style to indicate draggable
        mindmapContainer.style.cursor = 'grab';
        
        // Declare event handler functions
        function startPan(e) {
            console.log("Mouse down detected");
            // Only start pan if not clicking on a control button
            if (e.target.closest('.control-button') || e.target.closest('.mindmap-controls')) {
                console.log("Clicked on control, ignoring pan");
                return;
            }
            
            e.preventDefault();
            isPanning = true;
            mindmapContainer.style.cursor = 'grabbing';
            startX = e.clientX - translateX;
            startY = e.clientY - translateY;
            console.log(`Pan started at ${startX}, ${startY}`);
        }
        
        function pan(e) {
            if (!isPanning) return;
            e.preventDefault();
            
            translateX = e.clientX - startX;
            translateY = e.clientY - startY;
            console.log(`Panning to ${translateX}, ${translateY}`);
            updateTransform();
        }
        
        function endPan(e) {
            if (!isPanning) return;
            console.log("Panning ended");
            isPanning = false;
            mindmapContainer.style.cursor = 'grab';
        }
        
        // Add mouse event listeners
        mindmapContainer.addEventListener('mousedown', startPan);
        document.addEventListener('mousemove', pan);
        document.addEventListener('mouseup', endPan);
        
        // Touch Events (simplified)
        mindmapContainer.addEventListener('touchstart', function(e) {
            if (e.target.closest('.control-button')) return;
            e.preventDefault();
            isPanning = true;
            const touch = e.touches[0];
            startX = touch.clientX - translateX;
            startY = touch.clientY - translateY;
            console.log("Touch pan started");
        });
        
        document.addEventListener('touchmove', function(e) {
            if (!isPanning) return;
            e.preventDefault();
            const touch = e.touches[0];
            translateX = touch.clientX - startX;
            translateY = touch.clientY - startY;
            updateTransform();
        });
        
        document.addEventListener('touchend', function() {
            isPanning = false;
            console.log("Touch pan ended");
        });
        
        console.log("Pan controls initialized successfully");
    };
    
    // Initialize pan controls if container exists
    if (mindmapContainer) {
        console.log("Mindmap container found, initializing pan controls");
        initPanControls();
    }
    
    // Zoom in handler
    if (zoomInBtn) {
        zoomInBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            if (currentZoom < maxZoom) {
                currentZoom += zoomStep;
                updateTransform();
            }
        });
    }
    
    // Zoom out handler
    if (zoomOutBtn) {
        zoomOutBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            if (currentZoom > minZoom) {
                currentZoom -= zoomStep;
                updateTransform();
            }
        });
    }
    
    // Reset zoom and pan handler
    if (resetZoomBtn) {
        resetZoomBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            currentZoom = 1.0;
            translateX = 0;
            translateY = 0;
            updateTransform();
            
            // Keep fullscreen logic
            if (document.fullscreenElement) {
                return;
            }
            
            const container = document.getElementById('visualizer-mindmap-container');
            if (container && container.classList.contains('fullscreen-mindmap')) {
                container.classList.remove('fullscreen-mindmap');
            }
        });
    }
    
    // Fullscreen toggle handler
    if (fullscreenToggle) {
        fullscreenToggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            
            const container = document.getElementById('visualizer-mindmap-container');
            if (!container) return;
            
            // Modern fullscreen API
            if (document.fullscreenEnabled) {
                if (!document.fullscreenElement) {
                    container.requestFullscreen().catch(err => {
                        console.error(`Error attempting to enable fullscreen: ${err.message}`);
                        container.classList.add('fullscreen-mindmap');
                    });
                } else {
                    document.exitFullscreen().catch(err => {
                        console.error(`Error attempting to exit fullscreen: ${err.message}`);
                        container.classList.remove('fullscreen-mindmap');
                    });
                }
            } else {
                container.classList.toggle('fullscreen-mindmap');
            }
        });
    }
    
    // Add mousewheel zoom support with target container
    if (mindmapContainer) {
        mindmapContainer.addEventListener('wheel', function(e) {
            if (e.ctrlKey) {
                e.preventDefault();
                
                // Calculate zoom point to keep focus
                const rect = mindmapContainer.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                
                const oldZoom = currentZoom;
                
                if (e.deltaY < 0 && currentZoom < maxZoom) {
                    currentZoom += zoomStep;
                } else if (e.deltaY > 0 && currentZoom > minZoom) {
                    currentZoom -= zoomStep;
                }
                
                // Adjust pan position to zoom toward mouse position
                const zoomFactor = currentZoom / oldZoom;
                translateX = x - (x - translateX) * zoomFactor;
                translateY = y - (y - translateY) * zoomFactor;
                
                updateTransform();
            }
        }, { passive: false });
    }
}); 