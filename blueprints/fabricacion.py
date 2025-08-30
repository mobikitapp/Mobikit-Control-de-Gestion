from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from pydantic import ValidationError
from app import db
from replit_auth import require_login, require_role
from models import RolUsuario
from services.fabricacion_service import FabricacionService
from services.proyectos_service import ProyectosService
from services.contratos_service import ContratosService
from services.clientes_service import ClientesService
from schemas.fabricacion import (OrdenFabricacionCreate, OrdenFabricacionUpdate, 
                                OrdenFabricacionSearchFilters, CambioEstadoOF)
import logging

logger = logging.getLogger(__name__)

fabricacion_bp = Blueprint('fabricacion', __name__)
fabricacion_service = FabricacionService()
proyectos_service = ProyectosService()
contratos_service = ContratosService()
clientes_service = ClientesService()

@fabricacion_bp.route('/')
@require_login
def index():
    """Lista de órdenes de fabricación con filtros"""
    try:
        # Get search parameters
        filters_data = {
            'proyecto_id': request.args.get('proyecto_id', type=int),
            'contrato_id': request.args.get('contrato_id', type=int),
            'codigo': request.args.get('codigo', ''),
            'estado': request.args.get('estado', ''),
            'responsable': request.args.get('responsable', ''),
            'fecha_planificada_desde': request.args.get('fecha_planificada_desde', ''),
            'fecha_planificada_hasta': request.args.get('fecha_planificada_hasta', ''),
            'page': request.args.get('page', 1, type=int),
            'per_page': request.args.get('per_page', 20, type=int)
        }
        
        # Clean empty values
        filters_data = {k: v for k, v in filters_data.items() if v}
        
        # Validate filters
        filters = OrdenFabricacionSearchFilters(**filters_data)
        
        # Search OFs
        ofs, total_count = fabricacion_service.search_ordenes_fabricacion(filters)
        
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
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def nueva():
    """Formulario para nueva orden de fabricación"""
    try:
        clientes = clientes_service.get_active_clientes()
        return render_template('fabricacion/form.html', 
                             of=None, 
                             clientes=clientes,
                             title="Nueva Orden de Fabricación")
    except Exception as e:
        logger.error(f"Error cargando formulario nueva OF: {str(e)}")
        flash('Error al cargar formulario', 'error')
        return redirect(url_for('fabricacion.index'))

@fabricacion_bp.route('/crear', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def crear():
    """Crear nueva orden de fabricación"""
    try:
        # Get form data
        form_data = request.form.to_dict()
        
        # Process items
        items_data = []
        item_count = int(request.form.get('item_count', 0))
        for i in range(item_count):
            item_data = {
                'sku_codigo': request.form.get(f'items[{i}][sku_codigo]', ''),
                'descripcion': request.form.get(f'items[{i}][descripcion]', ''),
                'cantidad': request.form.get(f'items[{i}][cantidad]', '0'),
                'unidad': request.form.get(f'items[{i}][unidad]', 'UN'),
                'notas': request.form.get(f'items[{i}][notas]', '')
            }
            if item_data['sku_codigo'] and item_data['descripcion']:
                items_data.append(item_data)
        
        form_data['items'] = items_data
        
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
        
        return render_template('fabricacion/detalle.html', of=of)
                             
    except Exception as e:
        logger.error(f"Error obteniendo OF {of_id}: {str(e)}")
        flash('Error al cargar orden de fabricación', 'error')
        return redirect(url_for('fabricacion.index'))

@fabricacion_bp.route('/<int:of_id>/editar')
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def editar(of_id):
    """Formulario de edición de orden de fabricación"""
    try:
        of = fabricacion_service.get_orden_fabricacion_by_id(of_id)
        if not of:
            flash('Orden de Fabricación no encontrada', 'error')
            return redirect(url_for('fabricacion.index'))
        
        clientes = clientes_service.get_active_clientes()
        return render_template('fabricacion/form.html', 
                             of=of,
                             clientes=clientes,
                             title=f"Editar OF - {of.codigo}")
                             
    except Exception as e:
        logger.error(f"Error obteniendo OF para editar {of_id}: {str(e)}")
        flash('Error al cargar orden de fabricación', 'error')
        return redirect(url_for('fabricacion.index'))

@fabricacion_bp.route('/<int:of_id>/actualizar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def actualizar(of_id):
    """Actualizar orden de fabricación existente"""
    try:
        of = fabricacion_service.get_orden_fabricacion_by_id(of_id)
        if not of:
            flash('Orden de Fabricación no encontrada', 'error')
            return redirect(url_for('fabricacion.index'))
        
        # Validate form data
        update_data = OrdenFabricacionUpdate(**request.form.to_dict())
        
        # Update OF
        of_actualizada = fabricacion_service.update_orden_fabricacion(of_id, update_data.dict(exclude_unset=True))
        
        flash(f'Orden de Fabricación {of_actualizada.codigo} actualizada exitosamente', 'success')
        return redirect(url_for('fabricacion.detalle', of_id=of_id))
        
    except ValidationError as e:
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
        clientes = clientes_service.get_active_clientes()
        return render_template('fabricacion/form.html', 
                             of=of,
                             clientes=clientes,
                             title=f"Editar OF - {of.codigo}")
    except Exception as e:
        logger.error(f"Error actualizando OF {of_id}: {str(e)}")
        flash('Error al actualizar orden de fabricación', 'error')
        return redirect(url_for('fabricacion.detalle', of_id=of_id))

@fabricacion_bp.route('/<int:of_id>/cambiar-estado', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION)
def cambiar_estado(of_id):
    """Cambiar estado de la orden de fabricación"""
    try:
        # Validate request data
        cambio_data = CambioEstadoOF(**request.form.to_dict())
        
        success = fabricacion_service.change_of_status(of_id, cambio_data.nuevo_estado, cambio_data.notas)
        if success:
            flash('Estado de la OF actualizado exitosamente', 'success')
        else:
            flash('Error al cambiar estado de la OF', 'error')
            
    except ValidationError as e:
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
    except Exception as e:
        logger.error(f"Error cambiando estado de OF {of_id}: {str(e)}")
        flash('Error al cambiar estado de la OF', 'error')
    
    return redirect(url_for('fabricacion.detalle', of_id=of_id))

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
            'estado': of.estado.value
        } for of in ofs])
        
    except Exception as e:
        logger.error(f"Error en API OFs por proyecto: {str(e)}")
        return jsonify({'error': 'Error al cargar órdenes de fabricación'}), 500

