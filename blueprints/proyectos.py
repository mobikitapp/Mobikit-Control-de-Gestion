from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_login import current_user, login_required
from pydantic import ValidationError
from app import db
from replit_auth import require_login, require_role
from models import RolUsuario, Contrato, EstadoFacturacion, TipoDocumento, PendienteFacturar, EstadoPendienteFacturar
from services.proyectos_service import ProyectosService
from services.clientes_service import ClientesService
from services.estados_pago_service import EstadosPagoService
from services.treasury_integration_service import TreasuryIntegrationService
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

# Estados de Pago endpoints
@proyectos_bp.route('/<int:proyecto_id>/estados-pago', methods=['GET'])
@require_login
def get_estados_pago(proyecto_id):
    """Get project payment states"""
    try:
        from services.estados_pago_service import EstadosPagoService
        estados_pago_service = EstadosPagoService()

        estados_pago = estados_pago_service.get_estados_pago_by_proyecto(proyecto_id)

        return jsonify({
            'success': True,
            'estados_pago': [{
                'id': ep.id,
                'tipo': ep.tipo.value,
                'titulo': ep.titulo_display,
                'monto': float(ep.monto_efectivo),
                'estado': ep.estado.value,
                'fecha_programada': ep.fecha_programada.strftime('%d/%m/%Y') if ep.fecha_programada else None,
                'fecha_pago': ep.fecha_pago.strftime('%d/%m/%Y') if ep.fecha_pago else None,
                'observaciones': ep.observaciones,
                'created_at': ep.created_at.strftime('%d/%m/%Y %H:%M')
            } for ep in estados_pago]
        })

    except Exception as e:
        logger.error(f"Error getting estados pago for proyecto {proyecto_id}: {str(e)}")
        return jsonify({'success': False, 'message': 'Error al cargar Tesorería'}), 500

