// ===== Newsletter Admin Shared JS =====

const API_BASE_URL = 'https://YOUR_API_GATEWAY_URL';

// ===== API Key Management =====
function getAdminKey() {
    return localStorage.getItem('newsletter_admin_api_key');
}

function setAdminKey(key) {
    localStorage.setItem('newsletter_admin_api_key', key);
}

function clearAdminKey() {
    localStorage.removeItem('newsletter_admin_api_key');
}

function promptForApiKey() {
    const key = prompt('Enter admin API key:');
    if (key) {
        setAdminKey(key);
    }
    return key;
}

// ===== API Helper =====
async function apiCall(endpoint, method = 'GET', body = null) {
    let adminKey = getAdminKey();

    if (!adminKey) {
        adminKey = promptForApiKey();
        if (!adminKey) {
            throw new Error('Admin key required');
        }
    }

    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
            'X-API-Key': adminKey
        }
    };

    if (body) {
        options.body = JSON.stringify(body);
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, options);

    // Handle 401/403 - invalid API key
    if (response.status === 401 || response.status === 403) {
        clearAdminKey();
        alert('Invalid admin key. Please refresh and try again.');
        throw new Error('Unauthorized: Invalid admin key');
    }

    if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || `HTTP ${response.status}`);
    }

    // Return JSON for non-empty responses
    const text = await response.text();
    return text ? JSON.parse(text) : null;
}

// ===== Utility Functions =====
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showToast(message, type = 'info') {
    // Remove existing toast
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        padding: 12px 24px;
        border-radius: 8px;
        color: white;
        font-size: 14px;
        z-index: 10000;
        animation: slideIn 0.3s ease;
        background: ${type === 'success' ? '#4caf50' : type === 'error' ? '#f44336' : '#333'};
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ===== API Key Dialog =====
function showApiKeyDialog() {
    const currentKey = getAdminKey();
    const maskedKey = currentKey ? currentKey.substring(0, 8) + '...' : 'Not set';

    const dialog = document.createElement('div');
    dialog.id = 'api-key-dialog';
    dialog.innerHTML = `
        <div style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center">
            <div style="background:white;padding:30px;border-radius:12px;max-width:400px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.3)">
                <h3 style="margin:0 0 20px 0;color:#667eea">API Key Settings</h3>
                <p style="margin:0 0 15px 0;color:#666;font-size:14px">Current: <code style="background:#f5f5f5;padding:2px 6px;border-radius:4px">${escapeHtml(maskedKey)}</code></p>
                <input type="password" id="api-key-input" placeholder="Enter new API key" value="${currentKey || ''}"
                    style="width:100%;padding:12px;border:1px solid #ddd;border-radius:6px;font-size:14px;margin-bottom:20px;box-sizing:border-box">
                <div style="display:flex;gap:10px;justify-content:flex-end">
                    <button onclick="closeApiKeyDialog()" style="padding:10px 20px;border:1px solid #ddd;border-radius:6px;background:white;cursor:pointer">Cancel</button>
                    <button onclick="saveApiKey()" style="padding:10px 20px;border:none;border-radius:6px;background:#667eea;color:white;cursor:pointer;font-weight:600">Save</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(dialog);
    document.getElementById('api-key-input').focus();
}

function closeApiKeyDialog() {
    const dialog = document.getElementById('api-key-dialog');
    if (dialog) dialog.remove();
}

function saveApiKey() {
    const input = document.getElementById('api-key-input');
    const key = input.value.trim();

    if (key) {
        setAdminKey(key);
        showToast('API key saved', 'success');
    } else {
        clearAdminKey();
        showToast('API key cleared', 'info');
    }

    closeApiKeyDialog();
}

// ===== Settings Button =====
function addSettingsButton() {
    // Check if already added
    if (document.getElementById('settings-btn')) return;

    const btn = document.createElement('button');
    btn.id = 'settings-btn';
    btn.innerHTML = '&#9881;'; // Gear icon
    btn.title = 'API Key Settings';
    btn.style.cssText = `
        position: fixed;
        bottom: 20px;
        left: 20px;
        width: 48px;
        height: 48px;
        border-radius: 50%;
        border: none;
        background: #667eea;
        color: white;
        font-size: 24px;
        cursor: pointer;
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
        z-index: 1000;
        transition: transform 0.2s, box-shadow 0.2s;
    `;
    btn.onmouseover = () => {
        btn.style.transform = 'scale(1.1)';
        btn.style.boxShadow = '0 6px 16px rgba(102, 126, 234, 0.5)';
    };
    btn.onmouseout = () => {
        btn.style.transform = 'scale(1)';
        btn.style.boxShadow = '0 4px 12px rgba(102, 126, 234, 0.4)';
    };
    btn.onclick = showApiKeyDialog;

    document.body.appendChild(btn);
}

// Add settings button when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', addSettingsButton);
} else {
    addSettingsButton();
}
