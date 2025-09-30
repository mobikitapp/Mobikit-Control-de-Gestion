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
from services.configuraciones_service import ConfiguracionesService
from services.productividad_service import ProductividadService
from utils.auth import require_role

# Create blueprint
planificacion_operacional_bp = Blueprint('planificacion_operacional', __name__)

@planificacion_operacional_bp.route('/')
@planificacion_operacional_bp.route('/matriz')
@login_required
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES)
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


@planificacion_operacional_bp.route('/prioridades')
@login_required  
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
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


@planificacion_operacional_bp.route('/productividad-real')
@login_required
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def productividad_real():
    """Template de Productividad Real - Análisis de tableros/día con gráficos de dispersión"""
    try:
        from datetime import timedelta

        # Obtener filtros de la request
        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')
        tipo_proyecto = request.args.get('tipo_proyecto', 'TODAS')
        area_filtro = request.args.get('area', 'todas')
        estado_of = request.args.get('estado_of', 'completadas')

        # Fechas por defecto (últimos 3 meses)
        if not fecha_inicio_str:
            fecha_inicio = date.today() - timedelta(days=90)
        else:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()

        if not fecha_fin_str:
            fecha_fin = date.today()
        else:
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()

        # Construir filtros
        filtros = {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'tipo_proyecto': tipo_proyecto if tipo_proyecto != 'TODAS' else None,
            'area': area_filtro if area_filtro != 'todas' else None,
            'estado_of': estado_of
        }

        # Obtener datos de productividad
        service = ProductividadService()
        datos_productividad = service.get_productividad_real(filtros)

        # Preparar datos para el template
        template_data = {
            'datos_productividad': datos_productividad,
            'filtros_aplicados': {
                'fecha_inicio': fecha_inicio.isoformat(),
                'fecha_fin': fecha_fin.isoformat(),
                'tipo_proyecto': tipo_proyecto,
                'area_filtro': area_filtro,
                'estado_of': estado_of
            },
            'tipos_proyecto': ['TODAS', 'SOCIAL', 'ESTANDAR', 'ESPECIAL'],
            'areas_disponibles': ['todas', 'fabrica', 'embalaje'],
            'estados_of': ['completadas', 'en_proceso', 'todas']
        }

        return render_template('planificacion_operacional/productividad_real.html', **template_data)

    except Exception as e:
        flash(f'Error al cargar análisis de productividad: {str(e)}', 'error')
        return redirect(url_for('planificacion_operacional.matriz_operacional'))


