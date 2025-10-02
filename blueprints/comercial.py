from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import current_user, login_required
from sqlalchemy import and_, or_, func, extract
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import calendar
import logging

from app import db
from models import (
    Proyecto, Cliente, User, TareaComercial, ObjetivoMensual,
    EstadoComercial, RolUsuario
)
from services.comercial_service import ComercialService
from services.revenue_service import RevenueService
from utils.auth import role_required

# Configure logging
logger = logging.getLogger(__name__)

# Create blueprint
comercial_bp = Blueprint('comercial', __name__)

# Instantiate services
comercial_service = ComercialService()
revenue_service = RevenueService()

# Sales center routes
@comercial_bp.route('/')
@comercial_bp.route('/centro-vendedores')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def centro_vendedores():
    """Redirige a lista de vendedores"""
    return redirect(url_for('comercial.lista_vendedores'))


@comercial_bp.route('/vendedores')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def lista_vendedores():
    """Lista de vendedores con estadísticas fusionando centro de vendedores"""
    try:
        from services.dashboard_vendedor_service import DashboardVendedorService

        dashboard_service = DashboardVendedorService()

        # Get filters from request (similar to centro_vendedores)
        cliente_id = request.args.get('cliente_id', type=int)
        vendedor_id = request.args.get('vendedor_id')
        estado_comercial = request.args.get('estado_comercial')

        # Get data for the sales center (general statistics)
        centro_data = comercial_service.get_centro_vendedores_data(
            current_user_id=current_user.id,
            cliente_id=cliente_id,
            vendedor_id=vendedor_id,
            estado_comercial=estado_comercial
        )

        # Get vendedores statistics
        vendedores_stats = comercial_service.get_vendedores_estadisticas()

        # Agregar métricas de tasa de éxito a cada vendedor
        for vendedor_data in vendedores_stats:
            vendedor_id_inner = vendedor_data['vendedor'].id
            tasa_exito = dashboard_service.get_tasa_exito_vendedor(vendedor_id_inner)
            vendedor_data['tasa_exito'] = tasa_exito

        # Preparar datos para el gráfico de comisiones mensuales consolidado
        current_year = datetime.now().year
        meses_actual_year = [calendar.month_name[i] for i in range(1, 13)]

        # Calcular comisiones consolidadas por mes para todos los vendedores
        comisiones_mensuales_adjudicadas = []

        for mes in range(1, 13):
            comision_mes = 0
            for vendedor_data in vendedores_stats:
                comisiones_vendedor = vendedor_data['stats'].get('comisiones_mensuales', [])
                comision_vendedor_mes = next((c['comision_total'] for c in comisiones_vendedor if c['mes'] == mes), 0)
                comision_mes += comision_vendedor_mes
            comisiones_mensuales_adjudicadas.append(comision_mes)

        # Merge centro data with vendedores data
        merged_data = {
            'vendedores': vendedores_stats,
            'vendedores_stats': vendedores_stats,
            'current_year': current_year,
            'meses_actual_year': meses_actual_year,
            'comisiones_mensuales_adjudicadas': comisiones_mensuales_adjudicadas,
            # Data from centro de vendedores
            'stats': centro_data['stats'],
            'proyectos_por_estado': centro_data['proyectos_por_estado'],
            'clientes': centro_data['clientes'],
            'estadios_comerciales': centro_data['estadios_comerciales'],
            'filtros': centro_data['filtros']
        }

        return render_template('comercial/vendedores.html', **merged_data)

    except Exception as e:
        logger.error(f'Error al cargar vendedores: {str(e)}')
        flash(f'Error al cargar vendedores: {str(e)}', 'error')
        current_year = datetime.now().year
        meses_actual_year = [calendar.month_name[i] for i in range(1, 13)]
        comisiones_mensuales_adjudicadas = [0] * 12

        return render_template('comercial/vendedores.html', 
                             vendedores=[],
                             vendedores_stats=[], 
                             current_year=current_year,
                             meses_actual_year=meses_actual_year,
                             comisiones_mensuales_adjudicadas=comisiones_mensuales_adjudicadas,
                             stats={},
                             proyectos_por_estado={},
                             clientes=[],
                             estadios_comerciales=[],
                             filtros={})


