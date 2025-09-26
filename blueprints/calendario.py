from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import current_user, login_required
from datetime import datetime, timedelta
import calendar
from dateutil.relativedelta import relativedelta
import pytz

from app import db
from models import EventoEntrega, Proyecto, Despacho, RolUsuario
from services.calendario_service import CalendarioService
from services.contrato_eventos_service import ContratoEventosService
from services.analisis_estrategico_service import AnalisisEstrategicoService
from utils.auth import role_required

# Create blueprint
calendario_bp = Blueprint('calendario', __name__)

@calendario_bp.route('/')
@calendario_bp.route('/vista-mensual')
@login_required
def vista_mensual():
    """Vista principal del calendario mensual"""
    try:
        service = CalendarioService()
        
        # Get month and year from query params
        year = request.args.get('year', type=int, default=datetime.now().year)
        month = request.args.get('month', type=int, default=datetime.now().month)
        
        # Validate month and year
        if month < 1 or month > 12:
            month = datetime.now().month
        if year < 2020 or year > 2030:
            year = datetime.now().year
        
        # Get filter parameters
        filtros_despachos = {
            'estado': request.args.get('estado'),
            'responsable_nombre': request.args.get('responsable_nombre'),
            'numero_despacho': request.args.get('numero_despacho'),
            'proyecto_id': request.args.get('proyecto_id', type=int),
            'fecha_desde': request.args.get('fecha_desde'),
            'fecha_hasta': request.args.get('fecha_hasta'),
            'con_ordenes': request.args.get('con_ordenes') is not None
        }
        # Remove None values
        filtros_despachos = {k: v for k, v in filtros_despachos.items() if v is not None and v != ''}
        
        # Check if strategic analysis mode is requested
        modo_estrategico = request.args.get('estrategico', default=False, type=bool)
        
        if modo_estrategico:
            # Use strategic analysis service
            service_estrategico = AnalisisEstrategicoService()
            data = service_estrategico.get_analisis_mensual(year, month, current_user.id, current_user.rol, filtros_despachos)
        else:
            # Use legacy calendar service
            data = service.get_calendario_mensual(year, month, current_user.id, current_user.rol, filtros_despachos)
        
        # Add current datetime for template
        now = datetime.now()
        data['now'] = now
        
        # Add filter information for template
        data['filtros_activos'] = filtros_despachos if filtros_despachos else None
        
        # Choose template based on analysis mode
        template = 'calendario/analisis_estrategico_mensual.html' if modo_estrategico else 'calendario/vista_mensual.html'
        return render_template(template, **data)
        
    except Exception as e:
        flash(f'Error al cargar calendario: {str(e)}', 'error')
        return redirect(url_for('index'))





@calendario_bp.route('/vista-semanal')
@login_required
def vista_semanal():
    """Vista semanal del calendario"""
    try:
        service = CalendarioService()
        
        # Get date parameters from query params
        year = request.args.get('year', type=int, default=datetime.now().year)
        month = request.args.get('month', type=int, default=datetime.now().month)
        day = request.args.get('day', type=int, default=datetime.now().day)
        
        # Validate parameters
        if month < 1 or month > 12:
            month = datetime.now().month
        if year < 2020 or year > 2030:
            year = datetime.now().year
        if day < 1 or day > 31:
            day = datetime.now().day
        
        # Get filter parameters for weekly view
        filtros_despachos = {
            'estado': request.args.get('estado'),
            'responsable_nombre': request.args.get('responsable_nombre'),
            'numero_despacho': request.args.get('numero_despacho'),
            'proyecto_id': request.args.get('proyecto_id', type=int),
            'fecha_desde': request.args.get('fecha_desde'),
            'fecha_hasta': request.args.get('fecha_hasta'),
            'con_ordenes': request.args.get('con_ordenes') is not None
        }
        # Remove None values
        filtros_despachos = {k: v for k, v in filtros_despachos.items() if v is not None and v != ''}
        
        # Check if strategic analysis mode is requested
        modo_estrategico = request.args.get('estrategico', default=False, type=bool)
        
        if modo_estrategico:
            # Use strategic analysis service
            service_estrategico = AnalisisEstrategicoService()
            data = service_estrategico.get_analisis_semanal(year, month, day, current_user.id, current_user.rol, filtros_despachos)
        else:
            # Use legacy calendar service
            data = service.get_calendario_semanal(year, month, day, current_user.id, current_user.rol, filtros_despachos)
        
        # Add current datetime for template
        now = datetime.now()
        data['now'] = now
        
        # Add filter information for template
        data['filtros_activos'] = filtros_despachos if filtros_despachos else None
        
        # Choose template based on analysis mode
        template = 'calendario/analisis_estrategico_semanal.html' if modo_estrategico else 'calendario/vista_semanal.html'
        return render_template(template, **data)
        
    except Exception as e:
        flash(f'Error al cargar vista semanal: {str(e)}', 'error')
        return redirect(url_for('calendario.vista_mensual'))


