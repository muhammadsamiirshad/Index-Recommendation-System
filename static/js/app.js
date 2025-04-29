/**
 * Automated Index Recommendation System
 * Main JavaScript file for client-side functionality
 */

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    try {
        console.log("DOM loaded, initializing app.js");
        
        // Create toast container if it doesn't exist
        if (!document.getElementById('toast-container')) {
            const toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'fixed bottom-4 right-4 flex flex-col space-y-2 z-50';
            document.body.appendChild(toastContainer);
        }

        // Initialize all interactive elements
        try {
            initializeDropdowns();
            initializeDarkMode();
            initializeTableEnhancements();
            
            // Make chart initialization optional in case Chart.js isn't loaded
            if (typeof Chart !== 'undefined') {
                initializeCharts();
            } else {
                console.warn("Chart.js is not available. Charts will not be initialized.");
            }
        } catch (err) {
            console.error("Error during UI initialization:", err);
            // Continue execution even if some UI elements fail
        }

        // Add dashboard card animation
        document.querySelectorAll('.bg-white.shadow.rounded-lg').forEach(card => {
            card.classList.add('dashboard-card');
        });

        // Add button effects
        document.querySelectorAll('button').forEach(button => {
            if (!button.classList.contains('no-effect')) {
                button.classList.add('btn-effect');
            }
        });
        
        console.log("app.js initialization complete");
    } catch (error) {
        console.error("Critical error in app.js:", error);
        // Show visible error message to help debugging
        document.body.insertAdjacentHTML('afterbegin', 
            '<div style="position:fixed;top:0;left:0;right:0;background:#fee2e2;color:#b91c1c;padding:10px;text-align:center;z-index:9999;">' +
            'Error initializing application. Check console for details.</div>');
    }
});

/**
 * Initialize dropdown menus
 */
function initializeDropdowns() {
    document.querySelectorAll('[data-dropdown-toggle]').forEach(toggleButton => {
        const targetId = toggleButton.getAttribute('data-dropdown-toggle');
        const targetElement = document.getElementById(targetId);
        
        if (targetElement) {
            toggleButton.addEventListener('click', (e) => {
                e.stopPropagation();
                targetElement.classList.toggle('hidden');
            });
            
            // Close when clicking outside
            document.addEventListener('click', (e) => {
                if (!toggleButton.contains(e.target) && !targetElement.contains(e.target)) {
                    targetElement.classList.add('hidden');
                }
            });
        }
    });
}

/**
 * Initialize dark mode toggle
 */
function initializeDarkMode() {
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    if (darkModeToggle) {
        darkModeToggle.addEventListener('click', function() {
            document.documentElement.classList.toggle('dark');
            
            // Update icon
            const icon = darkModeToggle.querySelector('i');
            if (document.documentElement.classList.contains('dark')) {
                icon.classList.remove('fa-moon');
                icon.classList.add('fa-sun');
            } else {
                icon.classList.remove('fa-sun');
                icon.classList.add('fa-moon');
            }
            
            // Store preference
            const darkMode = document.documentElement.classList.contains('dark');
            localStorage.setItem('darkMode', darkMode ? 'enabled' : 'disabled');
        });
        
        // Check for saved preference
        const darkMode = localStorage.getItem('darkMode');
        if (darkMode === 'enabled') {
            document.documentElement.classList.add('dark');
            const icon = darkModeToggle.querySelector('i');
            icon.classList.remove('fa-moon');
            icon.classList.add('fa-sun');
        }
    }
}

/**
 * Initialize table enhancements
 */
function initializeTableEnhancements() {
    const tables = document.querySelectorAll('table');
    tables.forEach(table => {
        table.classList.add('enhanced');
    });
}

/**
 * Initialize chart defaults
 */
function initializeCharts() {
    // Check if Chart.js is available before trying to use it
    if (typeof Chart !== 'undefined' && Chart !== null) {
        try {
            Chart.defaults.font.family = "'Inter', 'Segoe UI', 'Roboto', sans-serif";
            Chart.defaults.color = '#64748b';
            Chart.defaults.backgroundColor = '#e2e8f0';
            console.log('Chart.js initialized successfully');
        } catch (error) {
            console.error('Error initializing Chart.js:', error);
        }
    } else {
        console.warn('Chart.js is not loaded. Charts will not be available.');
    }
}