@proyectos_bp.route('/<int:proyecto_id>/estados-pago', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def crear_estado_pago(proyecto_id):
    """Create payment state for project"""
    try:
        from services.estados_pago_service import EstadosPagoService
        from models import TipoEstadoPago
        from decimal import Decimal

        data = request.get_json()
        estados_pago_service = EstadosPagoService()

        tipo = data.get('tipo')

        # Only Contract Payment States are supported now - OCs are handled separately as PendienteFacturar
        if tipo != TipoEstadoPago.ESTADO_PAGO_CONTRATO.value:
            return jsonify({'success': False, 'message': 'Solo se permiten Estados de Pago de Contrato. Las OCs se gestionan automáticamente.'}), 400

        # Create Contract Payment State
        estado_pago = estados_pago_service.create_estado_pago_contrato(
            proyecto_id=proyecto_id,
            contrato_id=data.get('contrato_id'),
            descripcion=data.get('descripcion'),
            porcentaje_avance=Decimal(str(data.get('porcentaje_avance', 0))),
            monto_estado_pago=Decimal(str(data.get('monto_estado_pago', 0))),
            fecha_programada=datetime.strptime(data.get('fecha_programada'), '%Y-%m-%d').date() if data.get('fecha_programada') else None,
            observaciones=data.get('observaciones'),
            created_by=current_user.id
        )

        return jsonify({
            'success': True,
            'message': 'Estado de pago creado exitosamente',
            'estado_pago': {
                'id': estado_pago.id,
                'titulo': estado_pago.titulo_display,
                'monto': float(estado_pago.monto_efectivo),
                'estado': estado_pago.estado.value
            }
        })

    except Exception as e:
        logger.error(f"Error creating estado pago for proyecto {proyecto_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al crear estado de pago: {str(e)}'}), 500

@proyectos_bp.route('/estados-pago/<int:estado_pago_id>/marcar-pagado', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def marcar_estado_pago_pagado(estado_pago_id):
    """Mark payment state as paid"""
    try:
        from services.estados_pago_service import EstadosPagoService

        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict()
        
        estados_pago_service = EstadosPagoService()

        fecha_pago = None
        if data.get('fecha_pago'):
            try:
                fecha_pago = datetime.strptime(data.get('fecha_pago'), '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'message': 'Formato de fecha inválido. Use YYYY-MM-DD'}), 400

        estado_pago = estados_pago_service.marcar_como_pagado(
            estado_pago_id=estado_pago_id,
            fecha_pago=fecha_pago,
            observaciones=data.get('observaciones')
        )

        if not estado_pago:
            return jsonify({'success': False, 'message': 'No se pudo encontrar el estado de pago'}), 404

        return jsonify({
            'success': True,
            'message': 'Estado de pago marcado como pagado',
            'estado_pago': {
                'id': estado_pago.id,
                'estado': estado_pago.estado.value,
                'fecha_pago': estado_pago.fecha_pago.strftime('%d/%m/%Y') if estado_pago.fecha_pago else None
            }
        })

    except Exception as e:
        logger.error(f"Error marking estado pago as paid {estado_pago_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al marcar como pagado: {str(e)}'}), 500

@proyectos_bp.route('/estados-pago')
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def estados_pago_index():
    """Tesorería - Lista de proyectos agrupados por cliente y contratos pendientes"""
    try:
        from services.estados_pago_service import EstadosPagoService
        from services.treasury_integration_service import TreasuryIntegrationService
        
        estados_pago_service = EstadosPagoService()
        treasury_service = TreasuryIntegrationService()
        
        # Get all projects with payment states grouped by client
        proyectos_por_cliente = treasury_service.get_projects_grouped_by_client()
        
        # Get contracts that need manual treasury state creation (only CONTRATOS)
        contratos_pendientes = treasury_service.get_contracts_without_treasury_states()
        
        # Get OCs as pending invoices (separate concept)
        pendientes_facturar = treasury_service.get_pending_invoices()
        
        # Get clients with contracts data for the dropdown functionality
        clientes_contratos = []
        clientes = clientes_service.get_active_clientes()
        
        for cliente in clientes:
            # Get active projects for this client
            proyectos_activos = [p for p in cliente.proyectos 
                               if p.estado_comercial and p.estado_comercial.value in ['EN_DESARROLLO', 'ADJUDICADO']]
            
            if proyectos_activos:
                # Count active projects
                count_proyectos_activos = len(proyectos_activos)
                
                clientes_contratos.append({
                    'cliente': cliente,
                    'proyectos_activos': proyectos_activos,
                    'count_proyectos_activos': count_proyectos_activos
                })
        
        return render_template('proyectos/estados_pago_index.html', 
                             proyectos_por_cliente=proyectos_por_cliente,
                             contratos_pendientes=contratos_pendientes,
                             pendientes_facturar=pendientes_facturar,
                             clientes_contratos=clientes_contratos,
                             title="Tesorería")
        
    except Exception as e:
        logger.error(f"Error loading estados pago index: {str(e)}")
        flash('Error al cargar Tesorería', 'error')
        return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/estados-pago/<int:proyecto_id>')
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def estados_pago_detalle(proyecto_id):
    """Estados de Pago - Detalle de un proyecto específico con estructura jerárquica"""
    try:
        from services.treasury_integration_service import TreasuryIntegrationService
        from services.estados_pago_service import EstadosPagoService
        
        treasury_service = TreasuryIntegrationService()
        estados_pago_service = EstadosPagoService()

        # Get structured project treasury data
        proyecto_data = treasury_service.get_project_treasury_detail(proyecto_id)
        if not proyecto_data:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('proyectos.estados_pago_index'))

        # Get all payment states for legacy compatibility (used in modal)
        estados_pago = estados_pago_service.get_estados_pago_by_proyecto(proyecto_id)
        
        # Get all contracts for modal dropdown (legacy)
        contratos_legacy = []
        if proyecto_data.get('contratos'):
            contratos_legacy.extend([c['contrato'] for c in proyecto_data['contratos']])
        if proyecto_data.get('ordenes_compra'):
            contratos_legacy.extend([oc['oc'] for oc in proyecto_data['ordenes_compra']])

        return render_template('proyectos/estados_pago_detalle.html',
                             proyecto_data=proyecto_data,
                             proyecto=proyecto_data.get('proyecto'),
                             cliente=proyecto_data.get('cliente'),
                             estados_pago=estados_pago,
                             contratos=contratos_legacy,
                             title=f"Estados de Pago - {proyecto_data.get('proyecto', {}).nombre if proyecto_data.get('proyecto') else 'Proyecto'}")

    except Exception as e:
        logger.error(f"Error loading estados pago detalle for proyecto {proyecto_id}: {str(e)}")
        flash('Error al cargar detalle de Tesorería', 'error')
        return redirect(url_for('proyectos.estados_pago_index'))

@proyectos_bp.route('/dashboard-financiero')
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def dashboard_financiero():
    """Dashboard de seguimiento financiero integral - Fase 1"""
    try:
        from services.contratos_financial_service import ContratosFinancialService
        financial_service = ContratosFinancialService()

        # Obtener resumen de cartera general
        portfolio_summary = financial_service.get_portfolio_summary()

        # Obtener contratos pendientes de facturación
        pending_invoicing = financial_service.get_contracts_requiring_invoicing()

        # Obtener proyectos con resúmenes financieros (top 10)
        from services.proyectos_service import ProyectosService
        proyectos_service = ProyectosService()

        # Obtener proyectos recientes para mostrar sus resúmenes financieros
        from schemas.proyectos import ProyectoSearchFilters
        filters = ProyectoSearchFilters(page=1, per_page=10)
        proyectos, _ = proyectos_service.search_proyectos(filters)

        # Enriquecer cada proyecto con su resumen financiero
        proyectos_financieros = []
        for proyecto in proyectos:
            resumen_financiero = financial_service.get_financial_summary_by_project(proyecto.id)
            proyectos_financieros.append({
                'proyecto': proyecto,
                'resumen': resumen_financiero
            })

        return render_template('proyectos/dashboard_financiero.html',
                             portfolio_summary=portfolio_summary,
                             pending_invoicing=pending_invoicing,
                             proyectos_financieros=proyectos_financieros,
                             title="Dashboard Financiero")

    except Exception as e:
        logger.error(f"Error loading dashboard financiero: {str(e)}")
        flash('Error al cargar dashboard financiero', 'error')
        return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/estados-pago/<int:estado_pago_id>/marcar-facturado', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def marcar_facturado(estado_pago_id):
    """Mark payment state as invoiced"""
    try:
        from services.estados_pago_service import EstadosPagoService
        from datetime import datetime, date

        data = request.get_json()
        estados_pago_service = EstadosPagoService()

        # Mark as invoiced
        success = estados_pago_service.marcar_como_facturado(
            estado_pago_id=estado_pago_id,
            numero_factura=data.get('numero_factura'),
            updated_by=current_user.id if current_user else 'system'
        )

        if success:
            return jsonify({
                'success': True,
                'message': 'Estado marcado como facturado exitosamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Error al marcar como facturado'
            }), 500

    except Exception as e:
        logger.error(f"Error marking estado pago as invoiced {estado_pago_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al marcar como facturado: {str(e)}'}), 500

@proyectos_bp.route('/sync-financial-totals/<int:proyecto_id>', methods=['POST'])
@require_role(RolUsuario.ADMIN)
def sync_financial_totals(proyecto_id):
    """Sync financial totals for all contracts in a project - temporary fix endpoint"""
    try:
        from services.estados_pago_service import EstadosPagoService
        
        estados_pago_service = EstadosPagoService()
        updated_count = estados_pago_service.sync_all_contracts_for_project(proyecto_id)
        
        return jsonify({
            'success': True, 
            'message': f'Synchronized {updated_count} contracts for project {proyecto_id}'
        })
        
    except Exception as e:
        logger.error(f"Error syncing financial totals for project {proyecto_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error syncing: {str(e)}'}), 500

@proyectos_bp.route('/estados-pago/<int:estado_pago_id>/sync-status', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def sync_payment_state_status(estado_pago_id):
    """Sync payment state status and contract totals - fix inconsistencies"""
    try:
        from services.estados_pago_service import EstadosPagoService
        
        estados_pago_service = EstadosPagoService()
        estado_pago = estados_pago_service.get_estado_pago_by_id(estado_pago_id)
        
        if not estado_pago:
            return jsonify({'success': False, 'message': 'Estado de pago no encontrado'}), 404
        
        # Force update contract financial totals
        if estado_pago.contrato_id:
            estados_pago_service._update_contract_financial_totals(estado_pago.contrato_id)
            db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Estado de pago sincronizado correctamente',
            'estado_pago': {
                'id': estado_pago.id,
                'estado': estado_pago.estado.value,
                'facturado': estado_pago.facturado,
                'fecha_pago': estado_pago.fecha_pago.strftime('%d/%m/%Y') if estado_pago.fecha_pago else None
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error syncing payment state {estado_pago_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error sincronizando: {str(e)}'}), 500

@proyectos_bp.route('/estados-pago/<int:estado_pago_id>', methods=['DELETE'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def eliminar_estado_pago(estado_pago_id):
    """Delete payment state"""
    try:
        from services.estados_pago_service import EstadosPagoService
        estados_pago_service = EstadosPagoService()

        success = estados_pago_service.delete_estado_pago(estado_pago_id)

        if success:
            return jsonify({'success': True, 'message': 'Estado de pago eliminado exitosamente'})
        else:
            return jsonify({'success': False, 'message': 'Error al eliminar estado de pago'}), 500

    except Exception as e:
        logger.error(f"Error deleting estado pago {estado_pago_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al eliminar estado de pago: {str(e)}'}), 500

@proyectos_bp.route('/contratos/<int:contrato_id>/crear-estados-tesoreria', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def crear_estados_tesoreria_contrato(contrato_id):
    """Crear estados de pago en tesorería para un contrato existente"""
    try:
        from services.treasury_integration_service import TreasuryIntegrationService
        treasury_service = TreasuryIntegrationService()

        # Create treasury states for existing contract
        estados_creados = treasury_service.create_states_for_existing_contract(
            contrato_id=contrato_id,
            created_by=current_user.id
        )

        if estados_creados:
            return jsonify({
                'success': True,
                'message': f'{len(estados_creados)} estados de pago creados exitosamente en tesorería',
                'estados_creados': len(estados_creados)
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudieron crear estados de pago (es posible que ya existan)'
            }), 400

    except Exception as e:
        logger.error(f"Error creando estados tesorería para contrato {contrato_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al crear estados de tesorería: {str(e)}'}), 500

@proyectos_bp.route('/pendientes-facturar/<int:pendiente_id>/marcar-facturado', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def marcar_pendiente_facturado(pendiente_id):
    """Marcar un pendiente de facturar como facturado"""
    try:
        from services.treasury_integration_service import TreasuryIntegrationService
        from models import EstadoPendienteFacturar
        treasury_service = TreasuryIntegrationService()

        data = request.get_json() or {}
        numero_factura = data.get('numero_factura', '')

        success = treasury_service.update_pending_invoice_status(
            pendiente_id=pendiente_id,
            nuevo_estado=EstadoPendienteFacturar.FACTURADO,
            updated_by=current_user.id,
            numero_factura=numero_factura
        )

        if success:
            return jsonify({
                'success': True,
                'message': 'OC marcada como facturada exitosamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudo actualizar el estado de la OC'
            }), 400

    except Exception as e:
        logger.error(f"Error marcando OC {pendiente_id} como facturada: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al marcar como facturada: {str(e)}'}), 500

@proyectos_bp.route('/pendientes-facturar/<int:pendiente_id>/marcar-pagado', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def marcar_pendiente_pagado(pendiente_id):
    """Marcar un pendiente de facturar como pagado"""
    try:
        from services.treasury_integration_service import TreasuryIntegrationService
        from models import EstadoPendienteFacturar
        treasury_service = TreasuryIntegrationService()

        success = treasury_service.update_pending_invoice_status(
            pendiente_id=pendiente_id,
            nuevo_estado=EstadoPendienteFacturar.PAGADO,
            updated_by=current_user.id
        )

        if success:
            return jsonify({
                'success': True,
                'message': 'OC marcada como pagada exitosamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudo actualizar el estado de la OC'
            }), 400

    except Exception as e:
        logger.error(f"Error marcando OC {pendiente_id} como pagada: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al marcar como pagada: {str(e)}'}), 500

@proyectos_bp.route('/estados-pago/<int:estado_pago_id>/marcar-facturado', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def marcar_estado_pago_facturado(estado_pago_id):
    """Marcar un estado de pago como facturado"""
    try:
        from services.estados_pago_service import EstadosPagoService
        estados_pago_service = EstadosPagoService()

        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json() or {}
        else:
            data = request.form.to_dict()
            
        numero_factura = data.get('numero_factura', '')

        if not numero_factura.strip():
            return jsonify({
                'success': False,
                'message': 'El número de factura es requerido'
            }), 400

        # Verificar que el estado de pago existe
        estado_pago = estados_pago_service.get_estado_pago_by_id(estado_pago_id)
        if not estado_pago:
            return jsonify({
                'success': False,
                'message': 'Estado de pago no encontrado'
            }), 404

        # Verificar que no esté ya facturado
        if hasattr(estado_pago, 'facturado') and estado_pago.facturado:
            return jsonify({
                'success': False,
                'message': 'El estado de pago ya está marcado como facturado'
            }), 400

        # Update payment state as invoiced
        success = estados_pago_service.marcar_como_facturado(
            estado_pago_id=estado_pago_id,
            numero_factura=numero_factura,
            updated_by=current_user.id if current_user else 'system'
        )

        if success:
            return jsonify({
                'success': True,
                'message': f'Estado de pago marcado como facturado (Factura: {numero_factura})'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudo marcar el estado de pago como facturado'
            }), 500

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error marcando estado de pago {estado_pago_id} como facturado: {str(e)}")
        return jsonify({'success': False, 'message': f'Error interno: {str(e)}'}), 500

@proyectos_bp.route('/api/<int:proyecto_id>/contratos')
@login_required
def api_get_contratos(proyecto_id):
    """API: Get contracts for a project"""
    try:
        contratos = Contrato.query.filter_by(proyecto_id=proyecto_id).all()
        return jsonify([{
            'id': c.id,
            'numero_oc': c.numero_oc,
            'monto_total': float(c.monto_total) if c.monto_total else 0,
            'estado': c.estado.value
        } for c in contratos])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@proyectos_bp.route('/estados-pago/marcar-facturado/<int:contrato_id>', methods=['POST'])
@login_required
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES)
def marcar_contrato_facturado(contrato_id):
    """API: Mark contract as invoiced"""
    try:
        from services.contratos_service import ContratosService

        service = ContratosService()
        contrato = Contrato.query.get_or_404(contrato_id)

        # Update invoice status
        if contrato.tipo_documento == TipoDocumento.ORDEN_COMPRA:
            # For OCs, update the pending invoice status
            treasury_service = TreasuryIntegrationService()
            pendiente = PendienteFacturar.query.filter_by(contrato_id=contrato_id).first()

            if pendiente:
                success = treasury_service.update_pending_invoice_status(
                    pendiente.id,
                    EstadoPendienteFacturar.FACTURADO,
                    current_user.id
                )
                if success:
                    return jsonify({
                        'success': True,
                        'message': f'OC {contrato.numero_oc} marcada como facturada'
                    })
            else:
                return jsonify({
                    'success': False,
                    'message': 'No se encontró registro en pendientes de facturar'
                }), 404
        else:
            # For contracts, update contract status
            contrato.estado_facturacion = EstadoFacturacion.FACTURADO
            contrato.monto_facturado = contrato.monto_total
            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'Contrato {contrato.numero_oc} marcado como facturado'
            })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Error al marcar como facturado: {str(e)}'
        }), 500
@proyectos_bp.route('/<int:proyecto_id>/debug-financial-status')
@require_role(RolUsuario.ADMIN)
def debug_financial_status(proyecto_id):
    """Debug endpoint to check financial status calculations"""
    try:
        from services.treasury_integration_service import TreasuryIntegrationService
        from services.estados_pago_service import EstadosPagoService
        
        treasury_service = TreasuryIntegrationService()
        estados_service = EstadosPagoService()
        
        # Get project data
        proyecto_data = treasury_service.get_project_treasury_detail(proyecto_id)
        
        # Get financial KPI
        kpi_data = proyectos_service.get_proyecto_with_stats(proyecto_id)
        
        debug_info = {
            'proyecto_id': proyecto_id,
            'proyecto_data_treasury': {
                'contratos_count': len(proyecto_data.get('contratos', [])),
                'ocs_count': len(proyecto_data.get('ordenes_compra', [])),
                'resumen_financiero': proyecto_data.get('resumen_financiero', {})
            },
            'kpi_data': kpi_data.get('stats', {}) if kpi_data else {},
            'raw_treasury_data': proyecto_data
        }
        
        return jsonify({
            'success': True,
            'debug_info': debug_info
        })
        
    except Exception as e:
        logger.error(f"Error en debug financial status {proyecto_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
