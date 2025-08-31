from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from pydantic import ValidationError
from app import db
from replit_auth import require_login, require_role
from models import RolUsuario
from services.proyectos_service import ProyectosService
from services.clientes_service import ClientesService
from schemas.proyectos import ProyectoCreate, ProyectoUpdate, ProyectoSearchFilters
from models import CategoriaMuebleModel, User
import logging
from datetime import datetime
from decimal import Decimal

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
        elif key in ['fecha_inicio', 'fecha_fin_estimada', 'fecha_fin_real', 
                     'fecha_presupuesto', 'fecha_adjudicacion']:
            try:
                processed[key] = datetime.strptime(value, '%Y-%m-%d').date() if value else None
            except ValueError:
                processed[key] = None
        elif key == 'categoria_ids':
            # Handle multiple category IDs if they come as list
            if isinstance(value, list):
                processed[key] = [int(v) for v in value if v]
            else:
                processed[key] = [int(value)] if value else []
        else:
            processed[key] = value
    
    return processed

@proyectos_bp.route('/')
@require_login
def index():
    """Lista de proyectos con filtros"""
    try:
        # Get search parameters
        filters_data = {
            'cliente_id': request.args.get('cliente_id', type=int),
            'nombre': request.args.get('nombre', ''),
            'estado': request.args.get('estado', ''),
            'responsable': request.args.get('responsable', ''),
            'fecha_inicio_desde': request.args.get('fecha_inicio_desde', ''),
            'fecha_inicio_hasta': request.args.get('fecha_inicio_hasta', ''),
            'page': request.args.get('page', 1, type=int),
            'per_page': request.args.get('per_page', 20, type=int)
        }
        
        # Clean empty values
        filters_data = {k: v for k, v in filters_data.items() if v}
        
        # Validate filters
        filters = ProyectoSearchFilters(**filters_data)
        
        # Search proyectos
        proyectos, total_count = proyectos_service.search_proyectos(filters)
        
        # Get clientes for filter dropdown
        clientes = clientes_service.get_active_clientes()
        
        # Calculate pagination
        total_pages = (total_count + filters.per_page - 1) // filters.per_page
        has_prev = filters.page > 1
        has_next = filters.page < total_pages
        
        return render_template('proyectos/index.html',
                             proyectos=proyectos,
                             clientes=clientes,
                             filters=filters,
                             total_count=total_count,
                             total_pages=total_pages,
                             has_prev=has_prev,
                             has_next=has_next)
                             
    except ValidationError as e:
        flash('Filtros inválidos', 'error')
        return redirect(url_for('proyectos.index'))
    except Exception as e:
        logger.error(f"Error en lista de proyectos: {str(e)}")
        flash('Error al cargar proyectos', 'error')
        return redirect(url_for('index'))

@proyectos_bp.route('/nuevo')
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def nuevo():
    """Formulario para nuevo proyecto"""
    try:
        clientes = clientes_service.get_active_clientes()
        categorias = CategoriaMuebleModel.query.filter_by(activo=True).all()
        usuarios = User.query.filter_by(activo=True).all()
        vendedores = User.query.filter_by(activo=True).all()  # Filtrar por rol si necesario
        
        return render_template('proyectos/form.html', 
                             proyecto=None, 
                             clientes=clientes,
                             categorias=categorias,
                             usuarios=usuarios,
                             vendedores=vendedores,
                             title="Nuevo Proyecto")
    except Exception as e:
        logger.error(f"Error cargando formulario nuevo proyecto: {str(e)}")
        flash('Error al cargar formulario', 'error')
        return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/crear', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def crear():
    """Crear nuevo proyecto"""
    try:
        # Process and validate form data
        form_data = process_form_data(request.form.to_dict())
        proyecto_data = ProyectoCreate(**form_data)
        
        # Create proyecto
        proyecto = proyectos_service.create_proyecto(proyecto_data.dict(), current_user.id)
        
        flash(f'Proyecto {proyecto.nombre} creado exitosamente', 'success')
        return redirect(url_for('proyectos.detalle', proyecto_id=proyecto.id))
        
    except ValidationError as e:
        error_messages = []
        for error in e.errors():
            field_name = error['loc'][0] if error['loc'] else 'campo'
            # Traducir nombres de campos al español
            field_translations = {
                'cliente_id': 'Cliente',
                'nombre': 'Nombre del proyecto',
                'fecha_inicio': 'Fecha de inicio',
                'fecha_fin_estimada': 'Fecha de fin estimada',
                'monto_provision_presupuestado': 'Monto de provisión',
                'monto_instalacion_presupuestado': 'Monto de instalación'
            }
            field_display = field_translations.get(field_name, field_name)
            error_messages.append(f"{field_display}: {error['msg']}")
        
        for msg in error_messages:
            flash(msg, 'error')
            
        clientes = clientes_service.get_active_clientes()
        categorias = CategoriaMuebleModel.query.filter_by(activo=True).all()
        usuarios = User.query.filter_by(activo=True).all()
        vendedores = User.query.filter_by(activo=True).all()
        return render_template('proyectos/form.html', 
                             proyecto=None, 
                             clientes=clientes,
                             categorias=categorias,
                             usuarios=usuarios,
                             vendedores=vendedores,
                             title="Nuevo Proyecto")
    except Exception as e:
        logger.error(f"Error creando proyecto: {str(e)}")
        flash(f'Error inesperado al crear proyecto: {str(e)}', 'error')
        clientes = clientes_service.get_active_clientes()
        categorias = CategoriaMuebleModel.query.filter_by(activo=True).all()
        usuarios = User.query.filter_by(activo=True).all()
        vendedores = User.query.filter_by(activo=True).all()
        return render_template('proyectos/form.html', 
                             proyecto=None, 
                             clientes=clientes,
                             categorias=categorias,
                             usuarios=usuarios,
                             vendedores=vendedores,
                             title="Nuevo Proyecto")

