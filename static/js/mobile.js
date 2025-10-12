// Mobile-First JavaScript for BetterGovPH Data Visualizations
document.addEventListener('DOMContentLoaded', function() {
    // Use touchstart for better mobile responsiveness
    const toggleEvent = 'ontouchstart' in window ? 'touchstart' : 'click';
    
    // Mobile Navigation Toggle
    const navToggle = document.getElementById('nav-toggle');
    const navMenu = document.getElementById('nav-menu');
    
    
    // Create menu overlay
    let menuOverlay = document.querySelector('.menu-overlay');
    if (!menuOverlay) {
        menuOverlay = document.createElement('div');
        menuOverlay.className = 'menu-overlay';
        document.body.appendChild(menuOverlay);
    }
    
    if (navToggle && navMenu) {
        
        // Remove any existing event listeners to prevent conflicts
        const newNavToggle = navToggle.cloneNode(true);
        navToggle.parentNode.replaceChild(newNavToggle, navToggle);
        
        // Function to open menu
        function openMenu() {
            navMenu.classList.add('active');
            menuOverlay.classList.add('active');
            document.body.classList.add('menu-open');
            
            // FORCE dark text color on all navigation links
            const navLinks = navMenu.querySelectorAll('.nav-link');
            navLinks.forEach(link => {
                link.style.color = '#333333';
                link.style.setProperty('color', '#333333', 'important');
            });
            
        // FORCE dark text color on all dropdown links
        const dropdownLinks = navMenu.querySelectorAll('.dropdown-menu li a');
        dropdownLinks.forEach(link => {
            link.style.color = '#333333';
            link.style.setProperty('color', '#333333', 'important');
            link.style.background = 'transparent';
            link.style.setProperty('background', 'transparent', 'important');
        });
        
        // FORCE dropdown menu background
        const dropdownMenus = navMenu.querySelectorAll('.dropdown-menu');
        dropdownMenus.forEach(menu => {
            menu.style.background = 'rgba(255, 255, 255, 0.98)';
            menu.style.setProperty('background', 'rgba(255, 255, 255, 0.98)', 'important');
        });
            
            // Animate hamburger menu
            const bars = newNavToggle.querySelectorAll('.bar');
            bars.forEach((bar, index) => {
                if (index === 0) bar.style.transform = 'rotate(45deg) translate(5px, 5px)';
                if (index === 1) bar.style.opacity = '0';
                if (index === 2) bar.style.transform = 'rotate(-45deg) translate(7px, -6px)';
            });
            
        }
        
        // Function to close menu
        function closeMenu() {
            navMenu.classList.remove('active');
            menuOverlay.classList.remove('active');
            document.body.classList.remove('menu-open');
            
            // FORCE dark text color on all navigation links (maintain when closed)
            const navLinks = navMenu.querySelectorAll('.nav-link');
            navLinks.forEach(link => {
                link.style.color = '#333333';
                link.style.setProperty('color', '#333333', 'important');
            });
            
            // FORCE dark text color on all dropdown links (maintain when closed)
            const dropdownLinks = navMenu.querySelectorAll('.dropdown-menu li a');
            dropdownLinks.forEach(link => {
                link.style.color = '#333333';
                link.style.setProperty('color', '#333333', 'important');
            });
            
            // Reset hamburger menu
            const bars = newNavToggle.querySelectorAll('.bar');
            bars.forEach(bar => {
                bar.style.transform = 'none';
                bar.style.opacity = '1';
            });
            
            // console.log('❌ Menu closed - page slid back to right');
        }
        
        newNavToggle.addEventListener(toggleEvent, function(e) {
            // console.log('Mobile nav-toggle clicked!');
            // console.log('Event type:', e.type);
            // console.log('Event target:', e.target);
            // console.log('Event currentTarget:', e.currentTarget);
            e.preventDefault();
            e.stopPropagation(); // Prevent event bubbling
            e.stopImmediatePropagation(); // Stop other handlers
            
            const isMenuOpen = navMenu.classList.contains('active');
            
            if (isMenuOpen) {
                closeMenu();
            } else {
                openMenu();
            }
        });
        
        // Also try click event as fallback
        if (toggleEvent !== 'click') {
            newNavToggle.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                
                const isMenuOpen = navMenu.classList.contains('active');
                
                if (isMenuOpen) {
                    closeMenu();
                } else {
                    openMenu();
                }
            });
        }
        
        // Close menu when clicking overlay
        menuOverlay.addEventListener(toggleEvent, function(e) {
            e.preventDefault();
            closeMenu();
        });
        
        // Close menu when clicking menu items
        const menuLinks = navMenu.querySelectorAll('.nav-link');
        menuLinks.forEach(link => {
            link.addEventListener(toggleEvent, function(e) {
                // Don't prevent default for actual navigation
                // Just close the menu
                setTimeout(() => {
                    closeMenu();
                }, 100); // Small delay to allow navigation to happen
            });
        });
        
    }
    
    // Mobile Dropdown Toggle
    const dropdowns = document.querySelectorAll('.dropdown');
    
    dropdowns.forEach((dropdown, index) => {
        const dropdownLink = dropdown.querySelector('.nav-link');
        const dropdownMenu = dropdown.querySelector('.dropdown-menu');
        
        if (dropdownLink && dropdownMenu) {
            dropdownLink.addEventListener(toggleEvent, function(e) {
                e.preventDefault();
                e.stopPropagation();
                
                // Close other dropdowns
                dropdowns.forEach(otherDropdown => {
                    if (otherDropdown !== dropdown) {
                        otherDropdown.classList.remove('active');
                    }
                });
                
                dropdown.classList.toggle('active');
            });
        }
    });
    
    // Close mobile menu when clicking outside
    document.addEventListener(toggleEvent, function(e) {
        if (navMenu && navMenu.classList.contains('active')) {
            if (!navMenu.contains(e.target) && !navToggle.contains(e.target) && !menuOverlay.contains(e.target)) {
                // Add a small delay to prevent immediate closing
                setTimeout(() => {
                    closeMenu();
                }, 100);
            }
        }
    });
    
    // Close menu on escape key
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && navMenu && navMenu.classList.contains('active')) {
            closeMenu();
        }
    });
    
    // Mobile Back to Top Button
    const backToTopBtn = document.getElementById('back-to-top');
    if (backToTopBtn) {
        window.addEventListener('scroll', function() {
            if (window.pageYOffset > 300) {
                backToTopBtn.classList.add('show');
            } else {
                backToTopBtn.classList.remove('show');
            }
        });
        
        backToTopBtn.addEventListener(toggleEvent, function(e) {
            e.preventDefault();
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }
    
    // Mobile Smooth Scrolling for Anchor Links
    const anchorLinks = document.querySelectorAll('a[href^="#"]');
    anchorLinks.forEach(link => {
        link.addEventListener(toggleEvent, function(e) {
            const href = this.getAttribute('href');
            if (href !== '#') {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    const offsetTop = target.offsetTop - 80; // Account for fixed navbar
                    window.scrollTo({
                        top: offsetTop,
                        behavior: 'smooth'
                    });
                    
                    // Close mobile menu if open
                    if (navMenu && navMenu.classList.contains('active')) {
                        closeMenu(); // Use closeMenu here
                    }
                }
            }
        });
    });
    
    // Mobile Form Enhancements
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        // Prevent zoom on input focus (iOS)
        const inputs = form.querySelectorAll('input, textarea, select');
        inputs.forEach(input => {
            input.addEventListener('focus', function() {
                // Add a small delay to prevent zoom
                setTimeout(() => {
                    this.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }, 300);
            });
        });
        
        // Enhanced form submission with loading states
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Sending...';
                
                // Re-enable after 5 seconds as fallback
                setTimeout(() => {
                    submitBtn.disabled = false;
                    submitBtn.textContent = submitBtn.getAttribute('data-original-text') || 'Submit';
                }, 5000);
            }
        });
    });
    
    // Mobile Touch Feedback
    const touchElements = document.querySelectorAll('.btn, .nav-link, .product-card, .service-card');
    touchElements.forEach(element => {
        element.addEventListener('touchstart', function() {
            this.style.transform = 'scale(0.98)';
        });
        
        element.addEventListener('touchend', function() {
            this.style.transform = '';
        });
    });
    
    // Mobile Performance Optimizations
    let ticking = false;
    
    function updateOnScroll() {
        // Add scroll-based animations here if needed
        ticking = false;
    }
    
    window.addEventListener('scroll', function() {
        if (!ticking) {
            requestAnimationFrame(updateOnScroll);
            ticking = true;
        }
    });
    
    // Enhanced Mobile Authentication Session Management
    class MobileAuthSessionManager {
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
            // Track user activity to extend session (mobile-optimized)
            const activityEvents = ['touchstart', 'touchmove', 'scroll', 'click', 'keypress'];
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
                    this.handleSessionIssue();
                } else {
                    this.retryAttempts = 0; // Reset retry attempts on success
                }
            } catch (error) {
                this.handleSessionIssue();
            }
        }

        async validateSession() {
            const timeSinceActivity = Date.now() - this.lastActivity;
            
            if (timeSinceActivity > this.sessionTimeout) {
                await this.checkSessionHealth();
            }
        }

        handleSessionIssue() {
            this.retryAttempts++;
            
            if (this.retryAttempts >= this.maxRetries) {
                this.redirectToLogin();
            } else {
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

    // Enhanced Mobile Element Selector with Retry Logic
    class MobileElementSelector {
        constructor() {
            this.defaultTimeout = 15000; // 15 seconds for mobile (longer due to slower devices)
            this.retryInterval = 200; // 200ms for mobile
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
            
            throw new Error(`Mobile element not found: ${selector} (timeout: ${timeout}ms)`);
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
            
            throw new Error(`Mobile elements not found: ${selector} (timeout: ${timeout}ms)`);
        }

        safeQuerySelector(selector, fallback = null) {
            try {
                const element = document.querySelector(selector);
                return element || fallback;
            } catch (error) {
                return fallback;
            }
        }

        safeQuerySelectorAll(selector, fallback = []) {
            try {
                const elements = document.querySelectorAll(selector);
                return Array.from(elements);
            } catch (error) {
                return fallback;
            }
        }
    }

    // Global mobile instances
    const mobileAuthSessionManager = new MobileAuthSessionManager();
    const mobileElementSelector = new MobileElementSelector();

    // Enhanced Mobile Authentication Status Check
    async function checkMobileAuthStatus() {
        // Skip auth check if we're in the middle of logging out
        if (window.isLoggingOut) {
            return;
        }

        // Skip auth check for public authentication pages
        const currentPath = window.location.pathname;
        const publicAuthPages = ['/signup', '/login', '/change-password'];
        if (publicAuthPages.includes(currentPath)) {
            updateMobileNavbarForUnauthenticatedUser();
            return;
        }
        
        try {
            const response = await fetch('/api/auth/me-cookie', {
                method: 'GET',
                credentials: 'include',
                headers: {
                    'Cache-Control': 'no-cache'
                }
            });
            
            if (response.ok) {
                const data = await response.json();
                // Handle both old and new response structures
                const userData = data.user || data;
                if (userData && userData.email) {
                    await updateMobileNavbarForAuthenticatedUser(userData);
                } else {
                    updateMobileNavbarForUnauthenticatedUser();
                }
            } else if (response.status === 401) {
                updateMobileNavbarForUnauthenticatedUser();
            } else {
                updateMobileNavbarForUnauthenticatedUser();
            }
        } catch (error) {
            updateMobileNavbarForUnauthenticatedUser();
        }
    }

    // Enhanced mobile navbar update with element selector safety
    async function updateMobileNavbarForAuthenticatedUser(userData) {
        try {
            // Wait for mobile navbar elements to be available
            const mobileNavUsername = await mobileElementSelector.waitForElement('#mobile-nav-username', 8000);
            
            // Update mobile navbar
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
                // console.log('🔍 mobile.js: Updated mobile navUsername with:', mobileUsernameText);
            }
            
            // Show authenticated elements
            const authElements = mobileElementSelector.safeQuerySelectorAll('.auth-only');
            authElements.forEach(el => el.style.display = '');
            
            const unauthElements = mobileElementSelector.safeQuerySelectorAll('.unauth-only');
            unauthElements.forEach(el => el.style.display = 'none');
            
            // Check admin status and show admin elements
            if (userData.is_admin) {
                const adminElements = mobileElementSelector.safeQuerySelectorAll('.admin-only');
                adminElements.forEach(el => el.style.display = '');
            }
            
            // Check tester status and show tester elements
            if (userData.tier === -1) {
                const testerElements = mobileElementSelector.safeQuerySelectorAll('.tester-only');
                testerElements.forEach(el => el.style.display = '');
            }
            
            // Show secret menu for admin OR tester users
            if (userData.is_admin || userData.tier === -1) {
                // console.log('🔍 mobile.js: User is admin/tester, showing secret menu');
                const secretMenuElements = mobileElementSelector.safeQuerySelectorAll('#mobile-secret-menu-item');
                secretMenuElements.forEach(el => {
                    if (el) {
                        el.style.display = 'block';
                        el.style.visibility = 'visible';
                        el.style.opacity = '1';
                        // console.log('🔍 mobile.js: Shown secret menu element:', el.id);
                    }
                });
            }
            
        } catch (error) {
            // console.error('🔍 mobile.js: Error updating mobile navbar for authenticated user:', error);
        }
    }

    // Enhanced mobile navbar update for unauthenticated users
    function updateMobileNavbarForUnauthenticatedUser() {
        try {
            // Hide authenticated elements
            const authElements = mobileElementSelector.safeQuerySelectorAll('.auth-only');
            authElements.forEach(el => el.style.display = 'none');
            
            // Show unauthenticated elements
            const unauthElements = mobileElementSelector.safeQuerySelectorAll('.unauth-only');
            unauthElements.forEach(el => el.style.display = '');
            
            // Hide admin and tester elements
            const adminElements = mobileElementSelector.safeQuerySelectorAll('.admin-only');
            adminElements.forEach(el => el.style.display = 'none');
            
            const testerElements = mobileElementSelector.safeQuerySelectorAll('.tester-only');
            testerElements.forEach(el => el.style.display = 'none');
            
            // Clear mobile username display
            const mobileNavUsername = mobileElementSelector.safeQuerySelector('#mobile-nav-username');
            if (mobileNavUsername) {
                mobileNavUsername.textContent = 'Login';
            }
            
        } catch (error) {
            // console.error('🔍 mobile.js: Error updating mobile navbar for unauthenticated user:', error);
        }
    }
    
    // Enhanced Mobile Logout Handler
    const logoutSpan = document.getElementById('logout');
    if (logoutSpan) {
        // console.log('🔍 [JS] DEBUG: Mobile logout span found, adding event listener');
        
        // Add both touchstart and click events for better responsiveness
        logoutSpan.addEventListener('touchstart', function(e) {
            // console.log('🔍 [JS] DEBUG: Mobile logout touchstart event');
            handleMobileLogout(e);
        }, { passive: false });
        
        logoutSpan.addEventListener('click', function(e) {
            // console.log('🔍 [JS] DEBUG: Mobile logout click event');
            handleMobileLogout(e);
        });
        
        function handleMobileLogout(e) {
            e.preventDefault();
            e.stopPropagation();
            
            // console.log('🔍 [JS] DEBUG: Mobile logout handler triggered');
            
            // Get the current token from localStorage or cookies
            const currentToken = localStorage.getItem('auth_token') || 
                               (document.cookie.split('; ').find(row => row.startsWith('auth_token=')) || '').split('=')[1] ||
                               (document.cookie.split('; ').find(row => row.startsWith('auth_basic_email=')) || '').split('=')[1] ||
                               (document.cookie.split('; ').find(row => row.startsWith('auth_token_fallback=')) || '').split('=')[1];
            
            // console.log('🔍 [JS] DEBUG: Current token found:', !!currentToken);
            
            // Set a flag to prevent auth checks during logout
            window.isLoggingOut = true;
            
            // Immediately update UI to prevent flickering
            updateMobileNavbarForUnauthenticatedUser();
            
            // Clear localStorage first
            localStorage.removeItem('auth_token');
            localStorage.removeItem('user_data');
            
            // Add visual feedback
            const logoutSpan = mobileElementSelector.safeQuerySelector('#logout');
            if (logoutSpan) {
                logoutSpan.style.opacity = '0.5';
                logoutSpan.textContent = 'Logging out...';
            }
            
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
                setTimeout(() => reject(new Error('Mobile logout timeout')), 8000); // 8 second timeout for mobile
            });
            
            Promise.race([logoutPromise, timeoutPromise])
                .then(() => {
                    // console.log('🔍 [JS] DEBUG: Mobile logout successful');
                    // Force a hard redirect to clear any cached state
                    window.location.replace('/');
                })
                .catch(error => {
                    // console.error('🔍 [JS] DEBUG: Mobile logout error:', error);
                    // Even if logout fails, redirect to home
                    window.location.replace('/');
                });
        }
    } else {
        // console.error('❌ [JS] DEBUG: Mobile logout span not found');
    }
    
    // FORCE dark text color on mobile navigation links immediately
    function forceMobileNavTextColor() {
        const navMenu = document.getElementById('nav-menu');
        if (navMenu) {
            const navLinks = navMenu.querySelectorAll('.nav-link');
            navLinks.forEach(link => {
                link.style.color = '#333333';
                link.style.setProperty('color', '#333333', 'important');
            });
            
            const dropdownLinks = navMenu.querySelectorAll('.dropdown-menu li a');
            dropdownLinks.forEach(link => {
                link.style.color = '#333333';
                link.style.setProperty('color', '#333333', 'important');
                link.style.background = 'transparent';
                link.style.setProperty('background', 'transparent', 'important');
            });
            
            // Also force dropdown menu background
            const dropdownMenus = navMenu.querySelectorAll('.dropdown-menu');
            dropdownMenus.forEach(menu => {
                menu.style.background = 'rgba(255, 255, 255, 0.98)';
                menu.style.setProperty('background', 'rgba(255, 255, 255, 0.98)', 'important');
            });
            
            // console.log('🔍 mobile.js: Forced dark text color on navigation links and dropdowns');
        }
    }
    
    // Run immediately and on DOM changes
    forceMobileNavTextColor();
    
    // Run again after a short delay to catch any dynamically loaded content
    setTimeout(forceMobileNavTextColor, 100);
    setTimeout(forceMobileNavTextColor, 500);
    setTimeout(forceMobileNavTextColor, 1000);

    // Initialize enhanced mobile session management
    mobileAuthSessionManager.init();
    
    // Initial mobile auth check with increased timeout
    setTimeout(() => {
        checkMobileAuthStatus();
    }, 1500); // Wait 1.5 seconds for mobile page to fully load
    
    // Mobile-specific authentication improvements
    // console.log('Mobile authentication system initialized');
    
    // Add mobile-specific error handling for authentication
    window.addEventListener('unhandledrejection', function(event) {
        // console.error('Mobile unhandled promise rejection:', event.reason);
    });
    
    // Mobile-specific optimizations
    if ('serviceWorker' in navigator) {
        // Register service worker for offline capabilities
        navigator.serviceWorker.register('/sw.js').catch(function(err) {
            // console.log('ServiceWorker registration failed: ', err);
        });
    }
    
    // Mobile viewport height fix for mobile browsers
    function setVH() {
        let vh = window.innerHeight * 0.01;
        document.documentElement.style.setProperty('--vh', `${vh}px`);
    }
    
    setVH();
    window.addEventListener('resize', setVH);
    window.addEventListener('orientationchange', setVH);
    
    // Mobile-specific CSS
    const mobileStyle = document.createElement('style');
    mobileStyle.textContent = `
        /* Mobile-optimized touch targets */
        @media (max-width: 767px) {
            .btn, .nav-link, .dropdown-menu li a {
                min-height: 44px;
                min-width: 44px;
            }
            
            /* Improve mobile scrolling */
            .nav-menu {
                -webkit-overflow-scrolling: touch;
            }
            
            /* Mobile-friendly focus states */
            .btn:focus,
            .nav-link:focus,
            input:focus,
            textarea:focus {
                outline: 2px solid var(--primary-color);
                outline-offset: 2px;
            }
        }
        
        /* Use custom viewport height for mobile browsers */
        .hero {
            height: calc(var(--vh, 1vh) * 100);
        }
    `;
    document.head.appendChild(mobileStyle);
    
    // Mobile lazy loading for images
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.classList.remove('lazy');
                    imageObserver.unobserve(img);
                }
            });
        });
        
        document.querySelectorAll('img[data-src]').forEach(img => {
            imageObserver.observe(img);
        });
    }
    
    // Mobile error handling
    window.addEventListener('error', function(e) {
        // console.error('Mobile error:', e.error);
    });
    
    // Mobile performance monitoring
    if ('performance' in window) {
        window.addEventListener('load', function() {
            const navigation = performance.getEntriesByType('navigation')[0];
            if (navigation) {
                // console.log('Mobile page load time:', navigation.loadEventEnd - navigation.loadEventStart);
            }
        });
    }
    
    // Initialize mobile budget functionality if on budget page
    // console.log('🔍 Mobile: DOM loaded, about to call initializeMobileBudget');
    
    // Simple test - add a visible message to confirm JavaScript is running
    const testDiv = document.createElement('div');
    testDiv.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:green;color:white;padding:20px;z-index:9999;font-size:16px;';
    testDiv.innerHTML = '✅ MOBILE JAVASCRIPT IS WORKING!<br>If you see this, the mobile.js file loaded correctly.';
    document.body.appendChild(testDiv);
    
    // Remove the test message after 3 seconds
    setTimeout(() => {
        if (testDiv.parentNode) {
            testDiv.parentNode.removeChild(testDiv);
        }
    }, 3000);
    
    initializeMobileBudget();
    // console.log('🔍 Mobile: initializeMobileBudget call completed');
}); 

