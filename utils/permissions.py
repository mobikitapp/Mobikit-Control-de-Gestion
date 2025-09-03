
"""
Sistema de permisos granular para Mobikit
"""

# Definición de permisos específicos
PERMISSIONS = {
    # Gestión de usuarios
    'users.view': ['ADMIN'],
    'users.create': ['ADMIN'],
    'users.edit': ['ADMIN'],
    'users.delete': ['ADMIN'],
    
    # Clientes
    'clients.view': ['ADMIN', 'GENERAL', 'VENTAS'],
    'clients.create': ['ADMIN', 'GENERAL'],
    'clients.edit': ['ADMIN', 'GENERAL'],
    'clients.delete': ['ADMIN'],
    
    # Proyectos
    'projects.view': ['ADMIN', 'GENERAL', 'VENTAS'],
    'projects.create': ['ADMIN', 'GENERAL', 'VENTAS'],
    'projects.edit': ['ADMIN', 'GENERAL', 'VENTAS'],
    'projects.delete': ['ADMIN'],
    'projects.archive': ['ADMIN', 'GENERAL'],
    
    # Órdenes de compra
    'orders.view': ['ADMIN', 'GENERAL', 'VENTAS', 'OPERACIONES'],
    'orders.create': ['ADMIN', 'GENERAL', 'VENTAS'],
    'orders.edit': ['ADMIN', 'GENERAL'],
    'orders.delete': ['ADMIN'],
    'orders.approve': ['ADMIN', 'GENERAL'],
    
    # Fabricación
    'manufacturing.view': ['ADMIN', 'GENERAL', 'OPERACIONES'],
    'manufacturing.create': ['ADMIN', 'GENERAL', 'OPERACIONES'],
    'manufacturing.edit': ['ADMIN', 'GENERAL', 'OPERACIONES'],
    'manufacturing.process': ['ADMIN', 'GENERAL', 'OPERACIONES'],
    
    # Despachos
    'dispatch.view': ['ADMIN', 'GENERAL', 'LOGISTICA'],
    'dispatch.create': ['ADMIN', 'GENERAL', 'LOGISTICA'],
    'dispatch.edit': ['ADMIN', 'GENERAL', 'LOGISTICA'],
    'dispatch.process': ['ADMIN', 'GENERAL', 'LOGISTICA'],
    
    # Reportes y configuraciones
    'reports.view': ['ADMIN', 'GENERAL'],
    'config.view': ['ADMIN'],
    'config.edit': ['ADMIN'],
    
    # Planificación
    'planning.view': ['ADMIN', 'GENERAL', 'VENTAS'],
    'planning.edit': ['ADMIN', 'GENERAL'],
}

# Permisos por rol (resumen)
ROLE_PERMISSIONS = {
    'ADMIN': 'all',  # Acceso completo
    'GENERAL': [
        'clients.view', 'clients.create', 'clients.edit',
        'projects.view', 'projects.create', 'projects.edit', 'projects.archive',
        'orders.view', 'orders.create', 'orders.edit', 'orders.approve',
        'manufacturing.view', 'manufacturing.create', 'manufacturing.edit', 'manufacturing.process',
        'dispatch.view', 'dispatch.create', 'dispatch.edit', 'dispatch.process',
        'reports.view', 'planning.view', 'planning.edit'
    ],
    'VENTAS': [
        'clients.view', 'projects.view', 'projects.create', 'projects.edit',
        'orders.view', 'orders.create', 'planning.view'
    ],
    'OPERACIONES': [
        'orders.view', 'manufacturing.view', 'manufacturing.create', 
        'manufacturing.edit', 'manufacturing.process'
    ],
    'PRODUCCION': [
        'orders.view', 'manufacturing.view', 'dispatch.view'
    ],
    'LOGISTICA': [
        'orders.view', 'dispatch.view', 'dispatch.create', 
        'dispatch.edit', 'dispatch.process'
    ]
}

def has_permission(user_role, permission):
    """
    Verifica si un rol tiene un permiso específico
    """
    if user_role == 'ADMIN':
        return True
    
    if permission in PERMISSIONS:
        return user_role in PERMISSIONS[permission]
    
    return False

def get_user_permissions(user_role):
    """
    Obtiene todos los permisos de un rol
    """
    if user_role == 'ADMIN':
        return list(PERMISSIONS.keys())
    
    return ROLE_PERMISSIONS.get(user_role, [])

def permission_required(permission):
    """
    Decorador para verificar permisos específicos
    """
    def decorator(f):
        from functools import wraps
        from flask import session, flash, redirect, url_for
        
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_role' not in session:
                flash('Debes iniciar sesión', 'error')
                return redirect(url_for('login'))
            
            if not has_permission(session['user_role'], permission):
                flash('No tienes permisos para realizar esta acción', 'error')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