@comercial_bp.route('/vendedor/<string:vendedor_id>')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def vendedor_detalle(vendedor_id):
    """Detalle de un vendedor específico"""
    try:
        from services.dashboard_vendedor_service import DashboardVendedorService

        dashboard_service = DashboardVendedorService()

        vendedor_data = comercial_service.get_vendedor_detalle(vendedor_id)
        if not vendedor_data:
            flash('Vendedor no encontrado', 'error')
            return redirect(url_for('comercial.lista_vendedores'))

        # Agregar año actual para el template
        vendedor_data['current_year'] = datetime.now().year

        # Agregar métricas de tasa de éxito
        vendedor_data['tasa_exito'] = dashboard_service.get_tasa_exito_vendedor(vendedor_id)

        return render_template('comercial/vendedor_detalle.html', **vendedor_data)

    except Exception as e:
        logger.error(f'Error al cargar detalle del vendedor {vendedor_id}: {str(e)}')
        flash(f'Error al cargar detalle del vendedor: {str(e)}', 'error')
        return redirect(url_for('comercial.lista_vendedores'))


# Project commercial management
@comercial_bp.route('/proyecto/<int:proyecto_id>/comercial')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def proyecto_comercial(proyecto_id):
    """Gestión comercial de un proyecto específico"""
    try:
        proyecto_data = comercial_service.get_proyecto_comercial_data(proyecto_id)

        if not proyecto_data:
            flash('Proyecto no encontrado o sin acceso', 'error')
            return redirect(url_for('comercial.lista_vendedores'))

        # Verificar permisos específicos del usuario
        proyecto = proyecto_data.get('proyecto')
        if proyecto and current_user.rol.value not in ['admin', 'general']:
            if proyecto.vendedor_id != current_user.id:
                flash('No tienes permisos para editar este proyecto', 'warning')
                return redirect(url_for('comercial.lista_vendedores'))

        return render_template('comercial/proyecto_comercial.html', **proyecto_data)

    except Exception as e:
        logger.error(f'Error al cargar datos comerciales del proyecto {proyecto_id}: {str(e)}')
        flash(f'Error al cargar datos comerciales del proyecto: {str(e)}', 'error')
        return redirect(url_for('comercial.centro_vendedores'))


