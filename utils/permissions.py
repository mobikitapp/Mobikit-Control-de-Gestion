
"""
Sistema de permisos granular para Mobikit
"""

# Definición de permisos específicos
PERMISSIONS = {
    # Gestión de usuarios
    'users.view': ['admin'],
    'users.create': ['admin'],
    'users.edit': ['admin'],
    'users.delete': ['admin'],
    
    # Clientes
    'clients.view': ['admin', 'general', 'vendedor'],
    'clients.create': ['admin', 'general'],
    'clients.edit': ['admin', 'general'],
    'clients.delete': ['admin'],
    
    # Proyectos
    'projects.view': ['admin', 'general', 'vendedor'],
    'projects.create': ['admin', 'general', 'vendedor'],
    'projects.edit': ['admin', 'general', 'vendedor'],
    'projects.delete': ['admin'],
    'projects.archive': ['admin', 'general'],
    
    # Órdenes de compra
    'orders.view': ['admin', 'general', 'vendedor', 'operación'],
    'orders.create': ['admin', 'general', 'vendedor'],
    'orders.edit': ['admin', 'general'],
    'orders.delete': ['admin'],
    'orders.approve': ['admin', 'general'],
    
    # Fabricación
    'manufacturing.view': ['admin', 'general', 'operación'],
    'manufacturing.create': ['admin', 'general', 'operación'],
    'manufacturing.edit': ['admin', 'general', 'operación'],
    'manufacturing.process': ['admin', 'general', 'operación'],
    
    # Despachos
    'dispatch.view': ['admin', 'general', 'despacho'],
    'dispatch.create': ['admin', 'general', 'despacho'],
    'dispatch.edit': ['admin', 'general', 'despacho'],
    'dispatch.process': ['admin', 'general', 'despacho'],
    
    # Reportes y configuraciones
    'reports.view': ['admin', 'general'],
    'config.view': ['admin'],
    'config.edit': ['admin'],
    
    # Planificación
    'planning.view': ['admin', 'general', 'vendedor'],
    'planning.edit': ['admin', 'general'],
    
    # Dashboard Personal del Vendedor
    'mi_dashboard.view': ['vendedor'],
    'mi_dashboard.mis_clientes': ['vendedor'],
    'mi_dashboard.mis_proyectos': ['vendedor'],
    'mi_dashboard.estadisticas': ['vendedor'],
}

# Permisos por rol (resumen)
ROLE_PERMISSIONS = {
    'admin': 'all',  # Acceso completo
    'general': [
        'clients.view', 'clients.create', 'clients.edit', 'clients.delete',
        'projects.view', 'projects.create', 'projects.edit', 'projects.delete', 'projects.archive',
        'orders.view', 'orders.create', 'orders.edit', 'orders.delete', 'orders.approve',
        'manufacturing.view', 'manufacturing.create', 'manufacturing.edit', 'manufacturing.process',
        'dispatch.view', 'dispatch.create', 'dispatch.edit', 'dispatch.process',
        'reports.view', 'planning.view', 'planning.edit',
        'config.view'  # Solo ver configuraciones, no editar
    ],
    'vendedor': [
        'clients.view', 'projects.view', 'projects.create', 'projects.edit',
        'orders.view', 'orders.create', 'planning.view',
        'mi_dashboard.view', 'mi_dashboard.mis_clientes', 'mi_dashboard.mis_proyectos', 'mi_dashboard.estadisticas'
    ],
    'operación': [
        'orders.view', 'manufacturing.view', 'manufacturing.create', 
        'manufacturing.edit', 'manufacturing.process'
    ],
    'embalaje': [
        'orders.view', 'manufacturing.view', 'dispatch.view'
    ],
    'despacho': [
        'orders.view', 'dispatch.view', 'dispatch.create', 
        'dispatch.edit', 'dispatch.process'
    ]
}

def has_permission(user_role, permission):
    """
    Verifica si un rol tiene un permiso específico
    Intenta usar el sistema dinámico primero, luego fallback al sistema estático
    """
    if user_role == 'admin':
        return True
    
    # Intentar usar el sistema dinámico de permisos
    try:
        from services.permisos_service import PermisosService
        service = PermisosService()
        
        # Parsear el permiso (formato: modulo.tipo_permiso)
        if '.' in permission:
            modulo_codigo, tipo_permiso_codigo = permission.split('.', 1)
            return service.verificar_permiso_dinamico(user_role, modulo_codigo, tipo_permiso_codigo)
    except Exception as e:
        # Si falla el sistema dinámico, usar el sistema estático como fallback
        pass
    
    # Sistema de permisos estático (fallback)
    if permission in PERMISSIONS:
        return user_role in PERMISSIONS[permission]
    
    return False

def get_user_permissions(user_role):
    """
    Obtiene todos los permisos de un rol
    Intenta usar el sistema dinámico primero, luego fallback al sistema estático
    """
    if user_role == 'admin':
        return list(PERMISSIONS.keys())
    
    # Intentar usar el sistema dinámico de permisos
    try:
        from services.permisos_service import PermisosService
        service = PermisosService()
        
        # Obtener permisos dinámicos
        matriz = service.obtener_matriz_permisos_completa()
        if matriz['success'] and user_role in matriz['matriz']:
            permisos_dinamicos = []
            for modulo_codigo, permisos_modulo in matriz['matriz'][user_role].items():
                for tipo_permiso, permitido in permisos_modulo.items():
                    if permitido:
                        permisos_dinamicos.append(f"{modulo_codigo}.{tipo_permiso}")
            return permisos_dinamicos
    except Exception as e:
        # Si falla el sistema dinámico, usar el sistema estático como fallback
        pass
    
    # Sistema de permisos estático (fallback)
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
