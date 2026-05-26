// shared.js — Shared utilities and API methods for admin-v2

// === XSS Protection ===
function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// === Environment detection ===
const isDev = window.location.hostname.includes('-dev') || window.location.hostname === 'localhost';
const API_BASE_URL = isDev
    ? 'https://d4xhvmdzbg.execute-api.eu-north-1.amazonaws.com/dev'
    : 'https://ovajavet67.execute-api.eu-north-1.amazonaws.com';

window.API_BASE_URL = API_BASE_URL;

// === API Helper ===
async function apiCall(endpoint, method = 'GET', body = null, _retry = false) {
    const token = Auth.getAccessToken();
    if (!token) {
        window.location.href = 'login.html';
        throw new Error('Not authenticated');
    }

    const options = {
        method,
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`,
        },
    };

    if (body) options.body = JSON.stringify(body);

    const response = await fetch(`${API_BASE_URL}${endpoint}`, options);

    if (response.status === 401 && !_retry) {
        try {
            await Auth.refreshToken();
            return apiCall(endpoint, method, body, true);
        } catch {
            await Auth.logout();
            throw new Error('Session expired');
        }
    }

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}`);
    }

    return data;
}

// === API Methods ===
const API = {
    // Events
    getEvents:    ()           => apiCall('/api/events'),
    getEvent:     (id)         => apiCall(`/api/events/${id}`),
    createEvent:  (data)       => apiCall('/api/events', 'POST', data),
    updateEvent:  (id, data)   => apiCall(`/api/events/${id}`, 'PUT', data),
    deleteEvent:  (id)         => apiCall(`/api/events/${id}`, 'DELETE'),
    getSeatingMap:(eventId)    => apiCall(`/api/events/${eventId}/seating-map`),

    // Locations
    getLocations:    ()          => apiCall('/api/locations'),
    getLocation:     (id)        => apiCall(`/api/locations/${id}`),
    createLocation:  (data)      => apiCall('/api/locations', 'POST', data),
    updateLocation:  (id, data)  => apiCall(`/api/locations/${id}`, 'PUT', data),
    deleteLocation:  (id)        => apiCall(`/api/locations/${id}`, 'DELETE'),

    // Orders
    getOrders:          ()            => apiCall('/api/orders'),
    getOrdersByEvent:   (eventId)     => apiCall(`/api/orders?event_id=${eventId}`),
    getOrder:           (id)          => apiCall(`/api/orders/${id}`),
    cancelTickets:      (id, data)    => apiCall(`/api/orders/${id}/cancel-tickets`, 'POST', data),
    resendEmail:        (id, data)    => apiCall(`/api/orders/${id}/resend-email`, 'POST', data),
    resendSms:          (id, data)    => apiCall(`/api/orders/${id}/resend-sms`, 'POST', data),
    sendSmsBlast:       (id, data)    => apiCall(`/api/events/${id}/send-sms-blast`, 'POST', data),
    updateOrderCustomer:(id, data)    => apiCall(`/api/orders/${id}/customer`, 'PATCH', data),

    // Coupons
    getCoupons:    (status = null) => apiCall(`/api/coupons${status ? `?status=${status}` : ''}`),
    getCoupon:     (code)          => apiCall(`/api/coupons/${code}`),
    createCoupon:  (data)          => apiCall('/api/coupons', 'POST', data),
    updateCoupon:  (code, data)    => apiCall(`/api/coupons/${code}`, 'PUT', data),
    deleteCoupon:  (code)          => apiCall(`/api/coupons/${code}`, 'DELETE'),

    // Influencers
    getInfluencers: () => apiCall('/api/influencers'),

    // Users (admin only)
    getUsers:           ()              => apiCall('/api/users'),
    getUser:            (id)            => apiCall(`/api/users/${id}`),
    createUser:         (data)          => apiCall('/api/users', 'POST', data),
    updateUser:         (id, data)      => apiCall(`/api/users/${id}`, 'PUT', data),
    deactivateUser:     (id)            => apiCall(`/api/users/${id}`, 'DELETE'),
    resetUserPassword:  (id, password)  => apiCall(`/api/users/${id}/reset-password`, 'POST', { new_password: password }),
    changePassword:     (data)          => apiCall('/api/auth/change-password', 'POST', data),

    // Performers (admin only)
    getPerformers:   ()          => apiCall('/api/performers'),
    getPerformer:    (id)        => apiCall(`/api/performers/${id}`),
    createPerformer: (data)      => apiCall('/api/performers', 'POST', data),
    updatePerformer: (id, data)  => apiCall(`/api/performers/${id}`, 'PUT', data),
    deletePerformer: (id)        => apiCall(`/api/performers/${id}`, 'DELETE'),

    // Products (admin only)
    getProducts:   (performerId = null) => apiCall(`/api/products${performerId ? `?performer_id=${performerId}` : ''}`),
    getProduct:    (id)                 => apiCall(`/api/products/${id}`),
    createProduct: (data)               => apiCall('/api/products', 'POST', data),
    updateProduct: (id, data)           => apiCall(`/api/products/${id}`, 'PUT', data),
    deleteProduct: (id)                 => apiCall(`/api/products/${id}`, 'DELETE'),

    // Merch orders (admin only)
    getMerchOrders:   (productId = null) => apiCall(`/api/merchandise/orders${productId ? `?product_id=${productId}` : ''}`),
    patchMerchOrder:  (id, data)         => apiCall(`/api/merchandise/orders/${id}`, 'PATCH', data),

    // Shows (admin only)
    getShows:   ()          => apiCall('/api/shows'),
    getShow:    (id)        => apiCall(`/api/shows/${id}`),
    createShow: (data)      => apiCall('/api/shows', 'POST', data),
    updateShow: (id, data)  => apiCall(`/api/shows/${id}`, 'PUT', data),
    deleteShow: (id)        => apiCall(`/api/shows/${id}`, 'DELETE'),

    // Episodes (admin only)
    getEpisodes:   (showId = null) => apiCall(`/api/episodes${showId ? `?show_id=${showId}` : ''}`),
    getEpisode:    (id)            => apiCall(`/api/episodes/${id}`),
    createEpisode: (data)          => apiCall('/api/episodes', 'POST', data),
    updateEpisode: (id, data)      => apiCall(`/api/episodes/${id}`, 'PUT', data),
    deleteEpisode: (id)            => apiCall(`/api/episodes/${id}`, 'DELETE'),

    // Global Search (admin only)
    search: (query) => apiCall(`/api/search?q=${encodeURIComponent(query)}`),
};

