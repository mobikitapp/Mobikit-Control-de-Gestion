from flask import session, render_template, redirect, url_for, jsonify
from flask_login import current_user
from app import app, db
from replit_auth import require_login, make_replit_blueprint
import os
import logging

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


# Monkey patch login_required to support test mode
import flask_login
from functools import wraps

_original_login_required = flask_login.login_required

def login_required_with_test_mode(func):
    """Wrapper for login_required that supports test mode bypass"""
    # Apply the original login_required decorator first
    decorated_func = _original_login_required(func)

    @wraps(func)
    def wrapper(*args, **kwargs):
        # Check for test mode bypass
        test_mode = os.environ.get('TEST_MODE', 'false').lower() == 'true'
        if test_mode:
            # In test mode, bypass login and call original function
            return func(*args, **kwargs)
        else:
            # Otherwise call the login_required decorated function
            return decorated_func(*args, **kwargs)
    return wrapper

# Replace the original login_required with our wrapper
flask_login.login_required = login_required_with_test_mode

# Import login_required for use in this module
from flask_login import login_required
from blueprints.clientes import clientes_bp
from blueprints.proyectos import proyectos_bp
from blueprints.contratos import contratos_bp
from blueprints.fabricacion import fabricacion_bp
from blueprints.despachos import despachos_bp
from blueprints.areas import areas_bp
from blueprints.comercial import comercial_bp
from blueprints.planificacion_operacional import planificacion_operacional_bp
from blueprints.configuraciones import configuraciones_bp
from blueprints.calendario import calendario_bp
from blueprints.mi_dashboard import mi_dashboard_bp
from models import EstadoOF

# Register auth blueprint
app.register_blueprint(make_replit_blueprint(), url_prefix="/auth")

# Register feature blueprints
app.register_blueprint(clientes_bp, url_prefix="/clientes")
app.register_blueprint(proyectos_bp, url_prefix="/proyectos")
app.register_blueprint(contratos_bp, url_prefix="/contratos")
app.register_blueprint(fabricacion_bp, url_prefix="/fabricacion")
app.register_blueprint(despachos_bp, url_prefix="/despachos")
app.register_blueprint(areas_bp, url_prefix="/areas")
app.register_blueprint(comercial_bp, url_prefix="/comercial")
app.register_blueprint(planificacion_operacional_bp, url_prefix="/planificacion-operacional")
app.register_blueprint(configuraciones_bp, url_prefix="/configuraciones")
app.register_blueprint(calendario_bp, url_prefix="/calendario")
app.register_blueprint(mi_dashboard_bp)

# Make session permanent
@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route('/')
def index():
    """Landing page for logged out users, dashboard for logged in users"""
    if not current_user.is_authenticated:
        return render_template('index.html', show_login=True)

    # Dashboard for authenticated users
    from repositories.clientes_repo import ClientesRepository
    from repositories.proyectos_repo import ProyectosRepository
    from repositories.contratos_repo import ContratosRepository
    from repositories.fabricacion_repo import FabricacionRepository
    from repositories.despachos_repo import DespachosRepository
    # Added: Import for Areas Dashboard data
    from services.areas_service import AreasService

    # Get dashboard statistics
    try:
        stats = {
            'total_clientes': ClientesRepository.count_active(),
            'proyectos_activos': ProyectosRepository.count_by_status(['PENDIENTE_PRESUPUESTO', 'PRESUPUESTADO', 'ADJUDICADO', 'EN_DESARROLLO']),
            'contratos_vigentes': ContratosRepository.count_by_status('VIGENTE'),
            'of_en_produccion': FabricacionRepository.count_by_status([
                'ENVIADO_A_FABRICACION',
                'SECCIONANDO',
                'ENCHAPANDO',
                'MECANIZANDO'
            ]),
            'despachos_pendientes': DespachosRepository.count_by_status(['PROGRAMADO', 'EN_TRANSPORTE'])
        }
    except Exception as e:
        logger.error(f"Dashboard stats error: {str(e)}")
        # Fallback stats if there's an error
        stats = {
            'total_clientes': 0,
            'proyectos_activos': 0,
            'contratos_vigentes': 0,
            'of_en_produccion': 0,
            'despachos_pendientes': 0
        }

    # Get recent activity
    try:
        recent_projects = ProyectosRepository.get_recent(limit=5)
        pending_ofs = FabricacionRepository.get_pending_by_user(current_user.id, limit=5)
        # Added: Get areas dashboard data
        areas_dashboard_data = AreasService().get_areas_dashboard_data()
    except Exception as e:
        logger.error(f"Dashboard activity error: {str(e)}")
        recent_projects = []
        pending_ofs = []
        areas_dashboard_data = {} # Default to empty dict if error

    return render_template('index.html',
                         stats=stats,
                         recent_projects=recent_projects,
                         pending_ofs=pending_ofs,
                         areas_dashboard_data=areas_dashboard_data, # Pass areas dashboard data to template
                         show_login=False)

