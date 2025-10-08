// Unified Authentication JavaScript Module
// Centralizes authentication logic for both desktop and mobile

window.AuthUnified = (function() {
    'use strict';

    // Configuration
    const CONFIG = {
        API_BASE: '/api',
        ENDPOINTS: {
            ME_COOKIE: '/api/auth/me-cookie',
            LOGIN: '/api/auth/login',
            LOGOUT: '/api/auth/logout',
            SIGNUP: '/api/auth/signup'
        },
        STORAGE_KEYS: {
            USER_DATA: 'userData',
            AUTH_TOKEN: 'authToken',
            LAST_CHECK: 'lastAuthCheck'
        },
        CACHE_DURATION: 5 * 60 * 1000, // 5 minutes
        DEBUG: true
    };

    // Internal state
    let cachedUserData = null;
    let lastCheckTime = 0;
    let authCheckPromise = null;

    // Utility functions
    function log(message, data = null) {
        if (CONFIG.DEBUG) {
            console.log(`🔍 [AUTH] ${message}`, data || '');
        }
    }

    function error(message, err = null) {
        console.error(`❌ [AUTH] ${message}`, err || '');
    }

    function isCacheValid() {
        return cachedUserData && (Date.now() - lastCheckTime) < CONFIG.CACHE_DURATION;
    }

    // Core authentication functions
    async function checkAuthentication(forceRefresh = false) {
        // Return cached data if valid and not forcing refresh
        if (!forceRefresh && isCacheValid()) {
            log('Using cached authentication data');
            return cachedUserData;
        }

        // Prevent multiple simultaneous requests
        if (authCheckPromise) {
            log('Authentication check already in progress, waiting...');
            return authCheckPromise;
        }

        authCheckPromise = performAuthCheck();
        try {
            const result = await authCheckPromise;
            return result;
        } finally {
            authCheckPromise = null;
        }
    }

    async function performAuthCheck() {
        try {
            log('Checking authentication status...');
            const response = await fetch(CONFIG.ENDPOINTS.ME_COOKIE, {
                credentials: 'include',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                log('Authentication successful', {
                    email: data.user && data.user.email,
                    tier: data.user && data.user.tier,
                    isAdmin: data.user && data.user.is_admin
                });

                // Cache the result
                cachedUserData = data;
                lastCheckTime = Date.now();

                return data;
            } else {
                log('Authentication failed', response.status);
                cachedUserData = null;
                lastCheckTime = 0;
                return null;
            }
        } catch (err) {
            error('Authentication check failed', err);
            cachedUserData = null;
            lastCheckTime = 0;
            return null;
        }
    }

    // User role checking functions
    function isAuthenticated(userData = null) {
        const data = userData || cachedUserData;
        return !!(data && data.user && data.user.email);
    }

    function isAdmin(userData = null) {
        const data = userData || cachedUserData;
        return !!(data && data.user && data.user.is_admin);
    }

    function isTester(userData = null) {
        // Tester tier removed - always return false
        return false;
    }

    function isOmega(userData = null) {
        const data = userData || cachedUserData;
        return !!(data && data.user && data.user.tier === 999);
    }

    function isPro(userData = null) {
        const data = userData || cachedUserData;
        return !!(data && data.user && data.user.tier >= 1);
    }

    function getTier(userData = null) {
        const data = userData || cachedUserData;
        return data && data.user ? data.user.tier : 0;
    }

    function getUser(userData = null) {
        const data = userData || cachedUserData;
        return data ? data.user : null;
    }

    // UI helper functions
    function shouldShowDebug(userData = null) {
        // Only admin users should see debug information
        // Omega tier gets features without debug clutter
        return isAdmin(userData);
    }

    function shouldShowFeatures(userData = null) {
        // Show features for admin, tester, or pro users
        return isAdmin(userData) || isTester(userData) || isPro(userData);
    }

    function getUserDisplayName(userData = null) {
        const user = getUser(userData);
        return user ? (user.name || user.email || 'User') : 'Guest';
    }

    function getTierDisplayName(userData = null) {
        const tier = getTier(userData);
        const user = getUser(userData);
        
        if (user && user.is_admin) return 'Admin';
        
        switch (tier) {
            case -1: return 'Tester';
            case 0: return 'Core';
            case 1: return 'Pro';
            case 2: return 'Omega';
            case 999: return 'Omega';
            default: return `Tier ${tier}`;
        }
    }

    // Centralized fetch utility
    async function fetchAPI(endpoint, options = {}) {
        const defaultOptions = {
            credentials: 'include',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json'
            }
        };

        const fullUrl = endpoint.startsWith('http') ? endpoint : CONFIG.API_BASE + endpoint;
        
        try {
            const response = await fetch(fullUrl, {
                ...defaultOptions,
                ...options
            });

            log(`Fetch ${options.method || 'GET'} ${endpoint}:`, response.status);
            return response;
        } catch (err) {
            error(`Fetch failed for ${endpoint}`, err);
            throw err;
        }
    }

    // Convenience methods for common HTTP verbs
    async function fetchGET(endpoint, options = {}) {
        return fetchAPI(endpoint, { ...options, method: 'GET' });
    }

    async function fetchPOST(endpoint, data = null, options = {}) {
        const postOptions = {
            ...options,
            method: 'POST'
        };

        if (data) {
            postOptions.body = typeof data === 'string' ? data : JSON.stringify(data);
        }

        return fetchAPI(endpoint, postOptions);
    }

    // Authentication actions
    async function login(credentials) {
        try {
            log('Attempting login...');
            const response = await fetch(CONFIG.ENDPOINTS.LOGIN, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify(credentials)
            });

            if (response.ok) {
                const data = await response.json();
                log('Login successful');
                
                // Clear cache to force refresh
                cachedUserData = null;
                lastCheckTime = 0;
                
                return { success: true, data };
            } else {
                const errorData = await response.json().catch(() => ({}));
                error('Login failed', errorData);
                return { success: false, error: errorData.detail || 'Login failed' };
            }
        } catch (err) {
            error('Login request failed', err);
            return { success: false, error: 'Network error' };
        }
    }

    async function logout() {
        try {
            log('Attempting logout...');
            const response = await fetch(CONFIG.ENDPOINTS.LOGOUT, {
                method: 'POST',
                credentials: 'include'
            });

            // Clear cache regardless of response
            cachedUserData = null;
            lastCheckTime = 0;

            if (response.ok) {
                log('Logout successful');
                return { success: true };
            } else {
                log('Logout request failed, but clearing local state');
                return { success: true }; // Still success since we cleared local state
            }
        } catch (err) {
            error('Logout request failed', err);
            // Clear cache even on error
            cachedUserData = null;
            lastCheckTime = 0;
            return { success: true }; // Still success since we cleared local state
        }
    }

    // Event handling
    const eventCallbacks = {
        'auth-changed': [],
        'login': [],
        'logout': []
    };

    function on(event, callback) {
        if (eventCallbacks[event]) {
            eventCallbacks[event].push(callback);
        } else {
            error(`Unknown event: ${event}`);
        }
    }

    function off(event, callback) {
        if (eventCallbacks[event]) {
            const index = eventCallbacks[event].indexOf(callback);
            if (index > -1) {
                eventCallbacks[event].splice(index, 1);
            }
        }
    }

    function emit(event, data = null) {
        if (eventCallbacks[event]) {
            eventCallbacks[event].forEach(callback => {
                try {
                    callback(data);
                } catch (err) {
                    error(`Error in event callback for ${event}`, err);
                }
            });
        }
    }

    // DOM helpers
    function showElement(selector) {
        const element = document.querySelector(selector);
        if (element) {
            element.style.display = 'block';
            element.classList.remove('hidden');
        }
    }

    function hideElement(selector) {
        const element = document.querySelector(selector);
        if (element) {
            element.style.display = 'none';
            element.classList.add('hidden');
        }
    }

    function toggleElement(selector, show) {
        if (show) {
            showElement(selector);
        } else {
            hideElement(selector);
        }
    }

    function updateElementText(selector, text) {
        const element = document.querySelector(selector);
        if (element) {
            element.textContent = text;
        }
    }

    // Initialize authentication on page load
    function init() {
        log('Initializing AuthUnified module');
        
        // Check authentication on page load
        document.addEventListener('DOMContentLoaded', async () => {
            try {
                const userData = await checkAuthentication();
                emit('auth-changed', userData);
            } catch (err) {
                error('Failed to initialize authentication', err);
            }
        });

        // Handle page visibility changes (refresh auth when page becomes visible)
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                // Page became visible, refresh auth if cache is old
                if (!isCacheValid()) {
                    checkAuthentication(true);
                }
            }
        });
    }

    // Public API
    return {
        // Core functions
        checkAuthentication,
        login,
        logout,
        
        // User role checks
        isAuthenticated,
        isAdmin,
        isTester,
        isOmega,
        isPro,
        getTier,
        getUser,
        
        // UI helpers
        shouldShowDebug,
        shouldShowFeatures,
        getUserDisplayName,
        getTierDisplayName,
        
        // DOM helpers
        showElement,
        hideElement,
        toggleElement,
        updateElementText,
        
        // Fetch utilities
        fetchAPI,
        fetchGET,
        fetchPOST,
        
        // Event handling
        on,
        off,
        emit,
        
        // Utilities
        clearCache: () => {
            cachedUserData = null;
            lastCheckTime = 0;
        },
        
        // Configuration
        config: CONFIG,
        
        // Initialize
        init
    };
})();

// Auto-initialize
AuthUnified.init();
