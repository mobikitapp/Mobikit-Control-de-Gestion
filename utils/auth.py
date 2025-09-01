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
        
        if current_user.rol != RolUsuario.ADMIN:
            abort(403)
        
        return f(*args, **kwargs)
    return decorated_function


def role_required(allowed_roles):
    """Decorator to require specific roles"""
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