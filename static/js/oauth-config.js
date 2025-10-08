/**
 * Centralized OAuth Configuration
 * Single source of truth for OAuth provider settings
 * Used by both desktop and mobile login systems
 */

window.OAUTH_CONFIG = {
    // OAuth Provider Credentials
    GOOGLE_CLIENT_ID: '968796729348-h4e3inns6bqpv6bkhf4fcaob8rrv1c82.apps.googleusercontent.com',
    FACEBOOK_APP_ID: '517796238632278',
    
    // Site Configuration
    SITE_NAME: 'KenchLightyear',
    SITE_URL: 'https://www.kenchlightyear.com',
    
    // Feature Flags
    ENABLE_GOOGLE_LOGIN: true,
    ENABLE_FACEBOOK_LOGIN: true,
    
    // Environment Detection
    NODE_ENV: 'production',
    
    // OAuth Scopes
    GOOGLE_SCOPES: 'profile email',
    FACEBOOK_SCOPES: 'public_profile,email',
    
    // Authentication Endpoints
    ENDPOINTS: {
        SET_COOKIE: '/api/auth/set-cookie',
        CHECK_AUTH: '/api/auth/me-cookie',
        LOGIN: '/api/auth/login',
        RESEND_ACTIVATION: '/api/auth/resend-activation'
    },
    
    // OAuth Settings
    GOOGLE_SETTINGS: {
        theme: 'outline',
        size: 'large',
        text: 'continue_with',
        shape: 'rectangular',
        type: 'standard',
        auto_select: false,
        cancel_on_tap_outside: true
    },
    
    FACEBOOK_SETTINGS: {
        cookie: true,
        xfbml: true,
        version: 'v23.0',
        status: true,
        autoLogAppEvents: false,
        disableMobileRedirect: true,
        scope: 'public_profile,email',
        auth_type: 'rerequest',
        return_scopes: true,
        enable_profile_selector: false,
        use_continue_as: false,
        display: 'popup'
    }
};

// Utility functions for OAuth configuration
window.OAUTH_UTILS = {
    /**
     * Get OAuth configuration for environment
     */
    getConfig: function() {
        return window.OAUTH_CONFIG;
    },
    
    /**
     * Check if OAuth provider is enabled
     */
    isProviderEnabled: function(provider) {
        const config = this.getConfig();
        if (provider === 'google') return config.ENABLE_GOOGLE_LOGIN;
        if (provider === 'facebook') return config.ENABLE_FACEBOOK_LOGIN;
        return false;
    },
    
    /**
     * Get provider-specific settings
     */
    getProviderSettings: function(provider) {
        const config = this.getConfig();
        if (provider === 'google') return config.GOOGLE_SETTINGS;
        if (provider === 'facebook') return config.FACEBOOK_SETTINGS;
        return {};
    },
    
    /**
     * Get authentication endpoint
     */
    getEndpoint: function(name) {
        return this.getConfig().ENDPOINTS[name] || null;
    }
};

console.log('🔧 OAuth configuration loaded:', window.OAUTH_CONFIG.SITE_NAME);
