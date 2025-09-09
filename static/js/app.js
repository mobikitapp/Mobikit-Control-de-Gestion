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
        debounceDelay: 300,
        isMobile: window.innerWidth <= 768,
        isTouch: 'ontouchstart' in window
    },

    // Initialize the application
    init() {
        this.bindGlobalEvents();
        this.initializeComponents();
        this.setupFormValidation();
        this.initializeNotifications();
        this.optimizeForMobile();
    },

    // Mobile-specific optimizations
    optimizeForMobile() {
        if (this.config.isMobile) {
            // Reduce debounce delay for mobile for better responsiveness
            this.config.debounceDelay = 150;

            // Add mobile-specific CSS class
            document.body.classList.add('mobile-device');

            // Optimize scroll performance
            document.addEventListener('touchstart', function() {}, {passive: true});
            document.addEventListener('touchmove', function() {}, {passive: true});

            // Handle orientation changes
            window.addEventListener('orientationchange', () => {
                setTimeout(() => {
                    this.handleOrientationChange();
                }, 100);
            });
        }

        if (this.config.isTouch) {
            document.body.classList.add('touch-device');
        }
    },

    // Handle orientation changes
    handleOrientationChange() {
        // Trigger window resize event to update components
        window.dispatchEvent(new Event('resize'));

        // Re-initialize tooltips and popovers after orientation change
        this.initializeBootstrapComponents();
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

        // Initialize collapsible filters
        this.initializeCollapsibleFilters();
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

    // Initialize collapsible filters
    initializeCollapsibleFilters() {
        const filterToggles = document.querySelectorAll('[data-bs-toggle="collapse"]');

        filterToggles.forEach(toggle => {
            toggle.addEventListener('click', () => {
                const target = document.querySelector(toggle.getAttribute('data-bs-target'));
                const chevron = toggle.querySelector('[data-feather="chevron-down"]');

                if (target && chevron) {
                    toggle.addEventListener('shown.bs.collapse', () => {
                        chevron.style.transform = 'rotate(180deg)';
                    });

                    toggle.addEventListener('hidden.bs.collapse', () => {
                        chevron.style.transform = 'rotate(0deg)';
                    });
                }
            });
        });
    },

    // Setup cascade select functionality
    setupCascadeSelects() {
        // This is handled in individual templates, but we can add common functionality here
        console.log('Cascade selects initialized');
    },

    // Setup dynamic item management (for OF items, etc.)
    setupDynamicItems() {
        // Handle dynamic item addition/removal
        document.addEventListener('click', (e) => {
            try {
                if (!e.target) return;

                if (e.target.classList && e.target.classList.contains('add-item-btn')) {
                    this.addDynamicItem(e.target);
                } else if (e.target.classList && e.target.classList.contains('remove-item-btn')) {
                    this.removeDynamicItem(e.target);
                } else if (e.target.closest) {
                    const removeBtn = e.target.closest('.remove-item-btn');
                    if (removeBtn) {
                        this.removeDynamicItem(removeBtn);
                    }

                    // Handle estado change buttons
                    const estadoBtn = e.target.closest('.change-estado-btn');
                    if (estadoBtn) {
                        this.handleEstadoChange(estadoBtn);
                    }
                }
            } catch (error) {
                console.error('Error handling dynamic item click:', error);
            }
        });
    },

    // Handle estado change from project list
    handleEstadoChange(button) {
        if (!button || !button.dataset) return;

        const proyectoId = button.dataset.proyectoId;
        const estadoActual = button.dataset.estadoActual;

        if (!proyectoId) return;

        this.showEstadoChangeModal(proyectoId, estadoActual);
    },

    // Show modal to change project estado
    showEstadoChangeModal(proyectoId, estadoActual) {
        const modalHtml = `
            <div class="modal fade" id="cambiarEstadoModal" tabindex="-1">
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title">Cambiar Estado del Proyecto</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                        </div>
                        <div class="modal-body">
                            <form id="cambiarEstadoForm">
                                <input type="hidden" id="proyectoId" value="${proyectoId}">
                                <div class="mb-3">
                                    <label for="nuevoEstado" class="form-label">Nuevo Estado</label>
                                    <select class="form-select" id="nuevoEstado" required>
                                        <option value="">Seleccione estado...</option>
                                        <option value="PENDIENTE_PRESUPUESTO" ${estadoActual === 'PENDIENTE_PRESUPUESTO' ? 'selected' : ''}>Pendiente Presupuesto</option>
                                        <option value="PRESUPUESTADO" ${estadoActual === 'PRESUPUESTADO' ? 'selected' : ''}>Presupuestado</option>
                                        <option value="ADJUDICADO" ${estadoActual === 'ADJUDICADO' ? 'selected' : ''}>Adjudicado</option>
                                        <option value="EN_DESARROLLO" ${estadoActual === 'EN_DESARROLLO' ? 'selected' : ''}>En Desarrollo</option>
                                        <option value="TERMINADO" ${estadoActual === 'TERMINADO' ? 'selected' : ''}>Terminado</option>
                                        <option value="EN_DESARROLLO" ${estadoActual === 'EN_DESARROLLO' ? 'selected' : ''}>En Desarrollo</option>
                                        <option value="TERMINADO" ${estadoActual === 'TERMINADO' ? 'selected' : ''}>Terminado</option>
                                    </select>
                                </div>
                                <div class="mb-3">
                                    <label for="observacion" class="form-label">Observación (opcional)</label>
                                    <textarea class="form-control" id="observacion" rows="3" placeholder="Motivo del cambio de estado..."></textarea>
                                </div>
                            </form>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancelar</button>
                            <button type="button" class="btn btn-primary" onclick="ManufacturingApp.confirmarCambioEstado()">Cambiar Estado</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        // Remove existing modal if any
        const existingModal = document.getElementById('cambiarEstadoModal');
        if (existingModal) {
            existingModal.remove();
        }

        // Add modal to DOM
        document.body.insertAdjacentHTML('beforeend', modalHtml);

        // Show modal
        const modal = new bootstrap.Modal(document.getElementById('cambiarEstadoModal'));
        modal.show();
    },

    // Confirm estado change
    async confirmarCambioEstado() {
        const proyectoId = document.getElementById('proyectoId').value;
        const nuevoEstado = document.getElementById('nuevoEstado').value;
        const observacion = document.getElementById('observacion').value;

        if (!nuevoEstado) {
            this.showNotification('Debe seleccionar un estado', 'danger');
            return;
        }

        try {
            const response = await fetch(`/proyectos/${proyectoId}/cambiar-estado`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    estado: nuevoEstado,
                    observacion: observacion
                })
            });

            const data = await response.json();

            if (data.success) {
                this.showNotification('Estado actualizado correctamente', 'success');
                // Close modal
                bootstrap.Modal.getInstance(document.getElementById('cambiarEstadoModal')).hide();
                // Reload page to show changes
                setTimeout(() => location.reload(), 1000);
            } else {
                this.showNotification(data.message || 'Error al cambiar estado', 'danger');
            }
        } catch (error) {
            console.error('Error changing estado:', error);
            this.showNotification('Error en la comunicación con el servidor', 'danger');
        }
    },

    // Add dynamic item (generic implementation)
    addDynamicItem(button) {
        try {
            if (!button || typeof button.closest !== 'function') return;

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
        } catch (error) {
            console.error('Error adding dynamic item:', error);
        }
    },

    // Remove dynamic item
    removeDynamicItem(button) {
        try {
            if (!button || typeof button.closest !== 'function') return;

            const item = button.closest('.dynamic-item');
            if (item && confirm('¿Estás seguro de que deseas eliminar este elemento?')) {
                item.remove();
            }
        } catch (error) {
            console.error('Error removing dynamic item:', error);
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

    // Initialize cascade selects on page load
    document.addEventListener('DOMContentLoaded', function() {
        initializeCascadeSelects();
        console.log('Cascade selects initialized');
    });

    // Selector de cliente -> proyecto en despachos
    const clienteSelect = document.getElementById('cliente_id');
    const proyectoSelect = document.getElementById('proyecto_id');

    if (clienteSelect && proyectoSelect) {
        clienteSelect.addEventListener('change', function() {
            const clienteId = this.value;
            proyectoSelect.innerHTML = '<option value="">Cargando...</option>';

            if (clienteId) {
                fetch(`/proyectos/api/by-cliente/${clienteId}`)
                    .then(response => response.json())
                    .then(data => {
                        proyectoSelect.innerHTML = '<option value="">Seleccione un proyecto...</option>';
                        data.forEach(proyecto => {
                            proyectoSelect.innerHTML += `<option value="${proyecto.id}">${proyecto.nombre}</option>`;
                        });
                    })
                    .catch(error => {
                        console.error('Error cargando proyectos:', error);
                        proyectoSelect.innerHTML = '<option value="">Error cargando proyectos</option>';
                    });
            } else {
                proyectoSelect.innerHTML = '<option value="">Seleccione un proyecto...</option>';
            }
        });
    }

    // Manejar cambios en selectores de categoría
    const categoriaSelect = document.getElementById('categoria');
    const subcategoriaSelect = document.getElementById('subcategoria');

    if (categoriaSelect && subcategoriaSelect) {
        categoriaSelect.addEventListener('change', function() {
            const categoriaId = this.value;
            subcategoriaSelect.innerHTML = '<option value="">Cargando...</option>';

            if (categoriaId) {
                fetch(`/api/subcategorias/${categoriaId}`)
                    .then(response => response.json())
                    .then(data => {
                        subcategoriaSelect.innerHTML = '<option value="">Seleccione subcategoría...</option>';
                        data.forEach(sub => {
                            subcategoriaSelect.innerHTML += `<option value="${sub.id}">${sub.nombre}</option>`;
                        });
                    })
                    .catch(error => {
                        console.error('Error cargando subcategorías:', error);
                        subcategoriaSelect.innerHTML = '<option value="">Error cargando datos</option>';
                    });
            } else {
                subcategoriaSelect.innerHTML = '<option value="">Seleccione subcategoría...</option>';
            }
        });
    }

    // Validación de formularios con mejor manejo de errores
    const forms = document.querySelectorAll('form[data-validate]');
    forms.forEach(form => {
        if (form) {
            form.addEventListener('submit', function(e) {
                const requiredFields = form.querySelectorAll('[required]');
                let hasErrors = false;

                requiredFields.forEach(field => {
                    if (!field.value.trim()) {
                        field.classList.add('is-invalid');
                        hasErrors = true;
                    } else {
                        field.classList.remove('is-invalid');
                    }
                });

                if (hasErrors) {
                    e.preventDefault();
                    showAlert('Por favor complete todos los campos obligatorios', 'error');
                }
            });
        }
    });
});

// Función para mostrar/ocultar secciones del formulario
function toggleSection(sectionId, show) {
    const section = document.getElementById(sectionId);
    if (section) {
        section.style.display = show ? 'block' : 'none';
    }
}

// Función para mostrar alertas
function showAlert(message, type = 'info') {
    // Crear elemento de alerta si no existe
    let alertContainer = document.getElementById('alert-container');
    if (!alertContainer) {
        alertContainer = document.createElement('div');
        alertContainer.id = 'alert-container';
        alertContainer.style.position = 'fixed';
        alertContainer.style.top = '20px';
        alertContainer.style.right = '20px';
        alertContainer.style.zIndex = '9999';
        document.body.appendChild(alertContainer);
    }

    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type === 'error' ? 'danger' : type} alert-dismissible fade show`;
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    alertContainer.appendChild(alertDiv);

    // Auto-remove after 5 seconds
    setTimeout(() => {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

// Manejar errores globales de JavaScript con mejor logging
    window.addEventListener('error', function(e) {
        console.log('Global error:', {
            message: e.message,
            filename: e.filename,
            lineno: e.lineno,
            colno: e.colno
        });
    });

    // Toggle collapse containers (fix for null element access)
    function setupCollapseToggles() {
        document.querySelectorAll('[data-bs-toggle="collapse"]').forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();

                const targetSelector = this.getAttribute('data-bs-target') || this.getAttribute('href');
                if (!targetSelector) return;

                const targetElement = document.querySelector(targetSelector);

                if (targetElement) {
                    const isVisible = targetElement.style.display !== 'none';
                    targetElement.style.display = isVisible ? 'none' : 'block';

                    // Update button text/icon if needed
                    const icon = this.querySelector('i');
                    if (icon) {
                        icon.classList.toggle('fa-chevron-down');
                        icon.classList.toggle('fa-chevron-up');
                    }
                }
            });
        });
    }

