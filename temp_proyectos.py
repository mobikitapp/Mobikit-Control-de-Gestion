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
        elif key == 'categoria_ids':
            # Handle multiple category IDs if they come as list
            if isinstance(value, list):
                processed[key] = [int(v) for v in value if v]
            else:
                processed[key] = [int(value)] if value else []
        elif key == 'estado_comercial':
            # Estado comercial default value
            processed[key] = value if value else 'PENDIENTE_PRESUPUESTO'
        else:
            processed[key] = value

    return processed

@proyectos_bp.route('/')
@require_login
def index():
    """Lista de proyectos con filtros"""
    try:
        # Build search filters
        filters = ProyectoSearchFilters(
            cliente_id=request.args.get('cliente_id', type=int),
            nombre=request.args.get('nombre'),
            vendedor_id=request.args.get('vendedor_id'),
            fecha_inicio_desde=request.args.get('fecha_inicio_desde', type=lambda x: datetime.strptime(x, '%Y-%m-%d').date() if x else None),
            fecha_inicio_hasta=request.args.get('fecha_inicio_hasta', type=lambda x: datetime.strptime(x, '%Y-%m-%d').date() if x else None),
            page=request.args.get('page', 1, type=int),
            per_page=request.args.get('per_page', 20, type=int)
        )

        # Search proyectos
        proyectos, total_count = proyectos_service.search_proyectos(filters)

        # Get data for filters
        clientes = clientes_service.get_active_clientes()
        from services.user_service import UserService
        vendedores = UserService.get_users_by_roles(['ventas', 'admin'])

        return render_template('proyectos/index.html',
                             proyectos=proyectos,
                             clientes=clientes,
                             vendedores=vendedores,
                             filters=filters,
                             total_count=total_count,
                             total_pages=math.ceil(total_count / filters.per_page) if total_count > 0 else 1,
                             has_prev=filters.page > 1,
                             has_next=filters.page < math.ceil(total_count / filters.per_page) if total_count > 0 else False)

    except ValidationError as e:
        flash('Filtros inválidos', 'error')
        return redirect(url_for('proyectos.index'))
    except Exception as e:
        logger.error(f"Error en lista de proyectos: {str(e)}")
        flash('Error al cargar proyectos', 'error')
        return redirect(url_for('index'))

@proyectos_bp.route('/nuevo')
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
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

        response = make_response(render_template('proyectos/detalle.html',
                                               proyecto=proyecto_data['proyecto'],
                                               stats=proyecto_data['stats']))
        
        # Add headers to prevent caching of financial data
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response

    except Exception as e:
        logger.error(f"Error obteniendo proyecto {proyecto_id}: {str(e)}")
        flash('Error al cargar proyecto', 'error')
        return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/<int:proyecto_id>/editar')
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
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
            'estado': p.estado_comercial.value
        } for p in proyectos])

    except Exception as e:
        logger.error(f"Error en API proyectos por cliente: {str(e)}")
        return jsonify({'error': 'Error al cargar proyectos'}), 500

