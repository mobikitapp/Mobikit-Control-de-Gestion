"""
Blueprint para el Dashboard Personal del Vendedor
Permite a cada vendedor ver sus métricas, clientes y proyectos personales
"""

from flask import Blueprint, render_template, request, current_app
from flask_login import login_required, current_user
from utils.auth import role_required
from utils.permissions import permission_required
from models import RolUsuario
from services.dashboard_vendedor_service import DashboardVendedorService

mi_dashboard_bp = Blueprint('mi_dashboard', __name__, url_prefix='/mi-dashboard')

@mi_dashboard_bp.route('/')
@login_required
@role_required([RolUsuario.VENTAS])
def index():
    """Dashboard principal del vendedor"""
    try:
        # Obtener métricas del vendedor actual
        dashboard_service = DashboardVendedorService()
        vendedor_id = current_user.id
        
        # Métricas principales
        metricas = dashboard_service.get_metricas_vendedor(vendedor_id)
        
        # Proyectos activos
        proyectos_activos = dashboard_service.get_proyectos_activos(vendedor_id)
        
        # Clientes recientes
        clientes_recientes = dashboard_service.get_clientes_recientes(vendedor_id)
        
        # Tareas pendientes
        tareas_pendientes = dashboard_service.get_tareas_pendientes(vendedor_id)
        
        return render_template('mi_dashboard/index.html',
                             metricas=metricas,
                             proyectos_activos=proyectos_activos,
                             clientes_recientes=clientes_recientes,
                             tareas_pendientes=tareas_pendientes)
                             
    except Exception as e:
        current_app.logger.error(f"Error en dashboard personal: {e}")
        return render_template('mi_dashboard/index.html',
                             metricas={},
                             proyectos_activos=[],
                             clientes_recientes=[],
                             tareas_pendientes=[])

@mi_dashboard_bp.route('/mis-clientes')
@login_required
@role_required([RolUsuario.VENTAS])
def mis_clientes():
    """Lista de clientes asignados al vendedor"""
    try:
        dashboard_service = DashboardVendedorService()
        vendedor_id = current_user.id
        
        # Filtros
        estado = request.args.get('estado', 'todos')
        busqueda = request.args.get('busqueda', '')
        
        clientes = dashboard_service.get_mis_clientes(
            vendedor_id, 
            estado=estado,
            busqueda=busqueda
        )
        
        return render_template('mi_dashboard/mis_clientes.html',
                             clientes=clientes,
                             estado_actual=estado,
                             busqueda_actual=busqueda)
                             
    except Exception as e:
        current_app.logger.error(f"Error obteniendo mis clientes: {e}")
        return render_template('mi_dashboard/mis_clientes.html',
                             clientes=[])

@mi_dashboard_bp.route('/mis-proyectos')
@login_required
@role_required([RolUsuario.VENTAS])
def mis_proyectos():
    """Lista de proyectos del vendedor"""
    try:
        dashboard_service = DashboardVendedorService()
        vendedor_id = current_user.id
        
        # Filtros
        estado = request.args.get('estado', 'todos')
        periodo = request.args.get('periodo', 'actual')
        
        proyectos = dashboard_service.get_mis_proyectos(
            vendedor_id,
            estado=estado,
            periodo=periodo
        )
        
        return render_template('mi_dashboard/mis_proyectos.html',
                             proyectos=proyectos,
                             estado_actual=estado,
                             periodo_actual=periodo)
                             
    except Exception as e:
        current_app.logger.error(f"Error obteniendo mis proyectos: {e}")
        return render_template('mi_dashboard/mis_proyectos.html',
                             proyectos=[])

@mi_dashboard_bp.route('/estadisticas')
@login_required
@role_required([RolUsuario.VENTAS])
def estadisticas():
    """Estadísticas detalladas del vendedor"""
    try:
        dashboard_service = DashboardVendedorService()
        vendedor_id = current_user.id
        
        # Período seleccionado
        periodo = request.args.get('periodo', '6meses')
        
        # Estadísticas completas
        stats = dashboard_service.get_estadisticas_detalladas(vendedor_id, periodo)
        
        return render_template('mi_dashboard/estadisticas.html',
                             estadisticas=stats,
                             periodo_actual=periodo)
                             
    except Exception as e:
        current_app.logger.error(f"Error obteniendo estadísticas: {e}")
        return render_template('mi_dashboard/estadisticas.html',
                             estadisticas={})

@mi_dashboard_bp.route('/api/metricas-mes')
@login_required
@role_required([RolUsuario.VENTAS])
def api_metricas_mes():
    """API para obtener métricas mensuales (para gráficos)"""
    try:
        dashboard_service = DashboardVendedorService()
        vendedor_id = current_user.id
        
        meses = int(request.args.get('meses', 6))
        metricas = dashboard_service.get_metricas_mensuales(vendedor_id, meses)
        
        return {'success': True, 'data': metricas}
        
    except Exception as e:
        current_app.logger.error(f"Error API métricas mes: {e}")
        return {'success': False, 'error': str(e)}, 500