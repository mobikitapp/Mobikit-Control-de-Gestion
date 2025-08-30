from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from pydantic import ValidationError
from app import db
from replit_auth import require_login, require_role
from models import RolUsuario
from services.despachos_service import DespachosService
from services.proyectos_service import ProyectosService
from services.fabricacion_service import FabricacionService
from services.clientes_service import ClientesService
from schemas.despachos import (DespachoCreate, DespachoUpdate, DespachoSearchFilters, 
                             CambioEstadoDespacho)
import logging

logger = logging.getLogger(__name__)

despachos_bp = Blueprint('despachos', __name__)
despachos_service = DespachosService()
proyectos_service = ProyectosService()
fabricacion_service = FabricacionService()
clientes_service = ClientesService()

@despachos_bp.route('/')
@require_login
def index():
    """Lista de despachos con filtros"""
    try:
        # Get search parameters
        filters_data = {
            'proyecto_id': request.args.get('proyecto_id', type=int),
            'of_id': request.args.get('of_id', type=int),
            'numero_despacho': request.args.get('numero_despacho', ''),
            'estado': request.args.get('estado', ''),
            'responsable': request.args.get('responsable', ''),
            'fecha_programada_desde': request.args.get('fecha_programada_desde', ''),
            'fecha_programada_hasta': request.args.get('fecha_programada_hasta', ''),
            'page': request.args.get('page', 1, type=int),
            'per_page': request.args.get('per_page', 20, type=int)
        }
        
        # Clean empty values
        filters_data = {k: v for k, v in filters_data.items() if v}
        
        # Validate filters
        filters = DespachoSearchFilters(**filters_data)
        
        # Search despachos
        despachos, total_count = despachos_service.search_despachos(filters)
        
        # Get data for filter dropdowns
        clientes = clientes_service.get_active_clientes()
        
        # Calculate pagination
        total_pages = (total_count + filters.per_page - 1) // filters.per_page
        has_prev = filters.page > 1
        has_next = filters.page < total_pages
        
        return render_template('despachos/index.html',
                             despachos=despachos,
                             clientes=clientes,
                             filters=filters,
                             total_count=total_count,
                             total_pages=total_pages,
                             has_prev=has_prev,
                             has_next=has_next)
                             
    except ValidationError as e:
        flash('Filtros inválidos', 'error')
        return redirect(url_for('despachos.index'))
    except Exception as e:
        logger.error(f"Error en lista de despachos: {str(e)}")
        flash('Error al cargar despachos', 'error')
        return redirect(url_for('index'))

@despachos_bp.route('/nuevo')
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def nuevo():
    """Formulario para nuevo despacho"""
    try:
        clientes = clientes_service.get_active_clientes()
        return render_template('despachos/form.html', 
                             despacho=None, 
                             clientes=clientes,
                             title="Nuevo Despacho")
    except Exception as e:
        logger.error(f"Error cargando formulario nuevo despacho: {str(e)}")
        flash('Error al cargar formulario', 'error')
        return redirect(url_for('despachos.index'))