// === Formatting ===
function formatDate(isoString) {
    if (!isoString) return '-';
    return new Date(isoString).toLocaleDateString('ru-RU', {
        year: 'numeric', month: 'long', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
    });
}

function formatDateShort(isoString) {
    if (!isoString) return '-';
    return new Date(isoString).toLocaleDateString('ru-RU', {
        year: 'numeric', month: '2-digit', day: '2-digit',
    });
}

function formatCurrency(amount) {
    if (typeof amount !== 'number') return '-';
    return `${amount.toFixed(0)}₪`;
}

function formatPercent(value) {
    if (typeof value !== 'number') return '-';
    return `${value.toFixed(1)}%`;
}

// === Toast ===
function showToast(message, type = 'success') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.classList.add('toast-show'), 10);
    setTimeout(() => {
        toast.classList.remove('toast-show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// === CSV Export ===
function exportToCSV(data, filename) {
    if (!data || data.length === 0) {
        showToast('Нет данных для экспорта', 'error');
        return;
    }

    const headers = Object.keys(data[0]);
    let csv = headers.join(',') + '\n';

    data.forEach(row => {
        const values = headers.map(header => {
            let value = row[header];
            if (value === null || value === undefined) value = '';
            else if (typeof value === 'object') value = JSON.stringify(value);
            else if (typeof value === 'string' && value.includes(',')) value = `"${value}"`;
            return value;
        });
        csv += values.join(',') + '\n';
    });

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.style.display = 'none';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    showToast('CSV экспортирован', 'success');
}

// === Navigation ===
function navigateTo(page) { window.location.href = page; }

// === Date helpers ===
function getISODateTime(date, time) { return `${date}T${time}:00Z`; }
function getCurrentISODate() { return new Date().toISOString().split('T')[0]; }
function getCurrentISOTime() {
    const now = new Date();
    return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
}

// === Statistics ===
function calculateEventStats(event) {
    if (!event || !event.ticket_types) {
        return { totalTickets: 0, soldTickets: 0, availableTickets: 0, revenue: 0, capacity: 0 };
    }
    let totalTickets = 0, soldTickets = 0, revenue = 0;
    event.ticket_types.forEach(tt => {
        const total = tt.total || 0;
        const sold  = total - (tt.available || 0);
        totalTickets += total;
        soldTickets  += sold;
        revenue      += sold * (tt.price || 0);
    });
    return {
        totalTickets, soldTickets,
        availableTickets: totalTickets - soldTickets,
        revenue,
        capacity: totalTickets > 0 ? Math.round((soldTickets / totalTickets) * 100) : 0,
    };
}

function calculateOrdersStats(orders) {
    if (!orders || orders.length === 0) return { totalOrders: 0, totalTickets: 0, totalRevenue: 0 };
    const completed = orders.filter(o => o.payment && o.payment.status === 'completed');
    let totalTickets = 0, totalRevenue = 0;
    completed.forEach(o => {
        if (o.tickets) o.tickets.forEach(t => { totalTickets += t.quantity || 0; });
        totalRevenue += o.total_amount || 0;
    });
    return { totalOrders: completed.length, totalTickets, totalRevenue };
}

// === Image Upload ===
async function uploadFile(file, folder = 'images') {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = async (e) => {
            const b64 = btoa(new Uint8Array(e.target.result).reduce((d, b) => d + String.fromCharCode(b), ''));
            const ext = (file.name || 'image.jpg').split('.').pop().toLowerCase();
            const filename = `${folder}/${Date.now()}-${Math.random().toString(36).slice(2, 7)}.${ext}`;
            try {
                const data = await apiCall('/api/upload-image', 'POST', { filename, contentType: file.type, data: b64 });
                resolve(data.url);
            } catch (err) {
                reject(err);
            }
        };
        reader.onerror = () => reject(new Error('Failed to read file'));
        reader.readAsArrayBuffer(file);
    });
}

// Sets up a cover-image upload zone with click, drag-drop, and Ctrl+V paste.
// previewId / placeholderId / urlInputId / fileInputId are element IDs in the page.
function initCoverUpload({ uploadAreaId, fileInputId, previewId, placeholderId, urlInputId, folder, onUpload }) {
    const area = document.getElementById(uploadAreaId);
    const fileInput = document.getElementById(fileInputId);
    if (!area || !fileInput) return;

    async function handleFile(file) {
        if (!file || !file.type.startsWith('image/')) return;
        area.classList.add('uploading');
        try {
            const url = await uploadFile(file, folder);
            if (urlInputId) document.getElementById(urlInputId).value = url;
            if (previewId) { document.getElementById(previewId).src = url; document.getElementById(previewId).style.display = 'block'; }
            if (placeholderId) document.getElementById(placeholderId).style.display = 'none';
            if (onUpload) onUpload(url);
        } catch { showToast('Ошибка загрузки фото', 'error'); }
        finally { area.classList.remove('uploading'); }
    }

    area.addEventListener('dragover', (e) => { e.preventDefault(); area.classList.add('drag-over'); });
    area.addEventListener('dragleave', () => area.classList.remove('drag-over'));
    area.addEventListener('drop', (e) => {
        e.preventDefault();
        area.classList.remove('drag-over');
        const file = Array.from(e.dataTransfer.files).find(f => f.type.startsWith('image/'));
        if (file) handleFile(file);
    });

    fileInput.addEventListener('change', function() {
        if (this.files[0]) handleFile(this.files[0]);
        this.value = '';
    });

    document.addEventListener('paste', (e) => {
        const item = Array.from(e.clipboardData.items).find(i => i.type.startsWith('image/'));
        if (item) { e.preventDefault(); handleFile(item.getAsFile()); }
    });
}

// === Error Handler ===
function handleError(error, defaultMessage = 'Произошла ошибка') {
    console.error('Error:', error);
    showToast(error.message || defaultMessage, 'error');
}

// === Site Regeneration ===
async function regenerateSite() {
    const btn = document.getElementById('regenerate-site-btn');
    const statusDiv = document.getElementById('regenerate-status');
    if (!btn) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner spinner-white"></span> Генерация...';
    if (statusDiv) statusDiv.textContent = '';

    try {
        const token = Auth.getAccessToken();
        if (!token) { window.location.href = 'login.html'; return; }

        const response = await fetch(`${API_BASE_URL}/api/admin/regenerate-site`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        });

        if (response.status === 401) { await Auth.logout(); return; }

        const data = await response.json();

        if (response.ok && data.status === 'success') {
            const sec = parseFloat(data.message.match(/[\d.]+/)?.[0] || 0).toFixed(1);
            showToast(`Сайт обновлён за ${sec}с`, 'success');
            if (statusDiv) statusDiv.innerHTML = `
                <span style="font-size:13px;color:var(--green);">
                    ✓ Обновлено: ${data.events_count} событий · ${data.files_uploaded} файлов
                    &nbsp;<a href="${data.url}" target="_blank" style="color:var(--purple)">Открыть сайт →</a>
                </span>`;
        } else {
            throw new Error(data.message || 'Ошибка генерации');
        }
    } catch (error) {
        showToast('Ошибка генерации: ' + error.message, 'error');
    } finally {
        setTimeout(() => {
            btn.disabled = false;
            btn.textContent = 'Обновить сайт';
        }, 2000);
    }
}

