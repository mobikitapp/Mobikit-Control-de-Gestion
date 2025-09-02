from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import current_user, login_required
from sqlalchemy import and_, or_, func, extract
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import calendar

from app import db
from models import (
    Proyecto, Cliente, User, TareaComercial, ObjetivoMensual,
    EstadoComercial, RolUsuario
)
from services.comercial_service import ComercialService
from services.revenue_service import RevenueService
from utils.auth import role_required

# Create blueprint
comercial_bp = Blueprint('comercial', __name__)

# Sales center routes
@comercial_bp.route('/')
@comercial_bp.route('/centro-vendedores')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def centro_vendedores():
    """Centro de vendedores - Vista principal del área comercial"""
    try:
        service = ComercialService()
        
        # Get filters from request
        cliente_id = request.args.get('cliente_id', type=int)
        vendedor_id = request.args.get('vendedor_id')
        estado_comercial = request.args.get('estado_comercial')
        
        # Get data for the sales center
        data = service.get_centro_vendedores_data(
            current_user_id=current_user.id,
            cliente_id=cliente_id,
            vendedor_id=vendedor_id,
            estado_comercial=estado_comercial
        )
        
        return render_template('comercial/centro_vendedores.html', **data)
        
    except Exception as e:
        flash(f'Error al cargar centro de vendedores: {str(e)}', 'error')
        return redirect(url_for('index'))


@comercial_bp.route('/vendedores')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def lista_vendedores():
    """Lista de vendedores con estadísticas"""
    try:
        service = ComercialService()
        vendedores_stats = service.get_vendedores_estadisticas()
        
        return render_template('comercial/vendedores.html', 
                             vendedores=vendedores_stats)
        
    except Exception as e:
        flash(f'Error al cargar vendedores: {str(e)}', 'error')
        return redirect(url_for('comercial.centro_vendedores'))


@comercial_bp.route('/vendedor/<string:vendedor_id>')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def vendedor_detalle(vendedor_id):
    """Detalle de un vendedor específico"""
    try:
        service = ComercialService()
        
        vendedor_data = service.get_vendedor_detalle(vendedor_id)
        if not vendedor_data:
            flash('Vendedor no encontrado', 'error')
            return redirect(url_for('comercial.lista_vendedores'))
        
        return render_template('comercial/vendedor_detalle.html', **vendedor_data)
        
    except Exception as e:
        flash(f'Error al cargar detalle del vendedor: {str(e)}', 'error')
        return redirect(url_for('comercial.lista_vendedores'))


# Project commercial management
@comercial_bp.route('/proyecto/<int:proyecto_id>/comercial')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def proyecto_comercial(proyecto_id):
    """Gestión comercial de un proyecto específico"""
    try:
        service = ComercialService()
        proyecto_data = service.get_proyecto_comercial_data(proyecto_id)
        
        if not proyecto_data:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('comercial.centro_vendedores'))
        
        return render_template('comercial/proyecto_comercial.html', **proyecto_data)
        
    except Exception as e:
        flash(f'Error al cargar datos comerciales del proyecto: {str(e)}', 'error')
        return redirect(url_for('comercial.centro_vendedores'))


