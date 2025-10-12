window.ENV = {
    SITE_NAME: 'BetterGovPH Data Visualizations',
    SITE_URL: 'https://visualizations.bettergov.ph',
    GOOGLE_CLIENT_ID: '968796729348-h4e3inns6bqpv6bkhf4fcaob8rrv1c82.apps.googleusercontent.com',
    FACEBOOK_APP_ID: '517796238632278',
    PAYPAL_CLIENT_ID: 'ATrwsIxZ8bVeWiMSbfbx-X2r9UFXc6mvPgoHsGKKtCafmfnOCDZOIcHLB6B1zpacXoOvJtDjP1eN3lfw',
    ENABLE_GOOGLE_LOGIN: true,
    ENABLE_FACEBOOK_LOGIN: true,
    ENABLE_PAYPAL_UPGRADE: true,
    GOOGLE_ANALYTICS_ID: 'your_ga_id_here',
    YOUTUBE_URL: 'https://www.youtube.com/@joebertj/streams',
    GITHUB_URL: 'https://github.com/joebertj',
    CONTACT_EMAIL: 'info@bettergov.ph',
    CONTACT_PHONE: '+1-555-123-4567',
    NODE_ENV: 'production',
};

// Enhanced Authentication Session Management
class AuthSessionManager {
    constructor() {
        this.sessionCheckInterval = null;
        this.lastActivity = Date.now();
        this.sessionTimeout = 30 * 60 * 1000; // 30 minutes
        this.retryAttempts = 0;
        this.maxRetries = 3;
        this.retryDelay = 2000; // 2 seconds
    }

    init() {
        this.startSessionMonitoring();
        this.setupActivityTracking();
        this.setupPeriodicSessionCheck();
    }

    startSessionMonitoring() {
        // Check session every 5 minutes
        this.sessionCheckInterval = setInterval(() => {
            this.checkSessionHealth();
        }, 5 * 60 * 1000);
    }

    setupActivityTracking() {
        // Track user activity to extend session
        const activityEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click'];
        activityEvents.forEach(event => {
            document.addEventListener(event, () => {
                this.lastActivity = Date.now();
            }, { passive: true });
        });
    }

    setupPeriodicSessionCheck() {
        // Check session health every 10 minutes
        setInterval(() => {
            this.validateSession();
        }, 10 * 60 * 1000);
    }

    async checkSessionHealth() {
        try {
            const response = await fetch('/api/auth/me-cookie', {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'Cache-Control': 'no-cache'
                }
            });

            if (!response.ok) {
                console.warn('🔍 Session health check failed, status:', response.status);
                this.handleSessionIssue();
            } else {
                this.retryAttempts = 0; // Reset retry attempts on success
            }
        } catch (error) {
            console.error('🔍 Session health check error:', error);
            this.handleSessionIssue();
        }
    }

    async validateSession() {
        const timeSinceActivity = Date.now() - this.lastActivity;
        
        if (timeSinceActivity > this.sessionTimeout) {
            console.warn('🔍 Session timeout detected, validating...');
            await this.checkSessionHealth();
        }
    }

    handleSessionIssue() {
        this.retryAttempts++;
        
        if (this.retryAttempts >= this.maxRetries) {
            console.error('🔍 Max retry attempts reached, redirecting to login');
            this.redirectToLogin();
        } else {
            console.log(`🔍 Retrying session check in ${this.retryDelay}ms (attempt ${this.retryAttempts}/${this.maxRetries})`);
            setTimeout(() => {
                this.checkSessionHealth();
            }, this.retryDelay);
        }
    }

    redirectToLogin() {
        const currentPath = window.location.pathname;
        const loginUrl = `/login?redirect=${encodeURIComponent(currentPath)}`;
        window.location.href = loginUrl;
    }

    destroy() {
        if (this.sessionCheckInterval) {
            clearInterval(this.sessionCheckInterval);
        }
    }
}

// Enhanced Element Selector with Retry Logic
class ElementSelector {
    constructor() {
        this.defaultTimeout = 10000; // 10 seconds
        this.retryInterval = 100; // 100ms
    }

    async waitForElement(selector, timeout = this.defaultTimeout) {
        const startTime = Date.now();
        
        while (Date.now() - startTime < timeout) {
            const element = document.querySelector(selector);
            if (element) {
                return element;
            }
            await new Promise(resolve => setTimeout(resolve, this.retryInterval));
        }
        
        throw new Error(`Element not found: ${selector} (timeout: ${timeout}ms)`);
    }

