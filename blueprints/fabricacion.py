from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user, login_required
from pydantic import ValidationError
from app import db
from replit_auth import require_login, require_role
from models import RolUsuario
from services.fabricacion_service import FabricacionService
from services.proyectos_service import ProyectosService
from services.contratos_service import ContratosService
from services.clientes_service import ClientesService
from services.user_service import UserService
from services.areas_service import AreasService  # Import added
from schemas.fabricacion import (OrdenFabricacionCreate, OrdenFabricacionUpdate, 
                                OrdenFabricacionSearchFilters)
import logging

logger = logging.getLogger(__name__)

fabricacion_bp = Blueprint('fabricacion', __name__)
fabricacion_service = FabricacionService()
proyectos_service = ProyectosService()
contratos_service = ContratosService()
clientes_service = ClientesService()
user_service = UserService()
areas_service = AreasService() # Instance created

@fabricacion_bp.route('/')
@require_login
def index():
    """Lista de órdenes de fabricación con filtros"""
    try:
        # Get search parameters with proper defaults
        filters_data = {
            'page': request.args.get('page', 1, type=int),
            'per_page': request.args.get('per_page', 20, type=int)
        }

        # Add optional filters only if they exist and are valid
        if request.args.get('proyecto_id'):
            try:
                filters_data['proyecto_id'] = int(request.args.get('proyecto_id'))
            except (ValueError, TypeError):
                pass

        if request.args.get('contrato_id'):
            try:
                filters_data['contrato_id'] = int(request.args.get('contrato_id'))
            except (ValueError, TypeError):
                pass

        if request.args.get('area_id'):
            try:
                filters_data['area_id'] = int(request.args.get('area_id'))
            except (ValueError, TypeError):
                pass

        if request.args.get('estado_id'):
            try:
                filters_data['estado_id'] = int(request.args.get('estado_id'))
            except (ValueError, TypeError):
                pass

        if request.args.get('codigo', '').strip():
            filters_data['codigo'] = request.args.get('codigo').strip()

        if request.args.get('responsable', '').strip():
            filters_data['responsable'] = request.args.get('responsable').strip()

        if request.args.get('fecha_planificada_desde', '').strip():
            filters_data['fecha_planificada_desde'] = request.args.get('fecha_planificada_desde').strip()

        if request.args.get('fecha_planificada_hasta', '').strip():
            filters_data['fecha_planificada_hasta'] = request.args.get('fecha_planificada_hasta').strip()

        # Validate filters
        filters = OrdenFabricacionSearchFilters(**filters_data)

        # Search OFs
        ofs, total_count = fabricacion_service.search_ordenes_fabricacion(filters)

        # Add days remaining calculation
        from datetime import date
        today = date.today()
        for of in ofs:
            if of.fecha_entrega_fabrica:
                entrega_date = of.fecha_entrega_fabrica.date() if hasattr(of.fecha_entrega_fabrica, 'date') else of.fecha_entrega_fabrica
                of.days_remaining = (entrega_date - today).days
            else:
                of.days_remaining = None

        # Get data for filter dropdowns
        clientes = clientes_service.get_active_clientes()

        # Calculate pagination
        total_pages = (total_count + filters.per_page - 1) // filters.per_page
        has_prev = filters.page > 1
        has_next = filters.page < total_pages

        return render_template('fabricacion/index.html',
                             ofs=ofs,
                             clientes=clientes,
                             filters=filters,
                             total_count=total_count,
                             total_pages=total_pages,
                             has_prev=has_prev,
                             has_next=has_next)

    except ValidationError as e:
        flash('Filtros inválidos', 'error')
        return redirect(url_for('fabricacion.index'))
    except Exception as e:
        logger.error(f"Error en lista de OFs: {str(e)}")
        flash('Error al cargar órdenes de fabricación', 'error')
        return redirect(url_for('index'))