# Strategic Analysis Routes

@calendario_bp.route('/analisis-estrategico')
@calendario_bp.route('/analisis-estrategico/mensual')
@login_required
def analisis_estrategico_mensual():
    """Strategic monthly analysis view"""
    try:
        service = AnalisisEstrategicoService()
        
        # Get month and year from query params
        year = request.args.get('year', type=int, default=datetime.now().year)
        month = request.args.get('month', type=int, default=datetime.now().month)
        
        # Validate month and year
        if month < 1 or month > 12:
            month = datetime.now().month
        if year < 2020 or year > 2030:
            year = datetime.now().year
        
        # Get filter parameters
        filtros = {
            'estado': request.args.get('estado'),
            'responsable_nombre': request.args.get('responsable_nombre'),
            'numero_despacho': request.args.get('numero_despacho'),
            'proyecto_id': request.args.get('proyecto_id', type=int),
            'fecha_desde': request.args.get('fecha_desde'),
            'fecha_hasta': request.args.get('fecha_hasta'),
            'con_ordenes': request.args.get('con_ordenes') is not None
        }
        # Remove None values
        filtros = {k: v for k, v in filtros.items() if v is not None and v != ''}
        
        # Get strategic analysis data
        data = service.get_analisis_estrategico('mensual', year, month, None, current_user.id, current_user.rol, filtros)
        
        # Add current datetime for template
        data['now'] = datetime.now()
        data['filtros_activos'] = filtros if filtros else None
        
        return render_template('calendario/analisis_estrategico_mensual.html', **data)
        
    except Exception as e:
        flash(f'Error al cargar análisis estratégico mensual: {str(e)}', 'error')
        return redirect(url_for('calendario.vista_mensual'))

@calendario_bp.route('/analisis-estrategico/semanal')
@login_required
def analisis_estrategico_semanal():
    """Strategic weekly analysis view"""
    try:
        service = AnalisisEstrategicoService()
        
        # Get date parameters from query params
        year = request.args.get('year', type=int, default=datetime.now().year)
        month = request.args.get('month', type=int, default=datetime.now().month)
        day = request.args.get('day', type=int, default=datetime.now().day)
        
        # Validate parameters
        if month < 1 or month > 12:
            month = datetime.now().month
        if year < 2020 or year > 2030:
            year = datetime.now().year
        if day < 1 or day > 31:
            day = datetime.now().day
        
        # Get filter parameters
        filtros = {
            'estado': request.args.get('estado'),
            'responsable_nombre': request.args.get('responsable_nombre'),
            'numero_despacho': request.args.get('numero_despacho'),
            'proyecto_id': request.args.get('proyecto_id', type=int),
            'fecha_desde': request.args.get('fecha_desde'),
            'fecha_hasta': request.args.get('fecha_hasta'),
            'con_ordenes': request.args.get('con_ordenes') is not None
        }
        # Remove None values
        filtros = {k: v for k, v in filtros.items() if v is not None and v != ''}
        
        # Get strategic analysis data
        data = service.get_analisis_estrategico('semanal', year, month, day, current_user.id, current_user.rol, filtros)
        
        # Add current datetime for template
        data['now'] = datetime.now()
        data['filtros_activos'] = filtros if filtros else None
        
        return render_template('calendario/analisis_estrategico_semanal.html', **data)
        
    except Exception as e:
        flash(f'Error al cargar análisis estratégico semanal: {str(e)}', 'error')
        return redirect(url_for('calendario.vista_mensual'))