    async waitForElements(selector, timeout = this.defaultTimeout) {
        const startTime = Date.now();
        
        while (Date.now() - startTime < timeout) {
            const elements = document.querySelectorAll(selector);
            if (elements.length > 0) {
                return Array.from(elements);
            }
            await new Promise(resolve => setTimeout(resolve, this.retryInterval));
        }
        
        throw new Error(`Elements not found: ${selector} (timeout: ${timeout}ms)`);
    }

    safeQuerySelector(selector, fallback = null) {
        try {
            const element = document.querySelector(selector);
            return element || fallback;
        } catch (error) {
            console.warn(`🔍 Selector error for ${selector}:`, error);
            return fallback;
        }
    }

    safeQuerySelectorAll(selector, fallback = []) {
        try {
            const elements = document.querySelectorAll(selector);
            return Array.from(elements);
        } catch (error) {
            console.warn(`🔍 Selector error for ${selector}:`, error);
            return fallback;
        }
    }
}

// Global instances
const authSessionManager = new AuthSessionManager();
const elementSelector = new ElementSelector();

// Enhanced Authentication Status Check with better error handling
async function checkAuthStatus() {
    // Skip auth check if we're in the middle of logging out
    if (window.isLoggingOut) {
        console.log('🔍 main.js: Skipping auth check - logging out');
        return;
    }

    // Skip auth check for public authentication pages
    const currentPath = window.location.pathname;
    const publicAuthPages = ['/signup', '/login', '/change-password'];
    if (publicAuthPages.includes(currentPath)) {
        console.log('🔍 main.js: Skipping auth check for public auth page:', currentPath);
        updateNavbarForUnauthenticatedUser();
        return;
    }

    console.log('🔍 main.js: Checking authentication status...');
    console.log('🔍 main.js: Current URL:', window.location.href);
    console.log('🔍 main.js: Cookies present:', document.cookie ? 'Yes' : 'No');

    try {
        const response = await fetch('/api/auth/me-cookie', {
            method: 'GET',
            credentials: 'include',
            headers: {
                'Cache-Control': 'no-cache'
            }
        });

        console.log('🔍 main.js: Auth response status:', response.status);
        console.log('🔍 main.js: Auth response headers:', Object.fromEntries(response.headers.entries()));

        if (response.ok) {
            const data = await response.json();
            console.log('🔍 main.js: Auth response data:', data);
            // Handle both old and new response structures
            const userData = data.user || data;
            if (userData && userData.email) {
                console.log('🔍 main.js: User authenticated, updating navbar...');
                await updateNavbarForAuthenticatedUser(userData);

                // Add authenticated class to body for CSS targeting
                document.body.classList.add('authenticated');
                document.body.classList.remove('unauthenticated');

                // DOUBLE-CHECK: Ensure logout element is visible after auth update
                setTimeout(() => {
                    const logoutElement = document.getElementById('logout');
                    if (logoutElement) {
                        console.log('🔍 main.js: Double-checking logout element visibility...');
                        logoutElement.style.display = 'inline-block';
                        logoutElement.style.visibility = 'visible';
                        logoutElement.style.opacity = '1';
                    }
                }, 100);

                // Additional fallback check
                setTimeout(() => {
                    ensureLogoutVisibility();
                }, 500);

            } else {
                console.log('🔍 main.js: No user data found, updating navbar for unauthenticated user');
                updateNavbarForUnauthenticatedUser();
            }
        } else if (response.status === 401) {
            console.log('🔍 main.js: User not authenticated (401), updating navbar for unauthenticated user');
            updateNavbarForUnauthenticatedUser();
        } else {
            console.error('🔍 main.js: Unexpected auth response status:', response.status);
            updateNavbarForUnauthenticatedUser();
        }
    } catch (error) {
        console.error('🔍 main.js: Error checking authentication status:', error);
        updateNavbarForUnauthenticatedUser();
    }
}