@comercial_bp.route('/proyecto/<int:proyecto_id>/comercial/actualizar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def actualizar_comercial_proyecto(proyecto_id):
    """Actualizar información comercial de un proyecto"""
    try:
        data = {
            'vendedor_id': request.form.get('vendedor_id'),
            'estado_comercial': request.form.get('estado_comercial'),
            'valor_presupuestado_provision': request.form.get('valor_presupuestado_provision'),
            'margen_venta_provision': request.form.get('margen_venta_provision'),
            'valor_instalacion': request.form.get('valor_instalacion'),
            'margen_venta_instalacion': request.form.get('margen_venta_instalacion'),
            'fecha_presupuesto': request.form.get('fecha_presupuesto'),
            'fecha_adjudicacion': request.form.get('fecha_adjudicacion'),
            'notas_comerciales': request.form.get('notas_comerciales')
        }

        success = comercial_service.actualizar_comercial_proyecto(proyecto_id, data, current_user.id)

        if success:
            flash('Información comercial actualizada exitosamente', 'success')
        else:
            flash('Error al actualizar información comercial', 'error')

        return redirect(url_for('comercial.proyecto_comercial', proyecto_id=proyecto_id))

    except Exception as e:
        logger.error(f'Error al actualizar comercial proyecto {proyecto_id}: {str(e)}')
        flash(f'Error al actualizar: {str(e)}', 'error')
        return redirect(url_for('comercial.proyecto_comercial', proyecto_id=proyecto_id))


# Commercial tasks management
@comercial_bp.route('/tareas')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def tareas_comerciales():
    """Lista de tareas comerciales"""
    try:
        vendedor_id = request.args.get('vendedor_id')
        estado = request.args.get('estado')  # 'pendientes', 'completadas', 'todas'

        tareas_data = comercial_service.get_tareas_comerciales(
            vendedor_id=vendedor_id,
            estado=estado
        )

        return render_template('comercial/tareas.html', **tareas_data)

    except Exception as e:
        logger.error(f'Error al cargar tareas comerciales: {str(e)}')
        flash(f'Error al cargar tareas: {str(e)}', 'error')
        return redirect(url_for('comercial.lista_vendedores'))


@comercial_bp.route('/tarea/<int:tarea_id>/completar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def completar_tarea(tarea_id):
    """Marcar una tarea como completada"""
    try:
        notas = request.form.get('notas', '')
        success = comercial_service.completar_tarea(tarea_id, current_user.id, notas)

        if success:
            flash('Tarea completada exitosamente', 'success')
        else:
            flash('Error al completar la tarea', 'error')

    except Exception as e:
        logger.error(f"Error completando tarea {tarea_id}: {str(e)}")
        flash(f'Error: {str(e)}', 'error')

    return redirect(url_for('comercial.tareas_comerciales'))

# Endpoint to create pending budget tasks
@comercial_bp.route('/tareas/crear-presupuestos-pendientes', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL])
def crear_tareas_presupuestos_pendientes():
    """Crear tareas automáticas para proyectos pendientes de presupuesto"""
    try:
        resultado = comercial_service.crear_tareas_presupuesto_pendientes(current_user.id)

        if resultado['success']:
            flash(resultado['message'], 'success')
        else:
            flash(f"Error al crear tareas: {resultado.get('error', 'Error desconocido')}", 'error')

        return redirect(url_for('comercial.tareas_comerciales'))

    except Exception as e:
        logger.error(f"Error en endpoint crear tareas presupuesto: {str(e)}")
        flash('Error interno al crear tareas de presupuesto', 'error')
        return redirect(url_for('comercial.tareas_comerciales'))


# Commercial planning routes
@comercial_bp.route('/planificacion')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def planificacion_comercial():
    """Planificación comercial - Vista de matriz mensual"""
    try:
        # Get filters
        año = request.args.get('año', type=int) or datetime.now().year
        mes_inicio = request.args.get('mes_inicio', type=int) or 1
        cliente_id = request.args.get('cliente_id', type=int)
        estado_filter = request.args.get('estados', 'todos')  # todos, presupuestado, adjudicado
        curve_type = request.args.get('curve_type', 'general')  # Default to 'general' curve

        planning_data = comercial_service.get_planificacion_comercial(
            año=año,
            mes_inicio=mes_inicio,
            cliente_id=cliente_id,
            estado_filter=estado_filter,
            curve_type=curve_type
        )

        # Add curve selection data for the template
        planning_data['available_curves'] = revenue_service.get_available_curves()
        planning_data['selected_curve'] = curve_type

        return render_template('comercial/planificacion.html', calendar=calendar, **planning_data)

    except Exception as e:
        logger.error(f'Error al cargar planificación comercial: {str(e)}')
        flash(f'Error al cargar planificación comercial: {str(e)}', 'error')
        return redirect(url_for('comercial.lista_vendedores'))


@comercial_bp.route('/objetivos')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def objetivos_mensuales():
    """Gestión de objetivos mensuales"""
    try:
        año = request.args.get('año', type=int) or datetime.now().year
        objetivos_data = comercial_service.get_objetivos_mensuales(año)

        return render_template('comercial/objetivos.html', **objetivos_data)

    except Exception as e:
        logger.error(f'Error al cargar objetivos mensuales: {str(e)}')
        flash(f'Error al cargar objetivos: {str(e)}', 'error')
        return redirect(url_for('comercial.lista_vendedores'))


@comercial_bp.route('/objetivos/actualizar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL])
def actualizar_objetivos():
    """Actualizar objetivos mensuales"""
    try:
        año = request.form.get('año', type=int)
        objetivos_data = []

        for mes in range(1, 13):
            objetivo_total = request.form.get(f'objetivo_total_{mes}')

            if objetivo_total:
                # Para mantener compatibilidad, dividimos el objetivo total entre provisión e instalación
                # Se puede ajustar la proporción según necesidades del negocio
                objetivo_total_decimal = Decimal(objetivo_total)
                # Asignamos 70% a provisión y 30% a instalación como proporción estándar
                objetivo_provision = objetivo_total_decimal * Decimal('0.7')
                objetivo_instalacion = objetivo_total_decimal * Decimal('0.3')

                objetivos_data.append({
                    'mes': mes,
                    'objetivo_provision': str(objetivo_provision),
                    'objetivo_instalacion': str(objetivo_instalacion)
                })

        success = comercial_service.actualizar_objetivos_mensuales(año, objetivos_data, current_user.id)

        if success:
            flash('Objetivos actualizados exitosamente', 'success')
        else:
            flash('Error al actualizar objetivos', 'error')

    except Exception as e:
        logger.error(f'Error al actualizar objetivos: {str(e)}')
        flash(f'Error: {str(e)}', 'error')

    año = request.form.get('año', type=int) or datetime.now().year
    return redirect(url_for('comercial.objetivos_mensuales', año=año))


# API routes for AJAX calls
@comercial_bp.route('/api/proyecto/<int:proyecto_id>/crear-tarea', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def api_crear_tarea(proyecto_id):
    """API para crear una nueva tarea comercial"""
    try:
        data = request.get_json()
        tarea_data = {
            'proyecto_id': proyecto_id,
            'vendedor_id': data.get('vendedor_id'),
            'titulo': data.get('titulo'),
            'descripcion': data.get('descripcion'),
            'fecha_limite': data.get('fecha_limite')
        }

        tarea = comercial_service.crear_tarea_comercial(tarea_data, current_user.id)

        if tarea:
            return jsonify({
                'success': True,
                'message': 'Tarea creada exitosamente',
                'tarea_id': tarea.id
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Error al crear la tarea'
            }), 400

    except Exception as e:
        logger.error(f"Error en API crear tarea para proyecto {proyecto_id}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@comercial_bp.route('/api/planificacion/<int:year>/datos')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def api_planificacion_datos(year):
    """API para obtener datos de planificación por año"""
    try:
        cliente_id = request.args.get('cliente_id', type=int)
        estado_filter = request.args.get('estados', 'todos')

        data = comercial_service.get_planificacion_comercial(
            año=year,
            cliente_id=cliente_id,
            estado_filter=estado_filter
        )

        return jsonify({
            'success': True,
            'data': {
                'matriz': data['matriz'],
                'totales_mes': data['totales_mes'],
                'proyectos_count': len(data['proyectos'])
            }
        })

    except Exception as e:
        logger.error(f"Error en API obtener datos planificación para año {year}: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500

# API endpoint to create pending budget tasks
@comercial_bp.route('/api/tareas/crear-presupuestos-pendientes', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL])
def api_crear_tareas_presupuestos_pendientes():
    """API endpoint para crear tareas automáticas de presupuesto"""
    try:
        resultado = comercial_service.crear_tareas_presupuesto_pendientes(current_user.id)
        return jsonify(resultado)

    except Exception as e:
        logger.error(f"Error en API crear tareas presupuesto: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'tareas_creadas': 0,
            'tareas_existentes': 0
        }), 500

# Revenue Management Routes
@comercial_bp.route('/revenue-management')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def revenue_management():
    """Revenue Management - Vista principal"""
    try:
        # Get filters
        año = request.args.get('año', type=int) or datetime.now().year

        # Get real planning data from comercial service including all project states
        planning_data = comercial_service.get_planificacion_comercial(año=año, estado_filter='todos')

        # Get KPIs from revenue service
        kpis = revenue_service.calculate_kpis(año)

        # Get break even curves for chart
        be_curve_general = revenue_service.get_break_even_curve('general')
        be_curve_constructoras = revenue_service.get_break_even_curve('constructoras')
        available_curves = revenue_service.get_available_curves()

        # Prepare monthly data with recommendations
        monthly_data = []
        for mes in range(1, 13):
            # Use the correct key format from planning data (año-mes)
            mes_key = f"{año}-{mes:02d}"
            mes_data = planning_data['matriz'].get(mes_key, {})
            # Get objective for this month using both possible keys
            objetivo_mes = planning_data['objetivos'].get(mes_key) or planning_data['objetivos'].get(mes)

            # Calculate values
            valor_provision = float(mes_data.get('valor_provision', 0))
            valor_instalacion = float(mes_data.get('valor_instalacion', 0))
            total_ventas = valor_provision + valor_instalacion
            margen_ponderado = float(mes_data.get('margen_ponderado', 0))

            # Calculate objective values
            objetivo_total = 0
            if objetivo_mes:
                objetivo_provision = float(objetivo_mes.objetivo_provision or 0)
                objetivo_instalacion = float(objetivo_mes.objetivo_instalacion or 0)
                objetivo_total = objetivo_provision + objetivo_instalacion

            # Calculate percentage and status
            porcentaje_objetivo = (total_ventas / objetivo_total * 100) if objetivo_total > 0 else 0

            # Determine status
            if porcentaje_objetivo >= 100:
                estado = 'VERDE'
            elif porcentaje_objetivo >= 80:
                estado = 'AMARILLO'
            else:
                estado = 'ROJO'

            # Generate recommendations
            recomendacion = revenue_service.get_recommendations(
                gap_venta=objetivo_total - total_ventas,
                margen_real_pct=margen_ponderado,
                margen_objetivo_pct=75  # Default BE margin
            )

            # Convert project objects to serializable dictionaries
            proyectos_serializables = []
            for proyecto_data in mes_data.get('proyectos', []):
                if 'proyecto' in proyecto_data and hasattr(proyecto_data['proyecto'], 'cliente'):
                    proyecto = proyecto_data['proyecto']
                    proyectos_serializables.append({
                        'proyecto': {
                            'id': proyecto.id,
                            'nombre': proyecto.nombre,
                            'cliente': {
                                'nombre': proyecto.cliente.nombre
                            },
                            'estado_comercial': {
                                'value': proyecto.estado_comercial.value
                            }
                        },
                        'valor_provision_mes': float(proyecto_data.get('valor_provision_mes', 0)),
                        'valor_instalacion_mes': float(proyecto_data.get('valor_instalacion_mes', 0))
                    })

            monthly_data.append({
                'mes': mes,
                'mes_nombre': calendar.month_name[mes],
                'num_proyectos': len(mes_data.get('proyectos', [])),
                'total_ventas': total_ventas,
                'valor_provision': valor_provision,
                'valor_instalacion': valor_instalacion,
                'margen_ponderado': margen_ponderado,
                'objetivo_total': objetivo_total,
                'porcentaje_objetivo': porcentaje_objetivo,
                'estado': estado,
                'recomendacion': recomendacion,
                'proyectos': proyectos_serializables
            })

        return render_template('comercial/revenue_management.html',
                             año=año,
                             monthly_data=monthly_data,
                             planning_data=planning_data,
                             kpis=kpis,
                             be_curve_general=be_curve_general,
                             be_curve_constructoras=be_curve_constructoras,
                             available_curves=available_curves)

    except Exception as e:
        logger.error(f'Error al cargar Revenue Management: {str(e)}')
        flash(f'Error al cargar Revenue Management: {str(e)}', 'error')
        return redirect(url_for('comercial.lista_vendedores'))


@comercial_bp.route('/api/revenue/meses')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def api_revenue_meses():
    """API: Get monthly revenue data"""
    try:
        año = request.args.get('año', type=int) or datetime.now().year

        monthly_data = revenue_service.get_monthly_data(año)
        return jsonify({
            'success': True,
            'data': monthly_data
        })

    except Exception as e:
        logger.error(f"Error en API obtener datos mensuales de revenue: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@comercial_bp.route('/api/revenue/mes', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def api_revenue_update_mes():
    """API: Update or create monthly objective"""
    try:
        data = request.get_json()

        required_fields = ['año', 'mes']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Campo requerido: {field}'
                }), 400

        objetivo = revenue_service.update_monthly_objective(
            año=data['año'],
            mes=data['mes'],
            data=data
        )

        return jsonify({
            'success': True,
            'message': 'Objetivo mensual actualizado',
            'id': objetivo.id
        })

    except Exception as e:
        logger.error(f"Error en API actualizar objetivo mensual de revenue: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@comercial_bp.route('/api/revenue/simular', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def api_revenue_simular():
    """API: Simulate revenue scenario"""
    try:
        data = request.get_json()

        # Get parameters with defaults
        adjudicado_base = float(data.get('adjudicado_base', 0))
        adjudicado_extra = float(data.get('adjudicado_extra', 0))
        margen_sim_pct = float(data.get('margen_sim_pct', 30))
        buffer_pp = float(data.get('buffer_pp', 2.0))
        utilidad_objetivo_clp = float(data.get('utilidad_objetivo_clp', 0))
        curve_type = data.get('curve_type', 'general')
        curve_buffer_pct = float(data.get('curve_buffer_pct', 0.0))

        resultado = revenue_service.simulate_scenario(
            adjudicado_base=adjudicado_base,
            adjudicado_extra=adjudicado_extra,
            margen_sim_pct=margen_sim_pct,
            buffer_pp=buffer_pp,
            utilidad_objetivo_clp=utilidad_objetivo_clp,
            curve_type=curve_type,
            curve_buffer_pct=curve_buffer_pct
        )

        return jsonify({
            'success': True,
            'data': resultado
        })

    except Exception as e:
        logger.error(f"Error en API simular escenario de revenue: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@comercial_bp.route('/api/revenue/calcular-proyectos/<int:anio>/<int:mes>', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def api_revenue_calcular_proyectos(anio, mes):
    """API: Calculate and update revenue data from real projects for a specific month"""
    try:
        # Calcular datos reales desde proyectos
        real_adjudicado = revenue_service.calculate_real_adjudicado_from_projects(anio, mes)
        real_presupuesto = revenue_service.calculate_real_presupuesto_from_projects(anio, mes)
        real_margen = revenue_service.calculate_real_margins_from_projects(anio, mes)

        # Update or create the monthly objective with real data
        data = {
            'presupuesto_facturacion': real_presupuesto,
            'adjudicado_facturacion': real_adjudicado,
            'margen_real_pct': real_margen
        }

        # Buscar o crear objetivo mensual
        objetivo = (db.session.query(ObjetivoMensual)
                   .filter_by(año=anio, mes=mes)
                   .first())

        if not objetivo:
            objetivo = ObjetivoMensual()
            objetivo.año = anio
            objetivo.mes = mes
            objetivo.created_by = current_user.id
            db.session.add(objetivo)

        objetivo.presupuesto_facturacion = Decimal(real_presupuesto) if real_presupuesto else None
        objetivo.adjudicado_facturacion = Decimal(real_adjudicado) if real_adjudicado else None
        objetivo.margen_real_pct = Decimal(real_margen) if real_margen else None

        db.session.commit()

        return jsonify({
            'success': True,
            'message': f'Datos calculados desde proyectos reales para {calendar.month_name[mes]} {anio}',
            'data': {
                'presupuesto_facturacion': real_presupuesto,
                'adjudicado_facturacion': real_adjudicado,
                'margen_real_pct': real_margen,
                'objetivo_id': objetivo.id
            }
        })

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error en API calcular proyectos de revenue para {mes}/{anio}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@comercial_bp.route('/api/revenue/calcular-proyectos/<int:anio>', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def api_revenue_calcular_proyectos_año(anio):
    """API: Calculate and update revenue data from real projects for entire year"""
    try:
        updated_months = []
        errors = []

        for mes in range(1, 13):
            try:
                # Calculate real data from projects
                real_adjudicado = revenue_service.calculate_real_adjudicado_from_projects(anio, mes)
                real_presupuesto = revenue_service.calculate_real_presupuesto_from_projects(anio, mes)
                real_margen = revenue_service.calculate_real_margins_from_projects(anio, mes)

                # Only update if there's real data
                if real_adjudicado > 0 or real_presupuesto > 0:
                    data = {
                        'presupuesto_facturacion': real_presupuesto,
                        'adjudicado_facturacion': real_adjudicado,
                        'margen_real_pct': real_margen
                    }

                    objetivo = revenue_service.update_monthly_objective(anio, mes, data)
                    updated_months.append({
                        'mes': mes,
                        'mes_nombre': calendar.month_name[mes],
                        'presupuesto': real_presupuesto,
                        'adjudicado': real_adjudicado,
                        'margen': real_margen
                    })

            except Exception as e:
                errors.append(f"Error en {calendar.month_name[mes]}: {str(e)}")

        return jsonify({
            'success': True,
            'message': f'Datos calculados desde proyectos reales para {len(updated_months)} meses',
            'updated_months': updated_months,
            'errors': errors
        })

    except Exception as e:
        logger.error(f"Error en API calcular proyectos de revenue para todo el año {anio}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@comercial_bp.route('/api/vendedor/<string:vendedor_id>/comisiones/<int:anio>')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.FINANZAS])
def api_vendedor_comisiones_detalle(vendedor_id, anio):
    """API: Get detailed commission data for a salesperson"""
    try:
        # Get commission details
        comisiones_data = comercial_service._calcular_comisiones_mensuales(vendedor_id, anio)

        # Get commission configuration
        from services.configuraciones_service import ConfiguracionesService
        config_service = ConfiguracionesService()
        comision_config = config_service.get_comision_vendedor(vendedor_id)

        # Get vendedor info
        vendedor = db.session.get(User, vendedor_id)

        return jsonify({
            'success': True,
            'data': {
                'vendedor': {
                    'id': vendedor.id,
                    'nombre': vendedor.nombre_completo,
                    'email': vendedor.email
                },
                'configuracion': {
                    'comision_provision_pct': float(comision_config.comision_provision_pct) if comision_config else 3.0,
                    'comision_instalacion_pct': float(comision_config.comision_instalacion_pct) if comision_config else 3.0
                },
                'comisiones_mensuales': comisiones_data,
                'resumen': {
                    'total_provision': sum(m['comision_provision'] for m in comisiones_data),
                    'total_instalacion': sum(m['comision_instalacion'] for m in comisiones_data),
                    'total_general': sum(m['comision_total'] for m in comisiones_data),
                    'meses_con_comisiones': len([m for m in comisiones_data if m['comision_total'] > 0]),
                    'proyectos_totales': sum(m['proyectos_adjudicados'] for m in comisiones_data)
                }
            }
        })

    except Exception as e:
        logger.error(f"Error en API obtener detalle comisiones vendedor {vendedor_id} año {anio}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500