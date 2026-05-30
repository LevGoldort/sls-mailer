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
 * @param {object} options - Optional settings: { existingImages: [], onRemove: (url) => {} }
 */
function initImageUpload(containerId, folder, onUploadComplete, onUploadError, options = {}) {
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

    // Click to select files (skip label clicks — the label's `for` attr already opens the dialog)
    dropZone.addEventListener('click', (e) => {
        if (e.target.tagName === 'LABEL' || e.target === fileInput) return;
        fileInput.click();
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

    // Store options for remove callback
    container._imageUploadOptions = options;

    // Display existing images if provided
    if (options.existingImages && options.existingImages.length > 0) {
        options.existingImages.forEach(url => {
            addExistingImageCard(uploadedContainer, url, containerId, options.onRemove);
        });
    }
}

/**
 * Add a card for an existing image (already uploaded)
 */
function addExistingImageCard(container, url, containerId, onRemove) {
    const cardId = `img-existing-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    const card = document.createElement('div');
    card.className = 'image-upload-card';
    card.id = cardId;
    card.dataset.url = url;

    const preview = document.createElement('img');
    preview.className = 'image-preview';
    preview.src = url;
    preview.onerror = () => {
        preview.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><text y="50" x="50" text-anchor="middle" font-size="14">Image</text></svg>';
    };

    const status = document.createElement('div');
    status.className = 'upload-status success';
    status.textContent = '✓ Uploaded';

    const urlDiv = document.createElement('div');
    urlDiv.className = 'image-url-display';
    urlDiv.innerHTML = `
        <input type="text" class="url-input-display" value="${url}" readonly>
        <button class="copy-url-btn" onclick="copyImageUrl('${url}', this)">Copy</button>
        <button class="remove-img-btn" onclick="removeImageCardWithCallback('${cardId}', '${url}')">×</button>
    `;

    card.appendChild(preview);
    card.appendChild(status);
    card.appendChild(urlDiv);
    container.appendChild(card);
}

const RESIZE_PRESETS = {
    'events':     { width: 1200, height: 675 },
    'performers': { width: 800,  height: 800 },
    'products':   { width: 1000, height: 1000 },
    'locations':  { width: 1200, height: 675 },
    'shows':      { width: 1200, height: 675 },
    'episodes':   { width: 1280, height: 720 },
};

// ── Crop Modal ──────────────────────────────────────────────────────────────

let _crop = null; // active crop session

function showCropModal(file, targetW, targetH, quality, onDone) {
    const MARGIN   = 50;
    const CROP_W   = Math.min(420, window.innerWidth - 80);
    const CROP_H   = Math.round(CROP_W * targetH / targetW);
    const DISPLAY_W = CROP_W + MARGIN * 2;
    const DISPLAY_H = CROP_H + MARGIN * 2;

    let modal = document.getElementById('yb-crop-modal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'yb-crop-modal';
        Object.assign(modal.style, {
            position: 'fixed', inset: '0', background: 'rgba(0,0,0,.78)',
            zIndex: '9999', display: 'flex', alignItems: 'center',
            justifyContent: 'center', padding: '16px',
        });
        modal.innerHTML = `
          <div id="yb-crop-dialog" style="background:#fff;border-radius:12px;padding:20px;width:100%;max-width:560px;box-shadow:0 24px 64px rgba(0,0,0,.45);">
            <div style="font-size:15px;font-weight:700;margin-bottom:2px;">Выбери область кадрирования</div>
            <div style="font-size:12px;color:#888;margin-bottom:12px;">Перетащи · прокрути для зума</div>
            <div id="yb-crop-viewport" style="position:relative;overflow:hidden;cursor:grab;border-radius:8px;touch-action:none;background:#1a1410;">
              <img id="yb-crop-img" style="position:absolute;transform-origin:0 0;pointer-events:none;user-select:none;-webkit-user-select:none;max-width:none;">
              <div id="yb-crop-overlay" style="position:absolute;pointer-events:none;box-shadow:0 0 0 9999px rgba(0,0,0,0.55);box-sizing:border-box;border:2px solid rgba(255,255,255,0.9);">
                <div style="position:absolute;inset:0;display:grid;grid-template-columns:1fr 1fr 1fr;grid-template-rows:1fr 1fr 1fr;opacity:.25;pointer-events:none;">
                  <div style="border-right:1px solid #fff;border-bottom:1px solid #fff;"></div><div style="border-right:1px solid #fff;border-bottom:1px solid #fff;"></div><div style="border-bottom:1px solid #fff;"></div>
                  <div style="border-right:1px solid #fff;border-bottom:1px solid #fff;"></div><div style="border-right:1px solid #fff;border-bottom:1px solid #fff;"></div><div style="border-bottom:1px solid #fff;"></div>
                  <div style="border-right:1px solid #fff;"></div><div style="border-right:1px solid #fff;"></div><div></div>
                </div>
                <div style="position:absolute;top:-2px;left:-2px;width:14px;height:14px;border-top:3px solid #fff;border-left:3px solid #fff;"></div>
                <div style="position:absolute;top:-2px;right:-2px;width:14px;height:14px;border-top:3px solid #fff;border-right:3px solid #fff;"></div>
                <div style="position:absolute;bottom:-2px;left:-2px;width:14px;height:14px;border-bottom:3px solid #fff;border-left:3px solid #fff;"></div>
                <div style="position:absolute;bottom:-2px;right:-2px;width:14px;height:14px;border-bottom:3px solid #fff;border-right:3px solid #fff;"></div>
              </div>
            </div>
            <div style="margin-top:12px;display:flex;align-items:center;gap:10px;">
              <span style="font-size:16px;opacity:.6;">🔍</span>
              <input type="range" id="yb-crop-zoom" min="1" max="3" step="0.01" value="1" style="flex:1;accent-color:#667eea;cursor:pointer;">
              <span id="yb-crop-zoom-label" style="font-size:12px;color:#888;min-width:28px;text-align:right;">1×</span>
            </div>
            <div style="display:flex;gap:10px;margin-top:16px;">
              <button id="yb-crop-confirm" style="flex:1;padding:11px;background:#667eea;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:600;">✓ Загрузить</button>
              <button id="yb-crop-cancel" style="padding:11px 20px;background:#fff;color:#333;border:2px solid #e5e7eb;border-radius:8px;cursor:pointer;font-size:14px;">Отмена</button>
            </div>
          </div>`;
        document.body.appendChild(modal);
    }

    const viewport = document.getElementById('yb-crop-viewport');
    const overlay  = document.getElementById('yb-crop-overlay');
    const img      = document.getElementById('yb-crop-img');
    const slider   = document.getElementById('yb-crop-zoom');
    const label    = document.getElementById('yb-crop-zoom-label');

    viewport.style.width  = DISPLAY_W + 'px';
    viewport.style.height = DISPLAY_H + 'px';
    overlay.style.left    = MARGIN + 'px';
    overlay.style.top     = MARGIN + 'px';
    overlay.style.width   = CROP_W + 'px';
    overlay.style.height  = CROP_H + 'px';
    slider.value = 1;
    label.textContent = '1×';

    const objectUrl = URL.createObjectURL(file);

    _crop = {
        targetW, targetH, quality, onDone,
        displayW: DISPLAY_W, displayH: DISPLAY_H,
        cropLeft: MARGIN, cropTop: MARGIN, cropW: CROP_W, cropH: CROP_H,
        x: 0, y: 0, zoom: 1,
        baseScale: 1, minZoom: 1,
        naturalW: 0, naturalH: 0,
        dragging: false, lastX: 0, lastY: 0,
        objectUrl,
    };

    img.onload = () => {
        const c = _crop;
        c.naturalW = img.naturalWidth;
        c.naturalH = img.naturalHeight;
        // baseScale: image covers the crop rect exactly at zoom=1
        c.baseScale = Math.max(CROP_W / c.naturalW, CROP_H / c.naturalH);
        // minZoom: full image fits within the display area (shows context around crop)
        const containInDisplay = Math.min(DISPLAY_W / c.naturalW, DISPLAY_H / c.naturalH);
        c.minZoom = Math.min(1, containInDisplay / c.baseScale);
        slider.min = c.minZoom.toFixed(3);
        slider.value = c.zoom = 1;
        // center image on the crop rect
        c.x = MARGIN + (CROP_W - c.naturalW * c.baseScale) / 2;
        c.y = MARGIN + (CROP_H - c.naturalH * c.baseScale) / 2;
        _cropClamp();
        _cropApply();
    };
    img.src = objectUrl;

    // Drag
    viewport.onmousedown = e => {
        _crop.dragging = true; _crop.lastX = e.clientX; _crop.lastY = e.clientY;
        viewport.style.cursor = 'grabbing'; e.preventDefault();
    };
    viewport.onmousemove = e => {
        if (!_crop?.dragging) return;
        _crop.x += e.clientX - _crop.lastX; _crop.y += e.clientY - _crop.lastY;
        _crop.lastX = e.clientX; _crop.lastY = e.clientY;
        _cropClamp(); _cropApply();
    };
    viewport.onmouseup = viewport.onmouseleave = () => {
        if (_crop) { _crop.dragging = false; viewport.style.cursor = 'grab'; }
    };

    // Touch
    let _touch = null;
    viewport.ontouchstart = e => {
        if (e.touches.length === 1) { _touch = { x: e.touches[0].clientX, y: e.touches[0].clientY }; }
        e.preventDefault();
    };
    viewport.ontouchmove = e => {
        if (!_touch || e.touches.length !== 1) return;
        _crop.x += e.touches[0].clientX - _touch.x;
        _crop.y += e.touches[0].clientY - _touch.y;
        _touch = { x: e.touches[0].clientX, y: e.touches[0].clientY };
        _cropClamp(); _cropApply(); e.preventDefault();
    };
    viewport.ontouchend = () => { _touch = null; };

    // Wheel zoom
    viewport.onwheel = e => {
        e.preventDefault();
        _cropZoomBy(e.deltaY < 0 ? 0.08 : -0.08, e.offsetX, e.offsetY);
        slider.value = _crop.zoom;
        label.textContent = _crop.zoom.toFixed(1) + '×';
    };

    // Slider zoom
    slider.oninput = () => {
        const newZoom = parseFloat(slider.value);
        _cropZoomBy(newZoom - _crop.zoom, _crop.displayW / 2, _crop.displayH / 2);
        label.textContent = _crop.zoom.toFixed(1) + '×';
    };

    document.getElementById('yb-crop-confirm').onclick = _cropConfirm;
    document.getElementById('yb-crop-cancel').onclick  = _cropCancel;

    modal.style.display = 'flex';
}

function _cropZoomBy(delta, pivotX, pivotY) {
    const c = _crop;
    const oldScale = c.baseScale * c.zoom;
    c.zoom = Math.min(3, Math.max(c.minZoom || 1, c.zoom + delta));
    const newScale = c.baseScale * c.zoom;
    // keep pivot point fixed
    c.x = pivotX - (pivotX - c.x) * (newScale / oldScale);
    c.y = pivotY - (pivotY - c.y) * (newScale / oldScale);
    _cropClamp();
    _cropApply();
}

function _cropClamp() {
    const c = _crop;
    const totalScale = c.baseScale * c.zoom;
    const scaledW = c.naturalW * totalScale;
    const scaledH = c.naturalH * totalScale;
    // horizontal: center in display if smaller, otherwise keep within display bounds
    c.x = scaledW <= c.displayW
        ? (c.displayW - scaledW) / 2
        : Math.min(0, Math.max(c.displayW - scaledW, c.x));
    // vertical: same
    c.y = scaledH <= c.displayH
        ? (c.displayH - scaledH) / 2
        : Math.min(0, Math.max(c.displayH - scaledH, c.y));
}

function _cropApply() {
    const img = document.getElementById('yb-crop-img');
    if (!img || !_crop) return;
    const s = _crop.baseScale * _crop.zoom;
    img.style.transform = `translate(${_crop.x}px,${_crop.y}px) scale(${s})`;
}

function _cropConfirm() {
    const c = _crop;
    const img = document.getElementById('yb-crop-img');
    const canvas = document.createElement('canvas');
    canvas.width = c.targetW; canvas.height = c.targetH;
    const ctx = canvas.getContext('2d');
    // fill background (visible when image doesn't fully cover the crop rect)
    ctx.fillStyle = '#1a1410';
    ctx.fillRect(0, 0, c.targetW, c.targetH);
    // render exactly what's inside the crop rect
    const totalScale = c.baseScale * c.zoom;
    const srcX = (c.cropLeft - c.x) / totalScale;
    const srcY = (c.cropTop  - c.y) / totalScale;
    const srcW = c.cropW / totalScale;
    const srcH = c.cropH / totalScale;
    ctx.drawImage(img, srcX, srcY, srcW, srcH, 0, 0, c.targetW, c.targetH);
    canvas.toBlob(blob => {
        URL.revokeObjectURL(c.objectUrl);
        _cropClose();
        c.onDone(blob);
    }, 'image/jpeg', c.quality);
}

function _cropCancel() {
    const onDone = _crop?.onDone;
    if (_crop) URL.revokeObjectURL(_crop.objectUrl);
    _cropClose();
    if (onDone) onDone(null);
}

function _cropClose() {
    const modal = document.getElementById('yb-crop-modal');
    if (modal) modal.style.display = 'none';
    _crop = null;
}

// ── Upload ──────────────────────────────────────────────────────────────────

async function handleFiles(files, folder, container, onSuccess, onError) {
    for (const file of files) {
        await uploadImage(file, folder, container, onSuccess, onError);
    }
}

async function uploadImage(file, folder, container, onSuccess, onError) {
    const preset = RESIZE_PRESETS[folder];
    if (preset) {
        const blob = await new Promise(resolve => showCropModal(file, preset.width, preset.height, 0.88, resolve));
        if (!blob) return; // cancelled
        file = new File([blob], 'image.jpg', { type: 'image/jpeg' });
    }

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

                // Upload via API (use API_BASE_URL from shared.js)
                const apiBaseUrl = window.API_BASE_URL || API_BASE_URL;
                const response = await fetch(`${apiBaseUrl}/api/upload-image`, {
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
        card.dataset.url = url;
        status.className = 'upload-status success';
        status.textContent = '✓ Uploaded';

        const urlDiv = document.createElement('div');
        urlDiv.className = 'image-url-display';
        urlDiv.innerHTML = `
            <input type="text" class="url-input-display" value="${url}" readonly>
            <button class="copy-url-btn" onclick="copyImageUrl('${url}', this)">Copy</button>
            <button class="remove-img-btn" onclick="removeImageCardWithCallback('${cardId}', '${url}')">×</button>
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
    if (card) {
        const url = card.dataset.url;
        card.remove();
        return url;
    }
    return null;
}

function removeImageCardWithCallback(cardId, url) {
    const card = document.getElementById(cardId);
    if (card) {
        // Find the container and get onRemove callback
        const container = card.closest('.uploaded-images');
        if (container && container.parentElement._imageUploadOptions?.onRemove) {
            container.parentElement._imageUploadOptions.onRemove(url);
        }
        card.remove();
    }
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

// ── Cover upload with crop (overrides shared.js initCoverUpload) ─────────────

function initCoverUpload({ uploadAreaId, fileInputId, previewId, placeholderId, urlInputId, folder, onUpload }) {
    const area      = document.getElementById(uploadAreaId);
    const fileInput = document.getElementById(fileInputId);
    if (!area || !fileInput) return;

    const preset = RESIZE_PRESETS[folder];

    async function handleFile(file) {
        if (!file || !file.type.startsWith('image/')) return;
        if (preset) {
            const blob = await new Promise(resolve => showCropModal(file, preset.width, preset.height, 0.88, resolve));
            if (!blob) return;
            file = new File([blob], 'image.jpg', { type: 'image/jpeg' });
        }
        area.classList.add('uploading');
        try {
            const url = await uploadFile(file, folder);
            if (urlInputId)    document.getElementById(urlInputId).value = url;
            if (previewId)     { const img = document.getElementById(previewId); img.src = url; img.style.display = 'block'; }
            if (placeholderId) document.getElementById(placeholderId).style.display = 'none';
            if (onUpload)      onUpload(url);
        } catch { if (typeof showToast === 'function') showToast('Ошибка загрузки фото', 'error'); }
        finally { area.classList.remove('uploading'); }
    }

    area.addEventListener('dragover',  (e) => { e.preventDefault(); area.classList.add('drag-over'); });
    area.addEventListener('dragleave', ()  => area.classList.remove('drag-over'));
    area.addEventListener('drop', (e) => {
        e.preventDefault(); area.classList.remove('drag-over');
        const file = Array.from(e.dataTransfer.files).find(f => f.type.startsWith('image/'));
        if (file) handleFile(file);
    });
    fileInput.addEventListener('change', function() {
        if (this.files[0]) handleFile(this.files[0]);
        this.value = '';
    });
    document.addEventListener('paste', (e) => {
        const item = Array.from(e.clipboardData?.items || []).find(i => i.type.startsWith('image/'));
        if (item) { e.preventDefault(); handleFile(item.getAsFile()); }
    });
}

// Crop-aware drop-in replacement for uploadFile() used in gallery handlers
async function uploadFileWithCrop(file, folder) {
    const preset = RESIZE_PRESETS[folder];
    if (preset) {
        const blob = await new Promise(resolve => showCropModal(file, preset.width, preset.height, 0.88, resolve));
        if (!blob) return null;
        file = new File([blob], 'image.jpg', { type: 'image/jpeg' });
    }
    return uploadFile(file, folder);
}
