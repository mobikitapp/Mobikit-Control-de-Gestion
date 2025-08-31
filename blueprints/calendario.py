from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import current_user, login_required
from datetime import datetime, timedelta
import calendar
from dateutil.relativedelta import relativedelta

from app import db
from models import EventoEntrega, Proyecto, Despacho, RolUsuario
from services.calendario_service import CalendarioService
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
        
        # Get calendar data
        data = service.get_calendario_mensual(year, month, current_user.id, current_user.rol)
        
        return render_template('calendario/vista_mensual.html', **data)
        
    except Exception as e:
        flash(f'Error al cargar calendario: {str(e)}', 'error')
        return redirect(url_for('index'))


@calendario_bp.route('/eventos')
@login_required
def lista_eventos():
    """Lista completa de eventos de entrega"""
    try:
        service = CalendarioService()
        
        # Get filters from request
        fecha_inicio = request.args.get('fecha_inicio')
        fecha_fin = request.args.get('fecha_fin')
        estado = request.args.get('estado')
        tipo_evento = request.args.get('tipo')
        
        # Convert date strings to datetime objects
        if fecha_inicio:
            try:
                fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            except ValueError:
                fecha_inicio = None
        
        if fecha_fin:
            try:
                fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
            except ValueError:
                fecha_fin = None
        
        # Get events data
        data = service.get_eventos_lista(
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
            estado=estado,
            tipo_evento=tipo_evento,
            usuario_id=current_user.id,
            rol_usuario=current_user.rol
        )
        
        return render_template('calendario/lista_eventos.html', **data)
        
    except Exception as e:
        flash(f'Error al cargar eventos: {str(e)}', 'error')
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


@calendario_bp.route('/nuevo-evento')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.VENTAS])
def nuevo_evento():
    """Formulario para crear nuevo evento de entrega"""
    try:
        service = CalendarioService()
        
        # Get projects available for events
        proyectos = service.get_proyectos_disponibles(current_user.id, current_user.rol)
        
        return render_template('calendario/evento_form.html', 
                             proyectos=proyectos, evento=None, accion='crear')
        
    except Exception as e:
        flash(f'Error al cargar formulario: {str(e)}', 'error')
        return redirect(url_for('calendario.vista_mensual'))


@calendario_bp.route('/nuevo-evento', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.VENTAS])
def crear_evento():
    """Crear nuevo evento de entrega"""
    try:
        service = CalendarioService()
        
        # Get form data
        datos_evento = {
            'proyecto_id': request.form.get('proyecto_id'),
            'titulo': request.form.get('titulo', '').strip(),
            'descripcion': request.form.get('descripcion', '').strip(),
            'fecha_evento': request.form.get('fecha_evento'),
            'hora_evento': request.form.get('hora_evento'),
            'tipo_evento': request.form.get('tipo_evento'),
            'prioridad': request.form.get('prioridad'),
            'recordatorio_dias': request.form.get('recordatorio_dias', type=int),
            'notas': request.form.get('notas', '').strip()
        }
        
        # Validate required fields
        if not all([datos_evento['titulo'], datos_evento['fecha_evento'], datos_evento['tipo_evento']]):
            flash('Título, fecha y tipo de evento son obligatorios', 'error')
            return redirect(url_for('calendario.nuevo_evento'))
        
        # Create event
        success, mensaje = service.crear_evento(datos_evento, current_user.id)
        
        if success:
            flash(f'Evento "{datos_evento["titulo"]}" creado exitosamente', 'success')
            return redirect(url_for('calendario.vista_mensual'))
        else:
            flash(f'Error al crear evento: {mensaje}', 'error')
            return redirect(url_for('calendario.nuevo_evento'))
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('calendario.vista_mensual'))


@calendario_bp.route('/evento/<evento_id>/editar')
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.VENTAS])
def editar_evento(evento_id):
    """Formulario para editar evento existente"""
    try:
        service = CalendarioService()
        
        # Get event data
        evento = service.get_evento_by_id(evento_id, current_user.id, current_user.rol)
        if not evento:
            flash('Evento no encontrado', 'error')
            return redirect(url_for('calendario.vista_mensual'))
        
        # Get projects available
        proyectos = service.get_proyectos_disponibles(current_user.id, current_user.rol)
        
        return render_template('calendario/evento_form.html',
                             proyectos=proyectos, evento=evento, accion='editar')
        
    except Exception as e:
        flash(f'Error al cargar evento: {str(e)}', 'error')
        return redirect(url_for('calendario.vista_mensual'))


@calendario_bp.route('/evento/<evento_id>/editar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.VENTAS])
def actualizar_evento(evento_id):
    """Actualizar evento existente"""
    try:
        service = CalendarioService()
        
        # Get form data
        datos_evento = {
            'proyecto_id': request.form.get('proyecto_id'),
            'titulo': request.form.get('titulo', '').strip(),
            'descripcion': request.form.get('descripcion', '').strip(),
            'fecha_evento': request.form.get('fecha_evento'),
            'hora_evento': request.form.get('hora_evento'),
            'tipo_evento': request.form.get('tipo_evento'),
            'prioridad': request.form.get('prioridad'),
            'recordatorio_dias': request.form.get('recordatorio_dias', type=int),
            'notas': request.form.get('notas', '').strip()
        }
        
        # Validate required fields
        if not all([datos_evento['titulo'], datos_evento['fecha_evento'], datos_evento['tipo_evento']]):
            flash('Título, fecha y tipo de evento son obligatorios', 'error')
            return redirect(url_for('calendario.editar_evento', evento_id=evento_id))
        
        # Update event
        success, mensaje = service.actualizar_evento(evento_id, datos_evento, current_user.id)
        
        if success:
            flash(f'Evento actualizado exitosamente', 'success')
            return redirect(url_for('calendario.detalle_evento', evento_id=evento_id))
        else:
            flash(f'Error al actualizar evento: {mensaje}', 'error')
            return redirect(url_for('calendario.editar_evento', evento_id=evento_id))
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('calendario.vista_mensual'))


@calendario_bp.route('/evento/<evento_id>/completar', methods=['POST'])
@login_required
@role_required([RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.VENTAS, RolUsuario.LOGISTICA])
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
    """Dashboard del calendario con resumen de eventos"""
    try:
        service = CalendarioService()
        
        # Get dashboard data
        data = service.get_calendario_dashboard(current_user.id, current_user.rol)
        
        return render_template('calendario/dashboard.html', **data)
        
    except Exception as e:
        flash(f'Error al cargar dashboard del calendario: {str(e)}', 'error')
        return redirect(url_for('index'))


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