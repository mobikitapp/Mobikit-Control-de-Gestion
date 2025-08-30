from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from pydantic import ValidationError
from werkzeug.utils import secure_filename
from app import db
from replit_auth import require_login, require_role
from models import RolUsuario
from services.contratos_service import ContratosService
from services.proyectos_service import ProyectosService
from services.clientes_service import ClientesService
from schemas.contratos import ContratoCreate, ContratoUpdate, ContratoSearchFilters
import logging

logger = logging.getLogger(__name__)

contratos_bp = Blueprint('contratos', __name__)
contratos_service = ContratosService()
proyectos_service = ProyectosService()
clientes_service = ClientesService()

@contratos_bp.route('/')
@require_login
def index():
    """Lista de contratos con filtros"""
    try:
        # Get search parameters
        filters_data = {
            'proyecto_id': request.args.get('proyecto_id', type=int),
            'numero_oc': request.args.get('numero_oc', ''),
            'estado': request.args.get('estado', ''),
            'moneda': request.args.get('moneda', ''),
            'fecha_emision_desde': request.args.get('fecha_emision_desde', ''),
            'fecha_emision_hasta': request.args.get('fecha_emision_hasta', ''),
            'page': request.args.get('page', 1, type=int),
            'per_page': request.args.get('per_page', 20, type=int)
        }
        
        # Clean empty values
        filters_data = {k: v for k, v in filters_data.items() if v}
        
        # Validate filters
        filters = ContratoSearchFilters(**filters_data)
        
        # Search contratos
        contratos, total_count = contratos_service.search_contratos(filters)
        
        # Get data for filter dropdowns
        clientes = clientes_service.get_active_clientes()
        
        # Calculate pagination
        total_pages = (total_count + filters.per_page - 1) // filters.per_page
        has_prev = filters.page > 1
        has_next = filters.page < total_pages
        
        return render_template('contratos/index.html',
                             contratos=contratos,
                             clientes=clientes,
                             filters=filters,
                             total_count=total_count,
                             total_pages=total_pages,
                             has_prev=has_prev,
                             has_next=has_next)
                             
    except ValidationError as e:
        flash('Filtros inválidos', 'error')
        return redirect(url_for('contratos.index'))
    except Exception as e:
        logger.error(f"Error en lista de contratos: {str(e)}")
        flash('Error al cargar contratos', 'error')
        return redirect(url_for('index'))

@contratos_bp.route('/nuevo')
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS)
def nuevo():
    """Formulario para nuevo contrato"""
    try:
        clientes = clientes_service.get_active_clientes()
        return render_template('contratos/form.html', 
                             contrato=None, 
                             clientes=clientes,
                             title="Nuevo Contrato")
    except Exception as e:
        logger.error(f"Error cargando formulario nuevo contrato: {str(e)}")
        flash('Error al cargar formulario', 'error')
        return redirect(url_for('contratos.index'))

@contratos_bp.route('/crear', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS)
def crear():
    """Crear nuevo contrato"""
    try:
        # Validate form data
        contrato_data = ContratoCreate(**request.form.to_dict())
        
        # Handle file uploads
        archivos = request.files.getlist('archivos')
        
        # Create contrato with files
        contrato = contratos_service.create_contrato_with_files(
            contrato_data.dict(), 
            archivos, 
            current_user.id
        )
        
        flash(f'Contrato {contrato.numero_oc} creado exitosamente', 'success')
        return redirect(url_for('contratos.detalle', contrato_id=contrato.id))
        
    except ValidationError as e:
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
        clientes = clientes_service.get_active_clientes()
        return render_template('contratos/form.html', 
                             contrato=None, 
                             clientes=clientes,
                             title="Nuevo Contrato")
    except Exception as e:
        logger.error(f"Error creando contrato: {str(e)}")
        flash('Error al crear contrato', 'error')
        clientes = clientes_service.get_active_clientes()
        return render_template('contratos/form.html', 
                             contrato=None, 
                             clientes=clientes,
                             title="Nuevo Contrato")

@contratos_bp.route('/<int:contrato_id>')
@require_login
def detalle(contrato_id):
    """Detalle de contrato"""
    try:
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('contratos.index'))
        
        return render_template('contratos/detalle.html', contrato=contrato)
                             
    except Exception as e:
        logger.error(f"Error obteniendo contrato {contrato_id}: {str(e)}")
        flash('Error al cargar contrato', 'error')
        return redirect(url_for('contratos.index'))

