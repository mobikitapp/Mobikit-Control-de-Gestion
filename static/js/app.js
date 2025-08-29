// Funcionalidades JavaScript para Mobikit

document.addEventListener('DOMContentLoaded', function() {
    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s';
            alert.style.opacity = '0';
            setTimeout(() => {
                if (alert.parentNode) {
                    alert.parentNode.removeChild(alert);
                }
            }, 500);
        }, 5000);
    });

    // Intercept form submissions to show loading
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.disabled) {
                submitBtn.disabled = true;
                const originalText = submitBtn.textContent;
                submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Procesando...';

                // Re-enable after 5 seconds as fallback
                setTimeout(() => {
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                }, 5000);
            }
        });
    });

    // Intercept navigation links
    const navLinks = document.querySelectorAll('.nav-link, .btn[href], a[href]:not([target="_blank"])');
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            if (href && href !== '#' && !href.startsWith('javascript:') && !href.startsWith('mailto:')) {
                e.preventDefault();
                navigateWithLoader(href);
            }
        });
    });

    // Confirm dialogs for dangerous actions
    const dangerousButtons = document.querySelectorAll('[data-confirm]');
    dangerousButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm');
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });

    // Form validation
    const forms = document.querySelectorAll('form[data-validate]');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            const requiredFields = form.querySelectorAll('[required]');
            let valid = true;

            requiredFields.forEach(field => {
                if (!field.value.trim()) {
                    field.classList.add('is-invalid');
                    valid = false;
                } else {
                    field.classList.remove('is-invalid');
                }
            });

            if (!valid) {
                e.preventDefault();
                alert('Por favor completa todos los campos requeridos');
            }
        });
    });

    // Auto-update timestamps
    const timestamps = document.querySelectorAll('[data-timestamp]');
    timestamps.forEach(element => {
        const timestamp = element.getAttribute('data-timestamp');
        const date = new Date(timestamp);
        element.textContent = formatDate(date);
    });

    // Search functionality for tables
    const searchInputs = document.querySelectorAll('[data-search]');
    searchInputs.forEach(input => {
        const targetTable = document.querySelector(input.getAttribute('data-search'));
        if (targetTable) {
            input.addEventListener('input', function() {
                const searchTerm = this.value.toLowerCase();
                const rows = targetTable.querySelectorAll('tbody tr');

                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    row.style.display = text.includes(searchTerm) ? '' : 'none';
                });
            });
        }
    });

    // Progress bar animations
    const progressBars = document.querySelectorAll('.progress-bar');
    progressBars.forEach(bar => {
        const width = bar.style.width;
        bar.style.width = '0%';
        setTimeout(() => {
            bar.style.transition = 'width 1s ease-in-out';
            bar.style.width = width;
        }, 100);
    });

    // Tooltip initialization for Bootstrap
    if (typeof bootstrap !== 'undefined') {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
});

// Utility functions
function formatDate(date) {
    const options = { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    return date.toLocaleDateString('es-ES', options);
}

// Loading and UX improvements
function showPageLoader(message = 'Cargando...') {
    const loader = document.createElement('div');
    loader.id = 'page-loader';
    loader.innerHTML = `
        <div class="loading-overlay">
            <div class="loading-message">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <div>${message}</div>
            </div>
        </div>
    `;
    document.body.appendChild(loader);
}

function hidePageLoader() {
    const loader = document.getElementById('page-loader');
    if (loader) {
        loader.remove();
    }
}

// Optimized navigation with loading
function navigateWithLoader(url, message = 'Cargando página...') {
    showPageLoader(message);
    setTimeout(() => {
        window.location.href = url;
    }, 100);
}

function showLoading(element) {
    element.classList.add('loading');
    const originalText = element.textContent;
    element.textContent = 'Cargando...';
    return originalText;
}

function hideLoading(element, originalText) {
    element.classList.remove('loading');
    element.textContent = originalText;
}

// AJAX helper function
function makeRequest(url, method = 'GET', data = null) {
    return fetch(url, {
        method: method,
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
        },
        body: data ? JSON.stringify(data) : null
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    });
}

// Export functions for global use
window.MobikitApp = {
    formatDate: formatDate,
    showLoading: showLoading,
    hideLoading: hideLoading,
    makeRequest: makeRequest
};

// Dashboard Auto-refresh and Real-time Updates
let dashboardRefreshInterval;
const DASHBOARD_REFRESH_RATE = 30000; // 30 segundos

function startDashboardAutoRefresh() {
    if (window.location.pathname === '/dashboard') {
        dashboardRefreshInterval = setInterval(refreshDashboardData, DASHBOARD_REFRESH_RATE);
    }
}

function stopDashboardAutoRefresh() {
    if (dashboardRefreshInterval) {
        clearInterval(dashboardRefreshInterval);
        dashboardRefreshInterval = null;
    }
}