# Add main API endpoint for testing
@proyectos_bp.route('/<int:proyecto_id>/cambiar-estado', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def cambiar_estado(proyecto_id):
    """Cambiar estado comercial de un proyecto"""
    try:
        data = request.get_json()
        nuevo_estado = data.get('estado')
        observacion = data.get('observacion', '')

        if not nuevo_estado:
            return jsonify({'success': False, 'message': 'Estado requerido'}), 400

        # Validate estado is valid
        from models import EstadoComercial
        try:
            estado_enum = EstadoComercial(nuevo_estado)
        except ValueError:
            return jsonify({'success': False, 'message': 'Estado inválido'}), 400

        # Get proyecto
        proyecto = proyectos_service.get_proyecto_by_id(proyecto_id)
        if not proyecto:
            return jsonify({'success': False, 'message': 'Proyecto no encontrado'}), 404

        # Update estado
        update_data = {
            'estado_comercial': nuevo_estado
        }
        if observacion:
            current_notas = proyecto.notas_comerciales or ''
            update_data['notas_comerciales'] = f"{current_notas}\n[{datetime.now().strftime('%d/%m/%Y %H:%M')}] Cambio de estado a {nuevo_estado}: {observacion}".strip()

        proyecto_actualizado = proyectos_service.update_proyecto(proyecto_id, update_data)

        return jsonify({
            'success': True,
            'message': f'Estado cambiado a {nuevo_estado}',
            'nuevo_estado': proyecto_actualizado.estado_comercial.value
        })

    except Exception as e:
        logger.error(f"Error cambiando estado del proyecto {proyecto_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@proyectos_bp.route('/api/', methods=['GET'])
def api_proyectos():
    """API endpoint principal para proyectos - usado en tests"""
    try:
        # Get recent projects for testing
        from repositories.proyectos_repo import ProyectosRepository
        repo = ProyectosRepository()
        proyectos = repo.get_recent_proyectos(limit=10)

        return jsonify({
            'success': True,
            'data': [{
                'id': p.id,
                'nombre': p.nombre,
                'cliente_id': p.cliente_id,
                'estado': p.estado_comercial.value if hasattr(p, 'estado_comercial') else 'PENDIENTE'
            } for p in proyectos]
        })

    except Exception as e:
        logger.error(f"Error en API proyectos: {str(e)}")
        return jsonify({'error': 'Error al cargar proyectos'}), 500

@proyectos_bp.route('/<int:proyecto_id>/adjuntos', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def subir_adjunto(proyecto_id):
    """Upload attachment to project"""
    try:
        if 'archivo' not in request.files:
            return jsonify({'success': False, 'message': 'No se seleccionó archivo'}), 400

        file = request.files['archivo']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'No se seleccionó archivo'}), 400

        tipo = request.form.get('tipo', 'especificacion')
        descripcion = request.form.get('descripcion', '')

        # Validate file type
        allowed_types = ['presupuesto', 'eett', 'especificacion', 'plano', 'contrato', 'foto', 'qa']
        if tipo not in allowed_types:
            tipo = 'especificacion'

        adjunto = proyectos_service.add_project_attachment(
            proyecto_id, file, tipo, descripcion, current_user.id
        )

        return jsonify({
            'success': True,
            'message': 'Documento subido exitosamente',
            'adjunto': {
                'id': adjunto.id,
                'filename': adjunto.filename,
                'tipo': adjunto.tipo.value,
                'descripcion': adjunto.descripcion,
                'created_at': adjunto.created_at.strftime('%d/%m/%Y %H:%M')
            }
        })

    except Exception as e:
        logger.error(f"Error uploading attachment to proyecto {proyecto_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al subir documento: {str(e)}'}), 500

@proyectos_bp.route('/<int:proyecto_id>/adjuntos', methods=['GET'])
@require_login
def get_adjuntos(proyecto_id):
    """Get project attachments"""
    try:
        adjuntos = proyectos_service.get_project_attachments(proyecto_id)

        return jsonify({
            'success': True,
            'adjuntos': [{
                'id': adj.id,
                'filename': adj.filename,
                'tipo': adj.tipo.value,
                'descripcion': adj.descripcion,
                'size_mb': round(adj.size_bytes / 1024 / 1024, 2),
                'created_at': adj.created_at.strftime('%d/%m/%Y %H:%M'),
                'created_by': adj.creator.nombre_completo if adj.creator else 'Usuario desconocido'
            } for adj in adjuntos]
        })

    except Exception as e:
        logger.error(f"Error getting adjuntos for proyecto {proyecto_id}: {str(e)}")
        return jsonify({'success': False, 'message': 'Error al cargar documentos'}), 500

@proyectos_bp.route('/adjuntos/<int:adjunto_id>/descargar')
@require_login
def descargar_adjunto(adjunto_id):
    """Download project attachment"""
    try:
        from repositories.proyecto_adjuntos_repo import ProyectoAdjuntosRepository
        from services.storage_service import StorageService

        adjuntos_repo = ProyectoAdjuntosRepository()
        adjunto = adjuntos_repo.get_by_id(adjunto_id)

        if not adjunto:
            flash('Documento no encontrado', 'error')
            return redirect(url_for('proyectos.index'))

        storage_service = StorageService()
        return storage_service.serve_file(adjunto.storage_key, adjunto.filename)

    except Exception as e:
        logger.error(f"Error downloading adjunto {adjunto_id}: {str(e)}")
        flash('Error al descargar documento', 'error')
        return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/adjuntos/<int:adjunto_id>/eliminar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def eliminar_adjunto(adjunto_id):
    """Delete project attachment"""
    try:
        success = proyectos_service.delete_project_attachment(adjunto_id, current_user.id)

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


@proyectos_bp.route('/<int:proyecto_id>/estados-pago', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