@contratos_bp.route('/<int:contrato_id>/editar')
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS)
def editar(contrato_id):
    """Formulario de edición de contrato"""
    try:
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('contratos.index'))
        
        clientes = clientes_service.get_active_clientes()
        return render_template('contratos/form.html', 
                             contrato=contrato,
                             clientes=clientes,
                             title=f"Editar Contrato - {contrato.numero_oc}")
                             
    except Exception as e:
        logger.error(f"Error obteniendo contrato para editar {contrato_id}: {str(e)}")
        flash('Error al cargar contrato', 'error')
        return redirect(url_for('contratos.index'))

@contratos_bp.route('/<int:contrato_id>/actualizar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS)
def actualizar(contrato_id):
    """Actualizar contrato existente"""
    try:
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('contratos.index'))
        
        # Validate form data
        update_data = ContratoUpdate(**request.form.to_dict())
        
        # Update contrato
        contrato_actualizado = contratos_service.update_contrato(contrato_id, update_data.dict(exclude_unset=True))
        
        flash(f'Contrato {contrato_actualizado.numero_oc} actualizado exitosamente', 'success')
        return redirect(url_for('contratos.detalle', contrato_id=contrato_id))
        
    except ValidationError as e:
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
        clientes = clientes_service.get_active_clientes()
        return render_template('contratos/form.html', 
                             contrato=contrato,
                             clientes=clientes,
                             title=f"Editar Contrato - {contrato.numero_oc}")
    except Exception as e:
        logger.error(f"Error actualizando contrato {contrato_id}: {str(e)}")
        flash('Error al actualizar contrato', 'error')
        return redirect(url_for('contratos.detalle', contrato_id=contrato_id))

@contratos_bp.route('/<int:contrato_id>/cambiar-estado', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS)
def cambiar_estado(contrato_id):
    """Cambiar estado del contrato"""
    try:
        nuevo_estado = request.form.get('nuevo_estado')
        if not nuevo_estado:
            flash('Estado requerido', 'error')
            return redirect(url_for('contratos.detalle', contrato_id=contrato_id))
        
        success = contratos_service.change_contract_status(contrato_id, nuevo_estado)
        if success:
            flash('Estado del contrato actualizado exitosamente', 'success')
        else:
            flash('Error al cambiar estado del contrato', 'error')
            
    except Exception as e:
        logger.error(f"Error cambiando estado de contrato {contrato_id}: {str(e)}")
        flash('Error al cambiar estado del contrato', 'error')
    
    return redirect(url_for('contratos.detalle', contrato_id=contrato_id))

@contratos_bp.route('/<int:contrato_id>/adjuntos/subir', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS)
def subir_adjunto(contrato_id):
    """Subir nuevo adjunto al contrato"""
    try:
        archivo = request.files.get('archivo')
        tipo = request.form.get('tipo', 'contrato')
        
        if not archivo or not archivo.filename:
            flash('Archivo requerido', 'error')
            return redirect(url_for('contratos.detalle', contrato_id=contrato_id))
        
        adjunto = contratos_service.add_contract_attachment(contrato_id, archivo, tipo, current_user.id)
        flash('Archivo subido exitosamente', 'success')
        
    except Exception as e:
        logger.error(f"Error subiendo adjunto a contrato {contrato_id}: {str(e)}")
        flash('Error al subir archivo', 'error')
    
    return redirect(url_for('contratos.detalle', contrato_id=contrato_id))

@contratos_bp.route('/adjuntos/<int:adjunto_id>/eliminar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS)
def eliminar_adjunto(adjunto_id):
    """Eliminar adjunto del contrato"""
    try:
        contrato_id = contratos_service.delete_contract_attachment(adjunto_id)
        flash('Archivo eliminado exitosamente', 'success')
        return redirect(url_for('contratos.detalle', contrato_id=contrato_id))
        
    except Exception as e:
        logger.error(f"Error eliminando adjunto {adjunto_id}: {str(e)}")
        flash('Error al eliminar archivo', 'error')
        return redirect(url_for('contratos.index'))