// Handle contracts collapse toggle
    document.addEventListener('click', function(e) {
        if (e.target.closest('.contratos-toggle-btn')) {
            const button = e.target.closest('.contratos-toggle-btn');
            const icon = button.querySelector('[data-feather]');
            const targetSelector = button.getAttribute('data-bs-target');

            if (targetSelector) {
                const target = document.querySelector(targetSelector);

                if (target && icon) {
                    const isCollapsed = !target.classList.contains('show');

                    if (isCollapsed) {
                        target.classList.add('show');
                        icon.setAttribute('data-feather', 'chevron-down');
                    } else {
                        target.classList.remove('show');
                        icon.setAttribute('data-feather', 'chevron-right');
                    }

                    // Re-render feather icons
                    if (typeof feather !== 'undefined') {
                        feather.replace();
                    }
                }
            }
        }
    });

// Función para confirmar eliminación
function confirmarEliminacion(mensaje) {
    return confirm(mensaje || '¿Está seguro de que desea eliminar este elemento?');
}

// Función para formatear números como moneda
function formatearMoneda(numero) {
    return new Intl.NumberFormat('es-CL', {
        style: 'currency',
        currency: 'CLP'
    }).format(numero);
}

// Función para validar RUT chileno
function validarRUT(rut) {
    if (!/^[0-9]+[-|‐]{1}[0-9kK]{1}$/.test(rut)) {
        return false;
    }

    const tmp = rut.split('-');
    const digv = tmp[1];
    const rut_num = tmp[0];

    if (digv == 'K') digv = 'k';

    return (dv(rut_num) == digv);
}

function dv(T) {
    let M = 0, S = 1;
    for (; T; T = Math.floor(T / 10)) {
        S = (S + T % 10 * (9 - M++ % 6)) % 11;
    }
    return S ? S - 1 : 'k';
}

// Enhanced row details functionality
        document.querySelectorAll('.toggle-details').forEach(button => {
            button.addEventListener('click', function() {
                const row = this.closest('tr');
                if (!row) return;

                const detailsRow = row.nextElementSibling;

                if (detailsRow && detailsRow.classList.contains('details-row')) {
                    detailsRow.style.display = detailsRow.style.display === 'none' ? '' : 'none';

                    // Update icon
                    const icon = this.querySelector('i');
                    if (icon) {
                        icon.classList.toggle('fa-chevron-down');
                        icon.classList.toggle('fa-chevron-up');
                    }
                }
            });
        });

// Export for use in other scripts
window.ManufacturingApp = ManufacturingApp;
window.API = API;