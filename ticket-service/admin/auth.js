// auth.js — JWT authentication state management for admin panel

const Auth = (() => {
    const KEYS = {
        access:  'auth_access_token',
        refresh: 'auth_refresh_token',
        user:    'auth_user',
    };

    // ── JWT helpers ──────────────────────────────────────────────────────────

    function _decodePayload(token) {
        try {
            const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
            return JSON.parse(atob(base64));
        } catch {
            return null;
        }
    }

    function _isTokenExpired(token) {
        const payload = _decodePayload(token);
        if (!payload || !payload.exp) return true;
        // 30-second buffer so we refresh slightly before real expiry
        return payload.exp * 1000 < Date.now() + 30_000;
    }

    // ── Storage ──────────────────────────────────────────────────────────────

    function _store(accessToken, refreshToken, user) {
        localStorage.setItem(KEYS.access,  accessToken);
        localStorage.setItem(KEYS.refresh, refreshToken);
        localStorage.setItem(KEYS.user,    JSON.stringify(user));
    }

    function _clear() {
        Object.values(KEYS).forEach(k => localStorage.removeItem(k));
    }

    // ── Public API ───────────────────────────────────────────────────────────

    async function login(email, password) {
        const resp = await fetch(`${window.API_BASE_URL}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || `Login failed (${resp.status})`);
        _store(data.access_token, data.refresh_token, data.user);
        return data.user;
    }

    async function logout() {
        const refreshToken = localStorage.getItem(KEYS.refresh);
        if (refreshToken) {
            try {
                await fetch(`${window.API_BASE_URL}/api/auth/logout`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh_token: refreshToken }),
                });
            } catch { /* ignore network errors on logout */ }
        }
        _clear();
        window.location.href = 'login.html';
    }

    function isAuthenticated() {
        const token = localStorage.getItem(KEYS.access);
        return !!token && !_isTokenExpired(token);
    }

    function getAccessToken() {
        return localStorage.getItem(KEYS.access);
    }

    function getUser() {
        try {
            return JSON.parse(localStorage.getItem(KEYS.user)) || null;
        } catch {
            return null;
        }
    }

    function getRole() {
        return getUser()?.role || null;
    }

    function isAdmin() {
        return getRole() === 'admin';
    }

    async function refreshToken() {
        const token = localStorage.getItem(KEYS.refresh);
        if (!token) throw new Error('No refresh token');

        const resp = await fetch(`${window.API_BASE_URL}/api/auth/refresh`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: token }),
        });
        const data = await resp.json();
        if (!resp.ok) {
            _clear();
            throw new Error(data.error || 'Token refresh failed');
        }
        localStorage.setItem(KEYS.access, data.access_token);
        return data.access_token;
    }

    async function requireAuth() {
        if (isAuthenticated()) return;

        // Try silent refresh before redirecting
        try {
            await refreshToken();
        } catch {
            window.location.href = 'login.html';
        }
    }

    return { login, logout, isAuthenticated, getAccessToken, getUser, getRole, isAdmin, refreshToken, requireAuth };
})();

window.Auth = Auth;
