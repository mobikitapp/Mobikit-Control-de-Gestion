from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, abort
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import logging

from services.areas_service import AreasService
from services.fabricacion_service import FabricacionService
from services.user_service import UserService
from repositories.areas_repository import AreasRepository
from utils.auth import admin_required, role_required
from utils.responses import success_response, error_response
from utils.validators import validate_not_empty
from models import User

logger = logging.getLogger(__name__)
areas_bp = Blueprint('areas', __name__, url_prefix='/areas')

areas_service = AreasService()
fabricacion_service = FabricacionService()
user_service = UserService()
areas_repo = AreasRepository()


@areas_bp.route('/dashboard')
@login_required
def dashboard():
    """Areas dashboard with all production areas"""
    try:
        # Get dashboard data
        dashboard_data = areas_service.get_areas_dashboard_data()
        users = User.query.filter_by(activo=True).all()

        # Ensure stats is always defined
        stats = dashboard_data.get('stats', {
            'total_active': 0,
            'overdue_count': 0,
            'area_counts': []
        })

        return render_template(
            'areas/dashboard.html',
            areas=dashboard_data.get('areas', []),
            stats=stats,
            users=users,
            moment_global=datetime,
            title='Dashboard de Áreas'
        )

    except Exception as e:
        logger.error(f"Error en dashboard de áreas: {str(e)}")
        flash('Error cargando el dashboard de áreas', 'error')

        # Return a safe fallback template with empty data
        return render_template(
            'areas/dashboard.html',
            areas=[],
            stats={
                'total_active': 0,
                'overdue_count': 0,
                'area_counts': []
            },
            users=User.query.filter_by(activo=True).all(),
            moment_global=datetime,
            title='Dashboard de Áreas'
        )


@areas_bp.route('/area/<int:area_id>')
@login_required
def area_detail(area_id):
    """Detailed view of a specific area"""
    try:
        area = areas_repo.get_area_by_id(area_id)
        if not area:
            abort(404)

        # Get orders in this area
        from repositories.areas_repository import OrdenAreaProgresoRepository
        progreso_repo = OrdenAreaProgresoRepository()
        orders_in_area = progreso_repo.get_orders_in_area(area_id)

        # Group by state
        states_data = []
        for estado in area.estados:
            orders_in_state = [o for o in orders_in_area if o.estado_id == estado.id]
            states_data.append({
                'estado': estado,
                'orders': orders_in_state,
                'count': len(orders_in_state)
            })

        return render_template(
            'areas/area_detail.html',
            area=area,
            states_data=states_data,
            total_orders=len(orders_in_area),
            title=f'Área: {area.nombre}'
        )

    except Exception as e:
        logger.error(f"Error obteniendo detalle de área: {str(e)}")
        flash('Error cargando detalles del área', 'error')
        return redirect(url_for('areas.dashboard'))


@areas_bp.route('/orden/<int:orden_id>/history')
@login_required
def orden_history(orden_id):
    """Show area transition history for an order"""
    try:
        # Verify order exists and user has access
        orden = fabricacion_service.get_orden_by_id(orden_id)
        if not orden:
            abort(404)

        # Get area history
        history = areas_service.get_orden_area_history(orden_id)

        return render_template(
            'areas/orden_history.html',
            orden=orden,
            history=history,
            title=f'Historial de Áreas - Orden {orden.codigo}'
        )

    except Exception as e:
        logger.error(f"Error obteniendo historial: {str(e)}")
        flash('Error cargando el historial', 'error')
        return redirect(url_for('areas.dashboard'))


@areas_bp.route('/mis-pendientes')
@login_required
def mis_pendientes():
    """Show orders assigned to current user"""
    try:
        orders = areas_service.get_my_pending_orders(current_user.id)

        return render_template(
            'areas/mis_pendientes.html',
            orders=orders,
            title='Mis Órdenes Pendientes'
        )

    except Exception as e:
        logger.error(f"Error obteniendo órdenes pendientes: {str(e)}")
        flash('Error cargando órdenes pendientes', 'error')
        return redirect(url_for('areas.dashboard'))


