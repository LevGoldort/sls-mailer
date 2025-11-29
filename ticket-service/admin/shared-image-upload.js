// shared-image-upload.js - Reusable image upload component for ticket admin
// Supports drag & drop, file select, and Ctrl+V paste

const TICKETS_MEDIA_BUCKET = 'yallabalagan-ticket-media';
const AWS_REGION = 'eu-north-1';

// Inject CSS styles if not already present
if (!document.getElementById('image-upload-styles')) {
    const style = document.createElement('style');
    style.id = 'image-upload-styles';
    style.textContent = `
        .image-drop-zone {
            border: 3px dashed #667eea;
            border-radius: 12px;
            padding: 30px;
            text-align: center;
            background: #f8f9ff;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 15px;
        }
        .image-drop-zone.dragover {
            background: #e8ebff;
            border-color: #5568d3;
            transform: scale(1.02);
        }
        .drop-zone-icon {
            font-size: 36px;
            margin-bottom: 10px;
        }
        .image-drop-zone h4 {
            color: #667eea;
            margin-bottom: 8px;
            font-size: 16px;
        }
        .image-drop-zone p {
            color: #666;
            font-size: 13px;
            margin-bottom: 15px;
        }
        .upload-btn {
            display: inline-block;
            padding: 10px 20px;
            background: #667eea;
            color: white;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }
        .upload-btn:hover {
            background: #5568d3;
        }
        .file-input-hidden {
            display: none;
        }
        .paste-hint {
            text-align: center;
            color: #666;
            font-size: 12px;
            margin-bottom: 15px;
        }
        .uploaded-images {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
            gap: 12px;
            margin-top: 15px;
        }
        .image-upload-card {
            position: relative;
            border: 2px solid #ddd;
            border-radius: 8px;
            overflow: hidden;
            background: white;
        }
        .image-preview {
            width: 100%;
            height: 120px;
            object-fit: cover;
            display: block;
        }
        .upload-status {
            padding: 8px;
            text-align: center;
            font-size: 12px;
        }
        .upload-status.uploading {
            background: #fff3cd;
            color: #856404;
        }
        .upload-status.success {
            background: #d4edda;
            color: #155724;
        }
        .upload-status.error {
            background: #f8d7da;
            color: #721c24;
        }
        .upload-spinner {
            display: inline-block;
            width: 10px;
            height: 10px;
            border: 2px solid #856404;
            border-top-color: transparent;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 5px;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .image-url-display {
            padding: 8px;
            background: #f9f9f9;
            border-top: 1px solid #ddd;
        }
        .url-input-display {
            width: 100%;
            padding: 6px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 11px;
            margin-bottom: 6px;
            font-family: monospace;
        }
        .copy-url-btn, .remove-img-btn {
            padding: 5px 10px;
            border: none;
            border-radius: 4px;
            font-size: 11px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .copy-url-btn {
            background: #667eea;
            color: white;
            margin-right: 5px;
        }
        .copy-url-btn:hover {
            background: #5568d3;
        }
        .remove-img-btn {
            background: #f44336;
            color: white;
        }
        .remove-img-btn:hover {
            background: #da190b;
        }
    `;
    document.head.appendChild(style);
}

/**
 * Initialize image upload for a container
 * @param {string} containerId - ID of the container element
 * @param {string} folder - S3 folder (e.g., 'events' or 'locations')
 * @param {function} onUploadComplete - Callback with (url) when upload succeeds
 * @param {function} onUploadError - Callback with (error) when upload fails
 */
function initImageUpload(containerId, folder, onUploadComplete, onUploadError) {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Container #${containerId} not found`);
        return;
    }

    // Create drop zone HTML
    container.innerHTML = `
        <div class="image-drop-zone" id="${containerId}-drop-zone">
            <div class="drop-zone-icon">📸</div>
            <h4>Drop images here</h4>
            <p>or click to select files, or paste (Ctrl+V)</p>
            <label for="${containerId}-file-input" class="upload-btn">Select Images</label>
            <input type="file" id="${containerId}-file-input" class="file-input-hidden" accept="image/*" multiple>
        </div>
        <div class="paste-hint">💡 Tip: You can paste images from clipboard (Ctrl+V)</div>
        <div class="uploaded-images" id="${containerId}-uploaded"></div>
    `;

    const dropZone = document.getElementById(`${containerId}-drop-zone`);
    const fileInput = document.getElementById(`${containerId}-file-input`);
    const uploadedContainer = document.getElementById(`${containerId}-uploaded`);

    // Click to select files
    dropZone.addEventListener('click', (e) => {
        if (e.target !== fileInput) {
            fileInput.click();
        }
    });

    // File input change
    fileInput.addEventListener('change', (e) => {
        handleFiles(Array.from(e.target.files), folder, uploadedContainer, onUploadComplete, onUploadError);
        fileInput.value = ''; // Reset
    });

    // Drag and drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
        handleFiles(files, folder, uploadedContainer, onUploadComplete, onUploadError);
    });

    // Paste from clipboard
    document.addEventListener('paste', (e) => {
        const items = Array.from(e.clipboardData.items);
        const imageItems = items.filter(item => item.type.startsWith('image/'));

        if (imageItems.length > 0) {
            e.preventDefault();
            const files = imageItems.map(item => item.getAsFile());
            handleFiles(files, folder, uploadedContainer, onUploadComplete, onUploadError);
        }
    });
}

async function handleFiles(files, folder, container, onSuccess, onError) {
    for (const file of files) {
        await uploadImage(file, folder, container, onSuccess, onError);
    }
}

