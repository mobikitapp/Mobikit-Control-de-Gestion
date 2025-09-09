from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_login import current_user, login_required
from pydantic import ValidationError
from app import db
from replit_auth import require_login, require_role
from models import RolUsuario, Contrato, TipoDocumento
from services.proyectos_service import ProyectosService
from services.clientes_service import ClientesService
from schemas.proyectos import ProyectoCreate, ProyectoUpdate, ProyectoSearchFilters
from models import CategoriaMuebleModel, User
import logging
from datetime import datetime, date
from decimal import Decimal
import math

logger = logging.getLogger(__name__)

proyectos_bp = Blueprint('proyectos', __name__)
proyectos_service = ProyectosService()
clientes_service = ClientesService()

def process_form_data(form_data, is_update=False):
    """Process form data for Pydantic validation"""
    processed = {}

    for key, value in form_data.items():
        if value == '' or value is None:
            if is_update:
                continue  # Skip empty values in updates
            else:
                processed[key] = None
        elif key in ['cliente_id']:
            processed[key] = int(value) if value else None

        elif key in ['monto_provision_presupuestado', 'margen_venta_provision',
                     'monto_instalacion_presupuestado', 'margen_venta_instalacion']:
            processed[key] = Decimal(str(value)) if value else None
        elif key == 'numero_viviendas':
            processed[key] = int(value) if value else None
        elif key in ['fecha_inicio', 'fecha_fin_estimada', 'fecha_fin_real',
                     'fecha_presupuesto', 'fecha_adjudicacion']:
            try:
                processed[key] = datetime.strptime(value, '%Y-%m-%d').date() if value else None
            except ValueError:
                processed[key] = None
        elif key == 'estado_comercial':
            processed[key] = value if value else None
        else:
            processed[key] = value

    return processed

@proyectos_bp.route('/')
@require_login
def index():
    """Lista de proyectos con filtros y paginación"""
    try:
        # Get search parameters
        filters_data = {
            'page': request.args.get('page', 1, type=int),
            'per_page': request.args.get('per_page', 10, type=int)
        }

        # Add optional filters only if they exist
        if request.args.get('nombre', '').strip():
            filters_data['nombre'] = request.args.get('nombre').strip()

        if request.args.get('cliente_id'):
            try:
                filters_data['cliente_id'] = int(request.args.get('cliente_id'))
            except (ValueError, TypeError):
                pass

        if request.args.get('estado_comercial', '').strip():
            filters_data['estado_comercial'] = request.args.get('estado_comercial').strip()

        if request.args.get('tipo_proyecto', '').strip():
            filters_data['tipo_proyecto'] = request.args.get('tipo_proyecto').strip()

        # Validate filters
        filters = ProyectoSearchFilters(**filters_data)

        # Search projects
        proyectos, total_count = proyectos_service.search_proyectos(filters)

        # Calculate pagination
        total_pages = math.ceil(total_count / filters.per_page)

        # Get clients for filter dropdown
        clientes = clientes_service.get_all_clientes()

        return render_template('proyectos/index.html',
                             proyectos=proyectos,
                             clientes=clientes,
                             filters=filters,
                             current_page=filters.page,
                             total_pages=total_pages,
                             total_count=total_count,
                             current_user=current_user,
                             title="Proyectos")

    except ValidationError as e:
        logger.warning(f"Error de validación en filtros de proyectos: {str(e)}")
        flash('Error en filtros de búsqueda', 'error')
        return redirect(url_for('proyectos.index'))
    except Exception as e:
        logger.error(f"Error loading projects index: {str(e)}")
        flash('Error al cargar proyectos', 'error')
        return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/nuevo', methods=['GET', 'POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS)
def nuevo():
    """Crear nuevo proyecto"""
    if request.method == 'GET':
        try:
            clientes = clientes_service.get_all_clientes()
            return render_template('proyectos/form.html',
                                 clientes=clientes,
                                 current_user=current_user,
                                 title="Nuevo Proyecto")
        except Exception as e:
            logger.error(f"Error loading new project form: {str(e)}")
            flash('Error al cargar formulario', 'error')
            return redirect(url_for('proyectos.index'))

    elif request.method == 'POST':
        try:
            # Process form data
            form_data = process_form_data(request.form.to_dict())

            # Validate data with Pydantic
            proyecto_data = ProyectoCreate(**form_data)

            # Create project
            proyecto = proyectos_service.create_proyecto(proyecto_data, current_user.id)

            flash(f'Proyecto "{proyecto.nombre}" creado exitosamente', 'success')
            return redirect(url_for('proyectos.detalle', proyecto_id=proyecto.id))

        except ValidationError as e:
            logger.warning(f"Validation error creating project: {str(e)}")
            flash('Error de validación en los datos del proyecto', 'error')
            clientes = clientes_service.get_all_clientes()
            return render_template('proyectos/form.html',
                                 clientes=clientes,
                                 proyecto_data=request.form.to_dict(),
                                 current_user=current_user,
                                 title="Nuevo Proyecto")
        except Exception as e:
            logger.error(f"Error creating project: {str(e)}")
            flash('Error al crear proyecto', 'error')
            return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/<int:proyecto_id>')