@proyectos_bp.route('/<int:proyecto_id>')
@require_login
def detalle(proyecto_id):
    """Detalle de proyecto con estadísticas"""
    try:
        proyecto_data = proyectos_service.get_proyecto_with_stats(proyecto_id)
        if not proyecto_data:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('proyectos.index'))
        
        return render_template('proyectos/detalle.html', 
                             proyecto=proyecto_data['proyecto'],
                             stats=proyecto_data['stats'])
                             
    except Exception as e:
        logger.error(f"Error obteniendo proyecto {proyecto_id}: {str(e)}")
        flash('Error al cargar proyecto', 'error')
        return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/<int:proyecto_id>/editar')
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def editar(proyecto_id):
    """Formulario de edición de proyecto"""
    try:
        proyecto = proyectos_service.get_proyecto_by_id(proyecto_id)
        if not proyecto:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('proyectos.index'))
        
        clientes = clientes_service.get_active_clientes()
        categorias = CategoriaMuebleModel.query.filter_by(activo=True).all()
        usuarios = User.query.filter_by(activo=True).all()
        vendedores = User.query.filter_by(activo=True).all()  # Filtrar por rol si necesario
        
        return render_template('proyectos/form.html', 
                             proyecto=proyecto,
                             clientes=clientes,
                             categorias=categorias,
                             usuarios=usuarios,
                             vendedores=vendedores,
                             title=f"Editar Proyecto - {proyecto.nombre}")
                             
    except Exception as e:
        logger.error(f"Error obteniendo proyecto para editar {proyecto_id}: {str(e)}")
        flash('Error al cargar proyecto', 'error')
        return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/<int:proyecto_id>/actualizar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def actualizar(proyecto_id):
    """Actualizar proyecto existente"""
    try:
        proyecto = proyectos_service.get_proyecto_by_id(proyecto_id)
        if not proyecto:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('proyectos.index'))
        
        # Process and validate form data
        form_data = process_form_data(request.form.to_dict(), is_update=True)
        update_data = ProyectoUpdate(**form_data)
        
        # Update proyecto
        proyecto_actualizado = proyectos_service.update_proyecto(proyecto_id, update_data.dict(exclude_unset=True))
        
        flash(f'Proyecto {proyecto_actualizado.nombre} actualizado exitosamente', 'success')
        return redirect(url_for('proyectos.detalle', proyecto_id=proyecto_id))
        
    except ValidationError as e:
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
        clientes = clientes_service.get_active_clientes()
        categorias = CategoriaMuebleModel.query.filter_by(activo=True).all()
        usuarios = User.query.filter_by(activo=True).all()
        vendedores = User.query.filter_by(activo=True).all()
        return render_template('proyectos/form.html', 
                             proyecto=proyecto,
                             clientes=clientes,
                             categorias=categorias,
                             usuarios=usuarios,
                             vendedores=vendedores,
                             title=f"Editar Proyecto - {proyecto.nombre}" if proyecto else "Editar Proyecto")
    except Exception as e:
        logger.error(f"Error actualizando proyecto {proyecto_id}: {str(e)}")
        flash('Error al actualizar proyecto', 'error')
        return redirect(url_for('proyectos.detalle', proyecto_id=proyecto_id))

@proyectos_bp.route('/<int:proyecto_id>/eliminar', methods=['POST'])
@require_role(RolUsuario.ADMIN)
def eliminar(proyecto_id):
    """Eliminar proyecto"""
    try:
        success = proyectos_service.delete_proyecto(proyecto_id)
        if success:
            flash('Proyecto eliminado exitosamente', 'success')
        else:
            flash('Error al eliminar proyecto', 'error')
            
    except Exception as e:
        logger.error(f"Error eliminando proyecto {proyecto_id}: {str(e)}")
        flash('Error al eliminar proyecto', 'error')
    
    return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/api/by-cliente/<int:cliente_id>')
@require_login
def api_by_cliente(cliente_id):
    """API endpoint para obtener proyectos por cliente"""
    try:
        proyectos = proyectos_service.get_proyectos_by_cliente(cliente_id)
        return jsonify([{
            'id': p.id,
            'nombre': p.nombre,
            'estado': p.estado.value
        } for p in proyectos])
        
    except Exception as e:
        logger.error(f"Error en API proyectos por cliente: {str(e)}")
        return jsonify({'error': 'Error al cargar proyectos'}), 500