async function uploadImage(file, folder, container, onSuccess, onError) {
    const cardId = `img-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const card = createImageCard(cardId, file);
    container.appendChild(card);

    try {
        // Generate unique filename
        const timestamp = Date.now();
        const randomStr = Math.random().toString(36).substring(2, 8);
        const ext = file.name.split('.').pop();
        const filename = `${folder}/${timestamp}-${randomStr}.${ext}`;

        // Upload directly to S3 using AWS SDK or pre-signed URL
        // For now, we'll use a simple approach with public bucket
        const url = await uploadToS3(file, filename);

        updateImageCard(cardId, url, 'success');
        if (onSuccess) onSuccess(url);

    } catch (error) {
        console.error('Upload error:', error);
        updateImageCard(cardId, null, 'error', error.message);
        if (onError) onError(error);
    }
}

async function uploadToS3(file, filename) {
    // Convert file to base64 for upload
    return new Promise((resolve, reject) => {
        const reader = new FileReader();

        reader.onload = async function(e) {
            try {
                // Get admin API key from localStorage
                const adminKey = localStorage.getItem('admin_api_key');
                if (!adminKey) {
                    throw new Error('Admin API key not found. Please refresh the page.');
                }

                // For now, we'll use a Lambda endpoint to handle S3 upload
                // You could also use pre-signed URLs like in newsletter admin
                const arrayBuffer = e.target.result;
                const base64 = btoa(
                    new Uint8Array(arrayBuffer)
                        .reduce((data, byte) => data + String.fromCharCode(byte), '')
                );

                // Upload via API
                const response = await fetch(`https://ovajavet67.execute-api.eu-north-1.amazonaws.com/api/upload-image`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-API-Key': adminKey
                    },
                    body: JSON.stringify({
                        filename: filename,
                        contentType: file.type,
                        data: base64
                    })
                });

                if (!response.ok) {
                    throw new Error(`Upload failed: ${response.status}`);
                }

                const data = await response.json();
                resolve(data.url);

            } catch (error) {
                reject(error);
            }
        };

        reader.onerror = () => reject(new Error('Failed to read file'));
        reader.readAsArrayBuffer(file);
    });
}

function createImageCard(cardId, file) {
    const card = document.createElement('div');
    card.className = 'image-upload-card';
    card.id = cardId;

    const preview = document.createElement('img');
    preview.className = 'image-preview';
    preview.src = URL.createObjectURL(file);

    const status = document.createElement('div');
    status.className = 'upload-status uploading';
    status.innerHTML = '<div class="upload-spinner"></div><span>Uploading...</span>';

    card.appendChild(preview);
    card.appendChild(status);

    return card;
}

function updateImageCard(cardId, url, state, errorMsg = '') {
    const card = document.getElementById(cardId);
    const status = card.querySelector('.upload-status');

    if (state === 'success') {
        status.className = 'upload-status success';
        status.textContent = '✓ Uploaded';

        const urlDiv = document.createElement('div');
        urlDiv.className = 'image-url-display';
        urlDiv.innerHTML = `
            <input type="text" class="url-input-display" value="${url}" readonly>
            <button class="copy-url-btn" onclick="copyImageUrl('${url}', this)">Copy</button>
            <button class="remove-img-btn" onclick="removeImageCard('${cardId}')">×</button>
        `;
        card.appendChild(urlDiv);
    } else {
        status.className = 'upload-status error';
        status.textContent = `✗ ${errorMsg || 'Upload failed'}`;
    }
}

function copyImageUrl(url, btn) {
    navigator.clipboard.writeText(url).then(() => {
        const originalText = btn.textContent;
        btn.textContent = '✓ Copied';
        setTimeout(() => {
            btn.textContent = originalText;
        }, 2000);
    });
}

function removeImageCard(cardId) {
    const card = document.getElementById(cardId);
    if (card) card.remove();
}

// Google Maps URL parsing
function parseGoogleMapsUrl(url) {
    // Handle various Google Maps URL formats
    // Format 1: https://www.google.com/maps/place/@32.0853,34.7818,17z
    // Format 2: https://www.google.com/maps?q=32.0853,34.7818
    // Format 3: https://maps.app.goo.gl/... (short link, harder to parse without API)

    try {
        // Try to extract coordinates from URL
        const patterns = [
            /@(-?\d+\.\d+),(-?\d+\.\d+)/,  // @lat,lng
            /q=(-?\d+\.\d+),(-?\d+\.\d+)/,  // q=lat,lng
            /!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)/, // !3dlat!4dlng
        ];

        for (const pattern of patterns) {
            const match = url.match(pattern);
            if (match) {
                return {
                    lat: parseFloat(match[1]),
                    lng: parseFloat(match[2])
                };
            }
        }

        return null;
    } catch (error) {
        console.error('Error parsing Google Maps URL:', error);
        return null;
    }
}

// Helper to set coordinates from Google Maps URL
function setCoordinatesFromUrl(urlInputId, latInputId, lngInputId) {
    const urlInput = document.getElementById(urlInputId);
    const latInput = document.getElementById(latInputId);
    const lngInput = document.getElementById(lngInputId);

    urlInput.addEventListener('blur', () => {
        const url = urlInput.value.trim();
        if (!url) return;

        const coords = parseGoogleMapsUrl(url);
        if (coords) {
            latInput.value = coords.lat;
            lngInput.value = coords.lng;
            showToast('Координаты извлечены из ссылки Google Maps', 'success');
        } else {
            showToast('Не удалось извлечь координаты. Проверьте ссылку.', 'error');
        }
    });
}
