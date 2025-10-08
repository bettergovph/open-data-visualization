
// Error handling utilities
window.addEventListener('error', function(e) {
    console.error('Global error caught:', e.error);
});

window.addEventListener('unhandledrejection', function(e) {
    console.error('Unhandled promise rejection:', e.reason);
});

// Safe DOM element access
function safeGetElement(id) {
    const element = document.getElementById(id);
    if (!element) {
        console.warn(`Element with id '${id}' not found`);
        return null;
    }
    return element;
}

// Safe text content setting
function safeSetTextContent(id, text) {
    const element = safeGetElement(id);
    if (element) {
        element.textContent = text;
    }
}

// Dashboard specific fixes
document.addEventListener('DOMContentLoaded', function() {
    // Only set these elements if they exist (dashboard page)
    if (window.location.pathname === '/dashboard') {
        // These elements are now handled by the dashboard's own JavaScript
        // No need to set them here as they're managed by the dashboard
    }
});

// Mobile responsiveness helpers
function isMobile() {
    return window.innerWidth <= 768;
}

function adjustForMobile() {
    if (isMobile()) {
        document.body.classList.add('mobile-view');
    } else {
        document.body.classList.remove('mobile-view');
    }
}

// Initialize mobile adjustments
window.addEventListener('resize', adjustForMobile);
adjustForMobile();
