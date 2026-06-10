// auth.js — JWT authentication state management for admin panel

const Auth = (() => {
    const KEYS = {
        access:       'auth_access_token',
        refresh:      'auth_refresh_token',
        user:         'auth_user',
        orig_access:  'auth_orig_access_token',
        orig_refresh: 'auth_orig_refresh_token',
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

    async function login(email, password, tenantId) {
        const payload = { email, password };
        if (tenantId) payload.tenant_id = tenantId;
        const resp = await fetch(`${window.API_BASE_URL}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
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
        const token = localStorage.getItem(KEYS.access);
        if (token) {
            const payload = _decodePayload(token);
            if (payload?.role) return payload.role;
        }
        return getUser()?.role || null;
    }

    function isAdmin() {
        const role = getRole();
        return role === 'admin' || role === 'platform_admin';
    }

    function isPlatformAdmin() {
        return getRole() === 'platform_admin';
    }

    function isMimicking() {
        const token = localStorage.getItem(KEYS.access);
        if (!token) return false;
        return _decodePayload(token)?.is_mimicking === true;
    }

    // Permission matrix — mirrors utils/permissions.py:ROLE_PERMISSIONS
    const _ROLE_PERMISSIONS = {
        content_manager: new Set([
            'events:write', 'locations:write', 'performers:write',
            'products:write', 'shows:write', 'episodes:write',
            'media:upload', 'site:regenerate',
        ]),
        organizer: new Set(['events:write_own']),
    };

    function hasPermission(permission) {
        if (isAdmin()) return true;
        const role = getRole();
        return !!role && !!_ROLE_PERMISSIONS[role]?.has(permission);
    }

    async function switchTenant(tenantId) {
        const resp = await fetch(`${window.API_BASE_URL}/api/auth/switch-tenant`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${localStorage.getItem(KEYS.access)}`,
            },
            body: JSON.stringify({ tenant_id: tenantId }),
        });
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.error || `Switch failed (${resp.status})`);

        localStorage.setItem(KEYS.orig_access,  localStorage.getItem(KEYS.access) || '');
        localStorage.setItem(KEYS.orig_refresh, localStorage.getItem(KEYS.refresh) || '');

        localStorage.setItem(KEYS.access, data.access_token);
        localStorage.removeItem(KEYS.refresh);

        return data;
    }

    function exitTenant() {
        const origAccess  = localStorage.getItem(KEYS.orig_access);
        const origRefresh = localStorage.getItem(KEYS.orig_refresh);
        if (!origAccess) return;

        localStorage.setItem(KEYS.access, origAccess);
        if (origRefresh) localStorage.setItem(KEYS.refresh, origRefresh);
        else localStorage.removeItem(KEYS.refresh);

        localStorage.removeItem(KEYS.orig_access);
        localStorage.removeItem(KEYS.orig_refresh);
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

    let _refreshInterval = null;

    function startAutoRefresh() {
        if (_refreshInterval) return;
        _refreshInterval = setInterval(async () => {
            const token = localStorage.getItem(KEYS.access);
            if (!token) return;
            if (_isTokenExpired(token)) {
                try {
                    await refreshToken();
                } catch {
                    // Refresh failed — requireAuth on next API call will redirect
                }
            }
        }, 60_000); // check every minute
    }

    const _origLogout = logout;
    async function logoutWithCleanup() {
        if (_refreshInterval) {
            clearInterval(_refreshInterval);
            _refreshInterval = null;
        }
        await _origLogout();
    }

    return {
        login,
        logout: logoutWithCleanup,
        isAuthenticated,
        getAccessToken,
        getUser,
        getRole,
        isAdmin,
        isPlatformAdmin,
        isMimicking,
        switchTenant,
        exitTenant,
        hasPermission,
        refreshToken,
        requireAuth,
        startAutoRefresh,
    };
})();

window.Auth = Auth;