// Mobile Budget Functions
let mobileBudgetData = [];
let mobileCurrentPage = 1;
let mobileRowsPerPage = 5;
let mobileTotalPages = 1;
let mobileFilters = {};

// Initialize mobile budget functionality when on budget page
function initializeMobileBudget() {
    // console.log('🔍 Mobile Budget: initializeMobileBudget called');
    // console.log('🔍 Current path:', window.location.pathname);
    // console.log('🔍 Mobile budget section found:', !!document.querySelector('.budget-section'));
    
    // Show debug info on page for mobile debugging
    const debugDiv = document.createElement('div');
    debugDiv.style.cssText = 'position:fixed;top:10px;left:10px;background:red;color:white;padding:10px;z-index:9999;font-size:12px;max-width:300px;';
    debugDiv.innerHTML = `DEBUG:<br>Path: ${window.location.pathname}<br>Section: ${!!document.querySelector('.budget-section')}`;
    document.body.appendChild(debugDiv);
    
    // Check if we're on the mobile budget page
    if (window.location.pathname.includes('/budget') || document.querySelector('.budget-section')) {
        // console.log('🔍 Mobile Budget: Initializing budget functionality...');
        debugDiv.innerHTML += '<br>✅ Initializing budget...';
        
        // Load initial data
        // console.log('🔍 Mobile Budget: About to call loadMobileGAADocuments');
        debugDiv.innerHTML += '<br>📄 Loading GAA docs...';
        loadMobileGAADocuments();
        // console.log('🔍 Mobile Budget: About to call loadMobileDataBrowser');
        debugDiv.innerHTML += '<br>📊 Loading data browser...';
        loadMobileDataBrowser();
        // console.log('🔍 Mobile Budget: About to call loadMobileDuplicates');
        debugDiv.innerHTML += '<br>🔍 Loading duplicates...';
        loadMobileDuplicates();
        
        // Event listeners for buttons
        const applyFiltersBtn = document.getElementById('mobile-apply-filters-btn');
        if (applyFiltersBtn) {
            applyFiltersBtn.addEventListener('click', () => {
                mobileCurrentPage = 1;
                loadMobileDataBrowser();
            });
        }
        
        const clearFiltersBtn = document.getElementById('mobile-clear-filters-btn');
        if (clearFiltersBtn) {
            clearFiltersBtn.addEventListener('click', () => {
                // Clear all filter inputs
                document.querySelectorAll('[id^="mobile-filter-"]').forEach(input => {
                    input.value = '';
                });
                mobileCurrentPage = 1;
                loadMobileDataBrowser();
            });
        }
        
        // Pagination buttons
        const prevBtn = document.getElementById('mobile-prev-page-btn');
        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (mobileCurrentPage > 1) {
                    mobileCurrentPage--;
                    loadMobileDataBrowser();
                }
            });
        }
        
        const nextBtn = document.getElementById('mobile-next-page-btn');
        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                if (mobileCurrentPage < mobileTotalPages) {
                    mobileCurrentPage++;
                    loadMobileDataBrowser();
                }
            });
        }
        
        // Rows per page change
        const rowsPerPageSelect = document.getElementById('mobile-rows-per-page');
        if (rowsPerPageSelect) {
            rowsPerPageSelect.addEventListener('change', () => {
                mobileRowsPerPage = parseInt(rowsPerPageSelect.value);
                mobileCurrentPage = 1;
                loadMobileDataBrowser();
            });
        }
        
        // Sort controls
        const sortSelect = document.getElementById('mobile-sort-select');
        if (sortSelect) {
            sortSelect.addEventListener('change', () => {
                mobileCurrentPage = 1;
                loadMobileDataBrowser();
            });
        }
        
        const sortOrderBtn = document.getElementById('mobile-sort-order-btn');
        if (sortOrderBtn) {
            sortOrderBtn.addEventListener('click', () => {
                const currentOrder = sortOrderBtn.dataset.order;
                const newOrder = currentOrder === 'DESC' ? 'ASC' : 'DESC';
                sortOrderBtn.dataset.order = newOrder;
                sortOrderBtn.textContent = newOrder === 'DESC' ? '↓' : '↑';
                mobileCurrentPage = 1;
                loadMobileDataBrowser();
            });
        }
        
        // Duplicates controls
        const duplicatesSortBy = document.getElementById('mobile-duplicates-sort-by');
        if (duplicatesSortBy) {
            duplicatesSortBy.addEventListener('change', () => {
                mobileCurrentPage = 1;
                loadMobileDuplicates();
            });
        }
        
        const duplicatesSortOrder = document.getElementById('mobile-duplicates-sort-order');
        if (duplicatesSortOrder) {
            duplicatesSortOrder.addEventListener('change', () => {
                mobileCurrentPage = 1;
                loadMobileDuplicates();
            });
        }
        
        const duplicatesRowsPerPage = document.getElementById('mobile-duplicates-rows-per-page');
        if (duplicatesRowsPerPage) {
            duplicatesRowsPerPage.addEventListener('change', () => {
                mobileRowsPerPage = parseInt(duplicatesRowsPerPage.value);
                mobileCurrentPage = 1;
                loadMobileDuplicates();
            });
        }
        
        // console.log('🔍 Mobile Budget: All event listeners attached');
    }
}

