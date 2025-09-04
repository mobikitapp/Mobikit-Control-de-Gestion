from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import current_user, login_required
from sqlalchemy import and_, or_, func, extract
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from decimal import Decimal
import calendar

from app import db
from models import (
    Proyecto, Cliente, User, OrdenFabricacion,
    EstadoComercial, RolUsuario
)
from services.planificacion_operacional_service import PlanificacionOperacionalService
from services.planificacion_prioridades_service import PlanificacionPrioridadesService
from utils.auth import role_required

# Create blueprint
planificacion_operacional_bp = Blueprint('planificacion_operacional', __name__)

@planificacion_operacional_bp.route('/')
@planificacion_operacional_bp.route('/matriz')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION])
def matriz_operacional():
    """Matriz de planificación operacional - Conversión de montos a tableros"""
    try:
        service = PlanificacionOperacionalService()
        
        # Get filters from request
        año = request.args.get('año', type=int) or datetime.now().year
        mes_inicio = request.args.get('mes_inicio', type=int) or 1
        mes_fin = request.args.get('mes_fin', type=int) or 12
        cliente_id = request.args.get('cliente_id', type=int)
        tipo_material = request.args.get('tipo_material', default='melamina')
        
        # Get operational planning data
        data = service.get_matriz_operacional(
            año=año,
            mes_inicio=mes_inicio,
            mes_fin=mes_fin,
            cliente_id=cliente_id,
            tipo_material=tipo_material
        )
        
        return render_template('planificacion_operacional/matriz.html', calendar=calendar, **data)
        
    except Exception as e:
        flash(f'Error al cargar matriz operacional: {str(e)}', 'error')
        return redirect(url_for('index'))


@planificacion_operacional_bp.route('/configuracion')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES])
def configuracion_conversion():
    """Configuración de factores de conversión"""
    try:
        service = PlanificacionOperacionalService()
        
        # Get current conversion factors
        factores = service.get_factores_conversion()
        
        return render_template('planificacion_operacional/configuracion.html', 
                             factores=factores, calendar=calendar)
        
    except Exception as e:
        flash(f'Error al cargar configuración: {str(e)}', 'error')
        return redirect(url_for('planificacion_operacional.matriz_operacional'))


@planificacion_operacional_bp.route('/planificacion-prioridades')
@login_required  
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION])
def planificacion_prioridades():
    """Planificación y Prioridades - Matriz tipo Gantt para gestión de cola de producción"""
    try:
        service = PlanificacionPrioridadesService()
        
        # Obtener datos de la matriz de planificación
        datos_matriz = service.get_matriz_planificacion_prioridades()
        
        return render_template('planificacion_operacional/planificacion_prioridades.html', 
                             calendar=calendar, **datos_matriz)
        
    except Exception as e:
        flash(f'Error al cargar planificación y prioridades: {str(e)}', 'error')
        return redirect(url_for('planificacion_operacional.matriz_operacional'))


@planificacion_operacional_bp.route('/api/actualizar-fechas-of', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION])
def actualizar_fechas_of():
    """API endpoint para actualizar fechas de una OF"""
    try:
        data = request.get_json()
        service = PlanificacionPrioridadesService()
        
        of_id = data.get('of_id')
        fecha_planificada = data.get('fecha_planificada')
        fecha_entrega_fabrica = data.get('fecha_entrega_fabrica')
        fecha_entrega_embalaje = data.get('fecha_entrega_embalaje')
        
        # Convertir fechas string a objetos date
        if fecha_planificada:
            fecha_planificada = datetime.strptime(fecha_planificada, '%Y-%m-%d').date()
        if fecha_entrega_fabrica:
            fecha_entrega_fabrica = datetime.strptime(fecha_entrega_fabrica, '%Y-%m-%d').date()
        if fecha_entrega_embalaje:
            fecha_entrega_embalaje = datetime.strptime(fecha_entrega_embalaje, '%Y-%m-%d').date()
        
        exito = service.actualizar_fechas_of(
            of_id=of_id,
            fecha_planificada=fecha_planificada,
            fecha_entrega_fabrica=fecha_entrega_fabrica,
            fecha_entrega_embalaje=fecha_entrega_embalaje
        )
        
        if exito:
            return jsonify({'success': True, 'message': 'Fechas actualizadas correctamente'})
        else:
            return jsonify({'success': False, 'message': 'Error al actualizar fechas'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})


@planificacion_operacional_bp.route('/api/actualizar-prioridad-of', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION])
def actualizar_prioridad_of():
    """API endpoint para actualizar prioridad de una OF"""
    try:
        from models import PrioridadOrden
        data = request.get_json()
        service = PlanificacionPrioridadesService()
        
        of_id = data.get('of_id')
        nueva_prioridad = data.get('prioridad')
        
        # Si viene como string "P5", extraer el número
        if isinstance(nueva_prioridad, str) and nueva_prioridad.startswith('P'):
            try:
                prioridad_numerica = int(nueva_prioridad[1:])
            except ValueError:
                return jsonify({'success': False, 'message': f'Formato de prioridad inválido: {nueva_prioridad}'})
        else:
            prioridad_numerica = int(nueva_prioridad)
        
        exito = service.actualizar_prioridad_of(of_id, prioridad_numerica)
        
        if exito:
            return jsonify({'success': True, 'message': 'Prioridad actualizada correctamente'})
        else:
            return jsonify({'success': False, 'message': 'Error al actualizar prioridad'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})


