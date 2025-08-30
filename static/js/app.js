/**
 * Manufacturing System - Main JavaScript Application
 * Handles common functionality, form validation, and UI interactions
 */

// Global application object
const ManufacturingApp = {
    // Application configuration
    config: {
        animationDuration: 300,
        notificationTimeout: 5000,
        debounceDelay: 300
    },

    // Initialize the application
    init() {
        this.bindGlobalEvents();
        this.initializeComponents();
        this.setupFormValidation();
        this.initializeNotifications();
    },

    // Bind global event handlers
    bindGlobalEvents() {
        // Auto-hide flash messages
        this.autoHideAlerts();
        
        // Handle logout confirmation
        this.setupLogoutConfirmation();
        
        // Initialize tooltips and popovers
        this.initializeBootstrapComponents();
        
        // Handle navigation active states
        this.updateNavigationActiveStates();
    },

    // Initialize various UI components
    initializeComponents() {
        // Initialize date inputs with current date where appropriate
        this.initializeDateInputs();
        
        // Setup search functionality
        this.setupSearchComponents();
        
        // Initialize dynamic form components
        this.setupDynamicForms();
    },

    // Auto-hide alert messages after timeout
    autoHideAlerts() {
        const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(alert => {
            setTimeout(() => {
                if (alert.parentNode) {
                    const bsAlert = new bootstrap.Alert(alert);
                    bsAlert.close();
                }
            }, this.config.notificationTimeout);
        });
    },

    // Setup logout confirmation
    setupLogoutConfirmation() {
        const logoutLinks = document.querySelectorAll('a[href*="logout"]');
        logoutLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                if (!confirm('¿Estás seguro de que deseas cerrar sesión?')) {
                    e.preventDefault();
                }
            });
        });
    },

    // Initialize Bootstrap components
    initializeBootstrapComponents() {
        // Initialize tooltips
        const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => 
            new bootstrap.Tooltip(tooltipTriggerEl)
        );

        // Initialize popovers
        const popoverTriggerList = document.querySelectorAll('[data-bs-toggle="popover"]');
        const popoverList = [...popoverTriggerList].map(popoverTriggerEl => 
            new bootstrap.Popover(popoverTriggerEl)
        );
    },

    // Update navigation active states based on current URL
    updateNavigationActiveStates() {
        const currentPath = window.location.pathname;
        const navLinks = document.querySelectorAll('.navbar-nav .nav-link, .dropdown-item');
        
        navLinks.forEach(link => {
            const href = link.getAttribute('href');
            if (href && currentPath.includes(href) && href !== '/') {
                link.classList.add('active');
                
                // If it's a dropdown item, also mark the parent dropdown as active
                const dropdown = link.closest('.dropdown');
                if (dropdown) {
                    const dropdownToggle = dropdown.querySelector('.dropdown-toggle');
                    if (dropdownToggle) {
                        dropdownToggle.classList.add('active');
                    }
                }
            }
        });
    },

    // Initialize date inputs with sensible defaults
    initializeDateInputs() {
        const dateInputs = document.querySelectorAll('input[type="date"]');
        const today = new Date().toISOString().split('T')[0];
        
        dateInputs.forEach(input => {
            // Set min date for future dates
            if (input.name.includes('fin') || input.name.includes('vencimiento') || 
                input.name.includes('entrega') || input.name.includes('programada')) {
                input.min = today;
            }
        });
    },

    // Setup form validation
    setupFormValidation() {
        const forms = document.querySelectorAll('form[novalidate]');
        
        forms.forEach(form => {
            form.addEventListener('submit', (event) => {
                if (!form.checkValidity()) {
                    event.preventDefault();
                    event.stopPropagation();
                    
                    // Focus on first invalid field
                    const firstInvalid = form.querySelector(':invalid');
                    if (firstInvalid) {
                        firstInvalid.focus();
                    }
                }
                form.classList.add('was-validated');
            });
        });
    },

    // Setup search components with debounced input
    setupSearchComponents() {
        const searchInputs = document.querySelectorAll('input[type="search"], .search-input');
        
        searchInputs.forEach(input => {
            let timeout;
            input.addEventListener('input', (e) => {
                clearTimeout(timeout);
                timeout = setTimeout(() => {
                    this.handleSearch(e.target);
                }, this.config.debounceDelay);
            });
        });
    },

    // Handle search functionality
    handleSearch(input) {
        const searchTerm = input.value.toLowerCase();
        const searchTarget = input.getAttribute('data-search-target');
        
        if (searchTarget) {
            const targetElements = document.querySelectorAll(searchTarget);
            targetElements.forEach(element => {
                const text = element.textContent.toLowerCase();
                const shouldShow = text.includes(searchTerm);
                element.style.display = shouldShow ? '' : 'none';
            });
        }
    },

    // Setup dynamic form components
    setupDynamicForms() {
        // Handle cascade selects (cliente -> proyecto -> contrato/OF)
        this.setupCascadeSelects();
        
        // Handle dynamic item addition/removal
        this.setupDynamicItems();
    },

    // Setup cascade select functionality
    setupCascadeSelects() {
        // This is handled in individual templates, but we can add common functionality here
        console.log('Cascade selects initialized');
    },

    // Setup dynamic item management (for OF items, etc.)
    setupDynamicItems() {
        // Add event listeners for dynamic item addition/removal
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('add-item-btn')) {
                this.addDynamicItem(e.target);
            } else if (e.target.classList.contains('remove-item-btn') || 
                      e.target.closest('.remove-item-btn')) {
                this.removeDynamicItem(e.target);
            }
        });
    },

    // Add dynamic item (generic implementation)
    addDynamicItem(button) {
        const container = button.closest('.dynamic-container');
        if (!container) return;
        
        const template = container.querySelector('.item-template');
        if (!template) return;
        
        const newItem = template.cloneNode(true);
        newItem.classList.remove('item-template');
        newItem.style.display = 'block';
        
        // Update input names with new index
        const items = container.querySelectorAll('.dynamic-item:not(.item-template)');
        const newIndex = items.length;
        
        newItem.querySelectorAll('input, select, textarea').forEach(input => {
            const name = input.name;
            if (name) {
                input.name = name.replace(/\[\d+\]/, `[${newIndex}]`);
            }
        });
        
        container.appendChild(newItem);
        
        // Re-initialize Feather icons
        if (typeof feather !== 'undefined') {
            feather.replace();
        }
    },

    // Remove dynamic item
    removeDynamicItem(button) {
        const item = button.closest('.dynamic-item');
        if (item && confirm('¿Estás seguro de que deseas eliminar este elemento?')) {
            item.remove();
        }
    },

    // Initialize notifications system
    initializeNotifications() {
        // Setup notification container if it doesn't exist
        if (!document.getElementById('notification-container')) {
            const container = document.createElement('div');
            container.id = 'notification-container';
            container.className = 'position-fixed top-0 end-0 p-3';
            container.style.zIndex = '1070';
            document.body.appendChild(container);
        }
    },

    // Show notification
    showNotification(message, type = 'info', timeout = null) {
        const container = document.getElementById('notification-container');
        if (!container) return;
        
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} alert-dismissible fade show`;
        notification.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        container.appendChild(notification);
        
        // Auto-hide after timeout
        const hideTimeout = timeout || this.config.notificationTimeout;
        setTimeout(() => {
            if (notification.parentNode) {
                const bsAlert = new bootstrap.Alert(notification);
                bsAlert.close();
            }
        }, hideTimeout);
    },

    // Utility functions
    utils: {
        // Format currency
        formatCurrency(amount, currency = 'CLP') {
            return new Intl.NumberFormat('es-CL', {
                style: 'currency',
                currency: currency,
                minimumFractionDigits: 0
            }).format(amount);
        },

        // Format date
        formatDate(date, format = 'short') {
            const options = format === 'short' 
                ? { year: 'numeric', month: '2-digit', day: '2-digit' }
                : { year: 'numeric', month: 'long', day: 'numeric' };
            
            return new Intl.DateTimeFormat('es-CL', options).format(new Date(date));
        },

        // Validate RUT
        validateRUT(rut) {
            const cleanRUT = rut.replace(/\D/g, '');
            if (cleanRUT.length < 8) return false;
            
            const rutDigits = cleanRUT.slice(0, -1);
            const verifierDigit = cleanRUT.slice(-1);
            
            let sum = 0;
            let multiplier = 2;
            
            for (let i = rutDigits.length - 1; i >= 0; i--) {
                sum += parseInt(rutDigits[i]) * multiplier;
                multiplier = multiplier === 7 ? 2 : multiplier + 1;
            }
            
            const remainder = sum % 11;
            const calculatedVerifier = remainder === 0 ? '0' : 
                                     remainder === 1 ? 'K' : 
                                     (11 - remainder).toString();
            
            return verifierDigit.toUpperCase() === calculatedVerifier;
        },

        // Format RUT
        formatRUT(rut) {
            const cleanRUT = rut.replace(/\D/g, '');
            if (cleanRUT.length < 2) return cleanRUT;
            
            const body = cleanRUT.slice(0, -1);
            const verifier = cleanRUT.slice(-1);
            
            return body.replace(/(\d)(?=(\d{3})+(?!\d))/g, '$1.') + '-' + verifier;
        },

        // Debounce function
        debounce(func, delay) {
            let timeoutId;
            return function (...args) {
                clearTimeout(timeoutId);
                timeoutId = setTimeout(() => func.apply(this, args), delay);
            };
        },

        // Show loading state
        showLoading(element, text = 'Cargando...') {
            const originalContent = element.innerHTML;
            element.innerHTML = `
                <span class="spinner-border spinner-border-sm me-2"></span>
                ${text}
            `;
            element.disabled = true;
            
            return () => {
                element.innerHTML = originalContent;
                element.disabled = false;
            };
        }
    }
};

// API helper functions
const API = {
    // Generic API request helper
    async request(url, options = {}) {
        const defaultOptions = {
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            }
        };
        
        const mergedOptions = { ...defaultOptions, ...options };
        
        try {
            const response = await fetch(url, mergedOptions);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            return data;
        } catch (error) {
            console.error('API request failed:', error);
            ManufacturingApp.showNotification(
                'Error en la comunicación con el servidor', 
                'danger'
            );
            throw error;
        }
    },

    // Get projects by client
    async getProjectsByClient(clientId) {
        return this.request(`/proyectos/api/by-cliente/${clientId}`);
    },

    // Get manufacturing orders by project
    async getOrdersByProject(projectId) {
        return this.request(`/fabricacion/api/by-proyecto/${projectId}`);
    }
};

// Initialize application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    ManufacturingApp.init();
});

// Global error handler
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
    ManufacturingApp.showNotification(
        'Ha ocurrido un error inesperado. Por favor, recarga la página.', 
        'danger'
    );
});

// Export for use in other scripts
window.ManufacturingApp = ManufacturingApp;
window.API = API;