/**
 * Show a notification toast
 * @param {string} message - The message to display
 * @param {string} type - The type of notification (success, error, warning, info)
 * @param {number} duration - How long to show the notification in milliseconds
 */
function showNotification(message, type = 'info', duration = 3000) {
    const container = document.getElementById('toast-container');
    
    const toast = document.createElement('div');
    toast.className = 'rounded-md p-4 flex items-start shadow-lg transform transition-all duration-300 ease-in-out translate-y-2 opacity-0';
    
    switch (type) {
        case 'success':
            toast.classList.add('bg-green-50', 'border-l-4', 'border-green-500');
            break;
        case 'error':
            toast.classList.add('bg-red-50', 'border-l-4', 'border-red-500');
            break;
        case 'warning':
            toast.classList.add('bg-yellow-50', 'border-l-4', 'border-yellow-500');
            break;
        default:
            toast.classList.add('bg-blue-50', 'border-l-4', 'border-blue-500');
    }
    
    // Icon based on type
    let iconClass;
    switch (type) {
        case 'success':
            iconClass = 'fas fa-check-circle text-green-500';
            break;
        case 'error':
            iconClass = 'fas fa-exclamation-circle text-red-500';
            break;
        case 'warning':
            iconClass = 'fas fa-exclamation-triangle text-yellow-500';
            break;
        default:
            iconClass = 'fas fa-info-circle text-blue-500';
    }
    
    toast.innerHTML = `
        <div class="flex">
            <div class="flex-shrink-0">
                <i class="${iconClass} text-lg"></i>
            </div>
            <div class="ml-3 w-0 flex-1">
                <p class="text-sm font-medium text-gray-800">${message}</p>
            </div>
            <div class="ml-4 flex-shrink-0 flex">
                <button class="inline-flex text-gray-400 hover:text-gray-500 focus:outline-none">
                    <span class="sr-only">Close</span>
                    <i class="fas fa-times"></i>
                </button>
            </div>
        </div>
    `;
    
    container.appendChild(toast);
    
    // Animate in
    setTimeout(() => {
        toast.classList.remove('translate-y-2', 'opacity-0');
        toast.classList.add('translate-y-0', 'opacity-100');
    }, 10);
    
    // Add click handler to close button
    const closeBtn = toast.querySelector('button');
    closeBtn.addEventListener('click', () => {
        removeToast(toast);
    });
    
    // Auto remove after duration
    setTimeout(() => {
        removeToast(toast);
    }, duration);
}

function removeToast(toast) {
    // Animate out
    toast.classList.remove('translate-y-0', 'opacity-100');
    toast.classList.add('translate-y-2', 'opacity-0');
    
    // Remove from DOM after animation completes
    setTimeout(() => {
        toast.remove();
    }, 300);
}

/**
 * Copy text to clipboard
 * @param {string} text - The text to copy
 * @returns {Promise} - Resolves when copying is complete
 */
function copyToClipboard(text) {
    return navigator.clipboard.writeText(text)
        .then(() => {
            showNotification('Copied to clipboard!', 'success');
            return true;
        })
        .catch(() => {
            showNotification('Failed to copy text.', 'error');
            return false;
        });
}

/**
 * Format a number with commas for thousands
 * @param {number} number - The number to format
 * @returns {string} - Formatted number
 */
function formatNumber(number) {
    return numberWithCommas(number);
}

/**
 * Format file size in bytes to human readable format
 * @param {number} bytes - File size in bytes
 * @returns {string} - Formatted file size
 */
function formatFileSize(bytes) {
    return formatBytes(bytes);
}

/**
 * Format a date to a localized string
 * @param {string|Date} date - The date to format
 * @param {boolean} includeTime - Whether to include the time
 * @returns {string} - Formatted date string
 */
function formatDate(date, includeTime = false) {
    const dateObj = new Date(date);
    const options = {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        ...(includeTime && {
            hour: '2-digit',
            minute: '2-digit'
        })
    };
    
    return dateObj.toLocaleDateString(undefined, options);
}

/**
 * Create a downloadable file
 * @param {string} content - The file content
 * @param {string} fileName - The file name
 * @param {string} mimeType - The MIME type
 */
function downloadFile(content, fileName, mimeType = 'text/plain') {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    link.style.display = 'none';
    
    document.body.appendChild(link);
    link.click();
    
    setTimeout(() => {
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }, 100);
}

// Function to format numbers with commas
function numberWithCommas(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Function to format bytes to human-readable size
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
    
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}