// Enhanced navbar update with element selector safety
async function updateNavbarForAuthenticatedUser(userData) {
    try {
        console.log('🔍 main.js: Starting navbar update for authenticated user:', userData.email);

        // Update desktop navbar
        const navUsername = elementSelector.safeQuerySelector('#nav-username');
        if (navUsername) {
            let usernameText = `Hi ${userData.name || userData.email.split('@')[0]}`;

            // Add tier indicators
            if (userData.tier === -1) {
                usernameText += '<span class="tester-nav-indicator">⚡</span>';
            } else if (userData.tier === 1) {
                usernameText += '<span class="pro-nav-indicator">⭐</span>';
            } else if (userData.tier === 2) {
                usernameText += '<span class="omega-nav-indicator">🌟</span>';
            }

            navUsername.innerHTML = usernameText;
            navUsername.style.display = 'inline-block'; // Explicitly show username
            console.log('🔍 main.js: Updated navUsername with:', usernameText);
        }

        // Update mobile navbar
        const mobileNavUsername = elementSelector.safeQuerySelector('#mobile-nav-username');
        if (mobileNavUsername) {
            let mobileUsernameText = `Hi ${userData.name || userData.email.split('@')[0]}`;

            // Add tier indicators for mobile
            if (userData.tier === -1) {
                mobileUsernameText += '<span class="tester-nav-indicator">⚡</span>';
            } else if (userData.tier === 1) {
                mobileUsernameText += '<span class="pro-nav-indicator">⭐</span>';
            } else if (userData.tier === 2) {
                mobileUsernameText += '<span class="omega-nav-indicator">🌟</span>';
            }

            mobileNavUsername.innerHTML = mobileUsernameText;
            mobileNavUsername.style.display = 'inline-block'; // Explicitly show mobile username
            console.log('🔍 main.js: Updated mobile navUsername with:', mobileUsernameText);
        }

        // Immediately show logout element - CRITICAL FIX
        const logoutElement = elementSelector.safeQuerySelector('#logout');
        if (logoutElement) {
            logoutElement.style.display = 'inline-block';
            logoutElement.style.visibility = 'visible';
            logoutElement.style.opacity = '1';
            console.log('🔍 main.js: Logout element explicitly made visible');
        }

        // Show authenticated elements
        const authElements = elementSelector.safeQuerySelectorAll('.auth-only');
        authElements.forEach(el => {
            el.style.display = 'inline-block';
            el.style.visibility = 'visible';
            el.style.opacity = '1';
            console.log('🔍 main.js: Made auth element visible:', el.id || el.className);
        });

        const unauthElements = elementSelector.safeQuerySelectorAll('.unauth-only');
        unauthElements.forEach(el => {
            el.style.display = 'none';
            console.log('🔍 main.js: Hid unauth element:', el.id || el.className);
        });

        // Check admin status and show admin elements
        if (userData.is_admin) {
            const adminElements = elementSelector.safeQuerySelectorAll('.admin-only');
            adminElements.forEach(el => {
                el.style.display = 'inline-block';
                el.style.visibility = 'visible';
                el.style.opacity = '1';
                console.log('🔍 main.js: Made admin element visible:', el.id || el.className);
            });
        }

        // Check tester status and show tester elements
        if (userData.tier === -1) {
            const testerElements = elementSelector.safeQuerySelectorAll('.tester-only');
            testerElements.forEach(el => {
                el.style.display = 'inline-block';
                el.style.visibility = 'visible';
                el.style.opacity = '1';
                console.log('🔍 main.js: Made tester element visible:', el.id || el.className);
            });
        }

        // Force immediate layout recalculation
        document.body.offsetHeight;

        console.log('🔍 main.js: Navbar update completed for authenticated user');
        
        // Signal to base template that main.js has handled authentication
        window.mainJsAuthHandled = true;

    } catch (error) {
        console.error('🔍 main.js: Error updating navbar for authenticated user:', error);
    }
}

