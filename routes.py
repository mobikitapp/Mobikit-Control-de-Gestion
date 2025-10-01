from flask import session, render_template, redirect, url_for, jsonify, request, flash
from flask_login import current_user, login_user, logout_user
from app import app, db
from replit_auth import require_login, make_replit_blueprint
from models import User
from werkzeug.security import check_password_hash
import os
import logging
from datetime import datetime

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


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login route that handles both display and form submission"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Por favor ingresa usuario y contraseña', 'error')
            return render_template('login.html')
        
        # Find user by email
        user = User.query.filter_by(email=username).first()
        
        if user and user.activo and hasattr(user, 'password_hash') and check_password_hash(user.password_hash, password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Credenciales inválidas o usuario inactivo', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout route"""
    logout_user()
    return redirect(url_for('login'))

from blueprints.contratos import contratos_bp
from blueprints.fabricacion import fabricacion_bp
from blueprints.despachos import despachos_bp
from blueprints.areas import areas_bp
from blueprints.comercial import comercial_bp
from blueprints.planificacion_operacional import planificacion_operacional_bp
from blueprints.configuraciones import configuraciones_bp
from blueprints.calendario import calendario_bp
from blueprints.mi_dashboard import mi_dashboard_bp
from blueprints.capacitacion import capacitacion_bp
from blueprints.finanzas import finanzas_bp
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
app.register_blueprint(capacitacion_bp, url_prefix="/capacitacion")
app.register_blueprint(finanzas_bp, url_prefix="/finanzas")

# Make session permanent
@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route('/health')
def health():
    """Health check endpoint for deployment monitoring"""
    try:
        # Quick database check
        db.session.execute(db.text('SELECT 1'))
        return jsonify({'status': 'healthy', 'database': 'connected'}), 200
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 503

@app.route('/')
def index():
    """Landing page for logged out users, dashboard for logged in users"""
    if not current_user.is_authenticated:
        return render_template('index.html', show_login=True)

    # Dashboard for authenticated users - Dynamic based on role
    from services.dashboard_service import DashboardService

    try:
        # Get complete dashboard data based on user role
        dashboard_service = DashboardService()
        # Type assertion: current_user is User because is_authenticated is True
        user = current_user._get_current_object()
        if not isinstance(user, User):
            raise ValueError("Invalid user object")
        dashboard_data = dashboard_service.get_dashboard_data(user)
        
        return render_template('index.html', 
                             dashboard=dashboard_data,
                             show_login=False)
                             
    except Exception as e:
        logger.error(f"Dashboard error: {str(e)}")
        # Fallback to basic template if there's an error
        return render_template('index.html',
                             dashboard={
                                 'user': current_user,
                                 'rol': current_user.rol.value if current_user.rol else 'general',
                                 'nombre_usuario': current_user.id,
                                 'metrics': {},
                                 'quick_actions': [],
                                 'activity': {'recent_projects': [], 'pending_tasks': []},
                                 'visual': {'dashboard_title': 'Dashboard', 'primary_color': 'primary'}
                             },
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

# API endpoints for UF conversion
@app.route('/api/uf/current')
def api_uf_current():
    """API endpoint para obtener el valor UF actual"""
    try:
        from services.uf_conversion_service import UfConversionService
        uf_service = UfConversionService()
        valor_uf = uf_service.get_current_uf_value()
        
        if valor_uf is None:
            return jsonify({
                'success': False,
                'error': 'No se pudo obtener el valor UF'
            }), 500
        
        return jsonify({
            'success': True,
            'valor_uf': float(valor_uf),
            'fecha': datetime.now().strftime('%Y-%m-%d')
        })
    except Exception as e:
        logger.error(f"Error obteniendo valor UF actual: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Error al obtener valor UF'
        }), 500

@app.route('/api/uf/convert')
def api_uf_convert():
    """API endpoint para convertir entre UF y CLP"""
    try:
        from services.uf_conversion_service import UfConversionService
        
        # Obtener parámetros
        monto = request.args.get('monto', type=float)
        from_currency = request.args.get('from', 'UF').upper()  # UF o CLP
        
        if monto is None:
            return jsonify({
                'success': False,
                'error': 'Monto es requerido'
            }), 400
            
        if from_currency not in ['UF', 'CLP']:
            return jsonify({
                'success': False,
                'error': 'Moneda debe ser UF o CLP'
            }), 400
        
        uf_service = UfConversionService()
        valor_uf = uf_service.get_current_uf_value()
        
        if valor_uf is None:
            return jsonify({
                'success': False,
                'error': 'No se pudo obtener el valor UF'
            }), 500
        
        if from_currency == 'UF':
            # Convertir UF a CLP
            clp_amount = uf_service.convert_uf_to_clp(monto)
            if clp_amount is None:
                return jsonify({
                    'success': False,
                    'error': 'Error en conversión UF a CLP'
                }), 500
                
            return jsonify({
                'success': True,
                'original_amount': monto,
                'original_currency': 'UF',
                'converted_amount': float(clp_amount),
                'converted_currency': 'CLP',
                'uf_value': float(valor_uf),
                'fecha': datetime.now().strftime('%Y-%m-%d')
            })
        else:
            # Convertir CLP a UF
            uf_amount = uf_service.convert_clp_to_uf(monto)
            if uf_amount is None:
                return jsonify({
                    'success': False,
                    'error': 'Error en conversión CLP a UF'
                }), 500
                
            return jsonify({
                'success': True,
                'original_amount': monto,
                'original_currency': 'CLP',
                'converted_amount': float(uf_amount),
                'converted_currency': 'UF',
                'uf_value': float(valor_uf),
                'fecha': datetime.now().strftime('%Y-%m-%d')
            })
            
    except Exception as e:
        logger.error(f"Error en conversión UF: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Error en conversión'
        }), 500


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