@areas_bp.route('/api/avanzar-estado-directo', methods=['POST'])
@login_required
def api_advance_state_directly():
    """API endpoint to advance state directly without modal"""
    try:
        data = request.get_json()
        orden_id = data.get('orden_id')
        area_id = data.get('area_id')

        if not orden_id or not area_id:
            return error_response("Orden ID y Área ID son requeridos")

        # Get current progress
        from repositories.areas_repository import OrdenAreaProgresoRepository
        progreso_repo = OrdenAreaProgresoRepository()
        current_progress = progreso_repo.get_current_progress(orden_id)

        if not current_progress:
            return error_response("Orden no encontrada en sistema de áreas")

        # Get area states to find next state
        area_estados = AreasRepository.get_estados_by_area(area_id)
        current_estado_order = current_progress.estado.orden_en_area
        
        # Find next state in sequence
        next_estado = None
        for estado in area_estados:
            if estado.orden_en_area == current_estado_order + 1:
                next_estado = estado
                break

        if not next_estado:
            return error_response("No hay siguiente estado disponible en esta área")

        # Change to next state
        updated_progress = areas_service.change_estado_in_area(
            orden_id=orden_id,
            nuevo_estado_id=next_estado.id,
            responsable_id=current_user.id
        )

        return success_response({
            'message': f'Estado avanzado a: {next_estado.nombre}',
            'nuevo_estado': next_estado.nombre
        })

    except Exception as e:
        logger.error(f"Error avanzando estado directamente: {str(e)}")
        return error_response(f"Error: {str(e)}")


@areas_bp.route('/api/change-estado', methods=['POST'])
@login_required
def api_change_estado():
    """API endpoint to change state within area"""
    try:
        data = request.get_json()

        # Validate required fields
        orden_id = data.get('orden_id')
        nuevo_estado_id = data.get('nuevo_estado_id')

        if not orden_id or not nuevo_estado_id:
            return error_response("Orden ID y Estado ID son requeridos")

        # Optional fields
        responsable_id = data.get('responsable_id')
        notas = data.get('notas')
        tiempo_estimado_horas = data.get('tiempo_estimado_horas')

        # Change state
        updated_progress = areas_service.change_estado_in_area(
            orden_fabricacion_id=orden_id,
            nuevo_estado_id=nuevo_estado_id,
            responsable_id=responsable_id,
            notas=notas,
            tiempo_estimado_horas=tiempo_estimado_horas
        )

        return success_response({
            'message': 'Estado actualizado exitosamente',
            'progress': {
                'id': updated_progress.id,
                'estado_nombre': updated_progress.estado.nombre,
                'area_nombre': updated_progress.area.nombre,
                'fecha_cambio': updated_progress.fecha_cambio_estado.isoformat()
            }
        })

    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        logger.error(f"Error cambiando estado: {str(e)}")
        return error_response("Error interno del servidor")


@areas_bp.route('/api/advance-area', methods=['POST'])
@login_required
def api_advance_area():
    """API endpoint to advance order to next area"""
    try:
        data = request.get_json()

        # Validate required fields
        orden_id = data.get('orden_id')
        if not orden_id:
            return error_response("Orden ID es requerido")

        # Optional fields
        responsable_id = data.get('responsable_id')
        notas = data.get('notas')

        # Advance to next area
        new_progress = areas_service.advance_to_next_area(
            orden_fabricacion_id=orden_id,
            created_by=current_user.id,
            responsable_id=responsable_id,
            notas=notas
        )

        return success_response({
            'message': f'Orden avanzada a {new_progress.area.nombre}',
            'progress': {
                'id': new_progress.id,
                'area_nombre': new_progress.area.nombre,
                'estado_nombre': new_progress.estado.nombre,
                'fecha_ingreso': new_progress.fecha_ingreso_area.isoformat()
            }
        })

    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        logger.error(f"Error avanzando área: {str(e)}")
        return error_response("Error interno del servidor")


@areas_bp.route('/api/archive-dispatch', methods=['POST'])
@login_required
@role_required(['admin', 'logistica'])
def api_archive_dispatch():
    """API endpoint to archive dispatched orders"""
    try:
        data = request.get_json()

        orden_id = data.get('orden_id')
        if not orden_id:
            return error_response("Orden ID es requerido")

        # Archive dispatch
        success = areas_service.archive_dispatch(orden_id)

        if success:
            return success_response({
                'message': 'Despacho archivado exitosamente'
            })
        else:
            return error_response("No se pudo archivar el despacho")

    except ValueError as e:
        return error_response(str(e))
    except Exception as e:
        logger.error(f"Error archivando despacho: {str(e)}")
        return error_response("Error interno del servidor")