// Enhanced navbar update for unauthenticated users
function updateNavbarForUnauthenticatedUser() {
    try {
        // Remove authenticated class from body
        document.body.classList.remove('authenticated');
        document.body.classList.add('unauthenticated');

        // Hide authenticated elements
        const authElements = elementSelector.safeQuerySelectorAll('.auth-only');
        authElements.forEach(el => {
            el.style.display = 'none';
            console.log('🔍 main.js: Hid auth element:', el.id || el.className);
        });

        // Show unauthenticated elements
        const unauthElements = elementSelector.safeQuerySelectorAll('.unauth-only');
        unauthElements.forEach(el => {
            el.style.display = 'inline-block';
            console.log('🔍 main.js: Showed unauth element:', el.id || el.className);
        });

        // Hide admin and tester elements
        const adminElements = elementSelector.safeQuerySelectorAll('.admin-only');
        adminElements.forEach(el => {
            el.style.display = 'none';
            console.log('🔍 main.js: Hid admin element:', el.id || el.className);
        });

        const testerElements = elementSelector.safeQuerySelectorAll('.tester-only');
        testerElements.forEach(el => {
            el.style.display = 'none';
            console.log('🔍 main.js: Hid tester element:', el.id || el.className);
        });

        // Clear username displays
        const navUsername = elementSelector.safeQuerySelector('#nav-username');
        if (navUsername) {
            navUsername.textContent = 'Login';
            navUsername.style.display = 'none';
        }

        const mobileNavUsername = elementSelector.safeQuerySelector('#mobile-nav-username');
        if (mobileNavUsername) {
            mobileNavUsername.textContent = 'Login';
            mobileNavUsername.style.display = 'none';
        }

        console.log('🔍 main.js: Navbar updated for unauthenticated user');
        
        // Signal to base template that main.js has handled authentication
        window.mainJsAuthHandled = true;

    } catch (error) {
        console.error('🔍 main.js: Error updating navbar for unauthenticated user:', error);
    }
}

// Final safeguard function to ensure logout element visibility
function ensureLogoutVisibility() {
    console.log('🔍 main.js: Running final logout visibility check...');

    const logoutElement = document.getElementById('logout');
    const navUsername = document.getElementById('nav-username');

    // Check if user is authenticated by looking for username element
    if (navUsername && navUsername.style.display !== 'none' && navUsername.textContent) {
        if (logoutElement) {
            // Force all visibility properties
            logoutElement.style.display = 'inline-block';
            logoutElement.style.visibility = 'visible';
            logoutElement.style.opacity = '1';
            logoutElement.style.position = 'relative';
            logoutElement.style.zIndex = '1';

            // Remove any CSS that might hide it
            logoutElement.style.removeProperty('display');
            logoutElement.style.removeProperty('visibility');
            logoutElement.style.removeProperty('opacity');

            // Add back the correct display
            logoutElement.style.display = 'inline-block';
            logoutElement.style.visibility = 'visible';
            logoutElement.style.opacity = '1';

            console.log('🔍 main.js: Logout element visibility enforced');
        } else {
            console.warn('🔍 main.js: Logout element not found during visibility check');
        }
    } else {
        console.log('🔍 main.js: User not authenticated, logout element should remain hidden');
    }
}

// Logout Handler
const logoutSpan = document.getElementById('logout');
if (logoutSpan) {
    logoutSpan.addEventListener('click', function() {
        // Get the current token from localStorage or cookies
        const currentToken = localStorage.getItem('auth_token') || 
                           (document.cookie.split('; ').find(row => row.startsWith('auth_token=')) || '').split('=')[1] ||
                           (document.cookie.split('; ').find(row => row.startsWith('auth_token_fallback=')) || '').split('=')[1];
        
        // Set a flag to prevent auth checks during logout
        window.isLoggingOut = true;
        
        // Immediately update UI to prevent flickering
        updateNavbarForUnauthenticatedUser();
        
        // Clear localStorage first
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user_data');
        localStorage.removeItem('userToken');
        
        // Clear cookie and blacklist token with timeout
        const logoutPromise = fetch('/api/auth/clear-cookie', {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                token: currentToken || ''
            })
        });
        
        // Add timeout to prevent hanging
        const timeoutPromise = new Promise((_, reject) => {
            setTimeout(() => reject(new Error('Logout timeout')), 5000); // 5 second timeout
        });
        
        Promise.race([logoutPromise, timeoutPromise])
            .then(() => {
                console.log('🔍 main.js: Logout successful');
                // Force a hard redirect to clear any cached state
                window.location.replace('/');
            })
            .catch(error => {
                console.error('🔍 main.js: Logout error:', error);
                // Even if logout fails, redirect to home
                window.location.replace('/');
            });
    });
}

