from flask import session, render_template, redirect, url_for
from flask_login import current_user
from app import app, db
from replit_auth import require_login, make_replit_blueprint
from blueprints.clientes import clientes_bp
from blueprints.proyectos import proyectos_bp
from blueprints.contratos import contratos_bp
from blueprints.fabricacion import fabricacion_bp
from blueprints.despachos import despachos_bp
from blueprints.areas import areas_bp
from blueprints.comercial import comercial_bp
from blueprints.planificacion_operacional import planificacion_operacional_bp
from blueprints.configuraciones import configuraciones_bp

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
    
    # Get dashboard statistics
    stats = {
        'total_clientes': ClientesRepository.count_active(),
        'proyectos_activos': ProyectosRepository.count_by_status(['planificacion', 'en_desarrollo']),
        'contratos_vigentes': ContratosRepository.count_by_status('vigente'),
        'of_en_produccion': FabricacionRepository.count_by_status(['en_produccion', 'qa']),
        'despachos_pendientes': DespachosRepository.count_by_status(['programado', 'en_transporte'])
    }
    
    # Get recent activity
    recent_projects = ProyectosRepository.get_recent(limit=5)
    pending_ofs = FabricacionRepository.get_pending_by_user(current_user.id, limit=5)
    
    return render_template('index.html', 
                         stats=stats, 
                         recent_projects=recent_projects,
                         pending_ofs=pending_ofs,
                         show_login=False)

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