@calendario_bp.route('/vista-diaria')
@login_required
def vista_diaria():
    """Vista diaria del calendario enfocada en despachos"""
    try:
        service = CalendarioService()
        
        # Get date parameters from query params
        year = request.args.get('year', type=int, default=datetime.now().year)
        month = request.args.get('month', type=int, default=datetime.now().month)
        day = request.args.get('day', type=int, default=datetime.now().day)
        
        # Validate parameters
        if month < 1 or month > 12:
            month = datetime.now().month
        if year < 2020 or year > 2030:
            year = datetime.now().year
        
        # Get valid day range for the month
        import calendar as cal
        last_day_of_month = cal.monthrange(year, month)[1]
        if day < 1 or day > last_day_of_month:
            day = min(datetime.now().day, last_day_of_month)
        
        # Get filter parameters for daily view
        filtros_despachos = {
            'estado': request.args.get('estado'),
            'responsable_nombre': request.args.get('responsable_nombre'),
            'numero_despacho': request.args.get('numero_despacho'),
            'proyecto_id': request.args.get('proyecto_id', type=int),
            'fecha_desde': request.args.get('fecha_desde'),
            'fecha_hasta': request.args.get('fecha_hasta'),
            'con_ordenes': request.args.get('con_ordenes') is not None
        }
        # Remove None values
        filtros_despachos = {k: v for k, v in filtros_despachos.items() if v is not None and v != ''}
        
        # Get daily calendar data
        data = service.get_calendario_diario(year, month, day, current_user.id, current_user.rol, filtros_despachos)
        
        # Add current datetime for template
        now = datetime.now()
        data['now'] = now
        
        # Add filter information for template
        data['filtros_activos'] = filtros_despachos if filtros_despachos else None
        
        return render_template('calendario/vista_diaria.html', **data)
        
    except Exception as e:
        flash(f'Error al cargar vista diaria: {str(e)}', 'error')
        return redirect(url_for('calendario.vista_mensual'))


@calendario_bp.route('/evento/<evento_id>')
@login_required
def detalle_evento(evento_id):
    """Detalle de un evento específico"""
    try:
        service = CalendarioService()
        
        # Get event details
        evento = service.get_evento_by_id(evento_id, current_user.id, current_user.rol)
        if not evento:
            flash('Evento no encontrado', 'error')
            return redirect(url_for('calendario.vista_mensual'))
        
        return render_template('calendario/detalle_evento.html', evento=evento)
        
    except Exception as e:
        flash(f'Error al cargar evento: {str(e)}', 'error')
        return redirect(url_for('calendario.vista_mensual'))


# Rutas para crear eventos deshabilitadas
# @calendario_bp.route('/nuevo-evento')
# @login_required
# @role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.VENTAS])
# def nuevo_evento():
#     """Formulario para crear nuevo evento de entrega"""
#     flash('La creación de eventos está deshabilitada', 'warning')
#     return redirect(url_for('calendario.vista_mensual'))


# @calendario_bp.route('/nuevo-evento', methods=['POST'])
# @login_required
# @role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.VENTAS])
# def crear_evento():
#     """Crear nuevo evento de entrega"""
#     flash('La creación de eventos está deshabilitada', 'warning')
#     return redirect(url_for('calendario.vista_mensual'))


# Rutas para editar eventos deshabilitadas
# @calendario_bp.route('/evento/<evento_id>/editar')
# @login_required
# @role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.VENTAS])
# def editar_evento(evento_id):
#     """Formulario para editar evento existente"""
#     flash('La edición de eventos está deshabilitada', 'warning')
#     return redirect(url_for('calendario.detalle_evento', evento_id=evento_id))