@areas_bp.route('/api/assign-responsable', methods=['POST'])
@login_required
@role_required(['admin', 'operaciones', 'produccion'])
def api_assign_responsable():
    """API endpoint to assign responsible person to area state"""
    try:
        data = request.get_json()

        orden_id = data.get('orden_id')
        responsable_id = data.get('responsable_id')

        if not orden_id or not responsable_id:
            return error_response("Orden ID y Responsable ID son requeridos")

        # Verify user exists
        responsable = user_service.get_user_by_id(responsable_id)
        if not responsable:
            return error_response("Usuario responsable no encontrado")

        # Get current progress
        from repositories.areas_repository import OrdenAreaProgresoRepository
        progreso_repo = OrdenAreaProgresoRepository()
        current_progress = progreso_repo.get_current_progress(orden_id)

        if not current_progress:
            return error_response("Orden no encontrada en sistema de áreas")

        # Update responsible person
        updated_progress = progreso_repo.update_progress(
            current_progress,
            {'responsable_area': responsable_id}
        )

        from app import db
        db.session.commit()

        return success_response({
            'message': f'Responsable asignado: {responsable.nombre_completo}',
            'responsable_nombre': responsable.nombre_completo
        })

    except Exception as e:
        logger.error(f"Error asignando responsable: {str(e)}")
        return error_response("Error interno del servidor")


@areas_bp.route('/api/dashboard-stats')
@login_required
def api_dashboard_stats():
    """API endpoint for dashboard statistics (for refreshing)"""
    try:
        from repositories.areas_repository import OrdenAreaProgresoRepository
        progreso_repo = OrdenAreaProgresoRepository()
        stats = progreso_repo.get_dashboard_stats()

        return success_response(stats)

    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {str(e)}")
        return error_response("Error interno del servidor")


@areas_bp.route('/api/estados-by-area/<int:area_id>')
@login_required
def api_estados_by_area(area_id):
    """API endpoint to get states for a specific area"""
    try:
        estados = areas_repo.get_estados_by_area(area_id)

        return success_response([
            {
                'id': estado.id,
                'codigo': estado.codigo,
                'nombre': estado.nombre,
                'descripcion': estado.descripcion,
                'orden_en_area': estado.orden_en_area,
                'es_inicial': estado.es_inicial,
                'es_final': estado.es_final,
                'color_hex': estado.color_hex
            }
            for estado in estados
        ])

    except Exception as e:
        logger.error(f"Error obteniendo estados: {str(e)}")
        return error_response("Error interno del servidor")


# Form-based endpoints for non-JS browsers
@areas_bp.route('/orden/<int:orden_id>/cambiar-estado', methods=['GET', 'POST'])
@login_required
def cambiar_estado_form(orden_id):
    """Form-based state change"""
    try:
        # Get current progress
        from repositories.areas_repository import OrdenAreaProgresoRepository
        progreso_repo = OrdenAreaProgresoRepository()
        current_progress = progreso_repo.get_current_progress(orden_id)

        if not current_progress:
            flash('Orden no encontrada en sistema de áreas', 'error')
            return redirect(url_for('areas.dashboard'))

        # Get available states for current area
        estados = areas_repo.get_estados_by_area(current_progress.area_id)

        # Get users for responsable assignment
        users = user_service.get_active_users()

        if request.method == 'POST':
            nuevo_estado_id = request.form.get('nuevo_estado_id', type=int)
            responsable_id = request.form.get('responsable_id')
            notas = request.form.get('notas')
            tiempo_estimado = request.form.get('tiempo_estimado_horas', type=float)

            if not nuevo_estado_id:
                flash('Debe seleccionar un estado', 'error')
                return render_template(
                    'areas/cambiar_estado.html',
                    orden=current_progress.orden_fabricacion,
                    current_progress=current_progress,
                    estados=estados,
                    users=users
                )

            try:
                updated_progress = areas_service.change_estado_in_area(
                    orden_fabricacion_id=orden_id,
                    nuevo_estado_id=nuevo_estado_id,
                    responsable_id=responsable_id if responsable_id else None,
                    notas=notas,
                    tiempo_estimado_horas=tiempo_estimado
                )

                flash(f'Estado actualizado a: {updated_progress.estado.nombre}', 'success')
                return redirect(url_for('areas.area_detail', area_id=updated_progress.area_id))

            except ValueError as e:
                flash(str(e), 'error')
            except Exception as e_inner:
                logger.error(f"Error in change_estado_in_area: {str(e_inner)}")
                flash('Error al actualizar estado.', 'error')

        return render_template(
            'areas/cambiar_estado.html',
            orden=current_progress.orden_fabricacion,
            current_progress=current_progress,
            estados=estados,
            users=users,
            title=f'Cambiar Estado - {current_progress.orden_fabricacion.codigo}'
        )

    except Exception as e:
        logger.error(f"Error en formulario cambiar estado: {str(e)}")
        flash('Error procesando solicitud', 'error')
        return redirect(url_for('areas.dashboard'))