@comercial_bp.route('/proyecto/<int:proyecto_id>/comercial/actualizar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def actualizar_comercial_proyecto(proyecto_id):
    """Actualizar información comercial de un proyecto"""
    try:
        service = ComercialService()
        
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
        
        success = service.actualizar_comercial_proyecto(proyecto_id, data, current_user.id)
        
        if success:
            flash('Información comercial actualizada exitosamente', 'success')
        else:
            flash('Error al actualizar información comercial', 'error')
        
        return redirect(url_for('comercial.proyecto_comercial', proyecto_id=proyecto_id))
        
    except Exception as e:
        flash(f'Error al actualizar: {str(e)}', 'error')
        return redirect(url_for('comercial.proyecto_comercial', proyecto_id=proyecto_id))


# Commercial tasks management
@comercial_bp.route('/tareas')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def tareas_comerciales():
    """Lista de tareas comerciales"""
    try:
        service = ComercialService()
        
        vendedor_id = request.args.get('vendedor_id')
        estado = request.args.get('estado')  # 'pendientes', 'completadas', 'todas'
        
        tareas_data = service.get_tareas_comerciales(
            vendedor_id=vendedor_id,
            estado=estado
        )
        
        return render_template('comercial/tareas.html', **tareas_data)
        
    except Exception as e:
        flash(f'Error al cargar tareas: {str(e)}', 'error')
        return redirect(url_for('comercial.centro_vendedores'))


@comercial_bp.route('/tarea/<int:tarea_id>/completar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def completar_tarea(tarea_id):
    """Marcar una tarea como completada"""
    try:
        service = ComercialService()
        
        notas = request.form.get('notas', '')
        success = service.completar_tarea(tarea_id, current_user.id, notas)
        
        if success:
            flash('Tarea completada exitosamente', 'success')
        else:
            flash('Error al completar la tarea', 'error')
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('comercial.tareas_comerciales'))


# Commercial planning routes
@comercial_bp.route('/planificacion')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def planificacion_comercial():
    """Planificación comercial - Vista de matriz mensual"""
    try:
        service = ComercialService()
        
        # Get filters
        año = request.args.get('año', type=int) or datetime.now().year
        cliente_id = request.args.get('cliente_id', type=int)
        estado_filter = request.args.get('estados', 'todos')  # todos, presupuestado, adjudicado
        
        planning_data = service.get_planificacion_comercial(
            año=año,
            cliente_id=cliente_id,
            estado_filter=estado_filter
        )
        
        return render_template('comercial/planificacion.html', **planning_data)
        
    except Exception as e:
        flash(f'Error al cargar planificación comercial: {str(e)}', 'error')
        return redirect(url_for('comercial.centro_vendedores'))


@comercial_bp.route('/objetivos')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def objetivos_mensuales():
    """Gestión de objetivos mensuales"""
    try:
        service = ComercialService()
        
        año = request.args.get('año', type=int) or datetime.now().year
        objetivos_data = service.get_objetivos_mensuales(año)
        
        return render_template('comercial/objetivos.html', **objetivos_data)
        
    except Exception as e:
        flash(f'Error al cargar objetivos: {str(e)}', 'error')
        return redirect(url_for('comercial.centro_vendedores'))


@comercial_bp.route('/objetivos/actualizar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS])
def actualizar_objetivos():
    """Actualizar objetivos mensuales"""
    try:
        service = ComercialService()
        
        año = request.form.get('año', type=int)
        objetivos_data = []
        
        for mes in range(1, 13):
            objetivo_provision = request.form.get(f'objetivo_provision_{mes}')
            objetivo_instalacion = request.form.get(f'objetivo_instalacion_{mes}')
            
            if objetivo_provision or objetivo_instalacion:
                objetivos_data.append({
                    'mes': mes,
                    'objetivo_provision': objetivo_provision,
                    'objetivo_instalacion': objetivo_instalacion
                })
        
        success = service.actualizar_objetivos_mensuales(año, objetivos_data, current_user.id)
        
        if success:
            flash('Objetivos actualizados exitosamente', 'success')
        else:
            flash('Error al actualizar objetivos', 'error')
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    año = request.form.get('año', type=int) or datetime.now().year
    return redirect(url_for('comercial.objetivos_mensuales', año=año))


# API routes for AJAX calls
@comercial_bp.route('/api/proyecto/<int:proyecto_id>/crear-tarea', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def api_crear_tarea(proyecto_id):
    """API para crear una nueva tarea comercial"""
    try:
        service = ComercialService()
        
        data = request.get_json()
        tarea_data = {
            'proyecto_id': proyecto_id,
            'vendedor_id': data.get('vendedor_id'),
            'titulo': data.get('titulo'),
            'descripcion': data.get('descripcion'),
            'fecha_limite': data.get('fecha_limite')
        }
        
        tarea = service.crear_tarea_comercial(tarea_data, current_user.id)
        
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
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@comercial_bp.route('/api/planificacion/<int:year>/datos')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def api_planificacion_datos(year):
    """API para obtener datos de planificación por año"""
    try:
        service = ComercialService()
        
        cliente_id = request.args.get('cliente_id', type=int)
        estado_filter = request.args.get('estados', 'todos')
        
        data = service.get_planificacion_comercial(
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
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


# Revenue Management Routes
@comercial_bp.route('/revenue-management')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def revenue_management():
    """Revenue Management - Vista principal"""
    try:
        service = RevenueService()
        
        # Get filters
        año = request.args.get('año', type=int) or datetime.now().year
        
        # Get monthly data and KPIs
        monthly_data = service.get_monthly_data(año)
        kpis = service.calculate_kpis(año)
        
        # Get break even curve for chart
        be_curve = service.get_break_even_curve()
        
        return render_template('comercial/revenue_management.html',
                             año=año,
                             monthly_data=monthly_data,
                             kpis=kpis,
                             be_curve=be_curve)
        
    except Exception as e:
        flash(f'Error al cargar Revenue Management: {str(e)}', 'error')
        return redirect(url_for('comercial.centro_vendedores'))


@comercial_bp.route('/api/revenue/meses')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def api_revenue_meses():
    """API: Get monthly revenue data"""
    try:
        service = RevenueService()
        año = request.args.get('año', type=int) or datetime.now().year
        
        monthly_data = service.get_monthly_data(año)
        return jsonify({
            'success': True,
            'data': monthly_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@comercial_bp.route('/api/revenue/mes', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def api_revenue_update_mes():
    """API: Update or create monthly objective"""
    try:
        service = RevenueService()
        data = request.get_json()
        
        required_fields = ['año', 'mes']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'success': False,
                    'error': f'Campo requerido: {field}'
                }), 400
        
        objetivo = service.update_monthly_objective(
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
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@comercial_bp.route('/api/revenue/simular', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES])
def api_revenue_simular():
    """API: Simulate revenue scenario"""
    try:
        service = RevenueService()
        data = request.get_json()
        
        # Get parameters with defaults
        adjudicado_base = float(data.get('adjudicado_base', 0))
        adjudicado_extra = float(data.get('adjudicado_extra', 0))
        margen_sim_pct = float(data.get('margen_sim_pct', 30))
        buffer_pp = float(data.get('buffer_pp', 2.0))
        utilidad_objetivo_clp = float(data.get('utilidad_objetivo_clp', 0))
        
        resultado = service.simulate_scenario(
            adjudicado_base=adjudicado_base,
            adjudicado_extra=adjudicado_extra,
            margen_sim_pct=margen_sim_pct,
            buffer_pp=buffer_pp,
            utilidad_objetivo_clp=utilidad_objetivo_clp
        )
        
        return jsonify({
            'success': True,
            'data': resultado
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500