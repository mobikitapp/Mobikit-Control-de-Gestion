import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_migrate import Migrate
from flask_login import current_user
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
migrate = Migrate()

def create_app():
    # Create the app
    app = Flask(__name__)
    app.secret_key = os.environ.get("SESSION_SECRET")
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)  # needed for url_for to generate with https

    # Configure the database
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # File upload configuration
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "25")) * 1024 * 1024
    app.config["ALLOWED_MIME_TYPES"] = os.environ.get("ALLOWED_MIME", "application/pdf,image/jpeg,image/png").split(",")

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    with app.app_context():
        # Import models to ensure they are registered
        import models  # noqa: F401

        # Create tables
        db.create_all()
        logging.info("Database tables created")

    @app.context_processor
    def inject_current_user():
        """Inject current user into all templates"""
        return dict(
            current_user=current_user,
            timestamp=lambda: int(datetime.now().timestamp()),
            has_permission=lambda modulo, tipo_permiso: check_user_permission(modulo, tipo_permiso)
        )

    def check_user_permission(modulo_codigo, tipo_permiso):
        """Check if current user has specific permission"""
        if not current_user.is_authenticated:
            return False

        # Import RolUsuario here to avoid circular import
        from models import RolUsuario
        
        # Admin always has access
        if current_user.rol == RolUsuario.ADMIN:
            return True

        try:
            from services.permisos_service import PermisosService
            service = PermisosService()

            user_role = current_user.rol.value if hasattr(current_user.rol, 'value') else str(current_user.rol)
            has_permission = service.verificar_permiso_dinamico(user_role, modulo_codigo, tipo_permiso)

            if has_permission is True:
                return True
            elif has_permission is False:
                return False
            elif has_permission is None:
                # Fallback to static permissions
                from utils.permissions import has_permission as static_has_permission
                return static_has_permission(f"{modulo_codigo}.{tipo_permiso}", user_role)
            else:
                return False

        except Exception as e:
            print(f"Error checking template permission: {e}")
            return False

    @app.before_request
    def check_user_role():
        """Global guard: block authenticated users without role from accessing protected routes"""
        from flask import request, render_template
        
        # Allow public routes
        allowed_endpoints = [
            'static',
            'replit_auth.login',
            'replit_auth.logout',
            'replit_auth.authorized',  # OAuth callback
            'replit_auth.error',
            'health',
            'health_live',
            'health_ready'
        ]
        
        # Allow if not authenticated, endpoint is None (404), or endpoint is allowed
        if not current_user.is_authenticated or request.endpoint is None or request.endpoint in allowed_endpoints:
            return None
        
        # Block users without role (except logout)
        if current_user.rol is None:
            if request.endpoint == 'replit_auth.logout':
                return None
            return render_template("sin_rol.html"), 403
        
        # All other checks passed
        return None

    return app

# Create the app instance
app = create_app()