@planificacion_operacional_bp.route('/api/asignar-prioridades-automaticas', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION])
def asignar_prioridades_automaticas():
    """API para asignar prioridades automáticamente P1-P{total}"""
    try:
        service = PlanificacionPrioridadesService()
        resultado = service.asignar_prioridades_automaticas()
        return jsonify(resultado)
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@planificacion_operacional_bp.route('/api/rango-prioridades', methods=['GET'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION])
def rango_prioridades():
    """API para obtener el rango de prioridades disponible"""
    try:
        service = PlanificacionPrioridadesService()
        resultado = service.get_rango_prioridades_disponible()
        return jsonify(resultado)
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@planificacion_operacional_bp.route('/api/actualizar-prioridades-bodega/<int:of_id>', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION])
def actualizar_prioridades_bodega(of_id):
    """API para actualizar prioridades cuando una OF pasa a bodega"""
    try:
        service = PlanificacionPrioridadesService()
        resultado = service.actualizar_prioridades_al_pasar_bodega(of_id)
        return jsonify(resultado)
    
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@planificacion_operacional_bp.route('/configuracion/actualizar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES])
def actualizar_configuracion():
    """Actualizar factores de conversión"""
    try:
        service = PlanificacionOperacionalService()
        
        # Get form data
        factores_data = {
            'factor_melamina_m2': request.form.get('factor_melamina_m2', type=float),
            'factor_mdf_m2': request.form.get('factor_mdf_m2', type=float),
            'factor_madera_m2': request.form.get('factor_madera_m2', type=float),
            'area_tablero_estandar': request.form.get('area_tablero_estandar', type=float),
            'factor_desperdicio': request.form.get('factor_desperdicio', type=float),
        }
        
        success = service.actualizar_factores_conversion(factores_data, current_user.id)
        
        if success:
            flash('Factores de conversión actualizados exitosamente', 'success')
        else:
            flash('Error al actualizar factores de conversión', 'error')
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('planificacion_operacional.configuracion_conversion'))


@planificacion_operacional_bp.route('/detalle-proyecto/<int:proyecto_id>')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION])
def detalle_proyecto_operacional(proyecto_id):
    """Detalle operacional de un proyecto específico"""
    try:
        service = PlanificacionOperacionalService()
        
        # Get project operational details
        proyecto_data = service.get_detalle_proyecto_operacional(proyecto_id)
        
        if not proyecto_data:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('planificacion_operacional.matriz_operacional'))
        
        return render_template('planificacion_operacional/proyecto_detalle.html', 
                             calendar=calendar, **proyecto_data)
        
    except Exception as e:
        flash(f'Error al cargar detalle del proyecto: {str(e)}', 'error')
        return redirect(url_for('planificacion_operacional.matriz_operacional'))


@planificacion_operacional_bp.route('/capacidad-produccion')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION])
def capacidad_produccion():
    """Análisis de capacidad de producción"""
    try:
        service = PlanificacionOperacionalService()
        
        # Get filters
        año = request.args.get('año', type=int) or datetime.now().year
        vista = request.args.get('vista', default='mensual')  # mensual, semanal
        
        # Get capacity analysis
        data = service.get_analisis_capacidad(año=año, vista=vista)
        
        return render_template('planificacion_operacional/capacidad.html', calendar=calendar, **data)
        
    except Exception as e:
        flash(f'Error al cargar análisis de capacidad: {str(e)}', 'error')
        return redirect(url_for('planificacion_operacional.matriz_operacional'))


# API routes for AJAX calls
@planificacion_operacional_bp.route('/api/calcular-tableros', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION])
def api_calcular_tableros():
    """API para calcular tableros en tiempo real"""
    try:
        service = PlanificacionOperacionalService()
        
        data = request.get_json()
        monto_provision = data.get('monto_provision', 0)
        tipo_material = data.get('tipo_material', 'melamina')
        
        # Calculate boards
        resultado = service.calcular_tableros_aproximados(
            monto_provision=monto_provision,
            tipo_material=tipo_material
        )
        
        return jsonify({
            'success': True,
            'tableros_aproximados': resultado['tableros_aproximados'],
            'area_total_m2': resultado['area_total_m2'],
            'factor_usado': resultado['factor_usado'],
            'detalles': resultado['detalles']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@planificacion_operacional_bp.route('/api/matriz/<int:year>/datos')
@login_required  
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION])
def api_matriz_datos(year):
    """API para obtener datos de matriz operacional"""
    try:
        service = PlanificacionOperacionalService()
        
        mes_inicio = request.args.get('mes_inicio', type=int) or 1
        mes_fin = request.args.get('mes_fin', type=int) or 12
        cliente_id = request.args.get('cliente_id', type=int)
        tipo_material = request.args.get('tipo_material', default='melamina')
        
        data = service.get_matriz_operacional(
            año=year,
            mes_inicio=mes_inicio,
            mes_fin=mes_fin,
            cliente_id=cliente_id,
            tipo_material=tipo_material
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