@areas_bp.route('/orden/<int:orden_id>/avanzar-area', methods=['POST'])
@login_required
def avanzar_area_form(orden_id):
    """Form-based area advancement"""
    try:
        responsable_id = request.form.get('responsable_id')
        notas = request.form.get('notas')

        new_progress = areas_service.advance_to_next_area(
            orden_fabricacion_id=orden_id,
            created_by=current_user.id,
            responsable_id=responsable_id if responsable_id else None,
            notas=notas
        )

        flash(f'Orden avanzada a: {new_progress.area.nombre}', 'success')
        return redirect(url_for('areas.area_detail', area_id=new_progress.area_id))

    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('areas.dashboard'))
    except Exception as e:
        logger.error(f"Error avanzando área (form): {str(e)}")
        flash('Error procesando solicitud', 'error')
        return redirect(url_for('areas.dashboard'))


@areas_bp.route('/tv-display')
@login_required
def tv_display():
    """Vista optimizada para televisión - rotación automática de áreas"""
    try:
        dashboard_data = areas_service.get_areas_dashboard_data()

        return render_template(
            'areas/tv_display.html',
            areas=dashboard_data['areas'],
            stats=dashboard_data['stats'],
            title='Display de Producción TV'
        )

    except Exception as e:
        logger.error(f"Error en TV display: {str(e)}")
        flash('Error cargando display de TV', 'error')
        return redirect(url_for('areas.dashboard'))

@areas_bp.route('/area/<int:area_id>/tv')
@login_required
def area_tv_display(area_id):
    """Vista de área individual optimizada para TV"""
    try:
        area = areas_repo.get_area_by_id(area_id)
        if not area:
            abort(404)

        # Get orders in this area
        from repositories.areas_repository import OrdenAreaProgresoRepository
        progreso_repo = OrdenAreaProgresoRepository()
        orders_in_area = progreso_repo.get_orders_in_area(area_id)

        # Group by state with same format as area_detail
        states_data = []
        for estado in area.estados:
            orders_in_state = [o for o in orders_in_area if o.estado_id == estado.id]
            if orders_in_state:  # Only include states with orders for TV
                states_data.append({
                    'estado': estado,
                    'orders': orders_in_state,
                    'count': len(orders_in_state)
                })

        from datetime import datetime
        return render_template(
            'areas/area_tv_display.html',
            area=area,
            states_data=states_data,
            total_orders=len(orders_in_area),
            now=datetime.now(),
            title=f'TV - {area.nombre}'
        )

    except Exception as e:
        logger.error(f"Error en área TV display: {str(e)}")
        flash('Error cargando display de área', 'error')
        return redirect(url_for('areas.dashboard'))

@areas_bp.route('/api/', methods=['GET'])
def api_areas():
    """API endpoint principal para áreas - usado en tests"""
    try:
        areas = areas_repo.get_all_areas()

        return jsonify({
            'success': True,
            'data': [{
                'id': a.id,
                'nombre': a.nombre,
                'descripcion': a.descripcion,
                'activo': a.activo
            } for a in areas]
        })

    except Exception as e:
        logger.error(f"Error en API áreas: {str(e)}")
        return jsonify({'error': 'Error al cargar áreas'}), 500