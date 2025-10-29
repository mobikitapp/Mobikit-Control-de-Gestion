
"""
Sistema de permisos granular para Mobikit
Nomenclatura unificada en español para consistencia con sistema dinámico
"""

# Definición de permisos específicos
PERMISSIONS = {
    # Gestión de usuarios
    'usuarios.lectura': ['admin'],
    'usuarios.creacion': ['admin'],
    'usuarios.edicion': ['admin'],
    'usuarios.eliminacion': ['admin'],
    
    # Clientes
    'clientes.lectura': ['admin', 'general', 'ventas', 'finanzas'],
    'clientes.creacion': ['admin', 'general'],
    'clientes.edicion': ['admin', 'general'],
    'clientes.eliminacion': ['admin'],
    
    # Proyectos
    'proyectos.lectura': ['admin', 'general', 'ventas', 'operaciones', 'finanzas'],
    'proyectos.creacion': ['admin', 'general', 'ventas'],
    'proyectos.edicion': ['admin', 'general', 'ventas'],
    'proyectos.eliminacion': ['admin'],
    'proyectos.archivo': ['admin', 'general'],
    'proyectos.adjuntos': ['admin', 'general', 'operaciones', 'ventas'],
    'proyectos.adjuntos.eliminar': ['admin', 'general'],
    
    # Contratos y Órdenes de Compra
    'contratos.lectura': ['admin', 'general', 'ventas', 'operaciones', 'finanzas'],
    'contratos.creacion': ['admin', 'general', 'ventas', 'operaciones', 'finanzas'],
    'contratos.edicion': ['admin', 'general', 'finanzas'],
    'contratos.eliminacion': ['admin'],
    'contratos.aprobacion': ['admin', 'general'],
    'contratos.archivo': ['admin', 'general'],
    
    # Fabricación
    'fabricacion.lectura': ['admin', 'general', 'operaciones', 'produccion', 'finanzas'],
    'fabricacion.creacion': ['admin', 'general', 'operaciones', 'produccion'],
    'fabricacion.edicion': ['admin', 'general', 'operaciones', 'produccion'],
    'fabricacion.eliminacion': ['admin', 'general', 'operaciones'],
    'fabricacion.proceso': ['admin', 'general', 'operaciones', 'produccion'],
    
    # Despachos
    'despachos.lectura': ['admin', 'general', 'operaciones', 'logistica', 'produccion', 'finanzas'],
    'despachos.creacion': ['admin', 'general', 'operaciones', 'logistica'],
    'despachos.edicion': ['admin', 'general', 'operaciones', 'logistica'],
    'despachos.eliminacion': ['admin'],
    'despachos.proceso': ['admin', 'general', 'logistica'],
    'despachos.archivo': ['admin', 'general'],
    
    # Dashboard Comercial
    'comercial.lectura': ['admin', 'general', 'ventas', 'finanzas'],
    
    # Finanzas
    'finanzas.lectura': ['admin', 'general', 'finanzas'],
    'finanzas.creacion': ['admin', 'general', 'finanzas'],
    'finanzas.edicion': ['admin', 'general', 'finanzas'],
    
    # Configuraciones del Sistema
    'configuraciones.lectura': ['admin', 'general'],
    'configuraciones.edicion': ['admin'],
    
    # Planificación
    'planificacion.lectura': ['admin', 'general', 'ventas', 'operaciones', 'finanzas'],
    'planificacion.creacion': ['admin', 'general'],
    'planificacion.edicion': ['admin', 'general'],
    
    # Áreas
    'areas.lectura': ['admin', 'general', 'operaciones', 'produccion', 'logistica'],
    
    # Dashboard Personal del Vendedor
    'mi_dashboard.lectura': ['admin', 'general', 'ventas'],
    'mi_dashboard.mis_clientes': ['admin', 'general', 'ventas'],
    'mi_dashboard.mis_proyectos': ['admin', 'general', 'ventas'],
    'mi_dashboard.estadisticas': ['admin', 'general', 'ventas'],
}

# Mapa de sinónimos para compatibilidad con código antiguo
PERMISSION_SYNONYMS = {
    # Módulos (inglés y variaciones)
    'users': 'usuarios',
    'clients': 'clientes',
    'projects': 'proyectos',
    'orders': 'contratos',
    'purchase_orders': 'contratos',
    'oc': 'contratos',
    'po': 'contratos',
    'ordenes': 'contratos',
    'ordenes_compra': 'contratos',
    'manufacturing': 'fabricacion',
    'dispatch': 'despachos',
    'despacho': 'despachos',
    'commercial': 'comercial',
    'finance': 'finanzas',
    'reports': 'finanzas',  # reportes financieros mapeados a finanzas
    'reportes': 'finanzas',
    'config': 'configuraciones',
    'planning': 'planificacion',
    'calendar': 'planificacion',
    'calendario': 'planificacion',
    'areas': 'areas',
    
    # Tipos de permisos (inglés y español)
    'view': 'lectura',
    'ver': 'lectura',
    'read': 'lectura',
    'leer': 'lectura',
    'create': 'creacion',
    'crear': 'creacion',
    'add': 'creacion',
    'agregar': 'creacion',
    'edit': 'edicion',
    'editar': 'edicion',
    'update': 'edicion',
    'actualizar': 'edicion',
    'delete': 'eliminacion',
    'eliminar': 'eliminacion',
    'remove': 'eliminacion',
    'remover': 'eliminacion',
    'process': 'proceso',
    'procesar': 'proceso',
    'approve': 'aprobacion',
    'aprobar': 'aprobacion',
    'archive': 'archivo',
    'archivar': 'archivo',
}

