from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from pydantic import ValidationError
from app import db
from replit_auth import require_login, require_role
from models import RolUsuario
from services.despachos_service import DespachosService
from services.planificacion_despachos_service import PlanificacionDespachosService
from services.proyectos_service import ProyectosService
from services.fabricacion_service import FabricacionService
from services.clientes_service import ClientesService
# Importar el servicio de contratos (asumiendo que existe)
from services.contratos_service import ContratosService
from schemas.despachos import (DespachoCreate, DespachoUpdate, DespachoSearchFilters,
                             CambioEstadoDespacho)
from repositories.despachos_repo import DespachosRepository
from repositories.proyectos_repo import ProyectosRepository
from repositories.contratos_repo import ContratosRepository
from repositories.fabricacion_repo import FabricacionRepository
from sqlalchemy.orm import joinedload
import logging
import json # Ensure json is imported

logger = logging.getLogger(__name__)

despachos_bp = Blueprint('despachos', __name__)
despachos_service = DespachosService()
planificacion_service = PlanificacionDespachosService()
proyectos_service = ProyectosService()
fabricacion_service = FabricacionService()
clientes_service = ClientesService()
contratos_service = ContratosService() # Instanciar el servicio de contratos
despachos_repo = DespachosRepository()
proyectos_repo = ProyectosRepository()
contratos_repo = ContratosRepository()
fabrication_repo = FabricacionRepository()

@despachos_bp.route('/api/contratos/by-cliente/<int:cliente_id>')
@require_login
def api_contratos_by_cliente(cliente_id):
    """API endpoint to get contratos by cliente"""
    try:
        contratos = contratos_service.get_contratos_by_cliente(cliente_id)
        return jsonify([{
            'id': c.id,
            'numero_oc': c.numero_oc,
            'estado': c.estado.value if hasattr(c.estado, 'value') else str(c.estado),
            'proyecto_nombre': c.proyecto.nombre if c.proyecto else 'Sin proyecto'
        } for c in contratos])
    except Exception as e:
        logger.error(f"Error loading contratos for cliente {cliente_id}: {str(e)}")
        return jsonify({'error': 'Error al cargar contratos'}), 500

@despachos_bp.route('/api/fabricacion/by_proyecto/<int:proyecto_id>')
@require_login
def api_fabricacion_by_proyecto(proyecto_id):
    """API endpoint to get órdenes de fabricación by proyecto"""
    try:
        ofs = fabricacion_service.get_by_proyecto(proyecto_id)
        return jsonify([{
            'id': of.id,
            'codigo': of.codigo,
            'descripcion': of.descripcion or 'Sin descripción',
            'cantidad_total': of.cantidad_tableros or 0,
            'estado': of.estado_actual.nombre if of.estado_actual else 'Sin estado'
        } for of in ofs])
    except Exception as e:
        logger.error(f"Error loading OFs for proyecto {proyecto_id}: {str(e)}")
        return jsonify({'error': 'Error al cargar órdenes de fabricación'}), 500

@despachos_bp.route('/api/fabricacion/by_contrato/<int:contrato_id>')
@require_login
def api_fabricacion_by_contrato(contrato_id):
    """API endpoint to get órdenes de fabricación disponibles para despacho por contrato"""
    try:
        ofs_disponibles = fabricacion_service.get_ofs_disponibles_para_despacho(contrato_id)
        return jsonify([{
            'id': of.id,
            'codigo': of.codigo,
            'descripcion': of.descripcion or 'Sin descripción',
            'cantidad_total': of.cantidad_tableros or 0,
            'cantidad_despachada_previa': getattr(of, 'cantidad_despachada_previa', 0),
            'cantidad_disponible': getattr(of, 'cantidad_disponible_despacho', of.cantidad_tableros or 0),
            'tiene_despachos_parciales': getattr(of, 'tiene_despachos_parciales', False),
            'estado': getattr(of, 'estado_actual_nombre', 'Sin estado'),
            'area': getattr(of, 'area_actual_nombre', 'Sin área')
        } for of in ofs_disponibles])
    except Exception as e:
        logger.error(f"Error loading OFs for contrato {contrato_id}: {str(e)}")
        return jsonify({'error': 'Error al cargar órdenes de fabricación'}), 500