@despachos_bp.route('/crear', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def crear():
    """Crear nuevo despacho"""
    try:
        # Validate form data
        despacho_data = DespachoCreate(**request.form.to_dict())
        
        # Handle file uploads
        archivos = request.files.getlist('archivos')
        
        # Create despacho with files
        despacho = despachos_service.create_despacho_with_files(
            despacho_data.dict(), 
            archivos, 
            current_user.id
        )
        
        flash(f'Despacho {despacho.numero_despacho} creado exitosamente', 'success')
        return redirect(url_for('despachos.detalle', despacho_id=despacho.id))
        
    except ValidationError as e:
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
        clientes = clientes_service.get_active_clientes()
        return render_template('despachos/form.html', 
                             despacho=None, 
                             clientes=clientes,
                             title="Nuevo Despacho")
    except Exception as e:
        logger.error(f"Error creando despacho: {str(e)}")
        flash('Error al crear despacho', 'error')
        clientes = clientes_service.get_active_clientes()
        return render_template('despachos/form.html', 
                             despacho=None, 
                             clientes=clientes,
                             title="Nuevo Despacho")

@despachos_bp.route('/<int:despacho_id>')
@require_login
def detalle(despacho_id):
    """Detalle de despacho"""
    try:
        despacho = despachos_service.get_despacho_by_id(despacho_id)
        if not despacho:
            flash('Despacho no encontrado', 'error')
            return redirect(url_for('despachos.index'))
        
        return render_template('despachos/detalle.html', despacho=despacho)
                             
    except Exception as e:
        logger.error(f"Error obteniendo despacho {despacho_id}: {str(e)}")
        flash('Error al cargar despacho', 'error')
        return redirect(url_for('despachos.index'))

@despachos_bp.route('/<int:despacho_id>/editar')
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def editar(despacho_id):
    """Formulario de edición de despacho"""
    try:
        despacho = despachos_service.get_despacho_by_id(despacho_id)
        if not despacho:
            flash('Despacho no encontrado', 'error')
            return redirect(url_for('despachos.index'))
        
        clientes = clientes_service.get_active_clientes()
        return render_template('despachos/form.html', 
                             despacho=despacho,
                             clientes=clientes,
                             title=f"Editar Despacho - {despacho.numero_despacho}")
                             
    except Exception as e:
        logger.error(f"Error obteniendo despacho para editar {despacho_id}: {str(e)}")
        flash('Error al cargar despacho', 'error')
        return redirect(url_for('despachos.index'))

@despachos_bp.route('/<int:despacho_id>/actualizar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def actualizar(despacho_id):
    """Actualizar despacho existente"""
    try:
        despacho = despachos_service.get_despacho_by_id(despacho_id)
        if not despacho:
            flash('Despacho no encontrado', 'error')
            return redirect(url_for('despachos.index'))
        
        # Validate form data
        update_data = DespachoUpdate(**request.form.to_dict())
        
        # Update despacho
        despacho_actualizado = despachos_service.update_despacho(despacho_id, update_data.dict(exclude_unset=True))
        
        flash(f'Despacho {despacho_actualizado.numero_despacho} actualizado exitosamente', 'success')
        return redirect(url_for('despachos.detalle', despacho_id=despacho_id))
        
    except ValidationError as e:
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
        clientes = clientes_service.get_active_clientes()
        return render_template('despachos/form.html', 
                             despacho=despacho,
                             clientes=clientes,
                             title=f"Editar Despacho - {despacho.numero_despacho}")
    except Exception as e:
        logger.error(f"Error actualizando despacho {despacho_id}: {str(e)}")
        flash('Error al actualizar despacho', 'error')
        return redirect(url_for('despachos.detalle', despacho_id=despacho_id))

@despachos_bp.route('/<int:despacho_id>/cambiar-estado', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def cambiar_estado(despacho_id):
    """Cambiar estado del despacho"""
    try:
        # Validate request data
        cambio_data = CambioEstadoDespacho(**request.form.to_dict())
        
        success = despachos_service.change_despacho_status(despacho_id, cambio_data.nuevo_estado, cambio_data.observaciones)
        if success:
            flash('Estado del despacho actualizado exitosamente', 'success')
        else:
            flash('Error al cambiar estado del despacho', 'error')
            
    except ValidationError as e:
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
    except Exception as e:
        logger.error(f"Error cambiando estado de despacho {despacho_id}: {str(e)}")
        flash('Error al cambiar estado del despacho', 'error')
    
    return redirect(url_for('despachos.detalle', despacho_id=despacho_id))

@despachos_bp.route('/<int:despacho_id>/adjuntos/subir', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def subir_adjunto(despacho_id):
    """Subir nuevo adjunto al despacho"""
    try:
        archivo = request.files.get('archivo')
        tipo = request.form.get('tipo', 'foto')
        
        if not archivo or not archivo.filename:
            flash('Archivo requerido', 'error')
            return redirect(url_for('despachos.detalle', despacho_id=despacho_id))
        
        adjunto = despachos_service.add_despacho_attachment(despacho_id, archivo, tipo, current_user.id)
        flash('Archivo subido exitosamente', 'success')
        
    except Exception as e:
        logger.error(f"Error subiendo adjunto a despacho {despacho_id}: {str(e)}")
        flash('Error al subir archivo', 'error')
    
    return redirect(url_for('despachos.detalle', despacho_id=despacho_id))

@despachos_bp.route('/adjuntos/<int:adjunto_id>/eliminar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def eliminar_adjunto(adjunto_id):
    """Eliminar adjunto del despacho"""
    try:
        despacho_id = despachos_service.delete_despacho_attachment(adjunto_id)
        flash('Archivo eliminado exitosamente', 'success')
        return redirect(url_for('despachos.detalle', despacho_id=despacho_id))
        
    except Exception as e:
        logger.error(f"Error eliminando adjunto {adjunto_id}: {str(e)}")
        flash('Error al eliminar archivo', 'error')
        return redirect(url_for('despachos.index'))

@despachos_bp.route('/<int:despacho_id>/eliminar', methods=['POST'])
@require_role(RolUsuario.ADMIN)
def eliminar(despacho_id):
    """Eliminar despacho"""
    try:
        success = despachos_service.delete_despacho(despacho_id)
        if success:
            flash('Despacho eliminado exitosamente', 'success')
        else:
            flash('Error al eliminar despacho', 'error')
            
    except Exception as e:
        logger.error(f"Error eliminando despacho {despacho_id}: {str(e)}")
        flash('Error al eliminar despacho', 'error')
    
    return redirect(url_for('despachos.index'))

