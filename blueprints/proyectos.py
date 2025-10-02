from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_login import current_user, login_required
from pydantic import ValidationError
from app import db
from replit_auth import require_login, require_role
from utils.auth import require_permission
from models import RolUsuario, Contrato, TipoDocumento
from services.proyectos_service import ProyectosService
from services.clientes_service import ClientesService
from schemas.proyectos import ProyectoCreate, ProyectoUpdate, ProyectoSearchFilters
from schemas.bitacora import BitacoraProyectoCreate, BitacoraFilters
from services.bitacora_service import bitacora_service
from models import Cliente, Proyecto, Contrato, TipoDocumento, EstadoContrato, ProyectoAdjunto, TareaComercial, EstadoComercial
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
        # Handle empty values
        if value == '' or value is None:
            if is_update:
                continue  # Skip empty values in updates
            else:
                processed[key] = None
            continue

        # Handle integer fields
        if key in ['cliente_id', 'numero_viviendas', 'centro_costo']:
            try:
                processed[key] = int(value) if value else None
            except (ValueError, TypeError):
                processed[key] = None

        # Handle decimal fields
        elif key in ['monto_provision_presupuestado', 'margen_venta_provision',
                     'monto_instalacion_presupuestado', 'margen_venta_instalacion',
                     'monto_provision_presupuestado_uf', 'monto_instalacion_presupuestado_uf',
                     'valor_uf_presupuesto']:
            try:
                processed[key] = Decimal(str(value)) if value else None
            except (ValueError, TypeError):
                processed[key] = None

        # Handle date fields
        elif key in ['fecha_inicio', 'fecha_fin_estimada', 'fecha_fin_real',
                     'fecha_presupuesto', 'fecha_adjudicacion', 'fecha_conversion_presupuesto_uf']:
            try:
                processed[key] = datetime.strptime(value, '%Y-%m-%d').date() if value else None
            except ValueError:
                processed[key] = None

        # Handle enum fields
        elif key in ['estado_comercial', 'tipo_proyecto', 'tipo_vivienda', 'moneda_original_presupuesto']:
            processed[key] = value if value else None

        # Handle string fields
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
        clientes = clientes_service.get_active_clientes()

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
            clientes = clientes_service.get_active_clientes()
            # Get active vendors (sales + admin users)
            vendedores = (db.session.query(User)
                         .filter(User.rol.in_([RolUsuario.VENTAS, RolUsuario.ADMIN]))
                         .filter_by(activo=True)
                         .order_by(User.first_name, User.last_name)
                         .all())

            return render_template('proyectos/form.html',
                                 clientes=clientes,
                                 vendedores=vendedores,
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

            # Create project - convert Pydantic model to dict
            proyecto = proyectos_service.create_proyecto(proyecto_data.model_dump(), current_user.id)

            if proyecto:
                flash(f'Proyecto "{proyecto.nombre}" creado exitosamente', 'success')

                # Crear tarea automática si el proyecto tiene vendedor asignado
                if proyecto_data.get('vendedor_id'):
                    from services.comercial_service import ComercialService
                    comercial_service = ComercialService()
                    # Obtener el proyecto recién creado
                    proyecto_creado = (db.session.query(Proyecto)
                                   .filter_by(nombre=proyecto_data['nombre'])
                                   .order_by(Proyecto.created_at.desc())
                                   .first())
                    if proyecto_creado:
                        comercial_service._crear_tarea_automatica(proyecto_creado, current_user.id)
                        db.session.commit()

                return redirect(url_for('proyectos.detalle', proyecto_id=proyecto.id))
            else:
                flash('Error al crear proyecto', 'error')
                return redirect(url_for('proyectos.index'))

        except ValidationError as e:
            logger.warning(f"Validation error creating project: {str(e)}")
            flash('Error de validación en los datos del proyecto', 'error')
            clientes = clientes_service.get_active_clientes()
            # Get active vendors (sales + admin users)
            vendedores = (db.session.query(User)
                         .filter(User.rol.in_([RolUsuario.VENTAS, RolUsuario.ADMIN]))
                         .filter_by(activo=True)
                         .order_by(User.first_name, User.last_name)
                         .all())

            return render_template('proyectos/form.html',
                                 clientes=clientes,
                                 vendedores=vendedores,
                                 proyecto_data=request.form.to_dict(),
                                 current_user=current_user,
                                 title="Nuevo Proyecto")
        except Exception as e:
            logger.error(f"Error creating project: {str(e)}")
            flash('Error al crear proyecto', 'error')
            return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/<int:proyecto_id>')
@require_permission('proyectos:ver')
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS)
def editar(proyecto_id):
    """Editar proyecto"""
    if request.method == 'GET':
        try:
            proyecto = proyectos_service.get_proyecto_by_id(proyecto_id)
            if not proyecto:
                flash('Proyecto no encontrado', 'error')
                return redirect(url_for('proyectos.index'))

            clientes = clientes_service.get_active_clientes()
            # Get active vendors (sales + admin users)
            vendedores = (db.session.query(User)
                         .filter(User.rol.in_([RolUsuario.VENTAS, RolUsuario.ADMIN]))
                         .filter_by(activo=True)
                         .order_by(User.first_name, User.last_name)
                         .all())

            return render_template('proyectos/form.html',
                                 proyecto=proyecto,
                                 clientes=clientes,
                                 vendedores=vendedores,
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

            # Update project - convert Pydantic model to dict (exclude unset/none for partial updates)
            proyecto = proyectos_service.update_proyecto(proyecto_id, proyecto_data.model_dump(exclude_unset=True, exclude_none=True), current_user.id)

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
            clientes = clientes_service.get_active_clientes()
            # Get active vendors (sales + admin users)
            vendedores = (db.session.query(User)
                         .filter(User.rol.in_([RolUsuario.VENTAS, RolUsuario.ADMIN]))
                         .filter_by(activo=True)
                         .order_by(User.first_name, User.last_name)
                         .all())

            return render_template('proyectos/form.html',
                                 proyecto=proyecto,
                                 clientes=clientes,
                                 vendedores=vendedores,
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

        proyecto_nombre = proyecto.nombre
        success = proyectos_service.delete_proyecto(proyecto_id)

        if success:
            flash(f'Proyecto "{proyecto_nombre}" eliminado exitosamente', 'success')
        else:
            flash('Error al eliminar proyecto - puede tener datos relacionados', 'error')

        return redirect(url_for('proyectos.index'))

    except ValueError as ve:
        logger.warning(f"Business rule error deleting project {proyecto_id}: {str(ve)}")
        flash(f'No se puede eliminar el proyecto: {str(ve)}', 'warning')
        return redirect(url_for('proyectos.detalle', proyecto_id=proyecto_id))
    except Exception as e:
        logger.error(f"Error deleting project {proyecto_id}: {str(e)}")
        flash('Error interno al eliminar proyecto', 'error')
        return redirect(url_for('proyectos.detalle', proyecto_id=proyecto_id))

@proyectos_bp.route('/<int:proyecto_id>/adjuntos', methods=['GET', 'POST'])
@require_permission('proyectos:adjuntos')
def adjuntos(proyecto_id):
    """Handle project attachments - GET to list, POST to upload"""
    if request.method == 'GET':
        try:
            adjuntos = proyectos_service.get_project_attachments(proyecto_id)

            adjuntos_data = []
            for adj in adjuntos:
                adjuntos_data.append({
                    'id': adj.id,
                    'filename': adj.filename,
                    'tipo': adj.tipo.value if adj.tipo else 'especificacion',
                    'descripcion': adj.descripcion or '',
                    'size_mb': round(adj.size_bytes / (1024 * 1024), 2) if adj.size_bytes else 0,
                    'created_at': adj.created_at.strftime('%d/%m/%Y %H:%M') if adj.created_at else '',
                    'created_by': adj.created_by_user.nombre_completo if hasattr(adj, 'created_by_user') and adj.created_by_user else adj.created_by
                })

            return jsonify({'success': True, 'adjuntos': adjuntos_data})

        except Exception as e:
            logger.error(f"Error loading adjuntos for proyecto {proyecto_id}: {str(e)}")
            return jsonify({'success': False, 'message': f'Error al cargar documentos: {str(e)}'}), 500

    elif request.method == 'POST':
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
        file_content = storage_service.get_file(adjunto.storage_key)

        response = make_response(file_content)
        response.headers['Content-Disposition'] = f'attachment; filename={adjunto.filename}'
        response.headers['Content-Type'] = adjunto.mime_type or 'application/octet-stream'

        return response

    except Exception as e:
        logger.error(f"Error downloading adjunto {adjunto_id}: {str(e)}")
        flash('Error al descargar documento', 'error')
        return redirect(url_for('proyectos.index'))

@proyectos_bp.route('/adjuntos/<int:adjunto_id>/eliminar', methods=['POST'])
@require_permission('proyectos:adjuntos:eliminar')
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

@proyectos_bp.route('/api/by-cliente/<int:cliente_id>')
@require_login
def api_by_cliente(cliente_id):
    """API endpoint para obtener proyectos por cliente"""
    try:
        proyectos = proyectos_service.get_proyectos_by_cliente(cliente_id)
        return jsonify([{
            'id': p.id,
            'nombre': p.nombre,
            'estado': p.estado_comercial.value if p.estado_comercial else 'sin_estado'
        } for p in proyectos])

    except Exception as e:
        logger.error(f"Error en API proyectos por cliente: {str(e)}")
        return jsonify({'error': 'Error al cargar proyectos'}), 500

@proyectos_bp.route('/api/proyecto-destino/<int:proyecto_id>')
@require_login
def api_proyecto_destino(proyecto_id):
    """API endpoint para obtener información de destino del proyecto"""
    try:
        proyecto = proyectos_service.get_proyecto_by_id(proyecto_id)
        if not proyecto:
            return jsonify({'error': 'Proyecto no encontrado'}), 404

        return jsonify({
            'id': proyecto.id,
            'nombre': proyecto.nombre,
            'ubicacion_obra': proyecto.ubicacion_obra or '',
            'cliente_nombre': proyecto.cliente.nombre if proyecto.cliente else ''
        })

    except Exception as e:
        logger.error(f"Error obteniendo destino del proyecto {proyecto_id}: {str(e)}")
        return jsonify({'error': 'Error al cargar información del proyecto'}), 500

@proyectos_bp.route('/api/<int:proyecto_id>/kpi-cobranza')
@require_login
def api_kpi_cobranza(proyecto_id):
    """API endpoint para obtener KPI de cobranza de un proyecto"""
    # Asegurar que siempre devolvemos JSON con headers correctos
    from flask import jsonify, request

    try:
        # Verificar que el proyecto existe
        proyecto = proyectos_service.get_proyecto_by_id(proyecto_id)
        if not proyecto:
            logger.warning(f"Proyecto {proyecto_id} no encontrado para KPI cobranza")
            response = jsonify({
                'success': False,
                'message': f'Proyecto {proyecto_id} no encontrado',
                'porcentaje_cobrado': 0,
                'porcentaje_facturado': 0,
                'monto_pagado': 0,
                'monto_facturado': 0,
                'monto_contratado': 0,
                'estado': 'sin_datos'
            })
            response.status_code = 404
            response.headers['Content-Type'] = 'application/json'
            return response

        # Calcular KPI financiero directamente usando el método del servicio
        kpi_data = proyectos_service.calculate_financial_kpi_with_treasury(proyecto_id)

        if not kpi_data or kpi_data.get('estado') == 'error':
            logger.warning(f"No se pudo calcular KPI para proyecto {proyecto_id}")
            response = jsonify({
                'success': True,
                'porcentaje_cobrado': 0,
                'porcentaje_facturado': 0,
                'monto_pagado': 0,
                'monto_facturado': 0,
                'monto_contratado': 0,
                'estado': 'sin_datos'
            })
            response.headers['Content-Type'] = 'application/json'
            return response

        response = jsonify({
            'success': True,
            'porcentaje_cobrado': float(kpi_data.get('porcentaje_cobrado', 0)),
            'porcentaje_facturado': float(kpi_data.get('porcentaje_facturado', 0)),
            'monto_pagado': float(kpi_data.get('monto_pagado', 0)),
            'monto_facturado': float(kpi_data.get('monto_facturado', 0)),
            'monto_contratado': float(kpi_data.get('monto_contratado', 0)),
            'estado': kpi_data.get('estado', 'sin_datos')
        })
        response.headers['Content-Type'] = 'application/json'
        return response

    except Exception as e:
        logger.error(f"Error en API KPI cobranza para proyecto {proyecto_id}: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

        # Siempre devolver JSON válido, incluso en caso de error
        response = jsonify({
            'success': False,
            'message': 'Error interno del servidor',
            'error_details': str(e),
            'error_type': type(e).__name__,
            'porcentaje_cobrado': 0,
            'porcentaje_facturado': 0,
            'monto_pagado': 0,
            'monto_facturado': 0,
            'monto_contratado': 0,
            'estado': 'error'
        })
        response.status_code = 500
        response.headers['Content-Type'] = 'application/json'
        return response

@proyectos_bp.route('/<int:proyecto_id>/limpiar-kpi', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def limpiar_kpi(proyecto_id):
    """Limpiar datos de KPI del proyecto"""
    try:
        data = request.get_json()
        tipo = data.get('tipo', 'financiero')

        if tipo == 'financiero':
            # Limpiar estados de pago relacionados al proyecto
            from models import EstadoPago, Contrato
            contratos = Contrato.query.filter_by(proyecto_id=proyecto_id).all()
            estados_eliminados = 0

            for contrato in contratos:
                estados = EstadoPago.query.filter_by(contrato_id=contrato.id).all()
                for estado in estados:
                    db.session.delete(estado)
                    estados_eliminados += 1

            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'KPI financiero limpiado. {estados_eliminados} estados de pago eliminados.',
                'detalles': [f'{estados_eliminados} estados de pago eliminados']
            })

        elif tipo == 'eficiencia':
            # Limpiar progreso de áreas relacionado al proyecto
            from models import OrdenAreaProgreso, OrdenFabricacion
            ordenes = OrdenFabricacion.query.filter_by(proyecto_id=proyecto_id).all()
            progresos_eliminados = 0

            for orden in ordenes:
                progresos = OrdenAreaProgreso.query.filter_by(orden_fabricacion_id=orden.id).all()
                for progreso in progresos:
                    db.session.delete(progreso)
                    progresos_eliminados += 1

            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'KPI de eficiencia limpiado. {progresos_eliminados} registros de progreso eliminados.',
                'detalles': [f'{progresos_eliminados} registros de progreso por área eliminados']
            })

        else:
            return jsonify({'success': False, 'message': 'Tipo de KPI no válido'}), 400

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error limpiando KPI {tipo} del proyecto {proyecto_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al limpiar KPI: {str(e)}'}), 500

@proyectos_bp.route('/<int:proyecto_id>/bitacora', methods=['GET', 'POST'])
@require_login
def bitacora(proyecto_id):
    """Gestión de bitácora del proyecto"""
    if request.method == 'GET':
        try:
            # Verificar que el proyecto existe
            proyecto = proyectos_service.get_proyecto_by_id(proyecto_id)
            if not proyecto:
                return jsonify({'success': False, 'message': 'Proyecto no encontrado'}), 404

            # Obtener filtros de query parameters
            tipo = request.args.get('tipo')
            usuario_id = request.args.get('usuario_id')
            limit = int(request.args.get('limit', 50))

            filters = BitacoraFilters(
                proyecto_id=proyecto_id,
                tipo=tipo,
                usuario_id=usuario_id,
                limit=limit
            )

            comentarios = bitacora_service.get_comentarios_proyecto(filters)

            # Convertir a formato JSON serializable
            comentarios_data = []
            for comentario in comentarios:
                comentarios_data.append({
                    'id': comentario.id,
                    'usuario_nombre': comentario.usuario_nombre,
                    'comentario': comentario.comentario,
                    'tipo': comentario.tipo.value,
                    'fecha_comentario': comentario.fecha_comentario.strftime('%d/%m/%Y %H:%M')
                })

            return jsonify({
                'success': True,
                'comentarios': comentarios_data
            })

        except Exception as e:
            logger.error(f"Error getting bitacora for project {proyecto_id}: {str(e)}")
            return jsonify({'success': False, 'message': f'Error al cargar bitácora: {str(e)}'}), 500

    elif request.method == 'POST':
        try:
            # Verificar que el proyecto existe
            proyecto = proyectos_service.get_proyecto_by_id(proyecto_id)
            if not proyecto:
                return jsonify({'success': False, 'message': 'Proyecto no encontrado'}), 404

            # Validar datos del formulario
            comentario_text = request.form.get('comentario', '').strip()
            tipo = request.form.get('tipo', 'general')

            if not comentario_text:
                return jsonify({'success': False, 'message': 'El comentario es requerido'}), 400

            if len(comentario_text) > 1000:
                return jsonify({'success': False, 'message': 'El comentario no puede superar 1000 caracteres'}), 400

            # Crear comentario
            from models import TipoBitacora
            tipo_enum = TipoBitacora.GENERAL
            if tipo in ['especificacion', 'cambio', 'nota', 'general']:
                tipo_enum = getattr(TipoBitacora, tipo.upper())

            bitacora_data = BitacoraProyectoCreate(
                proyecto_id=proyecto_id,
                comentario=comentario_text,
                tipo=tipo_enum
            )

            comentario = bitacora_service.create_comentario(bitacora_data, current_user.id)

            return jsonify({
                'success': True,
                'message': 'Comentario agregado exitosamente',
                'comentario': {
                    'id': comentario.id,
                    'usuario_nombre': current_user.nombre_completo,
                    'comentario': comentario.comentario,
                    'tipo': comentario.tipo.value,
                    'fecha_comentario': comentario.fecha_comentario.strftime('%d/%m/%Y %H:%M')
                }
            })

        except ValidationError as e:
            logger.warning(f"Validation error creating bitacora comment: {str(e)}")
            return jsonify({'success': False, 'message': 'Error de validación en los datos'}), 400
        except Exception as e:
            logger.error(f"Error creating bitacora comment for project {proyecto_id}: {str(e)}")
            return jsonify({'success': False, 'message': f'Error al agregar comentario: {str(e)}'}), 500

@proyectos_bp.route('/bitacora/<int:comentario_id>/eliminar', methods=['POST'])
@require_login
def eliminar_comentario_bitacora(comentario_id):
    """Eliminar comentario de bitácora"""
    try:
        success = bitacora_service.delete_comentario(comentario_id, current_user.id)

        if success:
            return jsonify({
                'success': True,
                'message': 'Comentario eliminado exitosamente'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No se pudo eliminar el comentario'
            }), 400

    except Exception as e:
        logger.error(f"Error deleting bitacora comment {comentario_id}: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al eliminar comentario: {str(e)}'}), 500