@despachos_bp.route('/api/fabricacion/by_hito/<int:hito_id>')
@require_login
def api_fabricacion_by_hito(hito_id):
    """API endpoint to get órdenes de fabricación disponibles para despacho por hito"""
    try:
        ofs_disponibles = planificacion_service._get_ofs_disponibles_para_hito(hito_id)
        return jsonify(ofs_disponibles)
    except Exception as e:
        logger.error(f"Error loading OFs for hito {hito_id}: {str(e)}")
        return jsonify({'error': 'Error al cargar órdenes de fabricación'}), 500


@despachos_bp.route('/')
@require_login
def index():
    """Lista de despachos con filtros"""
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

        if request.args.get('of_id'):
            try:
                filters_data['of_id'] = int(request.args.get('of_id'))
            except (ValueError, TypeError):
                pass

        if request.args.get('numero_despacho', '').strip():
            filters_data['numero_despacho'] = request.args.get('numero_despacho').strip()

        if request.args.get('estado', '').strip():
            filters_data['estado'] = request.args.get('estado').strip()

        if request.args.get('responsable_nombre', '').strip():
            filters_data['responsable_nombre'] = request.args.get('responsable_nombre').strip()

        if request.args.get('fecha_programada_desde', '').strip():
            filters_data['fecha_programada_desde'] = request.args.get('fecha_programada_desde').strip()

        if request.args.get('fecha_programada_hasta', '').strip():
            filters_data['fecha_programada_hasta'] = request.args.get('fecha_programada_hasta').strip()

        # Validate filters
        filters = DespachoSearchFilters(**filters_data)

        # Search despachos
        despachos, total_count = despachos_service.search_despachos(filters)

        # Get data for filter dropdowns
        clientes = clientes_service.get_active_clientes()
        # Obtener contratos para el filtro (se podría mejorar para filtrar por cliente si se selecciona)
        contratos = contratos_service.get_all_contratos()

        # Calculate pagination
        total_pages = (total_count + filters.per_page - 1) // filters.per_page
        has_prev = filters.page > 1
        has_next = filters.page < total_pages

        return render_template('despachos/index.html',
                             despachos=despachos,
                             clientes=clientes,
                             contratos=contratos, # Pasar contratos a la plantilla
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def nuevo():
    """Formulario para nuevo despacho"""
    try:
        clientes = clientes_service.get_active_clientes()
        # Para el formulario de creación, no es necesario cargar todos los contratos aún,
        # se cargarán dinámicamente por cliente.
        return render_template('despachos/form.html',
                             despacho=None,
                             clientes=clientes,
                             contratos=None, # Inicialmente sin contratos
                             title="Nuevo Despacho")
    except Exception as e:
        logger.error(f"Error cargando formulario nuevo despacho: {str(e)}")
        flash('Error al cargar formulario', 'error')
        return redirect(url_for('despachos.index'))

@despachos_bp.route('/crear', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def crear():
    """Crear nuevo despacho"""
    try:
        # Validar y limpiar datos del formulario
        form_data = request.form.to_dict()

        # Clean empty strings to None for optional integer fields
        if 'hito_entrega_id' in form_data and form_data['hito_entrega_id'] == '':
            form_data['hito_entrega_id'] = None

        if 'contrato_id' in form_data and form_data['contrato_id'] == '':
            form_data['contrato_id'] = None

        # Clean empty numero_despacho to let it be auto-generated
        if 'numero_despacho' in form_data and form_data['numero_despacho'].strip() == '':
            form_data['numero_despacho'] = ''  # Will be auto-generated in service

        # Lógica para determinar si se usa proyecto o contrato
        if 'contrato_id' in form_data and form_data['contrato_id']:
            # Convert estado to uppercase for enum compatibility
            if 'estado' in form_data:
                form_data['estado'] = form_data['estado'].upper()

            # Process selected_ofs if provided
            ordenes_fabricacion = []
            if 'selected_ofs' in form_data and form_data['selected_ofs']:
                try:
                    selected_ofs = json.loads(form_data['selected_ofs'])

                    for of_data in selected_ofs:
                        if of_data.get('of_id'):
                            # Get OF details to determine cantidad_total
                            of = fabrication_repo.get_by_id(int(of_data['of_id']))
                            if of:
                                # For total dispatch, use all tableros; for partial, use specified cantidad
                                tipo_despacho = of_data.get('tipo_despacho', 'TOTAL').upper()

                                if tipo_despacho == 'TOTAL':
                                    cantidad_despachada = of.cantidad_tableros or 1
                                else:
                                    cantidad_despachada = float(of_data.get('cantidad_despachada', 1))

                                ordenes_fabricacion.append({
                                    'orden_fabricacion_id': of.id,
                                    'tipo_despacho': tipo_despacho,
                                    'cantidad_despachada': cantidad_despachada,
                                    'cantidad_total': of.cantidad_tableros or 1,
                                    'observaciones': of_data.get('observaciones', '')
                                })

                    # Remove the processed selected_ofs field
                    del form_data['selected_ofs']

                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    logger.error(f"Error procesando selected_ofs: {e}")
                    flash('Error procesando las órdenes de fabricación seleccionadas', 'danger')
                    return redirect(url_for('despachos.nuevo'))

            # Set ordenes_fabricacion (can be empty for generic dispatches)
            form_data['ordenes_fabricacion'] = ordenes_fabricacion


            # Clean up dynamic form fields that aren't part of the schema
            fields_to_remove = []
            for key in form_data.keys():
                if key.startswith('tipo_despacho_') or key.startswith('cantidad_'):
                    fields_to_remove.append(key)

            for field in fields_to_remove:
                del form_data[field]

            # Parse and validate form data using Pydantic
            despacho_data = DespachoCreate(**form_data)
            # Asociar OFs seleccionadas al despacho
            # of_ids = request.form.getlist('ordenes_fabricacion') # This line is no longer needed as 'ordenes_fabricacion' is now a processed list
            # despacho_data.ordenes_fabricacion_ids = [int(id) for id in of_ids] # This line is no longer needed
        elif 'proyecto_id' in form_data and form_data['proyecto_id']:
            # Clean empty strings for this case as well
            if 'hito_entrega_id' in form_data and form_data['hito_entrega_id'] == '':
                del form_data['hito_entrega_id']

            if 'contrato_id' in form_data and form_data['contrato_id'] == '':
                del form_data['contrato_id']

            # Convert estado to uppercase for enum compatibility
            if 'estado' in form_data:
                form_data['estado'] = form_data['estado'].upper()

            # Process selected_ofs if provided
            ordenes_fabricacion = []
            if 'selected_ofs' in form_data and form_data['selected_ofs']:
                try:
                    selected_ofs = json.loads(form_data['selected_ofs'])

                    for of_data in selected_ofs:
                        if of_data.get('of_id'):
                            # Get OF details to determine cantidad_total
                            of = fabrication_repo.get_by_id(int(of_data['of_id']))
                            if of:
                                # For total dispatch, use all tableros; for partial, use specified cantidad
                                tipo_despacho = of_data.get('tipo_despacho', 'TOTAL').upper()

                                if tipo_despacho == 'TOTAL':
                                    cantidad_despachada = of.cantidad_tableros or 1
                                else:
                                    cantidad_despachada = float(of_data.get('cantidad_despachada', 1))

                                ordenes_fabricacion.append({
                                    'orden_fabricacion_id': of.id,
                                    'tipo_despacho': tipo_despacho,
                                    'cantidad_despachada': cantidad_despachada,
                                    'cantidad_total': of.cantidad_tableros or 1,
                                    'observaciones': of_data.get('observaciones', '')
                                })

                    # Remove the processed selected_ofs field
                    del form_data['selected_ofs']

                except (json.JSONDecodeError, ValueError, KeyError) as e:
                    logger.error(f"Error procesando selected_ofs: {e}")
                    flash('Error procesando las órdenes de fabricación seleccionadas', 'danger')
                    return redirect(url_for('despachos.nuevo'))

            # Set ordenes_fabricacion (can be empty for generic dispatches)
            form_data['ordenes_fabricacion'] = ordenes_fabricacion


            # Clean up dynamic form fields that aren't part of the schema
            fields_to_remove = []
            for key in form_data.keys():
                if key.startswith('tipo_despacho_') or key.startswith('cantidad_'):
                    fields_to_remove.append(key)

            for field in fields_to_remove:
                del form_data[field]

            # Parse and validate form data using Pydantic
            despacho_data = DespachoCreate(**form_data)
            # Asociar OFs seleccionadas al despacho
            # of_ids = request.form.getlist('ordenes_fabricacion') # This line is no longer needed as 'ordenes_fabricacion' is now a processed list
            # despacho_data.ordenes_fabricacion_ids = [int(id) for id in of_ids] # This line is no longer needed
        else:
            flash('Debe seleccionar un contrato o un proyecto', 'error')
            clientes = clientes_service.get_active_clientes()
            return render_template('despachos/form.html',
                                 despacho=None,
                                 clientes=clientes,
                                 contratos=None,
                                 title="Nuevo Despacho")


        # Manejar subida de archivos
        archivos = request.files.getlist('archivos')

        # Crear despacho con archivos
        despacho = despachos_service.create_despacho_with_files(
            despacho_data.dict(),
            archivos,
            current_user.id
        )

        flash(f'Despacho {despacho.numero_despacho} creado exitosamente', 'success')
        return redirect(url_for('despachos.detalle', despacho_id=despacho.id))

    except ValidationError as e:
        logger.error(f"ValidationError al crear despacho: {e.errors()}")
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
        clientes = clientes_service.get_active_clientes()
        # Intentar recuperar los datos del formulario para volver a mostrarlos
        return render_template('despachos/form.html',
                             despacho=None,
                             clientes=clientes,
                             contratos=None, # Si hubo error, limpiar contratos
                             title="Nuevo Despacho")
    except Exception as e:
        logger.error(f"Error creando despacho: {str(e)}")
        flash('Error al crear despacho', 'error')
        clientes = clientes_service.get_active_clientes()
        return render_template('despachos/form.html',
                             despacho=None,
                             clientes=clientes,
                             contratos=None,
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

        # Asumiendo que el modelo Despacho tiene un campo 'responsable_usuario' que es un objeto Usuario
        # Si solo tiene el ID, se necesitaría obtener el nombre del usuario aquí.
        # Si 'responsable' es solo el nombre, no se necesita hacer nada.
        # Para este ejemplo, asumimos que 'responsable' en el modelo es el nombre.

        return render_template('despachos/detalle.html', despacho=despacho)

    except Exception as e:
        logger.error(f"Error obteniendo despacho {despacho_id}: {str(e)}")
        flash('Error al cargar despacho', 'error')
        return redirect(url_for('despachos.index'))

@despachos_bp.route('/<int:despacho_id>/editar')
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def editar(despacho_id):
    """Formulario de edición de despacho"""
    try:
        despacho = despachos_service.get_despacho_by_id(despacho_id)
        if not despacho:
            flash('Despacho no encontrado', 'error')
            return redirect(url_for('despachos.index'))

        clientes = clientes_service.get_active_clientes()
        # Cargar contratos asociados al cliente del despacho, si existe
        contratos = []
        if despacho.proyecto and despacho.proyecto.cliente_id:
            contratos = contratos_service.get_contratos_by_cliente(despacho.proyecto.cliente_id)

        # Cargar OFs asociadas al contrato del despacho, si existe
        ordenes_fabricacion = []
        if despacho.contrato_id:
            ordenes_fabricacion = fabricacion_service.get_ordenes_by_contrato(despacho.contrato_id)

        return render_template('despachos/form.html',
                             despacho=despacho,
                             clientes=clientes,
                             contratos=contratos, # Pasar contratos a la plantilla
                             ordenes_fabricacion=ordenes_fabricacion, # Pasar OFs a la plantilla
                             title=f"Editar Despacho - {despacho.numero_despacho}")

    except Exception as e:
        logger.error(f"Error obteniendo despacho para editar {despacho_id}: {str(e)}")
        flash('Error al cargar despacho', 'error')
        return redirect(url_for('despachos.index'))

@despachos_bp.route('/<int:despacho_id>/actualizar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def actualizar(despacho_id):
    """Actualizar despacho existente"""
    try:
        despacho = despachos_service.get_despacho_by_id(despacho_id)
        if not despacho:
            flash('Despacho no encontrado', 'error')
            return redirect(url_for('despachos.index'))

        # Validar y limpiar datos del formulario
        form_data = request.form.to_dict()

        # Clean empty strings to None for optional integer fields
        if 'hito_entrega_id' in form_data and form_data['hito_entrega_id'] == '':
            form_data['hito_entrega_id'] = None

        if 'contrato_id' in form_data and form_data['contrato_id'] == '':
            form_data['contrato_id'] = None

        # Validar datos del formulario
        update_data = DespachoUpdate(**form_data)

        # Manejar la actualización de las órdenes de fabricación asociadas si es necesario
        # Esto podría implicar eliminar las existentes y agregar las nuevas, o una lógica más compleja.
        # Por ahora, asumimos que las OFs no se modifican directamente desde este formulario o se manejan de otra manera.

        # Actualizar despacho
        despacho_actualizado = despachos_service.update_despacho(despacho_id, update_data.dict(exclude_unset=True))

        flash(f'Despacho {despacho_actualizado.numero_despacho} actualizado exitosamente', 'success')
        return redirect(url_for('despachos.detalle', despacho_id=despacho_id))

    except ValidationError as e:
        logger.error(f"ValidationError al actualizar despacho {despacho_id}: {e.errors()}")
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
        clientes = clientes_service.get_active_clientes()
        # Intentar recuperar los contratos y OFs para el formulario de edición
        contratos = []
        if despacho.proyecto and despacho.proyecto.cliente_id:
            contratos = contratos_service.get_contratos_by_cliente(despacho.proyecto.cliente_id)
        ordenes_fabricacion = []
        if despacho.contrato_id:
            ordenes_fabricacion = fabricacion_service.get_ordenes_by_contrato(despacho.contrato_id)

        return render_template('despachos/form.html',
                             despacho=despacho,
                             clientes=clientes,
                             contratos=contratos,
                             ordenes_fabricacion=ordenes_fabricacion,
                             title=f"Editar Despacho - {despacho.numero_despacho}")
    except Exception as e:
        logger.error(f"Error actualizando despacho {despacho_id}: {str(e)}")
        flash('Error al actualizar despacho', 'error')
        return redirect(url_for('despachos.detalle', despacho_id=despacho_id))

@despachos_bp.route('/<int:despacho_id>/cambiar-estado', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def cambiar_estado(despacho_id):
    """Cambiar estado del despacho"""
    try:
        # Validar datos de la solicitud
        cambio_data = CambioEstadoDespacho(**request.form.to_dict())

        success = despachos_service.change_despacho_status(despacho_id, cambio_data.nuevo_estado, cambio_data.observaciones)
        if success:
            flash('Estado del despacho actualizado exitosamente', 'success')
        else:
            flash('Error al cambiar estado del despacho', 'error')

    except ValidationError as e:
        logger.error(f"ValidationError al cambiar estado de despacho {despacho_id}: {e.errors()}")
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
    except Exception as e:
        logger.error(f"Error cambiando estado de despacho {despacho_id}: {str(e)}")
        flash('Error al cambiar estado del despacho', 'error')

    return redirect(url_for('despachos.detalle', despacho_id=despacho_id))

@despachos_bp.route('/<int:despacho_id>/adjuntos/subir', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def eliminar_adjunto(adjunto_id):
    """Eliminar adjunto del despacho"""
    try:
        despacho_id = despachos_service.delete_despacho_attachment(adjunto_id)
        flash('Archivo eliminado exitosamente', 'success')
        return redirect(url_for('despachos.detalle', despacho_id=despacho_id))

    except Exception as e:
        logger.error(f"Error eliminando adjunto {adjunto_id}: {str(e)}")
        flash('Error al eliminar archivo', 'error')
        # Se redirige al index si no se puede obtener el despacho_id
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


# API routes for cascading selects
@despachos_bp.route('/api/ofs_by_contrato/<int:contrato_id>')
@require_login
def api_ofs_by_contrato(contrato_id):
    """API para obtener órdenes de fabricación disponibles para despacho por contrato"""
    try:
        # Obtener OFs del contrato que están disponibles para despacho
        ofs_disponibles = fabricacion_service.get_ofs_disponibles_para_despacho(contrato_id)
        return jsonify([{
            'id': of.id,
            'codigo': of.codigo,
            'descripcion': of.descripcion or 'Sin descripción',
            'cantidad_total': of.cantidad_tableros or 0,
            'cantidad_despachada_previa': getattr(of, 'cantidad_despachada_previa', 0),
            'cantidad_disponible': getattr(of, 'cantidad_disponible_despacho', of.cantidad_tableros or 0),
            'tiene_despachos_parciales': getattr(of, 'tiene_despachos_parciales', False),
            'estado': of.estado_actual.nombre if of.estado_actual else 'Sin estado',
            'area_actual': of.progreso_actual.area.nombre if of.progreso_actual else 'Sin área'
        } for of in ofs_disponibles])
    except Exception as e:
        logger.error(f"Error obteniendo OFs disponibles para despacho del contrato {contrato_id}: {str(e)}")
        return jsonify([]), 500

# Add the new API endpoint for hitos by contrato
@despachos_bp.route('/api/hitos_by_contrato/<int:contrato_id>')
@require_login
def api_hitos_by_contrato(contrato_id):
    """API para obtener hitos de entrega por contrato"""
    try:
        from models import HitoEntrega, PlanEntrega, EstadoHitoEntrega

        # First check if the contract exists
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            return jsonify({'error': 'Contrato no encontrado'}), 404

        # Get delivery milestones for this contract
        hitos = []
        if contrato.plan_entrega and contrato.plan_entrega.hitos:
            for hito in contrato.plan_entrega.hitos:
                # Only include pending milestones
                if hito.estado == EstadoHitoEntrega.PENDIENTE:
                    hitos.append({
                        'id': hito.id,
                        'titulo': hito.titulo,
                        'descripcion': hito.descripcion or hito.titulo,
                        'fecha_programada': hito.fecha_programada.isoformat() if hito.fecha_programada else None,
                        'orden': hito.orden,
                        'estado': hito.estado.value
                    })

        # Sort by date and order
        hitos.sort(key=lambda x: (x['fecha_programada'] or '9999-12-31', x['orden']))

        logger.info(f"Found {len(hitos)} pending hitos for contrato {contrato_id}")
        return jsonify(hitos)

    except Exception as e:
        logger.error(f"Error obteniendo hitos para contrato {contrato_id}: {str(e)}")
        return jsonify({'error': 'Error al cargar hitos de entrega'}), 500

@despachos_bp.route('/crear-desde-hito/<int:hito_id>')
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def crear_despacho_desde_hito(hito_id):
    """Crear despacho desde un hito de entrega"""
    try:
        from models import HitoEntrega, PlanEntrega, Contrato, Proyecto

        # Obtener hito con sus relaciones
        hito = db.session.query(HitoEntrega).options(
            joinedload(HitoEntrega.plan_entrega).joinedload(PlanEntrega.contrato).joinedload(Contrato.proyecto).joinedload(Proyecto.cliente)
        ).filter_by(id=hito_id).first()

        if not hito:
            flash('Hito de entrega no encontrado', 'error')
            return redirect(url_for('despachos.planificacion'))

        contrato = hito.plan_entrega.contrato
        proyecto = contrato.proyecto

        # Redirigir al formulario de nuevo despacho con datos pre-cargados
        return redirect(url_for('despachos.nuevo', 
                              contrato_id=contrato.id,
                              hito_entrega_id=hito.id,
                              fecha_programada=hito.fecha_programada.isoformat()))

    except Exception as e:
        logger.error(f"Error creando despacho desde hito {hito_id}: {str(e)}")
        flash('Error al crear despacho desde hito', 'error')
        return redirect(url_for('despachos.planificacion'))

@despachos_bp.route('/api/generate_numero', methods=['POST'])
@require_login
def api_generate_numero():
    """API para generar número de despacho automáticamente"""
    try:
        data = request.get_json()
        proyecto_id = data.get('proyecto_id')
        contrato_id = data.get('contrato_id')

        if not proyecto_id:
            return jsonify({'error': 'proyecto_id es requerido'}), 400

        # Get proyecto to obtain cliente_id
        proyecto = proyectos_service.get_proyecto_by_id(proyecto_id)
        if not proyecto:
            return jsonify({'error': 'Proyecto no encontrado'}), 404

        # Generate dispatch number
        numero_despacho = DespachosRepository.generate_next_numero_despacho(
            contrato_id, proyecto.cliente_id
        )

        return jsonify({'numero_despacho': numero_despacho})

    except Exception as e:
        logger.error(f"Error generando número de despacho: {str(e)}")
        return jsonify({'error': 'Error interno del servidor'}), 500

# ================ NUEVAS RUTAS PARA PLANIFICACIÓN DE DESPACHOS ================

@despachos_bp.route('/planificacion')
@require_login
def planificacion():
    """Vista principal de planificación de despachos basada en hitos de entrega"""
    try:
        # Get hitos próximos with configurable days
        dias_filtro = request.args.get('dias_hitos', type=int, default=7)
        # Validate dias_filtro range (1-90 days)
        if dias_filtro < 1:
            dias_filtro = 1
        elif dias_filtro > 90:
            dias_filtro = 90

        # Obtener vista jerárquica de planificación
        vista_planificacion = planificacion_service.get_vista_planificacion()

        # Get hitos próximos
        hitos_proximos = planificacion_service.get_hitos_proximos_vencimiento(dias=dias_filtro)

        # Obtener estadísticas
        estadisticas = planificacion_service.get_estadisticas_planificacion()

        return render_template('despachos/planificacion.html',
                             vista_planificacion=vista_planificacion,
                             hitos_proximos=hitos_proximos,
                             estadisticas=estadisticas,
                             dias_filtro=dias_filtro,
                             page_title="Planificación de Despachos")

    except Exception as e:
        logger.error(f"Error en vista de planificación: {str(e)}")
        flash('Error al cargar la planificación de despachos', 'error')
        return redirect(url_for('despachos.index'))

@despachos_bp.route('/api/planificacion')
@require_login
def api_planificacion():
    """API endpoint para la vista de planificación (AJAX)"""
    try:
        vista_planificacion = planificacion_service.get_vista_planificacion()

        # Convertir a dict para JSON response
        response_data = {
            'clientes': [
                {
                    'id': cliente.id,
                    'nombre': cliente.nombre,
                    'proyectos': [
                        {
                            'id': proyecto.id,
                            'nombre': proyecto.nombre,
                            'hitos_entrega': [
                                {
                                    'id': hito.id,
                                    'contrato_id': hito.contrato_id,
                                    'contrato_numero_oc': hito.contrato_numero_oc,
                                    'descripcion': hito.descripcion,
                                    'fecha_entrega': hito.fecha_entrega.isoformat(),
                                    'estado': hito.estado,
                                    'despacho_creado': hito.despacho_creado,
                                    'despacho_id': hito.despacho_id,
                                    'ordenes_fabricacion_disponibles': hito.ordenes_fabricacion_disponibles
                                } for hito in proyecto.hitos_entrega
                            ]
                        } for proyecto in cliente.proyectos
                    ]
                } for cliente in vista_planificacion.clientes
            ],
            'total_hitos_pendientes': vista_planificacion.total_hitos_pendientes,
            'total_hitos_proximos': vista_planificacion.total_hitos_proximos
        }

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error en API planificación: {str(e)}")
        return jsonify({'error': 'Error al cargar planificación'}), 500

@despachos_bp.route('/api/estadisticas-planificacion')
@require_login
def api_estadisticas_planificacion():
    """API endpoint para estadísticas de planificación"""
    try:
        estadisticas = planificacion_service.get_estadisticas_planificacion()
        return jsonify(estadisticas)

    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {str(e)}")
        return jsonify({'error': 'Error al cargar estadísticas'}), 500