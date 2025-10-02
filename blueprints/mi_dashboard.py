"""
Blueprint para el Dashboard Personal del Vendedor
Permite a cada vendedor ver sus métricas, clientes y proyectos personales
"""

from flask import Blueprint, render_template, request, current_app
from flask_login import login_required, current_user
from models import RolUsuario, Proyecto
from utils.auth import role_required
from services.dashboard_vendedor_service import DashboardVendedorService
from app import db
from sqlalchemy.orm import joinedload
from sqlalchemy import or_


mi_dashboard_bp = Blueprint('mi_dashboard', __name__, url_prefix='/mi-dashboard')

@mi_dashboard_bp.route('/')
@login_required
@role_required([RolUsuario.VENTAS, RolUsuario.ADMIN, RolUsuario.GENERAL])
def index():
    """Dashboard principal del vendedor"""
    try:
        # Obtener métricas del vendedor actual
        dashboard_service = DashboardVendedorService()
        vendedor_id = current_user.id

        # Métricas principales
        metricas = dashboard_service.get_metricas_vendedor(vendedor_id)

        # Métricas de tasa de éxito
        tasa_exito = dashboard_service.get_tasa_exito_vendedor(vendedor_id)

        # Proyectos activos
        proyectos_activos = dashboard_service.get_proyectos_activos(vendedor_id)

        # Clientes recientes
        clientes_recientes = dashboard_service.get_clientes_recientes(vendedor_id)

        # Tareas pendientes
        tareas_pendientes = dashboard_service.get_tareas_pendientes(vendedor_id)

        return render_template('mi_dashboard/index.html',
                             metricas=metricas,
                             tasa_exito=tasa_exito,
                             proyectos_activos=proyectos_activos,
                             clientes_recientes=clientes_recientes,
                             tareas_pendientes=tareas_pendientes)

    except Exception as e:
        current_app.logger.error(f"Error en dashboard personal: {e}")
        return render_template('mi_dashboard/index.html',
                             metricas={},
                             tasa_exito={},
                             proyectos_activos=[],
                             clientes_recientes=[],
                             tareas_pendientes=[])

@mi_dashboard_bp.route('/mis-clientes')
@login_required
@role_required([RolUsuario.VENTAS, RolUsuario.ADMIN, RolUsuario.GENERAL])
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
@role_required([RolUsuario.VENTAS, RolUsuario.ADMIN, RolUsuario.GENERAL])
def mis_proyectos():
    """Lista de proyectos asignados al vendedor"""
    try:
        from services.proyectos_service import ProyectosService

        proyectos_service = ProyectosService()

        # Filtros
        estado = request.args.get('estado', 'todos')
        periodo = request.args.get('periodo', 'actual')

        # Obtener proyectos según el rol del usuario - siempre filtrar por vendedor_id
        # Todos los usuarios (incluyendo ADMIN y GENERAL) ven proyectos donde son vendedores
        proyectos = db.session.query(Proyecto)\
            .options(joinedload(Proyecto.cliente))\
            .filter_by(vendedor_id=current_user.id)\
            .filter_by(activo=True)\
            .order_by(Proyecto.created_at.desc())\
            .all()

        # Debug logging específico para identificar problemas de vendedor
        current_app.logger.info(f"=== DEBUG MIS PROYECTOS ===")
        current_app.logger.info(f"Usuario actual ID: {current_user.id}")
        current_app.logger.info(f"Usuario actual Rol: {current_user.rol}")
        current_app.logger.info(f"Usuario actual Email: {current_user.email}")

        # Verificar TODOS los proyectos en la base de datos
        todos_proyectos = db.session.query(Proyecto).filter_by(activo=True).all()
        current_app.logger.info(f"Total proyectos activos en BD: {len(todos_proyectos)}")

        # Log de proyectos con vendedor_id que coincida
        proyectos_con_vendedor_actual = [p for p in todos_proyectos if p.vendedor_id == current_user.id]
        current_app.logger.info(f"Proyectos con vendedor_id={current_user.id}: {len(proyectos_con_vendedor_actual)}")

        for proyecto in todos_proyectos[:10]:  # Log primeros 10 proyectos para debug
            current_app.logger.info(f"Proyecto {proyecto.id}: {proyecto.nombre}, Vendedor_ID: '{proyecto.vendedor_id}', Created_by: '{proyecto.created_by}'")

        current_app.logger.info(f"Proyectos filtrados encontrados: {len(proyectos)}")
        current_app.logger.info(f"=== FIN DEBUG ===")

        # Log específico de los proyectos encontrados
        for proyecto in proyectos[:5]:
            current_app.logger.info(f"Proyecto encontrado {proyecto.id}: {proyecto.nombre}, Cliente: {proyecto.cliente.nombre if proyecto.cliente else 'Sin cliente'}, Vendedor: {proyecto.vendedor_id}")


        # Aplicar filtros de estado
        if estado != 'todos':
            from models import EstadoComercial
            estado_enum = EstadoComercial(estado)
            proyectos = [p for p in proyectos if p.estado_comercial == estado_enum]

        # Aplicar filtros de periodo
        if periodo != 'todos':
            from datetime import datetime, timedelta
            hoy = datetime.now().date()

            if periodo == 'actual':
                inicio_mes = hoy.replace(day=1)
                proyectos = [p for p in proyectos if p.created_at.date() >= inicio_mes]
            elif periodo == 'trimestre':
                inicio_trimestre = hoy - timedelta(days=90)
                proyectos = [p for p in proyectos if p.created_at.date() >= inicio_trimestre]

        return render_template('mi_dashboard/mis_proyectos.html',
                             proyectos=proyectos,
                             estado_actual=estado,
                             periodo_actual=periodo)

    except Exception as e:
        current_app.logger.error(f"Error obteniendo mis proyectos: {e}")
        import traceback
        current_app.logger.error(f"Traceback: {traceback.format_exc()}")
        return render_template('mi_dashboard/mis_proyectos.html',
                             proyectos=[],
                             estado_actual='todos',
                             periodo_actual='actual')

@mi_dashboard_bp.route('/estadisticas')
@login_required
@role_required([RolUsuario.VENTAS, RolUsuario.ADMIN, RolUsuario.GENERAL])
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
@role_required([RolUsuario.VENTAS, RolUsuario.ADMIN, RolUsuario.GENERAL])
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