// Mobile GAA Documents Loading
async function loadMobileGAADocuments() {
    // console.log('🔍 Mobile: Loading GAA documents...');
    
    const titleElement = document.getElementById('mobile-gaa-files-title');
    const gridElement = document.getElementById('mobile-gaa-files-grid');
    
    // console.log('🔍 Mobile: titleElement found:', !!titleElement);
    // console.log('🔍 Mobile: gridElement found:', !!gridElement);
    
    if (!titleElement || !gridElement) {
        // console.error('❌ Mobile: Required elements not found');
        // console.error('❌ Mobile: titleElement:', titleElement);
        // console.error('❌ Mobile: gridElement:', gridElement);
        
        // Show error on page for mobile debugging
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = 'position:fixed;top:150px;left:10px;background:orange;color:white;padding:10px;z-index:9999;font-size:12px;max-width:300px;';
        errorDiv.innerHTML = '❌ ERROR: Required elements not found<br>titleElement: ' + !!titleElement + '<br>gridElement: ' + !!gridElement;
        document.body.appendChild(errorDiv);
        return;
    }
    
    try {
        // console.log('🔍 Mobile: About to fetch /api/budget/files for 2025');
        
        const response = await fetch('/api/budget/files?year=2025', {
            credentials: 'include'
        });
        
        // console.log('🔍 Mobile: Response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        // console.log('🔍 Mobile: GAA files data:', data);
        
        // Show success on page for mobile debugging
        const successDiv = document.createElement('div');
        successDiv.style.cssText = 'position:fixed;top:200px;left:10px;background:blue;color:white;padding:10px;z-index:9999;font-size:12px;max-width:300px;';
        successDiv.innerHTML = '✅ API Response: ' + (data.success ? 'SUCCESS' : 'FAILED') + '<br>Files: ' + (data.files ? data.files.length : 0);
        document.body.appendChild(successDiv);
        
        if (data.success && data.files) {
            titleElement.textContent = '📊 Available GAA Budget Documents';
            gridElement.innerHTML = '';
            
            data.files.forEach(file => {
                const fileCard = document.createElement('div');
                fileCard.className = 'mobile-file-card';
                fileCard.innerHTML = `
                    <div class="mobile-file-info">
                        <h4>${file.name}</h4>
                        <p>Size: ${file.size || 'Unknown'}</p>
                        <p>Uploaded: ${file.upload_date || 'Unknown'}</p>
                    </div>
                `;
                gridElement.appendChild(fileCard);
            });
        } else {
            throw new Error(data.error || 'Failed to load files');
        }
        
    } catch (error) {
        // console.error('❌ Mobile: Error loading GAA documents:', error);
        titleElement.textContent = '❌ Error Loading Documents';
        gridElement.innerHTML = `
            <div class="mobile-error-files" style="grid-column:1/-1;text-align:center;padding:2em;color:#dc3545;">
                <i class="fas fa-exclamation-triangle" style="margin-right:0.5em;"></i>
                <span>Error: ${error.message}</span>
            </div>
        `;
    }
}