# Permisos por rol (resumen)
ROLE_PERMISSIONS = {
    'admin': 'all',  # Acceso completo
    'general': [
        'clientes.lectura', 'clientes.creacion', 'clientes.edicion', 'clientes.eliminacion',
        'proyectos.lectura', 'proyectos.creacion', 'proyectos.edicion', 'proyectos.eliminacion', 'proyectos.archivo', 'proyectos.adjuntos', 'proyectos.adjuntos.eliminar',
        'contratos.lectura', 'contratos.creacion', 'contratos.edicion', 'contratos.eliminacion', 'contratos.aprobacion', 'contratos.archivo',
        'fabricacion.lectura', 'fabricacion.creacion', 'fabricacion.edicion', 'fabricacion.eliminacion', 'fabricacion.proceso',
        'despachos.lectura', 'despachos.creacion', 'despachos.edicion', 'despachos.proceso', 'despachos.archivo',
        'comercial.lectura', 'finanzas.lectura', 'finanzas.creacion', 'finanzas.edicion',
        'planificacion.lectura', 'planificacion.creacion', 'planificacion.edicion',
        'areas.lectura', 'areas.creacion', 'areas.edicion',
        'configuraciones.lectura',  # Solo ver configuraciones, no editar
        'mi_dashboard.lectura', 'mi_dashboard.mis_clientes', 'mi_dashboard.mis_proyectos', 'mi_dashboard.estadisticas'
    ],
    'ventas': [
        'clientes.lectura', 
        'proyectos.lectura', 'proyectos.creacion', 'proyectos.edicion', 'proyectos.adjuntos',
        'contratos.lectura', 'contratos.creacion', 
        'comercial.lectura',
        'planificacion.lectura',
        'mi_dashboard.lectura', 'mi_dashboard.mis_clientes', 'mi_dashboard.mis_proyectos', 'mi_dashboard.estadisticas'
    ],
    'operaciones': [
        'proyectos.lectura', 'proyectos.creacion', 'proyectos.edicion', 'proyectos.adjuntos',  # Acceso completo a proyectos incluyendo documentos
        'contratos.lectura', 'contratos.creacion',
        'fabricacion.lectura', 'fabricacion.creacion', 'fabricacion.edicion', 'fabricacion.eliminacion', 'fabricacion.proceso',
        'despachos.lectura', 'despachos.creacion', 'despachos.edicion',
        'planificacion.lectura',
        'areas.lectura'
    ],
    'produccion': [
        'contratos.lectura', 
        'fabricacion.lectura',
        'areas.lectura',
        'despachos.lectura'
    ],
    'logistica': [
        'contratos.lectura', 
        'despachos.lectura', 'despachos.creacion', 'despachos.edicion', 'despachos.proceso',
        'areas.lectura'
    ],
    'finanzas': [
        'clientes.lectura', 
        'proyectos.lectura', 
        'contratos.lectura', 'contratos.creacion', 'contratos.edicion',
        'fabricacion.lectura', 
        'despachos.lectura', 
        'comercial.lectura',
        'finanzas.lectura', 'finanzas.creacion', 'finanzas.edicion',
        'planificacion.lectura'
    ]
}

def normalize_permission(permission):
    """
    Normaliza un permiso usando el mapa de sinónimos
    Ejemplo: 'clients.view' -> 'clientes.lectura'
    Ejemplo: 'Clients.View' -> 'clientes.lectura' (case insensitive)
    """
    if not permission:
        return permission
        
    # Convertir a minúsculas para case insensitivity
    permission = permission.lower().strip()
    
    if '.' in permission:
        modulo, tipo = permission.split('.', 1)
        modulo_norm = PERMISSION_SYNONYMS.get(modulo, modulo)
        tipo_norm = PERMISSION_SYNONYMS.get(tipo, tipo)
        return f"{modulo_norm}.{tipo_norm}"
    return permission

def has_permission(user_role, permission):
    """
    Verifica si un rol tiene un permiso específico
    Admin siempre tiene acceso total, luego intenta sistema dinámico y fallback estático
    Soporta tanto nomenclatura nueva (español) como antigua (inglés) mediante normalización
    """
    # Admin siempre tiene todos los permisos - CRÍTICO: debe ser la primera verificación
    if user_role == 'admin':
        return True
    
    # Normalizar el permiso para soportar nomenclatura antigua
    permission_normalized = normalize_permission(permission)
    
    # Intentar usar el sistema dinámico de permisos solo para roles no-admin
    try:
        from services.permisos_service import PermisosService
        service = PermisosService()
        
        # Parsear el permiso (formato: modulo.tipo_permiso)
        if '.' in permission_normalized:
            modulo_codigo, tipo_permiso_codigo = permission_normalized.split('.', 1)
            resultado = service.verificar_permiso_dinamico(user_role, modulo_codigo, tipo_permiso_codigo)
            
            # Si el sistema dinámico devuelve un resultado explícito (True o False), usarlo
            if resultado is not None:
                return resultado
            # Si devuelve None, continuar al fallback estático
    except Exception as e:
        # Si falla el sistema dinámico, usar el sistema estático como fallback
        pass
    
    # Sistema de permisos estático (fallback) - usar permiso normalizado
    if permission_normalized in PERMISSIONS:
        return user_role in PERMISSIONS[permission_normalized]
    
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
