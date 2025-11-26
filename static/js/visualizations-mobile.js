/**
 * Mobile Visualizations JavaScript
 * Handles data fetching and interactivity for mobile templates
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('🚀 [MOBILE] Visualizations JS loading...');

    // Initialize mobile components
    initializeMobileDataBrowser();
    initializeMobileDuplicates();
    initializeMobileColumns();
});

// --- Data Browser Logic ---

let currentMobilePage = 1;
let currentMobileSortBy = 'amt';
let currentMobileSortOrder = 'DESC';
let currentMobileFilters = {};

function initializeMobileDataBrowser() {
    const container = document.getElementById('mobile-data-browser-container');
    if (!container) return;

    console.log('📱 [MOBILE] Initializing Data Browser...');

    // Event Listeners for Filters
    document.getElementById('mobile-apply-filters-btn')?.addEventListener('click', applyMobileFilters);
    document.getElementById('mobile-clear-filters-btn')?.addEventListener('click', clearMobileFilters);
    
    // Event Listeners for Sort/Pagination
    document.getElementById('mobile-sort-select')?.addEventListener('change', (e) => {
        currentMobileSortBy = e.target.value;
        loadMobileDataBrowser();
    });
    
    document.getElementById('mobile-sort-order-btn')?.addEventListener('click', (e) => {
        const btn = e.target;
        currentMobileSortOrder = currentMobileSortOrder === 'DESC' ? 'ASC' : 'DESC';
        btn.textContent = currentMobileSortOrder === 'DESC' ? '↓' : '↑';
        btn.setAttribute('data-order', currentMobileSortOrder);
        loadMobileDataBrowser();
    });

    document.getElementById('mobile-prev-page-btn')?.addEventListener('click', () => {
        if (currentMobilePage > 1) {
            currentMobilePage--;
            loadMobileDataBrowser();
        }
    });

    document.getElementById('mobile-next-page-btn')?.addEventListener('click', () => {
        currentMobilePage++;
        loadMobileDataBrowser();
    });

    // Initial Load
    loadMobileDataBrowser();
}

function applyMobileFilters() {
    currentMobileFilters = {
        uacs_dpt_dsc: document.getElementById('mobile-filter-uacs_dpt_dsc')?.value,
        uacs_agy_dsc: document.getElementById('mobile-filter-uacs_agy_dsc')?.value,
        dsc: document.getElementById('mobile-filter-dsc')?.value,
        amt_min: document.getElementById('mobile-filter-amt-min')?.value
    };
    currentMobilePage = 1; // Reset to first page
    loadMobileDataBrowser();
}

function clearMobileFilters() {
    currentMobileFilters = {};
    document.getElementById('mobile-filter-uacs_dpt_dsc').value = '';
    document.getElementById('mobile-filter-uacs_agy_dsc').value = '';
    document.getElementById('mobile-filter-dsc').value = '';
    document.getElementById('mobile-filter-amt-min').value = '';
    currentMobilePage = 1;
    loadMobileDataBrowser();
}

async function loadMobileDataBrowser() {
    const container = document.getElementById('mobile-data-browser-container');
    if (!container) return;

    container.innerHTML = '<div class="mobile-loading-spinner">Loading budget data...</div>';

    try {
        const params = new URLSearchParams({
            year: '2025', // Default to 2025 for now
            page: currentMobilePage,
            limit: 5, // Fixed limit for mobile
            sort_by: currentMobileSortBy,
            sort_order: currentMobileSortOrder
        });

        // Add filters
        Object.entries(currentMobileFilters).forEach(([key, value]) => {
            if (value) params.append(key, value);
        });

        const response = await fetch(`/api/budget/data-browser?${params.toString()}`);
        const result = await response.json();

        if (result.success) {
            displayMobileDataBrowser(result);
            updateMobilePagination(result.pagination);
        } else {
            container.innerHTML = `<div class="p-4 text-center text-red-500">Error: ${result.error}</div>`;
        }
    } catch (error) {
        console.error('❌ [MOBILE] Error loading data browser:', error);
        container.innerHTML = '<div class="p-4 text-center text-red-500">Failed to load data.</div>';
    }
}

function displayMobileDataBrowser(data) {
    const container = document.getElementById('mobile-data-browser-container');
    if (!container) return;

    if (!data.rows || data.rows.length === 0) {
        container.innerHTML = '<div class="p-4 text-center text-gray-500">No records found.</div>';
        return;
    }

    let html = '<div class="space-y-3">';
    
    data.rows.forEach(row => {
        const amount = parseFloat(row.amt || 0);
        const formattedAmount = `₱${(amount * 1000).toLocaleString('en-US')}`; // Assuming amount is in thousands like desktop
        
        html += `
            <div class="bg-gray-50 p-3 rounded-lg border border-gray-200 shadow-sm">
                <div class="flex justify-between items-start mb-2">
                    <div class="text-xs font-bold text-blue-800 bg-blue-100 px-2 py-1 rounded">
                        ${row.uacs_dpt_dsc || 'Unknown Dept'}
                    </div>
                    <div class="text-sm font-bold text-green-700">
                        ${formattedAmount}
                    </div>
                </div>
                <div class="text-xs text-gray-600 mb-1 font-semibold">
                    ${row.uacs_agy_dsc || 'Unknown Agency'}
                </div>
                <div class="text-sm text-gray-800">
                    ${row.dsc || 'No description'}
                </div>
            </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}

function updateMobilePagination(pagination) {
    const prevBtn = document.getElementById('mobile-prev-page-btn');
    const nextBtn = document.getElementById('mobile-next-page-btn');
    const infoSpan = document.getElementById('mobile-page-info');

    if (prevBtn) prevBtn.disabled = currentMobilePage <= 1;
    if (nextBtn) nextBtn.disabled = !pagination.has_next;
    if (infoSpan) infoSpan.textContent = `Page ${currentMobilePage} of ${pagination.total_pages || '?'}`;
}

// --- Duplicates Logic ---

let currentMobileDuplicatesPage = 1;

function initializeMobileDuplicates() {
    // Toggle function is inline in HTML (toggleMobileDuplicates)
    // We just need to handle pagination and loading
    
    document.getElementById('mobile-duplicates-prev-page-btn')?.addEventListener('click', () => {
        if (currentMobileDuplicatesPage > 1) {
            currentMobileDuplicatesPage--;
            loadMobileDuplicates();
        }
    });

    document.getElementById('mobile-duplicates-next-page-btn')?.addEventListener('click', () => {
        currentMobileDuplicatesPage++;
        loadMobileDuplicates();
    });
    
    document.getElementById('mobile-duplicates-sort-by')?.addEventListener('change', () => {
        currentMobileDuplicatesPage = 1;
        loadMobileDuplicates();
    });
}

// Global function for toggle (called from HTML)
window.toggleMobileDuplicates = function() {
    const container = document.getElementById('mobile-duplicates-container');
    const icon = document.getElementById('mobile-duplicates-collapse-icon');
    
    if (container.classList.contains('hidden')) {
        container.classList.remove('hidden');
        icon.textContent = '▲';
        loadMobileDuplicates();
    } else {
        container.classList.add('hidden');
        icon.textContent = '▼';
    }
};

async function loadMobileDuplicates() {
    const container = document.getElementById('mobile-duplicates-results');
    if (!container) return;

    container.innerHTML = '<div class="mobile-loading-spinner">Loading duplicates...</div>';

    const sortBy = document.getElementById('mobile-duplicates-sort-by')?.value || 'calculated_score';
    const limit = document.getElementById('mobile-duplicates-rows-per-page')?.value || 5;

    try {
        const params = new URLSearchParams({
            year: '2025',
            page: currentMobileDuplicatesPage,
            limit: limit,
            sort_by: sortBy,
            sort_order: 'DESC'
        });

        const response = await fetch(`/api/budget/duplicates?${params.toString()}`);
        const result = await response.json();

        if (result.success) {
            displayMobileDuplicates(result);
            updateMobileDuplicatesPagination(result.pagination);
        } else {
            container.innerHTML = `<div class="p-4 text-center text-red-500">Error: ${result.error}</div>`;
        }
    } catch (error) {
        console.error('❌ [MOBILE] Error loading duplicates:', error);
        container.innerHTML = '<div class="p-4 text-center text-red-500">Failed to load duplicates.</div>';
    }
}

function displayMobileDuplicates(data) {
    const container = document.getElementById('mobile-duplicates-results');
    if (!container) return;

    if (!data.duplicates || data.duplicates.length === 0) {
        container.innerHTML = '<div class="p-4 text-center text-gray-500">No duplicates found.</div>';
        return;
    }

    let html = '<div class="space-y-3">';
    
    data.duplicates.forEach(dup => {
        const amount = parseFloat(dup.amount || 0);
        const formattedAmount = `₱${(amount * 1000).toLocaleString('en-US')}`;
        const score = Math.round(dup.calculated_score || 0);
        
        html += `
            <div class="bg-red-50 p-3 rounded-lg border border-red-200 shadow-sm">
                <div class="flex justify-between items-center mb-2">
                    <span class="bg-red-600 text-white text-xs font-bold px-2 py-1 rounded-full">
                        Score: ${score}
                    </span>
                    <span class="text-xs text-red-800 font-semibold">
                        ${dup.duplicate_count} matches
                    </span>
                </div>
                <div class="text-sm font-bold text-gray-800 mb-1">
                    ${dup.description || 'No description'}
                </div>
                <div class="text-sm font-bold text-green-700">
                    ${formattedAmount}
                </div>
            </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}

function updateMobileDuplicatesPagination(pagination) {
    const prevBtn = document.getElementById('mobile-duplicates-prev-page-btn');
    const nextBtn = document.getElementById('mobile-duplicates-next-page-btn');
    const infoSpan = document.getElementById('mobile-duplicates-page-info');

    if (prevBtn) prevBtn.disabled = currentMobileDuplicatesPage <= 1;
    if (nextBtn) nextBtn.disabled = !pagination.has_next;
    if (infoSpan) infoSpan.textContent = `Page ${currentMobileDuplicatesPage} of ${pagination.total_pages || '?'}`;
}

// --- Columns Logic ---

window.toggleMobileColumns = function() {
    const container = document.getElementById('mobile-columns-container');
    const icon = document.getElementById('mobile-columns-collapse-icon');
    
    if (container.classList.contains('hidden')) {
        container.classList.remove('hidden');
        icon.textContent = '▲';
        loadMobileColumns();
    } else {
        container.classList.add('hidden');
        icon.textContent = '▼';
    }
};

async function loadMobileColumns() {
    const container = document.getElementById('mobile-columns-container');
    if (!container || container.innerHTML.includes('mobile-column-card')) return; // Don't reload if already loaded

    container.innerHTML = '<div class="mobile-loading-spinner">Loading columns...</div>';

    try {
        const response = await fetch('/api/budget/columns?year=2025');
        const result = await response.json();

        if (result.success) {
            displayMobileColumns(result.data);
        } else {
            container.innerHTML = `<div class="p-4 text-center text-red-500">Error: ${result.error}</div>`;
        }
    } catch (error) {
        console.error('❌ [MOBILE] Error loading columns:', error);
        container.innerHTML = '<div class="p-4 text-center text-red-500">Failed to load columns.</div>';
    }
}

function displayMobileColumns(columns) {
    const container = document.getElementById('mobile-columns-container');
    if (!container) return;

    if (!columns || columns.length === 0) {
        container.innerHTML = '<div class="p-4 text-center text-gray-500">No columns found.</div>';
        return;
    }

    let html = '<div class="grid grid-cols-1 gap-2">';
    
    columns.forEach(col => {
        html += `
            <div class="bg-white p-3 rounded border border-gray-200">
                <div class="flex justify-between items-center">
                    <span class="font-mono text-sm font-bold text-blue-800">${col.column_name}</span>
                    <span class="text-xs bg-gray-100 px-2 py-1 rounded text-gray-600">${col.data_type}</span>
                </div>
            </div>
        `;
    });

    html += '</div>';
    container.innerHTML = html;
}