// Mobile Data Browser Loading
async function loadMobileDataBrowser() {
    // console.log('🔍 Mobile: Loading data browser...');
    
    const container = document.getElementById('mobile-data-browser-container');
    if (!container) {
        // console.error('❌ Mobile: Data browser container not found');
        return;
    }
    
    try {
        // Build filters
        const filters = {};
        const filterInputs = document.querySelectorAll('[id^="mobile-filter-"]');
        filterInputs.forEach(input => {
            if (input.value.trim()) {
                const key = input.id.replace('mobile-filter-', '');
                filters[key] = input.value.trim();
            }
        });
        
        // Build URL with filters
        const sortSelect = document.getElementById('mobile-sort-select');
        const sortOrderBtn = document.getElementById('mobile-sort-order-btn');
        
        const params = new URLSearchParams({
            year: '2025',
            page: mobileCurrentPage,
            limit: mobileRowsPerPage,
            sort: sortSelect ? sortSelect.value : 'amt',
            order: sortOrderBtn ? sortOrderBtn.dataset.order : 'DESC',
            ...filters
        });
        
        // console.log('🔍 Mobile: Fetching data browser with params:', params.toString());
        
        const response = await fetch(`/api/budget/data-browser?${params}`, {
            credentials: 'include'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        // console.log('🔍 Mobile: Data browser response:', data);
        
        if (data.success) {
            mobileBudgetData = data.rows || data.data || [];
            mobileTotalPages = data.pagination ? data.pagination.total_pages : (data.total_pages || 1);
            
            displayMobileDataBrowser(mobileBudgetData);
            updateMobilePagination();
        } else {
            throw new Error(data.error || 'Failed to load data');
        }
        
    } catch (error) {
        // console.error('❌ Mobile: Error loading data browser:', error);
        container.innerHTML = `
            <div class="mobile-error-message">
                <i class="fas fa-exclamation-triangle"></i>
                Error: ${error.message}
            </div>
        `;
    }
}

// Display mobile data browser results
function displayMobileDataBrowser(data) {
    const container = document.getElementById('mobile-data-browser-container');
    if (!container) return;
    
    if (!data || data.length === 0) {
        container.innerHTML = `
            <div class="mobile-no-data">
                <i class="fas fa-info-circle"></i>
                No data found matching your filters.
            </div>
        `;
        return;
    }
    
    // Create mobile-optimized table
    const table = document.createElement('table');
    table.className = 'mobile-data-browser-table';
    
    // Table header
    const thead = document.createElement('thead');
    thead.innerHTML = `
        <tr>
            <th>Department</th>
            <th>Agency</th>
            <th>Description</th>
            <th>Amount</th>
        </tr>
    `;
    table.appendChild(thead);
    
    // Table body
    const tbody = document.createElement('tbody');
    data.forEach(row => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${row.uacs_dpt_dsc || 'N/A'}</td>
            <td>${row.uacs_agy_dsc || 'N/A'}</td>
            <td>${row.dsc || 'N/A'}</td>
            <td class="mobile-data-amount">₱${formatNumber(row.amt)}</td>
        `;
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    
    container.innerHTML = '';
    container.appendChild(table);
}

// Mobile pagination update
function updateMobilePagination() {
    const pageInfo = document.getElementById('mobile-page-info');
    const prevBtn = document.getElementById('mobile-prev-page-btn');
    const nextBtn = document.getElementById('mobile-next-page-btn');
    
    if (pageInfo) {
        pageInfo.textContent = `Page ${mobileCurrentPage} of ${mobileTotalPages}`;
    }
    
    if (prevBtn) {
        prevBtn.disabled = mobileCurrentPage <= 1;
    }
    
    if (nextBtn) {
        nextBtn.disabled = mobileCurrentPage >= mobileTotalPages;
    }
}

// Mobile duplicates loading
async function loadMobileDuplicates() {
    // console.log('🔍 Mobile: Loading potential duplicates...');
    
    const container = document.getElementById('mobile-duplicates-results');
    if (!container) {
        // console.error('❌ Mobile: Duplicates container not found');
        return;
    }
    
    try {
        const duplicatesSortBy = document.getElementById('mobile-duplicates-sort-by');
        const duplicatesSortOrder = document.getElementById('mobile-duplicates-sort-order');
        
        const params = new URLSearchParams({
            year: '2025',
            page: mobileCurrentPage,
            limit: mobileRowsPerPage,
            sort_by: duplicatesSortBy ? duplicatesSortBy.value : 'calculated_score',
            sort_order: duplicatesSortOrder ? duplicatesSortOrder.value : 'DESC'
        });
        
        const response = await fetch(`/api/budget/duplicates?${params}`, {
            credentials: 'include'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        // console.log('🔍 Mobile: Duplicates response:', data);
        
        if (data.success) {
            displayMobileDuplicates(data.duplicates || data.data || []);
        } else {
            throw new Error(data.error || 'Failed to load duplicates');
        }
        
    } catch (error) {
        // console.error('❌ Mobile: Error loading duplicates:', error);
        container.innerHTML = `
            <div class="mobile-error-message">
                <i class="fas fa-exclamation-triangle"></i>
                Error: ${error.message}
            </div>
        `;
    }
}

// Display mobile duplicates
function displayMobileDuplicates(data) {
    const container = document.getElementById('mobile-duplicates-results');
    if (!container) return;
    
    if (!data || data.length === 0) {
        container.innerHTML = `
            <div class="mobile-no-data">
                <i class="fas fa-check-circle"></i>
                No potential duplicates found! Your data looks clean.
            </div>
        `;
        return;
    }
    
    const table = document.createElement('table');
    table.className = 'mobile-duplicates-table';
    
    // Table header
    const thead = document.createElement('thead');
    thead.innerHTML = `
        <tr>
            <th>Department</th>
            <th>Agency</th>
            <th>Description</th>
            <th>Amount</th>
            <th>Count</th>
            <th>Score</th>
        </tr>
    `;
    table.appendChild(thead);
    
    // Table body
    const tbody = document.createElement('tbody');
    data.forEach(duplicate => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${duplicate.dept_desc1 || duplicate.uacs_dpt_dsc || 'N/A'}</td>
            <td>${duplicate.agy_desc1 || duplicate.uacs_agy_dsc || 'N/A'}</td>
            <td>${duplicate.description || duplicate.dsc || 'N/A'}</td>
            <td class="mobile-duplicate-amount">₱${formatNumber(duplicate.max_amount || duplicate.amount)}</td>
            <td class="mobile-duplicate-count">${duplicate.duplicate_count}</td>
            <td class="mobile-duplicate-score">${duplicate.calculated_score || 0}%</td>
        `;
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    
    container.innerHTML = '';
    container.appendChild(table);
}

// Mobile columns loading
async function loadMobileColumns() {
    // console.log('🔍 Mobile: Loading columns...');
    
    const container = document.getElementById('mobile-columns-container');
    if (!container) {
        // console.error('❌ Mobile: Columns container not found');
        return;
    }
    
    try {
        const response = await fetch('/api/budget/columns?year=2025', {
            credentials: 'include'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        // console.log('🔍 Mobile: Columns response:', data);
        
        if (data.success && data.columns) {
            displayMobileColumns(data.columns);
        } else {
            throw new Error(data.error || 'Failed to load columns');
        }
        
    } catch (error) {
        // console.error('❌ Mobile: Error loading columns:', error);
        container.innerHTML = `
            <div class="mobile-error-message">
                <i class="fas fa-exclamation-triangle"></i>
                Error: ${error.message}
            </div>
        `;
    }
}


// Utility functions
function formatNumber(num) {
    if (!num) return '0';
    return new Intl.NumberFormat('en-PH').format(num);
}


// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    mobileAuthSessionManager.destroy();
}); 