@planificacion_operacional_bp.route('/api/scatter-data')
@login_required
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def api_scatter_data():
    """API endpoint para datos de gráficos de dispersión"""
    try:
        from datetime import timedelta

        # Obtener filtros
        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')
        tipo_proyecto = request.args.get('tipo_proyecto')
        area_filtro = request.args.get('area')
        estado_of = request.args.get('estado_of', 'completadas')

        # Fechas por defecto
        if not fecha_inicio_str:
            fecha_inicio = date.today() - timedelta(days=90)
        else:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()

        if not fecha_fin_str:
            fecha_fin = date.today()
        else:
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()

        filtros = {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'tipo_proyecto': tipo_proyecto if tipo_proyecto != 'TODAS' else None,
            'area': area_filtro if area_filtro != 'todas' else None,
            'estado_of': estado_of
        }

        # Obtener datos
        service = ProductividadService()
        datos_productividad = service.get_productividad_real(filtros)

        return jsonify({
            'success': True,
            'datos_scatter': datos_productividad.get('datos_scatter', {}),
            'total_ofs': datos_productividad.get('total_ofs', 0)
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@planificacion_operacional_bp.route('/api/regression-analysis')
@login_required
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def api_regression_analysis():
    """API endpoint para análisis de regresión y estadísticas"""
    try:
        from datetime import timedelta

        # Obtener filtros
        fecha_inicio_str = request.args.get('fecha_inicio')
        fecha_fin_str = request.args.get('fecha_fin')
        tipo_proyecto = request.args.get('tipo_proyecto')
        estado_of = request.args.get('estado_of', 'completadas')

        # Fechas por defecto
        if not fecha_inicio_str:
            fecha_inicio = date.today() - timedelta(days=90)
        else:
            fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()

        if not fecha_fin_str:
            fecha_fin = date.today()
        else:
            fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()

        filtros = {
            'fecha_inicio': fecha_inicio,
            'fecha_fin': fecha_fin,
            'tipo_proyecto': tipo_proyecto if tipo_proyecto != 'TODAS' else None,
            'estado_of': estado_of
        }

        # Obtener datos
        service = ProductividadService()
        datos_productividad = service.get_productividad_real(filtros)

        return jsonify({
            'success': True,
            'analisis_estadistico': datos_productividad.get('analisis_estadistico', {}),
            'outliers': datos_productividad.get('outliers', []),
            'metricas_por_tipo': datos_productividad.get('metricas_por_tipo', {}),
            'metricas_por_area': datos_productividad.get('metricas_por_area', {})
        })

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@planificacion_operacional_bp.route('/api/actualizar-fechas-of', methods=['POST'])
@login_required
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES)
def actualizar_configuracion():
    """Actualizar factores de conversión, tiempo y capacidad"""
    try:
        service = PlanificacionOperacionalService()

        # Get form data for new project-type based factors
        factores_data = {}

        # Define operational fields first
        operational_fields = [
            'turnos_por_dia', 'horas_por_turno', 'dias_laborables_mes', 'oee',
            'horizonte_planificacion', 'umbral_sobrecarga',
            'factor_horas_extra', 'max_subcontrato', 'mejora_oee_objetivo'
        ]

        # Process conversion factors
        conversion_fields = [
            'factor_social_tablero', 'factor_estandar_tablero', 'factor_especial_tablero',
            'area_tablero_estandar', 'factor_desperdicio',
            'factor_tiempo_fabrica_social', 'factor_tiempo_embalaje_social',
            'factor_tiempo_fabrica_estandar', 'factor_tiempo_embalaje_estandar',
            'factor_tiempo_fabrica_especial', 'factor_tiempo_embalaje_especial',
            'capacidad_maxima_tableros_mes', 'capacidad_maxima_tableros_semana',
            'horas_disponibles_mes', 'horas_disponibles_semana',
            'horas_por_tablero_social', 'horas_por_tablero_estandar', 'horas_por_tablero_especial'
        ]

        for field in conversion_fields:
            value = request.form.get(field)
            if value is not None and value != '':
                if field in ['capacidad_maxima_tableros_mes', 'capacidad_maxima_tableros_semana', 
                           'horas_disponibles_mes', 'horas_disponibles_semana']:
                    factores_data[field] = int(value)
                else:
                    factores_data[field] = float(value)

        # Add operational parameters to factors_data
        for field in operational_fields:
            value = request.form.get(field)
            if value is not None and value != '':
                if field in ['turnos_por_dia', 'dias_laborables_mes', 
                           'horizonte_planificacion', 'umbral_sobrecarga', 'max_subcontrato']:
                    factores_data[field] = int(value)
                else:
                    factores_data[field] = float(value)

        # Process operational parameters
        from services.configuraciones_service import ConfiguracionesService
        config_service = ConfiguracionesService()

        parametros_operacionales = {}

        for field in operational_fields:
            value = request.form.get(field)
            if value is not None and value != '':
                if field in ['numero_maquinas', 'turnos_por_dia', 'dias_laborables_mes', 
                           'horizonte_planificacion', 'umbral_sobrecarga', 'max_subcontrato']:
                    parametros_operacionales[field] = int(value)
                else:
                    parametros_operacionales[field] = float(value)

        print(f"Datos recibidos del formulario: {factores_data}")

        # Update both conversion factors and operational parameters
        success_factors = service.actualizar_factores_conversion(factores_data, current_user.id)
        success_params = True

        if parametros_operacionales:
            success_params = config_service.actualizar_parametros_operacionales(parametros_operacionales, current_user.id)

        if success_factors and success_params:
            flash('Parámetros operacionales actualizados exitosamente', 'success')
        elif success_factors:
            flash('Factores actualizados exitosamente, pero algunos parámetros operacionales no se pudieron actualizar', 'warning')
        elif success_params:
            flash('Parámetros operacionales actualizados exitosamente, pero algunos factores no se pudieron actualizar', 'warning')
        else:
            flash('Error al actualizar parámetros operacionales', 'error')

    except Exception as e:
        print(f"Error en actualizar_configuracion: {e}")
        flash(f'Error: {str(e)}', 'error')

    return redirect(url_for('planificacion_operacional.configuracion_conversion'))

@planificacion_operacional_bp.route('/api/analisis-capacidad/<int:year>')
@login_required
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def analisis_capacidad_api(year):
    """API para obtener datos de análisis de capacidad y productividad"""
    try:
        service = PlanificacionOperacionalService()
        analisis = service.get_analisis_capacidad(año=year, vista='mensual')
        return jsonify(analisis)

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})