window.regenerateSite = regenerateSite;

// === Sidebar Nav ===
// permission: show only if Auth.hasPermission(permission)
// adminOnly:  show only if Auth.isAdmin()
// (no flag):  show to all authenticated users
const NAV_ITEMS = [
    { href: 'index.html',        icon: '⊞', label: 'Дашборд' },
    { href: 'events.html',       icon: '📅', label: 'События',       permission: 'events:write' },
    { href: 'orders.html',       icon: '🎫', label: 'Заказы',         adminOnly: true },
    { href: 'analytics.html',    icon: '📊', label: 'Аналитика',      adminOnly: true },
    { href: 'search.html',       icon: '🔍', label: 'Поиск' },
    { sep: true },
    { href: 'locations.html',    icon: '📍', label: 'Локации',        permission: 'locations:write' },
    { href: 'coupons.html',      icon: '🏷', label: 'Купоны',         adminOnly: true },
    { href: 'influencers.html', icon: '★', label: 'Инфлюенсеры',    adminOnly: true },
    { href: 'performers.html',   icon: '🎤', label: 'Артисты',        permission: 'performers:write' },
    { href: 'products.html',     icon: '🛍', label: 'Товары',         permission: 'products:write' },
    { href: 'merch-orders.html', icon: '📦', label: 'Мерч-заказы',    adminOnly: true },
    { href: 'shows.html',        icon: '🎬', label: 'Шоу',            permission: 'shows:write' },
    { href: 'users.html',        icon: '👥', label: 'Пользователи',   adminOnly: true },
    { sep: true },
    { href: 'scanner.html',      icon: '📷', label: 'Сканер' },
    { href: 'quick-post.html',   icon: '⚡', label: 'Быстрый пост',   adminOnly: true },
    { href: 'sms-blast.html',    icon: '💬', label: 'SMS рассылка',   adminOnly: true },
];