// Initialize enhanced session management
document.addEventListener('DOMContentLoaded', function() {
    console.log('🔍 main.js: DOM loaded, initializing...');

    // Initialize auth session manager
    authSessionManager.init();

    // Immediate logout visibility check for authenticated users
    setTimeout(() => {
        ensureLogoutVisibility();
    }, 50);

    // Initial auth check with increased timeout
    setTimeout(() => {
        checkAuthStatus();
    }, 100); // Reduced wait time for faster auth check

    // Additional visibility check after auth
    setTimeout(() => {
        ensureLogoutVisibility();
    }, 1000);
    
    // Desktop navigation toggle (mobile handled by mobile.js)
    const navToggle = document.getElementById('nav-toggle');
    const navMenu = document.getElementById('nav-menu');
    
    if (navToggle && navMenu && window.innerWidth > 768) {
        // Desktop-only navigation toggle
        navToggle.addEventListener('click', function() {
            navMenu.classList.toggle('active');
            navToggle.classList.toggle('active');
        });
    }
    
    // Desktop dropdown menu functionality (mobile handled by mobile.js)
    if (window.innerWidth > 768) {
        const dropdowns = document.querySelectorAll('.dropdown');
        dropdowns.forEach(dropdown => {
            const link = dropdown.querySelector('.nav-link');
            const menu = dropdown.querySelector('.dropdown-menu');
            
            if (link && menu) {
                // Desktop-only dropdown toggle
                link.addEventListener('click', function(e) {
                    e.preventDefault();
                    menu.classList.toggle('active');
                });
            }
        });
    }
    
    // Close dropdowns when clicking outside
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.dropdown')) {
            document.querySelectorAll('.dropdown-menu').forEach(menu => {
                menu.classList.remove('active');
            });
        }
    });
    
    // Back to top button
    const backToTopButton = document.getElementById('back-to-top');
    if (backToTopButton) {
        window.addEventListener('scroll', function() {
            if (window.pageYOffset > 300) {
                backToTopButton.style.display = 'block';
            } else {
                backToTopButton.style.display = 'none';
            }
        });
        
        backToTopButton.addEventListener('click', function() {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }
    
    // Desktop smooth scrolling for anchor links (mobile handled by mobile.js)
    if (window.innerWidth > 768) {
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function(e) {
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });
    }
    
    // Add loading states to forms (excluding upload forms that handle their own loading states)
    document.querySelectorAll('form').forEach(form => {
        // Skip forms that have specific upload handling (like the file upload form)
        if (form.id === 'text-file-upload-form' || form.classList.contains('upload-form')) {
            console.log('🔍 [JS] DEBUG: Skipping global loading state for upload form:', form.id || form.className);
            return;
        }
        
        form.addEventListener('submit', function() {
            const submitButton = form.querySelector('button[type="submit"]');
            if (submitButton) {
                submitButton.disabled = true;
                submitButton.textContent = 'Loading...';
            }
        });
    });
    
    // Add error handling for images
    document.querySelectorAll('img').forEach(img => {
        img.addEventListener('error', function() {
            this.style.display = 'none';
        });
    });
    
    // Desktop error handling for external links (mobile handled by mobile.js)
    if (window.innerWidth > 768) {
        document.querySelectorAll('a[href^="http"]').forEach(link => {
            link.addEventListener('click', function(e) {
                // Add loading indicator for external links
                this.style.opacity = '0.7';
                setTimeout(() => {
                    this.style.opacity = '1';
                }, 1000);
            });
        });
    }
    
    // Prevent MutationObserver errors by ensuring DOM elements exist before observing
    if (typeof MutationObserver !== 'undefined') {
        // Only observe if the target element exists
        const observeElement = (selector, callback) => {
            const element = document.querySelector(selector);
            if (element) {
                const observer = new MutationObserver(callback);
                observer.observe(element, {
                    childList: true,
                    subtree: true
                });
                return observer;
            }
            return null;
        };
        
        // Example usage (if needed)
        // observeElement('#some-element', (mutations) => {
        //     mutations.forEach((mutation) => {
        //         console.log('DOM changed:', mutation);
        //     });
        // });
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    authSessionManager.destroy();
});

// Desktop-only CSS for error animations
const style = document.createElement('style');
style.textContent = `
    @keyframes error-shake {
        0%, 100% { transform: translateX(0); }
        25% { transform: translateX(-5px); }
        75% { transform: translateX(5px); }
    }
    
    .error-shake {
        animation: error-shake 0.5s ease-in-out;
    }
`;
document.head.appendChild(style); 