@planificacion_operacional_bp.route('/detalle-proyecto/<int:proyecto_id>')
@login_required
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def capacidad_produccion():
    """Análisis estratégico de capacidad de producción"""
    try:
        from services.configuraciones_service import ConfiguracionesService
        service = PlanificacionOperacionalService()

        # Get filters
        año = request.args.get('año', type=int) or datetime.now().year
        vista = request.args.get('vista', default='estrategico')  # estrategico, mensual, semanal
        horizonte_meses = request.args.get('horizonte', type=int) or 6

        modo_rolling = request.args.get('modo_rolling', default='mensual')

        # Get strategic capacity analysis data
        if vista == 'estrategico':
            # Validate filter compatibility - allow full horizon for weekly mode
            # Weekly mode will internally ensure minimum 12 weeks
                
            # New strategic capacity planning data
            try:
                # Calculate rolling plan based on modo_rolling parameter
                rolling_plan_data = service.calcular_rolling_plan_con_backlog(año, horizonte_meses, modo_rolling)
                
                if modo_rolling == 'semanal':
                    demanda_jerarquica_data = service.calcular_demanda_semanal_jerarquica(año, horizonte_meses)
                else:
                    demanda_jerarquica_data = service.calcular_demanda_mensual_jerarquica(año, horizonte_meses)
                
                resumen_capacidad_data = service.get_resumen_capacidad_estrategica()
                escenarios_data = ConfiguracionesService().get_escenarios_deficit()
            except Exception as e:
                print(f"Error calculando datos estratégicos: {e}")
                import traceback
                traceback.print_exc()
                if modo_rolling == 'semanal':
                    rolling_plan_data = {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}
                    demanda_jerarquica_data = {'demanda_por_semana': {}}
                else:
                    rolling_plan_data = {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}
                    demanda_jerarquica_data = {'demanda_por_mes': {}}
                resumen_capacidad_data = {}
                escenarios_data = {}

            data = {
                'año': año,
                'vista': vista,
                'horizonte_meses': horizonte_meses,
                'modo_rolling': modo_rolling,
                'resumen_capacidad': resumen_capacidad_data,
                'demanda_jerarquica': demanda_jerarquica_data,
                'rolling_plan': rolling_plan_data,
                'escenarios_deficit': escenarios_data,
                # Add empty capacidad for template compatibility
                'capacidad': {}
            }
        elif vista == 'semanal': # Handle legacy weekly view
            try:
                # Calculate weekly rolling plan using legacy method
                rolling_plan_data = service._calcular_rolling_plan_semanal(año, horizonte_meses)
                demanda_jerarquica_data = service.calcular_demanda_semanal_jerarquica(año, horizonte_meses)
                resumen_capacidad_data = service.get_resumen_capacidad_estrategica()
                escenarios_data = ConfiguracionesService().get_escenarios_deficit()
            except Exception as e:
                print(f"Error calculando datos semanales: {e}")
                rolling_plan_data = {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}
                demanda_jerarquica_data = {'demanda_por_semana': {}}
                resumen_capacidad_data = {}
                escenarios_data = {}

            data = {
                'año': año,
                'vista': vista,
                'horizonte_meses': horizonte_meses,
                'modo_rolling': 'semanal',
                'resumen_capacidad': resumen_capacidad_data,
                'demanda_jerarquica': demanda_jerarquica_data,
                'rolling_plan': rolling_plan_data,
                'escenarios_deficit': escenarios_data
            }

        else:
            # Legacy capacity analysis for backward compatibility
            data = service.get_analisis_capacidad(año=año, vista=vista)
            data['horizonte_meses'] = horizonte_meses  # Ensure this is always available
            data['modo_rolling'] = vista # Pass the current view as mode
            
            # Ensure resumen exists for template compatibility
            if 'resumen' not in data:
                data['resumen'] = {
                    'total_tableros_año': data.get('total_tableros_año', 0),
                    'total_horas_año': data.get('total_horas_año', 0),
                    'promedio_capacidad_porcentaje': data.get('promedio_capacidad_porcentaje', 0),
                    'meses_sobrecargados': data.get('meses_sobrecargados', 0)
                }


        return render_template('planificacion_operacional/capacidad.html', calendar=calendar, **data)

    except Exception as e:
        flash(f'Error al cargar análisis de capacidad: {str(e)}', 'error')
        return redirect(url_for('planificacion_operacional.matriz_operacional'))


# API routes for AJAX calls
@planificacion_operacional_bp.route('/api/calcular-tableros', methods=['POST'])
@login_required
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def api_calcular_tableros():
    """API para calcular tableros en tiempo real"""
    try:
        service = PlanificacionOperacionalService()

        data = request.get_json()
        monto_provision = data.get('monto_provision', 0)
        tipo_proyecto = data.get('tipo_proyecto', 'ESTANDAR')
        margen_venta_provision = data.get('margen_venta_provision')

        # Calculate boards
        resultado = service.calcular_tableros_aproximados(
            monto_provision=monto_provision,
            tipo_proyecto=tipo_proyecto,
            margen_venta_provision=margen_venta_provision
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
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


@planificacion_operacional_bp.route('/api/capacidad_estrategica')
@login_required
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def api_capacidad_estrategica():
    """API endpoint para obtener cálculos de capacidad estratégica"""
    try:
        service = PlanificacionOperacionalService()
        resumen = service.get_resumen_capacidad_estrategica()
        return jsonify(resumen)
    except Exception as e:
        return jsonify({'error': str(e)}), 500