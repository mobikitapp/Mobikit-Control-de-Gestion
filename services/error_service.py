
import logging
import traceback
import os
from datetime import datetime
from flask import request, session
from flask_login import current_user

logger = logging.getLogger(__name__)

class ErrorService:
    """Service for comprehensive error handling and logging"""
    
    @staticmethod
    def log_error(error, context=None, user_id=None):
        """
        Log error with comprehensive context information
        
        Args:
            error: Exception object
            context: Additional context information
            user_id: User ID if available
        """
        try:
            error_info = {
                'timestamp': datetime.now().isoformat(),
                'error_type': type(error).__name__,
                'error_message': str(error),
                'traceback': traceback.format_exc(),
                'context': context or {},
            }
            
            # Add request context if available
            try:
                if request:
                    error_info['request'] = {
                        'method': request.method,
                        'url': request.url,
                        'endpoint': request.endpoint,
                        'user_agent': request.headers.get('User-Agent', ''),
                        'remote_addr': request.remote_addr,
                        'form_data': dict(request.form) if request.form else {},
                        'args': dict(request.args) if request.args else {}
                    }
            except Exception:
                pass
            
            # Add user context if available
            try:
                if current_user and current_user.is_authenticated:
                    error_info['user'] = {
                        'id': getattr(current_user, 'id', None),
                        'email': getattr(current_user, 'email', None),
                        'rol': getattr(current_user, 'rol', None)
                    }
                elif user_id:
                    error_info['user'] = {'id': user_id}
            except Exception:
                pass
            
            # Add session context if available
            try:
                if session:
                    error_info['session'] = {
                        'session_keys': list(session.keys())
                    }
            except Exception:
                pass
            
            # Log the comprehensive error
            logger.error(f"Production Error: {error_info['error_type']}", extra=error_info)
            
            # Also log to console for immediate visibility
            print(f"=== PRODUCTION ERROR ===")
            print(f"Time: {error_info['timestamp']}")
            print(f"Type: {error_info['error_type']}")
            print(f"Message: {error_info['error_message']}")
            if 'request' in error_info:
                print(f"Endpoint: {error_info['request']['endpoint']}")
                print(f"URL: {error_info['request']['url']}")
            if 'user' in error_info:
                print(f"User: {error_info['user']}")
            print(f"Traceback: {error_info['traceback']}")
            print("========================")
            
        except Exception as log_error:
            # Fallback logging if main logging fails
            print(f"Error logging failed: {log_error}")
            print(f"Original error: {error}")
            
    @staticmethod
    def get_safe_user_info():
        """
        Safely get user information without throwing exceptions
        """
        try:
            if current_user and current_user.is_authenticated:
                return {
                    'id': getattr(current_user, 'id', None),
                    'email': getattr(current_user, 'email', None),
                    'rol': str(getattr(current_user, 'rol', None)) if hasattr(current_user, 'rol') else None,
                    'activo': getattr(current_user, 'activo', None)
                }
            return None
        except Exception:
            return None
    
    @staticmethod
    def safe_template_render(template_name, **context):
        """
        Safely render template with fallback
        
        Args:
            template_name: Template file name
            **context: Template context
            
        Returns:
            Rendered template or error template
        """
        try:
            from flask import render_template
            return render_template(template_name, **context)
        except Exception as e:
            ErrorService.log_error(e, context={'template': template_name, 'context_keys': list(context.keys())})
            try:
                # Try to render basic error template
                return render_template('500.html'), 500
            except Exception:
                # Ultimate fallback - raw HTML
                return '''
                <html>
                    <head><title>Error del Sistema</title></head>
                    <body>
                        <h1>Error Interno del Servidor</h1>
                        <p>Ha ocurrido un error inesperado. Por favor contacte al administrador.</p>
                        <a href="/">Volver al inicio</a>
                    </body>
                </html>
                ''', 500