function refreshDashboardData() {
    // Actualizar conteos de órdenes
    fetch('/api/ordenes_compra_estado')
        .then(response => response.json())
        .then(data => {
            updateDashboardCounts(data);
        })
        .catch(error => {
            console.error('Error refreshing dashboard:', error);
        });
}

function updateDashboardCounts(ordenes) {
    const pendientesCount = ordenes.filter(o => o.estado === 'activo').length;
    const procesoCount = ordenes.filter(o => o.estado === 'aprobado_produccion').length;
    const terminadasCount = ordenes.filter(o => o.estado === 'entregado').length;

    // Actualizar badges en el dashboard si existen
    const badges = {
        'pendientes-count': pendientesCount,
        'proceso-count': procesoCount,
        'terminadas-count': terminadasCount
    };

    Object.entries(badges).forEach(([id, count]) => {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = count;
        }
    });
}

// Gestión de formularios mejorada
document.addEventListener('DOMContentLoaded', function() {
    const allForms = document.querySelectorAll('form');

    allForms.forEach(form => {
        form.addEventListener('submit', function(e) {
            // Prevenir doble envío
            const submitBtn = form.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.disabled) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Procesando...';

                setTimeout(() => {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = submitBtn.getAttribute('data-original-text') || 'Enviar';
                }, 3000);
            }
        });
    });

    // Configurar tooltips
    const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltips.forEach(tooltip => {
        new bootstrap.Tooltip(tooltip);
    });

    // Auto-refresh para dashboard
    startDashboardAutoRefresh();

    // Detener refresh al cambiar de página
    window.addEventListener('beforeunload', stopDashboardAutoRefresh);
});

// Validación de formularios en tiempo real
function setupFormValidation() {
    const validationForms = document.querySelectorAll('.needs-validation');

    validationForms.forEach(form => {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });
}

// Utilidades de UI
function showToast(message, type = 'info') {
    // Crear toast dinámico si no existe contenedor
    let toastContainer = document.querySelector('.toast-container');
    if (!toastContainer) {
        toastContainer = document.createElement('div');
        toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
        document.body.appendChild(toastContainer);
    }

    const toastHtml = `
        <div class="toast" role="alert">
            <div class="toast-header">
                <strong class="me-auto">Sistema Mobikit</strong>
                <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body bg-${type} text-white">
                ${message}
            </div>
        </div>
    `;

    toastContainer.insertAdjacentHTML('beforeend', toastHtml);

    const newToast = toastContainer.lastElementChild;
    const bsToast = new bootstrap.Toast(newToast);
    bsToast.show();

    // Auto-remove after hiding
    newToast.addEventListener('hidden.bs.toast', () => {
        newToast.remove();
    });
}

// Gestión de estados de carga
function showLoadingState(element, text = 'Cargando...') {
    element.innerHTML = `<i class="fas fa-spinner fa-spin"></i> ${text}`;
    element.disabled = true;
}

function hideLoadingState(element, originalText = 'Procesar') {
    element.innerHTML = originalText;
    element.disabled = false;
}

// Validaciones específicas
function validateEmail(email) {
    const re = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return re.test(email);
}

function validateRUT(rut) {
    // Validación básica de RUT chileno (formato XX.XXX.XXX-X)
    const re = /^\d{1,2}\.\d{3}\.\d{3}-[\dkK]$/;
    return re.test(rut) || rut === '';
}

function formatCurrency(amount) {
    return new Intl.NumberFormat('es-CL', {
        style: 'currency',
        currency: 'CLP',
        minimumFractionDigits: 0
    }).format(amount);
}

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString('es-CL');
}

// Configurar eventos al cargar la página
document.addEventListener('DOMContentLoaded', function() {
    setupFormValidation();

    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert-dismissible');
    alerts.forEach(alert => {
        setTimeout(() => {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // Setup date inputs with minimum date as today
    const dateInputs = document.querySelectorAll('input[type="date"]');
    const today = new Date().toISOString().split('T')[0];
    dateInputs.forEach(input => {
        if (!input.hasAttribute('data-allow-past')) {
            input.min = today;
        }
    });
});

// Función global para manejar errores de fetch
function handleFetchError(error, userMessage = 'Ha ocurrido un error') {
    console.error('Fetch Error:', error);
    showToast(userMessage, 'danger');
}

// Función global para manejar respuestas exitosas
function handleFetchSuccess(data, successMessage = 'Operación exitosa') {
    if (data.success) {
        showToast(data.message || successMessage, 'success');
        if (data.redirect) {
            window.location.href = data.redirect;
        } else {
            location.reload();
        }
    } else {
        showToast(data.message || 'Error en la operación', 'danger');
    }
}