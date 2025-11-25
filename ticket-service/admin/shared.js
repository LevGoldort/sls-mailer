// shared.js - Shared utilities and API methods for Ticket Admin

const API_BASE_URL = 'https://ovajavet67.execute-api.eu-north-1.amazonaws.com';

// ===== API Helper =====
async function apiCall(endpoint, method = 'GET', body = null) {
    const options = {
        method,
        headers: {
            'Content-Type': 'application/json'
        }
    };

    if (body) {
        options.body = JSON.stringify(body);
    }

    try {
        const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        return data;
    } catch (error) {
        console.error('API Error:', error);
        throw error;
    }
}

// ===== API Methods =====
const API = {
    // Events
    getEvents: () => apiCall('/api/events'),
    getEvent: (id) => apiCall(`/api/events/${id}`),
    createEvent: (data) => apiCall('/api/events', 'POST', data),
    updateEvent: (id, data) => apiCall(`/api/events/${id}`, 'PUT', data),
    deleteEvent: (id) => apiCall(`/api/events/${id}`, 'DELETE'),

    // Locations
    getLocations: () => apiCall('/api/locations'),
    getLocation: (id) => apiCall(`/api/locations/${id}`),
    createLocation: (data) => apiCall('/api/locations', 'POST', data),
    updateLocation: (id, data) => apiCall(`/api/locations/${id}`, 'PUT', data),
    deleteLocation: (id) => apiCall(`/api/locations/${id}`, 'DELETE'),

    // Orders
    getOrders: () => apiCall('/api/orders'),
    getOrdersByEvent: (eventId) => apiCall(`/api/orders?event_id=${eventId}`),
    getOrder: (id) => apiCall(`/api/orders/${id}`),

    // Coupons
    getCoupons: (status = null) => apiCall(`/api/coupons${status ? `?status=${status}` : ''}`),
    getCoupon: (code) => apiCall(`/api/coupons/${code}`),
    createCoupon: (data) => apiCall('/api/coupons', 'POST', data),
    validateCoupon: (code, eventId, amount) => apiCall('/api/coupons/validate', 'POST', { coupon_code: code, event_id: eventId, amount }),
    updateCoupon: (code, data) => apiCall(`/api/coupons/${code}`, 'PUT', data),
    deleteCoupon: (code) => apiCall(`/api/coupons/${code}`, 'DELETE')
};

// ===== Formatting Functions =====
function formatDate(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleDateString('ru-RU', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatDateShort(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleDateString('ru-RU', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

function formatCurrency(amount, currency = 'ILS') {
    if (typeof amount !== 'number') return '-';
    return `${amount.toFixed(0)}₪`;
}

function formatPercent(value) {
    if (typeof value !== 'number') return '-';
    return `${value.toFixed(1)}%`;
}

// ===== Toast Notifications =====
function showToast(message, type = 'success') {
    // Remove existing toasts
    const existing = document.querySelector('.toast');
    if (existing) {
        existing.remove();
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;

    document.body.appendChild(toast);

    // Animate in
    setTimeout(() => toast.classList.add('toast-show'), 10);

    // Remove after 3 seconds
    setTimeout(() => {
        toast.classList.remove('toast-show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ===== CSV Export =====
function exportToCSV(data, filename) {
    if (!data || data.length === 0) {
        showToast('Нет данных для экспорта', 'error');
        return;
    }

    // Get headers from first object
    const headers = Object.keys(data[0]);

    // Create CSV content
    let csv = headers.join(',') + '\n';

    data.forEach(row => {
        const values = headers.map(header => {
            let value = row[header];

            // Handle special cases
            if (value === null || value === undefined) {
                value = '';
            } else if (typeof value === 'object') {
                value = JSON.stringify(value);
            } else if (typeof value === 'string' && value.includes(',')) {
                value = `"${value}"`;
            }

            return value;
        });

        csv += values.join(',') + '\n';
    });

    // Create download link
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);

    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.display = 'none';

    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    showToast('CSV экспортирован успешно', 'success');
}

// ===== Loading State =====
function setLoading(element, isLoading) {
    if (isLoading) {
        element.classList.add('loading');
        element.disabled = true;
    } else {
        element.classList.remove('loading');
        element.disabled = false;
    }
}

// ===== Confirmation Dialog =====
function confirm(message) {
    return window.confirm(message);
}

// ===== Navigation =====
function navigateTo(page) {
    window.location.href = page;
}

// ===== Form Validation =====
function validateRequired(form, fieldNames) {
    const errors = [];

    fieldNames.forEach(name => {
        const field = form.elements[name];
        if (!field || !field.value.trim()) {
            errors.push(`Поле "${name}" обязательно`);
        }
    });

    return errors;
}

// ===== Date/Time Helpers =====
function getISODateTime(dateString, timeString) {
    return `${dateString}T${timeString}:00Z`;
}

function getCurrentISODate() {
    return new Date().toISOString().split('T')[0];
}

function getCurrentISOTime() {
    const now = new Date();
    return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
}

// ===== Storage Helpers =====
function saveToLocalStorage(key, data) {
    try {
        localStorage.setItem(key, JSON.stringify(data));
    } catch (e) {
        console.error('Failed to save to localStorage:', e);
    }
}

function getFromLocalStorage(key) {
    try {
        const data = localStorage.getItem(key);
        return data ? JSON.parse(data) : null;
    } catch (e) {
        console.error('Failed to get from localStorage:', e);
        return null;
    }
}

// ===== Statistics Helpers =====
function calculateEventStats(event) {
    if (!event || !event.ticket_types) {
        return { totalTickets: 0, soldTickets: 0, availableTickets: 0, revenue: 0, capacity: 0 };
    }

    let totalTickets = 0;
    let soldTickets = 0;
    let revenue = 0;

    event.ticket_types.forEach(tt => {
        const total = tt.total || 0;
        const available = tt.available || 0;
        const sold = total - available;

        totalTickets += total;
        soldTickets += sold;
        revenue += sold * (tt.price || 0);
    });

    return {
        totalTickets,
        soldTickets,
        availableTickets: totalTickets - soldTickets,
        revenue,
        capacity: Math.round((soldTickets / totalTickets) * 100) || 0
    };
}

function calculateOrdersStats(orders) {
    if (!orders || orders.length === 0) {
        return { totalOrders: 0, totalTickets: 0, totalRevenue: 0 };
    }

    let totalOrders = orders.length;
    let totalTickets = 0;
    let totalRevenue = 0;

    orders.forEach(order => {
        if (order.tickets) {
            order.tickets.forEach(ticket => {
                totalTickets += ticket.quantity || 0;
            });
        }
        totalRevenue += order.total_amount || 0;
    });

    return { totalOrders, totalTickets, totalRevenue };
}

// ===== Error Handler =====
function handleError(error, defaultMessage = 'Произошла ошибка') {
    console.error('Error:', error);
    const message = error.message || defaultMessage;
    showToast(message, 'error');
}

// ===== Init function to be called on page load =====
function initAdmin() {
    console.log('Admin panel initialized');

    // Add global error handler
    window.addEventListener('unhandledrejection', (event) => {
        handleError(event.reason);
    });
}

// Auto-init when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAdmin);
} else {
    initAdmin();
}