// Pages whose active state rolls up to a parent item
const PARENT_MAP = {
    'event-edit.html':       'events.html',
    'location-edit.html':    'locations.html',
    'performer-edit.html':   'performers.html',
    'product-edit.html':     'products.html',
    'shows-edit.html':       'shows.html',
    'episodes-edit.html':    'shows.html',
    'episodes.html':         'shows.html',
};

function renderSidebar() {
    const container = document.getElementById('sidebar-container');
    if (!container) return;

    const currentFile = window.location.pathname.split('/').pop() || 'index.html';
    const activeHref  = PARENT_MAP[currentFile] || currentFile;

    const navHtml = NAV_ITEMS.map(item => {
        if (item.sep) return '<li class="nav-sep"></li>';
        if (item.adminOnly && !Auth.isAdmin()) return '';
        if (item.permission && !Auth.hasPermission(item.permission)) return '';
        const active = activeHref === item.href ? 'active' : '';
        return `<li><a href="${item.href}" class="nav-link ${active}"><span class="nav-icon">${item.icon}</span>${item.label}</a></li>`;
    }).join('');

    container.innerHTML = `
        <div class="sidebar-logo">
            <span class="logo-text">Yalla, Balagan</span>
            <span class="logo-tag">admin</span>
        </div>
        <ul class="sidebar-nav">${navHtml}</ul>
        <div class="sidebar-footer">
            <div id="user-bar"></div>
        </div>
    `;
}

// === User Bar (inside sidebar footer, populated after renderSidebar) ===
function renderUserBar() {
    const user = Auth.getUser();
    if (!user) return;

    const bar = document.getElementById('user-bar');
    if (!bar) return;

    bar.innerHTML = `
        <div class="user-info">
            <div class="user-avatar">${escapeHtml((user.name || '?')[0].toUpperCase())}</div>
            <span class="user-name">${escapeHtml(user.name)}</span>
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
            <span class="role-badge role-${escapeHtml(user.role)}">${escapeHtml(user.role)}</span>
            <button onclick="Auth.logout()" class="btn-logout">Выйти</button>
        </div>
    `;

    document.querySelectorAll('[data-admin-only]').forEach(el => {
        el.style.display = Auth.isAdmin() ? '' : 'none';
    });
}

// === Mobile sidebar toggle ===
function initMobileMenu() {
    const btn     = document.getElementById('mobile-menu-btn');
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (!btn || !sidebar) return;

    btn.addEventListener('click', () => {
        sidebar.classList.toggle('open');
        if (overlay) overlay.classList.toggle('active');
    });

    if (overlay) {
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            overlay.classList.remove('active');
        });
    }
}

// === Init ===
async function initAdmin() {
    await Auth.requireAuth();
    Auth.startAutoRefresh();

    window.addEventListener('unhandledrejection', (event) => {
        handleError(event.reason);
    });

    renderSidebar();
    renderUserBar();
    initMobileMenu();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAdmin);
} else {
    initAdmin();
}