# Main API endpoints for testing
@app.route('/api/clientes')
def api_clientes():
    """Main API endpoint for clientes - used by tests"""
    try:
        from services.clientes_service import ClientesService
        service = ClientesService()
        clientes = service.get_active_clientes()
        return jsonify({
            'success': True,
            'data': [{
                'id': c.id,
                'nombre': c.nombre,
                'rut': c.rut,
                'activo': c.activo
            } for c in clientes]
        })
    except Exception as e:
        logger.error(f"Error en api_clientes: {str(e)}")
        return jsonify({'error': 'Error al cargar clientes'}), 500

@app.route('/api/proyectos')
def api_proyectos():
    """Main API endpoint for proyectos - used by tests"""
    try:
        from repositories.proyectos_repo import ProyectosRepository
        repo = ProyectosRepository()
        proyectos = repo.get_recent(limit=10)
        return jsonify({
            'success': True,
            'data': [{
                'id': p.id,
                'nombre': p.nombre,
                'cliente_id': p.cliente_id,
                'estado': p.estado_comercial.value if hasattr(p, 'estado_comercial') else 'PENDIENTE'
            } for p in proyectos]
        })
    except Exception as e:
        logger.error(f"Error en api_proyectos: {str(e)}")
        return jsonify({'error': 'Error al cargar proyectos'}), 500

@app.route('/api/areas')
def api_areas():
    """Main API endpoint for areas - used by tests"""
    try:
        from repositories.areas_repository import AreasRepository
        repo = AreasRepository()
        areas = repo.get_all_areas()
        return jsonify({
            'success': True,
            'data': [{
                'id': a.id,
                'nombre': a.nombre,
                'descripcion': a.descripcion,
                'activo': a.activo
            } for a in areas]
        })
    except Exception as e:
        logger.error(f"Error en api_areas: {str(e)}")
        return jsonify({'error': 'Error al cargar áreas'}), 500

# API endpoint for calendar events
@app.route('/api/calendar_events')
@login_required
def api_calendar_events():
    """API endpoint for calendar events"""
    try:
        # TODO: Implement calendar events functionality
        return jsonify([])
    except Exception as e:
        logger.error(f"Error obteniendo eventos calendario: {str(e)}")
        return jsonify([]), 500

# Added API endpoint for areas dashboard data
@app.route('/api/areas_dashboard_data')
@login_required
def api_areas_dashboard_data():
    """API endpoint for areas dashboard data"""
    try:
        from services.areas_service import AreasService
        areas_service = AreasService()
        dashboard_data = areas_service.get_areas_dashboard_data()

        return jsonify({
            'success': True,
            'data': dashboard_data
        })
    except Exception as e:
        logger.error(f"Error obteniendo datos dashboard áreas: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Note: Cache and data cleaning endpoints moved to blueprints/configuraciones.py


@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('403.html'), 403