import os
from functools import wraps
from flask import abort
from flask_login import current_user
from models import RolUsuario


def admin_required(f):
    """Decorator to require admin role"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for test mode bypass
        test_mode = os.environ.get('TEST_MODE', 'false').lower() == 'true'
        if test_mode:
            return f(*args, **kwargs)
            
        if not current_user.is_authenticated:
            abort(401)
        
        if not current_user.activo:
            abort(403)
        
        # Verificar admin tanto por enum como por string (compatibilidad)
        user_role = current_user.rol
        is_admin = (user_role == RolUsuario.ADMIN or 
                   (hasattr(user_role, 'value') and user_role.value == 'admin') or
                   str(user_role).lower() == 'admin')
        
        if not is_admin:
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def role_required(allowed_roles):
    """
    Decorator to require specific roles.
    Now integrates with dynamic permissions system.
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check for test mode bypass
            test_mode = os.environ.get('TEST_MODE', 'false').lower() == 'true'
            if test_mode:
                return f(*args, **kwargs)
                
            if not current_user.is_authenticated:
                abort(401)
            
            if not current_user.activo:
                abort(403)
            
            # Admin always has access
            if current_user.rol == RolUsuario.ADMIN:
                return f(*args, **kwargs)
            
            # Convert string roles to enum if needed
            roles_enum = []
            for role in allowed_roles:
                if isinstance(role, str):
                    roles_enum.append(RolUsuario(role))
                else:
                    roles_enum.append(role)
            
            # Check if user has one of the allowed roles (static check)
            if current_user.rol in roles_enum:
                # User has the role, now check dynamic permissions
                try:
                    from flask import request
                    from services.permisos_service import PermisosService
                    
                    # Try to get module code from blueprint name
                    blueprint_name = request.blueprint
                    if blueprint_name:
                        service = PermisosService()
                        user_role = current_user.rol.value if hasattr(current_user.rol, 'value') else str(current_user.rol)
                        
                        # Check dynamic permission (lectura by default)
                        has_permission = service.verificar_permiso_dinamico(user_role, blueprint_name, 'lectura')
                        
                        if has_permission is True:
                            # Dynamic permission explicitly allows
                            return f(*args, **kwargs)
                        elif has_permission is False:
                            # Dynamic permission explicitly denies
                            abort(403)
                        # If has_permission is None, fall through to allow (static role was valid)
                except Exception as e:
                    # If dynamic check fails, log and fall through to static role check
                    print(f"Dynamic permission check failed: {e}")
                
                # Static role check passed, allow access
                return f(*args, **kwargs)
            
            # User doesn't have any of the allowed roles
            abort(403)
            
        return decorated_function
    return decorator


def production_required(f):
    """Decorator to require production-related roles"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for test mode bypass
        test_mode = os.environ.get('TEST_MODE', 'false').lower() == 'true'
        if test_mode:
            return f(*args, **kwargs)
            
        if not current_user.is_authenticated:
            abort(401)
        
        if not current_user.activo:
            abort(403)
        
        allowed_roles = [
            RolUsuario.ADMIN,
            RolUsuario.OPERACIONES,
            RolUsuario.PRODUCCION
        ]
        
        if current_user.rol not in allowed_roles:
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def logistics_required(f):
    """Decorator to require logistics or admin roles"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for test mode bypass
        test_mode = os.environ.get('TEST_MODE', 'false').lower() == 'true'
        if test_mode:
            return f(*args, **kwargs)
            
        if not current_user.is_authenticated:
            abort(401)
        
        if not current_user.activo:
            abort(403)
        
        allowed_roles = [
            RolUsuario.ADMIN,
            RolUsuario.LOGISTICA
        ]
        
        if current_user.rol not in allowed_roles:
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def require_role(*allowed_roles):
    """Decorator to require specific roles - accepts multiple role arguments"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check for test mode bypass
            test_mode = os.environ.get('TEST_MODE', 'false').lower() == 'true'
            if test_mode:
                return f(*args, **kwargs)
                
            if not current_user.is_authenticated:
                abort(401)
            
            if not current_user.activo:
                abort(403)
            
            # Convert string roles to enum if needed
            roles_enum = []
            for role in allowed_roles:
                if isinstance(role, str):
                    roles_enum.append(RolUsuario(role))
                else:
                    roles_enum.append(role)
            
            if current_user.rol not in roles_enum:
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def require_permission(modulo_codigo, tipo_permiso='lectura'):
    """Decorator to require specific permission using dynamic permissions system"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Check for test mode bypass
            test_mode = os.environ.get('TEST_MODE', 'false').lower() == 'true'
            if test_mode:
                return f(*args, **kwargs)
                
            if not current_user.is_authenticated:
                abort(401)
            
            if not current_user.activo:
                abort(403)
            
            # Admin always has access
            if current_user.rol == RolUsuario.ADMIN:
                return f(*args, **kwargs)
            
            # Check dynamic permissions
            try:
                from services.permisos_service import PermisosService
                service = PermisosService()
                
                user_role = current_user.rol.value if hasattr(current_user.rol, 'value') else str(current_user.rol)
                has_permission = service.verificar_permiso_dinamico(user_role, modulo_codigo, tipo_permiso)
                
                if has_permission is True:
                    return f(*args, **kwargs)
                elif has_permission is False:
                    abort(403)
                elif has_permission is None:
                    # Fallback to static permissions
                    from utils.permissions import has_permission as static_has_permission
                    if static_has_permission(f"{modulo_codigo}.{tipo_permiso}", user_role):
                        return f(*args, **kwargs)
                    else:
                        abort(403)
                else:
                    abort(403)
                    
            except Exception as e:
                # In case of error, deny access for security
                print(f"Error checking permission: {e}")
                abort(403)
            
        return decorated_function
    return decorator