@fabricacion_bp.route('/nueva')
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def nueva():
    """Formulario para nueva orden de fabricación"""
    try:
        clientes = clientes_service.get_active_clientes()
        users = user_service.get_active_users()
        return render_template('fabricacion/form.html', 
                             of=None, 
                             clientes=clientes,
                             users=users,
                             title="Nueva Orden de Fabricación")
    except Exception as e:
        logger.error(f"Error cargando formulario nueva OF: {str(e)}")
        flash('Error al cargar formulario', 'error')
        return redirect(url_for('fabricacion.index'))

@fabricacion_bp.route('/crear', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def crear():
    """Crear nueva orden de fabricación"""
    try:
        # Get form data
        form_data = request.form.to_dict()

        # Generic orders don't have items
        form_data['items'] = []

        # Validate form data
        of_data = OrdenFabricacionCreate(**form_data)

        # Create OF
        of = fabricacion_service.create_orden_fabricacion(of_data.dict(), current_user.id)

        flash(f'Orden de Fabricación {of.codigo} creada exitosamente', 'success')
        return redirect(url_for('fabricacion.detalle', of_id=of.id))

    except ValidationError as e:
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
        clientes = clientes_service.get_active_clientes()
        return render_template('fabricacion/form.html', 
                             of=None, 
                             clientes=clientes,
                             title="Nueva Orden de Fabricación")
    except Exception as e:
        logger.error(f"Error creando OF: {str(e)}")
        flash('Error al crear orden de fabricación', 'error')
        clientes = clientes_service.get_active_clientes()
        return render_template('fabricacion/form.html', 
                             of=None, 
                             clientes=clientes,
                             title="Nueva Orden de Fabricación")

@fabricacion_bp.route('/<int:of_id>')
@require_login
def detalle(of_id):
    """Detalle de orden de fabricación"""
    try:
        of = fabricacion_service.get_orden_fabricacion_by_id(of_id)
        if not of:
            flash('Orden de Fabricación no encontrada', 'error')
            return redirect(url_for('fabricacion.index'))

        # Get complete progress history for timeline
        from repositories.areas_repository import OrdenAreaProgresoRepository
        progreso_repo = OrdenAreaProgresoRepository()
        historial_progreso = progreso_repo.get_progress_history(of_id)

        # Import areas service for action descriptions
        # from services.areas_service import AreasService # Already imported
        # areas_service = AreasService() # Already instantiated

        return render_template('fabricacion/detalle.html', 
                             of=of, 
                             historial_progreso=historial_progreso,
                             areas_service=areas_service)

    except Exception as e:
        logger.error(f"Error obteniendo OF {of_id}: {str(e)}")
        flash('Error al cargar orden de fabricación', 'error')
        return redirect(url_for('fabricacion.index'))

@fabricacion_bp.route('/<int:of_id>/editar')
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def editar(of_id):
    """Formulario de edición de orden de fabricación"""
    try:
        of = fabricacion_service.get_orden_fabricacion_by_id(of_id)
        if not of:
            flash('Orden de Fabricación no encontrada', 'error')
            return redirect(url_for('fabricacion.index'))

        clientes = clientes_service.get_active_clientes()
        users = user_service.get_active_users()

        # Get area states if admin and OF has area
        estados_area = []
        if current_user.rol.value == 'admin':
            from repositories.areas_repository import AreasRepository
            areas_repo = AreasRepository()
            if of.area_actual:
                # Get states for current area
                estados_area = areas_repo.get_estados_by_area(of.area_actual.id)
            else:
                # If no current area, get states for first area (Pendientes de Fabricación)
                from models import TipoArea
                primera_area = areas_repo.get_area_by_tipo(TipoArea.PENDIENTES_FABRICACION)
                if primera_area:
                    estados_area = areas_repo.get_estados_by_area(primera_area.id)

        return render_template('fabricacion/form.html', 
                             of=of,
                             clientes=clientes,
                             users=users,
                             estados_area=estados_area,
                             title=f"Editar OF - {of.codigo}")

    except Exception as e:
        logger.error(f"Error obteniendo OF para editar {of_id}: {str(e)}")
        flash('Error al cargar orden de fabricación', 'error')
        return redirect(url_for('fabricacion.index'))

@fabricacion_bp.route('/<int:of_id>/actualizar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def actualizar(of_id):
    """Actualizar orden de fabricación existente"""
    try:
        of = fabricacion_service.get_orden_fabricacion_by_id(of_id)
        if not of:
            flash('Orden de Fabricación no encontrada', 'error')
            return redirect(url_for('fabricacion.index'))

        form_data = request.form.to_dict()

        # Only allow admin to change status
        if current_user.rol.value != 'admin' and 'estado_actual_id' in form_data:
            del form_data['estado_actual_id']

        # Validate form data
        update_data = OrdenFabricacionUpdate(**form_data)

        # Update OF
        of_actualizada = fabricacion_service.update_orden_fabricacion(of_id, update_data.dict(exclude_unset=True))

        flash(f'Orden de Fabricación {of_actualizada.codigo} actualizada exitosamente', 'success')
        return redirect(url_for('fabricacion.detalle', of_id=of_id))

    except ValidationError as e:
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')

        # Reload data for the form in case of error
        clientes = clientes_service.get_active_clientes()
        users = user_service.get_active_users()

        # Get area states if admin and OF has area
        estados_area = []
        if current_user.rol.value == 'admin':
            from repositories.areas_repository import AreasRepository
            areas_repo = AreasRepository()
            if of.area_actual:
                # Get states for current area
                estados_area = areas_repo.get_estados_by_area(of.area_actual.id)
            else:
                # If no current area, get states for first area (Pendientes de Fabricación)
                from models import TipoArea
                primera_area = areas_repo.get_area_by_tipo(TipoArea.PENDIENTES_FABRICACION)
                if primera_area:
                    estados_area = areas_repo.get_estados_by_area(primera_area.id)

        return render_template('fabricacion/form.html', 
                             of=of,
                             clientes=clientes,
                             users=users,
                             estados_area=estados_area,
                             title=f"Editar OF - {of.codigo}")
    except Exception as e:
        logger.error(f"Error actualizando OF {of_id}: {str(e)}")
        flash('Error al actualizar orden de fabricación', 'error')
        return redirect(url_for('fabricacion.detalle', of_id=of_id))

@fabricacion_bp.route('/<int:of_id>/cambiar-estado', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def cambiar_estado(of_id):
    """Cambiar estado dentro del área actual"""
    try:
        nuevo_estado_id = request.form.get('nuevo_estado_id', type=int)
        responsable_id = request.form.get('responsable_id')
        notas = request.form.get('notas')

        if not nuevo_estado_id:
            flash('Debe seleccionar un estado', 'error')
            return redirect(url_for('fabricacion.detalle', of_id=of_id))

        success = fabricacion_service.change_estado_area(
            of_id, nuevo_estado_id, responsable_id=responsable_id, notas=notas
        )
        if success:
            flash('Estado actualizado exitosamente', 'success')
        else:
            flash('Error al cambiar estado', 'error')

    except Exception as e:
        logger.error(f"Error cambiando estado de OF {of_id}: {str(e)}")
        flash(f'Error al cambiar estado: {str(e)}', 'error')

    return redirect(url_for('fabricacion.detalle', of_id=of_id))

@fabricacion_bp.route('/<int:of_id>/avanzar-area', methods=['POST'])
@require_login
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def avanzar_area(of_id):
    """Avanzar orden a siguiente área"""
    try:
        notas = request.form.get('notas', '')

        # Advance to next area
        new_progress = areas_service.advance_to_next_area(
            orden_fabricacion_id=of_id,
            created_by=current_user.id,
            responsable_id=current_user.id,
            notas=notas
        )

        flash('Orden avanzada exitosamente', 'success')

    except ValueError as e:
        flash(f'Error: {str(e)}', 'danger')
    except Exception as e:
        logger.error(f"Error avanzando área para OF {of_id}: {str(e)}")
        flash('Error al avanzar la orden', 'danger')

    return redirect(url_for('fabricacion.index'))

@fabricacion_bp.route('/<int:of_id>/archivar', methods=['POST'])
@login_required
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.LOGISTICA)
def archivar_orden(of_id):
    """Archivar orden despachada"""
    try:
        # Verify order exists and is in dispatched state
        orden = fabricacion_service.get_orden_fabricacion_by_id(of_id)
        if not orden:
            flash('Orden no encontrada', 'danger')
            return redirect(url_for('fabricacion.index'))

        # Check if order is in DESPACHO area with DESPACHADO state
        progreso_actual = orden.area_progreso_actual
        if not progreso_actual or progreso_actual.area.tipo.value != 'despacho':
            flash('Solo se pueden archivar órdenes en el área de Despacho', 'danger')
            return redirect(url_for('fabricacion.index'))

        # Archive the order
        success = areas_service.archive_dispatch(of_id)

        if success:
            flash(f'Orden {orden.codigo} archivada exitosamente', 'success')
        else:
            flash('Error al archivar la orden', 'danger')

    except Exception as e:
        logger.error(f"Error archivando orden {of_id}: {str(e)}")
        flash('Error al archivar la orden', 'danger')

    return redirect(url_for('fabricacion.index'))


@fabricacion_bp.route('/archivos')
@login_required
def archivos():
    """Vista de órdenes archivadas"""
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # Get filter parameters
        cliente_id = request.args.get('cliente_id', type=int)
        proyecto_id = request.args.get('proyecto_id', type=int)
        codigo = request.args.get('codigo', '').strip()

        # Get archived orders with filters
        archived_orders, total_count = fabricacion_service.get_archived_orders(
            page=page,
            per_page=per_page,
            cliente_id=cliente_id,
            proyecto_id=proyecto_id,
            codigo=codigo
        )

        # Get clients for filter
        clientes = clientes_service.get_active_clientes()

        # Calculate pagination info
        total_pages = (total_count + per_page - 1) // per_page
        has_prev = page > 1
        has_next = page < total_pages

        return render_template(
            'fabricacion/archivos.html',
            archived_orders=archived_orders,
            total_count=total_count,
            total_pages=total_pages,
            has_prev=has_prev,
            has_next=has_next,
            page=page,
            per_page=per_page,
            clientes=clientes,
            filters={
                'cliente_id': cliente_id,
                'proyecto_id': proyecto_id,
                'codigo': codigo
            }
        )

    except Exception as e:
        logger.error(f"Error cargando archivos: {str(e)}")
        flash('Error cargando órdenes archivadas', 'danger')
        return redirect(url_for('fabricacion.index'))


@fabricacion_bp.route('/<int:of_id>/eliminar', methods=['POST'])
@require_role(RolUsuario.ADMIN)
def eliminar(of_id):
    """Eliminar orden de fabricación"""
    try:
        success = fabricacion_service.delete_orden_fabricacion(of_id)
        if success:
            flash('Orden de Fabricación eliminada exitosamente', 'success')
        else:
            flash('Error al eliminar orden de fabricación', 'error')

    except Exception as e:
        logger.error(f"Error eliminando OF {of_id}: {str(e)}")
        flash('Error al eliminar orden de fabricación', 'error')

    return redirect(url_for('fabricacion.index'))

@fabricacion_bp.route('/api/by-proyecto/<int:proyecto_id>')
@require_login
def api_by_proyecto(proyecto_id):
    """API endpoint para obtener OFs por proyecto"""
    try:
        ofs = fabricacion_service.get_ordenes_by_proyecto(proyecto_id)
        return jsonify([{
            'id': of.id,
            'codigo': of.codigo,
            'area': of.area_actual.nombre if of.area_actual else 'Sin área',
            'estado': of.estado_actual.nombre if of.estado_actual else 'Sin estado'
        } for of in ofs])

    except Exception as e:
        logger.error(f"Error en API OFs por proyecto: {str(e)}")
        return jsonify({'error': 'Error al cargar órdenes de fabricación'}), 500