# @calendario_bp.route('/evento/<evento_id>/editar', methods=['POST'])
# @login_required
# @role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.VENTAS])
# def actualizar_evento(evento_id):
#     """Actualizar evento existente"""
#     flash('La edición de eventos está deshabilitada', 'warning')
#     return redirect(url_for('calendario.detalle_evento', evento_id=evento_id))


@calendario_bp.route('/evento/<evento_id>/completar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.VENTAS, RolUsuario.LOGISTICA])
def completar_evento(evento_id):
    """Marcar evento como completado"""
    try:
        service = CalendarioService()
        
        # Complete event
        success, mensaje = service.completar_evento(evento_id, current_user.id)
        
        if success:
            flash(mensaje, 'success')
        else:
            flash(f'Error: {mensaje}', 'error')
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('calendario.detalle_evento', evento_id=evento_id))


@calendario_bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard del calendario centrado en entregas de contratos"""
    try:
        service = CalendarioService()
        contrato_service = ContratoEventosService()
        
        # Auto-generate events from contracts if needed
        contrato_service.generar_eventos_desde_contratos(current_user.id)
        
        # Get delivery-focused data
        entregas_proximas = contrato_service.get_entregas_proximas(dias=7)
        entregas_vencidas = contrato_service.get_entregas_vencidas()
        contratos_con_entregas = contrato_service.get_contratos_con_entregas_pendientes()
        
        # Get regular calendar data
        data = service.get_calendario_dashboard(current_user.id, current_user.rol)
        
        # Add delivery data to template context
        data.update({
            'entregas_proximas': entregas_proximas,
            'entregas_vencidas': entregas_vencidas,
            'contratos_con_entregas': contratos_con_entregas,
        })
        
        return render_template('calendario/dashboard.html', **data)
        
    except Exception as e:
        flash(f'Error al cargar dashboard del calendario: {str(e)}', 'error')
        return redirect(url_for('index'))





@calendario_bp.route('/contratos-con-entregas')
@login_required
def contratos_con_entregas():
    """Vista de contratos con fechas de entrega comprometidas"""
    try:
        contrato_service = ContratoEventosService()
        
        # Get contracts with delivery dates
        contratos = contrato_service.get_contratos_con_entregas_pendientes()
        
        # Get delivery events for these contracts
        entregas_proximas = contrato_service.get_entregas_proximas(dias=30)
        entregas_vencidas = contrato_service.get_entregas_vencidas()
        
        return render_template('calendario/contratos_entregas.html',
                             contratos=contratos,
                             entregas_proximas=entregas_proximas,
                             entregas_vencidas=entregas_vencidas)
                             
    except Exception as e:
        flash(f'Error al cargar contratos con entregas: {str(e)}', 'error')
        return redirect(url_for('calendario.dashboard'))


# API Routes for AJAX calls

@calendario_bp.route('/api/eventos/<int:year>/<int:month>')
@login_required
def api_eventos_mes(year, month):
    """API para obtener eventos de un mes específico"""
    try:
        service = CalendarioService()
        
        # Get events for the month
        eventos = service.get_eventos_mes(year, month, current_user.id, current_user.rol)
        
        return jsonify({
            'success': True,
            'eventos': eventos
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@calendario_bp.route('/api/evento/<evento_id>/toggle-recordatorio', methods=['POST'])
@login_required
def api_toggle_recordatorio(evento_id):
    """Toggle recordatorio de evento"""
    try:
        service = CalendarioService()
        
        # Toggle reminder
        success, mensaje = service.toggle_recordatorio(evento_id, current_user.id)
        
        return jsonify({
            'success': success,
            'message': mensaje
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500


@calendario_bp.route('/api/eventos-proximos')
@login_required
def api_eventos_proximos():
    """API para obtener eventos próximos (para widgets)"""
    try:
        service = CalendarioService()
        
        # Get upcoming events
        eventos = service.get_eventos_proximos(current_user.id, current_user.rol, dias=7)
        
        return jsonify({
            'success': True,
            'eventos': eventos
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        }), 500