@require_login
def detalle(proyecto_id):
    """Ver detalles del proyecto"""
    try:
        proyecto_data = proyectos_service.get_proyecto_with_stats(proyecto_id)

        if not proyecto_data:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('proyectos.index'))

        return render_template('proyectos/detalle.html',
                             proyecto=proyecto_data['proyecto'],
                             stats=proyecto_data['stats'],
                             current_user=current_user,
                             title=f"Proyecto: {proyecto_data['proyecto'].nombre}")

    except Exception as e:
        logger.error(f"Error loading project detail {proyecto_id}: {str(e)}")
        flash('Error al cargar detalle del proyecto', 'error')
        return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/<int:proyecto_id>/editar', methods=['GET', 'POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def editar(proyecto_id):
    """Editar proyecto"""
    if request.method == 'GET':
        try:
            proyecto = proyectos_service.get_proyecto_by_id(proyecto_id)
            if not proyecto:
                flash('Proyecto no encontrado', 'error')
                return redirect(url_for('proyectos.index'))

            clientes = clientes_service.get_all_clientes()
            return render_template('proyectos/form.html',
                                 proyecto=proyecto,
                                 clientes=clientes,
                                 current_user=current_user,
                                 title=f"Editar: {proyecto.nombre}")

        except Exception as e:
            logger.error(f"Error loading edit form for project {proyecto_id}: {str(e)}")
            flash('Error al cargar formulario de edición', 'error')
            return redirect(url_for('proyectos.detalle', proyecto_id=proyecto_id))

    elif request.method == 'POST':
        try:
            # Process form data for update
            form_data = process_form_data(request.form.to_dict(), is_update=True)

            # Validate data with Pydantic
            proyecto_data = ProyectoUpdate(**form_data)

            # Update project
            proyecto = proyectos_service.update_proyecto(proyecto_id, proyecto_data, current_user.id)

            if proyecto:
                flash(f'Proyecto "{proyecto.nombre}" actualizado exitosamente', 'success')
                return redirect(url_for('proyectos.detalle', proyecto_id=proyecto.id))
            else:
                flash('Error al actualizar proyecto', 'error')
                return redirect(url_for('proyectos.detalle', proyecto_id=proyecto_id))

        except ValidationError as e:
            logger.warning(f"Validation error updating project {proyecto_id}: {str(e)}")
            flash('Error de validación en los datos del proyecto', 'error')
            proyecto = proyectos_service.get_proyecto_by_id(proyecto_id)
            clientes = clientes_service.get_all_clientes()
            return render_template('proyectos/form.html',
                                 proyecto=proyecto,
                                 clientes=clientes,
                                 proyecto_data=request.form.to_dict(),
                                 current_user=current_user,
                                 title=f"Editar: {proyecto.nombre}")
        except Exception as e:
            logger.error(f"Error updating project {proyecto_id}: {str(e)}")
            flash('Error al actualizar proyecto', 'error')
            return redirect(url_for('proyectos.detalle', proyecto_id=proyecto_id))

@proyectos_bp.route('/<int:proyecto_id>/eliminar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def eliminar(proyecto_id):
    """Eliminar proyecto (soft delete)"""
    try:
        proyecto = proyectos_service.get_proyecto_by_id(proyecto_id)
        if not proyecto:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('proyectos.index'))

        success = proyectos_service.delete_proyecto(proyecto_id, current_user.id)

        if success:
            flash(f'Proyecto "{proyecto.nombre}" eliminado exitosamente', 'success')
        else:
            flash('Error al eliminar proyecto', 'error')

        return redirect(url_for('proyectos.index'))

    except Exception as e:
        logger.error(f"Error deleting project {proyecto_id}: {str(e)}")
        flash('Error al eliminar proyecto', 'error')
        return redirect(url_for('proyectos.detalle', proyecto_id=proyecto_id))

@proyectos_bp.route('/adjuntos/<int:adjunto_id>/eliminar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def eliminar_adjunto(adjunto_id):
    """Delete project attachment"""
    try:
        success = proyectos_service.delete_adjunto(adjunto_id, current_user.id)

        if success:
            return jsonify({'success': True, 'message': 'Documento eliminado exitosamente'})
        else:
            return jsonify({'success': False, 'message': 'Error al eliminar documento'}), 500

    except Exception as e:
        logger.error(f"Error deleting adjunto {adjunto_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al eliminar documento: {str(e)}'}), 500

@proyectos_bp.route('/api/<int:proyecto_id>/contratos-activos')
@require_login
def api_contratos_activos(proyecto_id):
    """API endpoint para obtener contratos activos de un proyecto"""
    try:
        contratos = proyectos_service.get_contratos_activos_by_proyecto(proyecto_id)
        return jsonify([{
            'id': c.id,
            'numero_oc': c.numero_oc,
            'tipo_documento': c.tipo_documento.value,
            'monto_total': float(c.monto_total) if c.monto_total else 0,
            'moneda': c.moneda,
            'fecha_proxima_entrega': c.fecha_proxima_entrega.strftime('%d/%m/%Y') if c.fecha_proxima_entrega else None,
            'proximo_hito_titulo': c.proximo_hito.titulo if c.proximo_hito else None,
            'fecha_vencimiento': c.fecha_vencimiento.strftime('%d/%m/%Y') if c.fecha_vencimiento else None,
            'estado': c.estado.value
        } for c in contratos])

    except Exception as e:
        logger.error(f"Error en API contratos activos: {str(e)}")
        return jsonify({'error': 'Error al cargar contratos'}), 500