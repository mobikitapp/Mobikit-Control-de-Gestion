from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user, login_required
from pydantic import ValidationError
from werkzeug.utils import secure_filename
from datetime import datetime, date
from app import db
from replit_auth import require_login, require_role
from models import RolUsuario, User # Import User model
from services.contratos_service import ContratosService
from services.proyectos_service import ProyectosService
from services.clientes_service import ClientesService
from services.planes_entrega_service import PlanesEntregaService
from schemas.contratos import ContratoCreate, ContratoUpdate, ContratoSearchFilters
from schemas.planes_entrega import PlanEntregaCreate, HitoEntregaCreate, CompletarHitoRequest
import logging

logger = logging.getLogger(__name__)

contratos_bp = Blueprint('contratos', __name__)
contratos_service = ContratosService()
proyectos_service = ProyectosService()
clientes_service = ClientesService()
planes_entrega_service = PlanesEntregaService()

@contratos_bp.route('/')
@require_login
def index():
    """Lista de contratos con filtros"""
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

        if request.args.get('numero_oc', '').strip():
            filters_data['numero_oc'] = request.args.get('numero_oc').strip()

        if request.args.get('estado', '').strip():
            filters_data['estado'] = request.args.get('estado').strip()

        if request.args.get('moneda', '').strip():
            filters_data['moneda'] = request.args.get('moneda').strip()

        if request.args.get('fecha_emision_desde', '').strip():
            filters_data['fecha_emision_desde'] = request.args.get('fecha_emision_desde').strip()

        if request.args.get('fecha_emision_hasta', '').strip():
            filters_data['fecha_emision_hasta'] = request.args.get('fecha_emision_hasta').strip()

        # Handle archivado filter: '' -> None, 'true' -> True, 'false' -> False
        archivado_param = request.args.get('archivado', '').strip()
        if archivado_param == 'true':
            filters_data['archivado'] = True
        elif archivado_param == 'false':
            filters_data['archivado'] = False
        # else: archivado_param == '' means None (default, shows all)

        # Validate filters
        filters = ContratoSearchFilters(**filters_data)

        # Search contratos grouped by client
        contratos_agrupados, total_count = contratos_service.get_contratos_grouped_by_client(filters)

        # Get data for filter dropdowns
        clientes = clientes_service.get_active_clientes()

        # Calculate pagination
        total_pages = (total_count + filters.per_page - 1) // filters.per_page
        has_prev = filters.page > 1
        has_next = filters.page < total_pages

        return render_template('contratos/index.html',
                             contratos_agrupados=contratos_agrupados,
                             clientes=clientes,
                             filters=filters,
                             total_count=total_count,
                             total_pages=total_pages,
                             has_prev=has_prev,
                             has_next=has_next,
                             now=datetime.now())

    except ValidationError as e:
        flash('Filtros inválidos', 'error')
        return redirect(url_for('contratos.index'))
    except Exception as e:
        logger.error(f"Error en lista de contratos: {str(e)}")
        flash('Error al cargar contratos', 'error')
        return redirect(url_for('index'))

@contratos_bp.route('/nuevo')
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES, RolUsuario.FINANZAS)
def nuevo():
    """Formulario para nuevo contrato"""
    try:
        clientes = clientes_service.get_active_clientes()
        # Obtener proyectos para el dropdown
        proyectos = proyectos_service.get_active_proyectos()
        return render_template('contratos/form.html',
                             contrato=None,
                             clientes=clientes,
                             proyectos=proyectos,
                             current_user=current_user,
                             title="Nuevo Contrato / OC")
    except Exception as e:
        logger.error(f"Error cargando formulario nuevo contrato: {str(e)}")
        flash('Error al cargar formulario', 'error')
        return redirect(url_for('contratos.index'))

@contratos_bp.route('/crear', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES, RolUsuario.FINANZAS)
def crear():
    """Crear nuevo contrato"""
    try:
        # Get form data and log for debugging
        form_data = request.form.to_dict()
        logger.info(f"Creando contrato con datos: {form_data}")
        
        # Clean up empty string fields to avoid validation errors
        cleaned_form_data = {}
        for key, value in form_data.items():
            if isinstance(value, str) and value.strip() == '':
                # Skip empty strings entirely
                continue
            else:
                cleaned_form_data[key] = value
        
        # Specifically handle UF fields that should be None if empty
        uf_fields = ['valor_uf_conversion', 'fecha_conversion_uf', 'monto_total_uf', 'moneda_original']
        for field in uf_fields:
            if field in form_data and not form_data[field].strip():
                # Remove empty UF fields completely
                cleaned_form_data.pop(field, None)
        
        logger.info(f"Datos limpiados para validación: {cleaned_form_data}")
        
        contrato_data = ContratoCreate(**cleaned_form_data)

        # Handle file uploads
        archivos = request.files.getlist('archivos')

        # Create contrato with files
        contrato = contratos_service.create_contrato_with_files(
            contrato_data.dict(),
            archivos,
            current_user.id
        )

        # Check if plan de entrega should be created
        crear_plan = form_data.get('crear_plan_entrega') == 'on'
        plan_creado = False

        if crear_plan:
            try:
                # Get plan data
                plan_data = {
                    'contrato_id': contrato.id,
                    'nombre': form_data.get('plan_nombre', f'Plan de Entrega - {contrato.numero_oc}'),
                    'descripcion': form_data.get('plan_descripcion', '')
                }

                # Get hitos data
                cantidad_hitos_str = form_data.get('cantidad_hitos', '2')
                try:
                    cantidad_hitos = int(cantidad_hitos_str) if cantidad_hitos_str else 2
                except (ValueError, TypeError):
                    cantidad_hitos = 2

                hitos_data = []

                for i in range(1, cantidad_hitos + 1):
                    titulo = form_data.get(f'hito_titulo_{i}', '').strip()
                    fecha = form_data.get(f'hito_fecha_{i}', '').strip()
                    descripcion = form_data.get(f'hito_descripcion_{i}', '').strip()

                    if titulo and fecha:
                        try:
                            # Validate date format
                            from datetime import datetime
                            datetime.strptime(fecha, '%Y-%m-%d')
                            
                            hitos_data.append({
                                'titulo': titulo,
                                'descripcion': descripcion,
                                'fecha_programada': fecha,
                                'orden': i
                            })
                        except ValueError:
                            logger.warning(f"Fecha inválida para hito {i}: {fecha}")
                            continue

                if hitos_data:
                    # Create plan with hitos
                    plan = planes_entrega_service.create_plan_with_hitos(
                        plan_data, hitos_data, current_user.id
                    )
                    plan_creado = True

            except Exception as e:
                logger.warning(f"Error creando plan de entrega para contrato {contrato.id}: {str(e)}")
                # Don't fail the contrato creation if plan creation fails

        # Create success message
        mensaje = f'Contrato {contrato.numero_oc} creado exitosamente'
        if plan_creado:
            mensaje += ' con plan de entrega'
        flash(mensaje, 'success')

        return redirect(url_for('contratos.detalle', contrato_id=contrato.id))

    except ValidationError as e:
        for error in e.errors():
            flash(f"Error en {error['loc'][0]}: {error['msg']}", 'error')
        clientes = clientes_service.get_active_clientes()
        proyectos = proyectos_service.get_active_proyectos()
        return render_template('contratos/form.html',
                             contrato=None,
                             clientes=clientes,
                             proyectos=proyectos,
                             current_user=current_user,
                             title="Nuevo Contrato / OC")
    except Exception as e:
        logger.error(f"Error creando contrato: {str(e)}")
        flash('Error al crear contrato', 'error')
        clientes = clientes_service.get_active_clientes()
        proyectos = proyectos_service.get_active_proyectos()
        return render_template('contratos/form.html',
                             contrato=None,
                             clientes=clientes,
                             proyectos=proyectos,
                             current_user=current_user,
                             title="Nuevo Contrato / OC")

@contratos_bp.route('/<int:contrato_id>')
@require_login
def detalle(contrato_id):
    """Detalle de contrato"""
    try:
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('contratos.index'))

        # Add today's date for template comparison
        today = date.today()

        return render_template('contratos/detalle.html',
                             contrato=contrato,
                             today=today,
                             current_user=current_user)

    except Exception as e:
        logger.error(f"Error obteniendo contrato {contrato_id}: {str(e)}")
        flash('Error al cargar contrato', 'error')
        return redirect(url_for('contratos.index'))

@contratos_bp.route('/<int:contrato_id>/editar')
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.FINANZAS)
def editar(contrato_id):
    """Formulario de edición de contrato"""
    try:
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('contratos.index'))

        clientes = clientes_service.get_active_clientes()
        proyectos = proyectos_service.get_active_proyectos()
        return render_template('contratos/form.html',
                             contrato=contrato,
                             clientes=clientes,
                             proyectos=proyectos,
                             current_user=current_user,
                             title=f"Editar Contrato / OC - {contrato.numero_oc}")

    except Exception as e:
        logger.error(f"Error obteniendo contrato para editar {contrato_id}: {str(e)}")
        flash('Error al cargar contrato', 'error')
        return redirect(url_for('contratos.index'))

@contratos_bp.route('/<int:contrato_id>/actualizar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.FINANZAS)
def actualizar(contrato_id):
    """Actualizar contrato existente"""
    try:
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('contratos.index'))

        # Get form data and log for debugging
        form_data = request.form.to_dict()
        logger.info(f"Actualizando contrato {contrato_id} con datos: {form_data}")
        
        # Clean up empty string fields to avoid validation errors
        cleaned_form_data = {}
        for key, value in form_data.items():
            if isinstance(value, str) and value.strip() == '':
                # Skip empty strings entirely
                continue
            else:
                cleaned_form_data[key] = value
        
        # Specifically handle UF fields that should be None if empty
        uf_fields = ['valor_uf_conversion', 'fecha_conversion_uf', 'monto_total_uf', 'moneda_original']
        for field in uf_fields:
            if field in form_data and not form_data[field].strip():
                # Remove empty UF fields completely
                cleaned_form_data.pop(field, None)
        
        logger.info(f"Datos limpiados para validación: {cleaned_form_data}")
        
        # Validate with cleaned data
        update_data = ContratoUpdate(**cleaned_form_data)

        # Update contrato
        contrato_actualizado = contratos_service.update_contrato(contrato_id, update_data.dict(exclude_unset=True))

        # Check if plan de entrega should be created (for existing contracts without plan)
        crear_plan = cleaned_form_data.get('crear_plan_entrega') == 'on'
        plan_creado = False

        if crear_plan and not contrato_actualizado.plan_entrega:
            try:
                # Get plan data
                plan_data = {
                    'contrato_id': contrato_actualizado.id,
                    'nombre': cleaned_form_data.get('plan_nombre', f'Plan de Entrega - {contrato_actualizado.numero_oc}'),
                    'descripcion': cleaned_form_data.get('plan_descripcion', '')
                }

                # Get hitos data with safer parsing
                cantidad_hitos_str = cleaned_form_data.get('cantidad_hitos', '2')
                try:
                    cantidad_hitos = int(cantidad_hitos_str) if cantidad_hitos_str else 2
                except (ValueError, TypeError):
                    cantidad_hitos = 2

                hitos_data = []

                for i in range(1, cantidad_hitos + 1):
                    titulo = cleaned_form_data.get(f'hito_titulo_{i}', '').strip()
                    fecha = cleaned_form_data.get(f'hito_fecha_{i}', '').strip()
                    descripcion = cleaned_form_data.get(f'hito_descripcion_{i}', '').strip()

                    if titulo and fecha:
                        try:
                            # Validate date format
                            from datetime import datetime
                            datetime.strptime(fecha, '%Y-%m-%d')
                            
                            hitos_data.append({
                                'titulo': titulo,
                                'descripcion': descripcion,
                                'fecha_programada': fecha,
                                'orden': i
                            })
                        except ValueError:
                            logger.warning(f"Fecha inválida para hito {i}: {fecha}")
                            continue

                if hitos_data:
                    # Create plan with hitos
                    plan = planes_entrega_service.create_plan_with_hitos(
                        plan_data, hitos_data, current_user.id
                    )
                    plan_creado = True

            except Exception as e:
                logger.error(f"Error creando plan de entrega para contrato {contrato_actualizado.id}: {str(e)}")
                logger.exception("Full traceback for plan creation error:")
                # Don't fail the contrato update if plan creation fails

        # Create success message
        mensaje = f'Contrato {contrato_actualizado.numero_oc} actualizado exitosamente'
        if plan_creado:
            mensaje += ' y plan de entrega creado'
        flash(mensaje, 'success')
        return redirect(url_for('contratos.detalle', contrato_id=contrato_id))

    except ValidationError as e:
        logger.error(f"ValidationError actualizando contrato {contrato_id}: {e.errors()}")
        for error in e.errors():
            field_name = error['loc'][0] if error['loc'] else 'unknown'
            error_msg = error['msg']
            logger.error(f"Validation error - Field: {field_name}, Message: {error_msg}")
            flash(f"Error en {field_name}: {error_msg}", 'error')
        clientes = clientes_service.get_active_clientes()
        proyectos = proyectos_service.get_active_proyectos()
        return render_template('contratos/form.html',
                             contrato=contrato,
                             clientes=clientes,
                             proyectos=proyectos,
                             current_user=current_user,
                             title=f"Editar Contrato / OC - {contrato.numero_oc}")
    except Exception as e:
        logger.error(f"Error actualizando contrato {contrato_id}: {str(e)}")
        logger.exception("Full exception traceback:")
        flash('Error al actualizar contrato', 'error')
        return redirect(url_for('contratos.detalle', contrato_id=contrato_id))

@contratos_bp.route('/<int:contrato_id>/cambiar-estado', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.FINANZAS)
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
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.FINANZAS)
def subir_adjunto(contrato_id):
    """Subir nuevo adjunto al contrato"""
    try:
        # Verificar que el contrato existe
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('contratos.index'))

        archivo = request.files.get('archivo')
        tipo = request.form.get('tipo', 'contrato')

        logger.info(f"Attempting to upload file for contract {contrato_id}. File: {archivo.filename if archivo else 'None'}")

        if not archivo or not archivo.filename:
            flash('Archivo requerido', 'error')
            return redirect(url_for('contratos.detalle', contrato_id=contrato_id))

        # Log file details
        logger.info(f"File details - Name: {archivo.filename}, Content-Type: {archivo.content_type}, Size: {archivo.content_length}")

        # Validate file before processing
        from services.storage_service import StorageService
        storage_service = StorageService()
        is_valid, error_msg = storage_service.validate_file_upload(archivo)
        
        if not is_valid:
            logger.warning(f"File validation failed: {error_msg}")
            flash(f'Archivo inválido: {error_msg}', 'error')
            return redirect(url_for('contratos.detalle', contrato_id=contrato_id))

        adjunto = contratos_service.add_contract_attachment(contrato_id, archivo, tipo, current_user.id)
        
        if adjunto:
            logger.info(f"File uploaded successfully: {adjunto.filename} for contract {contrato_id}")
            flash('Archivo subido exitosamente', 'success')
        else:
            logger.error(f"Failed to create attachment record for contract {contrato_id}")
            flash('Error al registrar archivo', 'error')

    except Exception as e:
        logger.error(f"Error subiendo adjunto a contrato {contrato_id}: {str(e)}")
        logger.exception("Full traceback for file upload error:")
        flash(f'Error al subir archivo: {str(e)}', 'error')

    return redirect(url_for('contratos.detalle', contrato_id=contrato_id))

@contratos_bp.route('/adjuntos/<int:adjunto_id>/eliminar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS)
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

# ============================
# PLAN DE ENTREGA ROUTES
# ============================

@contratos_bp.route('/<int:contrato_id>/plan-entrega')
@require_login
def plan_entrega(contrato_id):
    """Ver plan de entrega del contrato"""
    try:
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('contratos.index'))

        plan = planes_entrega_service.get_plan_by_contrato_id(contrato_id)
        estadisticas = None

        if plan:
            estadisticas = planes_entrega_service.get_estadisticas_plan(plan.id)

        return render_template('contratos/plan_entrega.html',
                             contrato=contrato,
                             plan=plan,
                             estadisticas=estadisticas)

    except Exception as e:
        logger.error(f"Error cargando plan de entrega para contrato {contrato_id}: {str(e)}")
        flash('Error al cargar plan de entrega', 'error')
        return redirect(url_for('contratos.detalle', contrato_id=contrato_id))

@contratos_bp.route('/<int:contrato_id>/plan-entrega/crear', methods=['GET', 'POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.VENTAS)
def crear_plan_entrega(contrato_id):
    """Crear plan de entrega para contrato"""
    try:
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('contratos.index'))

        # Check if plan already exists
        existing_plan = planes_entrega_service.get_plan_by_contrato_id(contrato_id)
        if existing_plan:
            flash('El contrato ya tiene un plan de entrega', 'warning')
            return redirect(url_for('contratos.plan_entrega', contrato_id=contrato_id))

        if request.method == 'POST':
            # Get plan data
            plan_data = {
                'contrato_id': contrato_id,
                'nombre': request.form.get('nombre'),
                'descripcion': request.form.get('descripcion')
            }

            # Get hitos data
            hitos_data = []
            titulos = request.form.getlist('hito_titulo[]')
            descripciones = request.form.getlist('hito_descripcion[]')
            fechas = request.form.getlist('hito_fecha[]')

            for i, titulo in enumerate(titulos):
                if titulo.strip():
                    hito_data = {
                        'titulo': titulo.strip(),
                        'descripcion': descripciones[i] if i < len(descripciones) else '',
                        'fecha_programada': fechas[i] if i < len(fechas) else None,
                        'orden': i + 1
                    }
                    hitos_data.append(hito_data)

            if not hitos_data:
                flash('Debe agregar al menos un hito de entrega', 'error')
                return render_template('contratos/plan_entrega_form.html', contrato=contrato)

            # Create plan with hitos
            plan = planes_entrega_service.create_plan_with_hitos(
                plan_data, hitos_data, current_user.id
            )

            flash('Plan de entrega creado exitosamente', 'success')
            return redirect(url_for('contratos.plan_entrega', contrato_id=contrato_id))

        return render_template('contratos/plan_entrega_form.html', contrato=contrato)

    except Exception as e:
        logger.error(f"Error creando plan de entrega para contrato {contrato_id}: {str(e)}")
        flash('Error al crear plan de entrega', 'error')
        return redirect(url_for('contratos.detalle', contrato_id=contrato_id))

@contratos_bp.route('/planes-entrega/<int:plan_id>/editar', methods=['GET', 'POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.VENTAS)
def editar_plan_entrega(plan_id):
    """Editar plan de entrega existente"""
    try:
        plan = planes_entrega_service.get_plan_by_id(plan_id)
        if not plan:
            flash('Plan de entrega no encontrado', 'error')
            return redirect(url_for('contratos.index'))

        contrato = contratos_service.get_contrato_by_id(plan.contrato_id)
        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('contratos.index'))

        if request.method == 'POST':
            # Update plan data
            plan_update_data = {
                'nombre': request.form.get('nombre'),
                'descripcion': request.form.get('descripcion')
            }

            # Update plan
            plan_actualizado = planes_entrega_service.update_plan(plan_id, plan_update_data)

            # Handle hitos updates
            titulos = request.form.getlist('hito_titulo[]')
            descripciones = request.form.getlist('hito_descripcion[]')
            fechas = request.form.getlist('hito_fecha[]')
            hito_ids = request.form.getlist('hito_id[]')

            if not titulos or all(not titulo.strip() for titulo in titulos):
                flash('Debe tener al menos un hito de entrega', 'error')
                return render_template('contratos/plan_entrega_edit.html', 
                                     contrato=contrato, plan=plan)

            # Update existing hitos and create new ones
            planes_entrega_service.update_plan_hitos(
                plan_id, titulos, descripciones, fechas, hito_ids, current_user.id
            )

            flash('Plan de entrega actualizado exitosamente', 'success')
            return redirect(url_for('contratos.plan_entrega', contrato_id=contrato.id))

        return render_template('contratos/plan_entrega_edit.html', 
                             contrato=contrato, plan=plan)

    except Exception as e:
        logger.error(f"Error editando plan de entrega {plan_id}: {str(e)}")
        flash('Error al editar plan de entrega', 'error')
        return redirect(url_for('contratos.index'))

@contratos_bp.route('/hitos/<int:hito_id>/completar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
def completar_hito(hito_id):
    """Marcar hito como completado"""
    try:
        notas = request.form.get('notas_completado', '')

        hito = planes_entrega_service.completar_hito(
            hito_id, notas, current_user.id
        )

        flash(f'Hito "{hito.titulo}" completado exitosamente', 'success')
        return redirect(url_for('contratos.plan_entrega',
                              contrato_id=hito.plan_entrega.contrato_id))

    except Exception as e:
        logger.error(f"Error completando hito {hito_id}: {str(e)}")
        flash('Error al completar hito', 'error')
        # Try to redirect back, or to main page if we can't determine the contrato
        return redirect(request.referrer or url_for('contratos.index'))

@contratos_bp.route('/planes-entrega/<int:plan_id>/hitos/agregar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.VENTAS)
def agregar_hito(plan_id):
    """Agregar nuevo hito al plan de entrega"""
    try:
        # Get plan first to validate it exists
        plan = planes_entrega_service.get_plan_by_id(plan_id)
        if not plan:
            flash('Plan de entrega no encontrado', 'error')
            return redirect(url_for('contratos.index'))

        # Store contrato_id before any operations that might detach the object
        contrato_id = plan.contrato_id

        # Validar datos del formulario
        titulo = request.form.get('titulo', '').strip()
        descripcion = request.form.get('descripcion', '').strip()
        fecha_programada = request.form.get('fecha_programada', '').strip()

        if not titulo:
            flash('El título del hito es requerido', 'error')
            return redirect(url_for('contratos.plan_entrega', contrato_id=contrato_id))

        if not fecha_programada:
            flash('La fecha programada del hito es requerida', 'error')
            return redirect(url_for('contratos.plan_entrega', contrato_id=contrato_id))

        # Validate date format
        try:
            from datetime import datetime
            datetime.strptime(fecha_programada, '%Y-%m-%d')
        except ValueError:
            flash('Formato de fecha inválido', 'error')
            return redirect(url_for('contratos.plan_entrega', contrato_id=contrato_id))

        hito_data = {
            'titulo': titulo,
            'descripcion': descripcion if descripcion else None,
            'fecha_programada': fecha_programada
        }

        logger.info(f"Agregando hito al plan {plan_id}: {hito_data}")
        hito = planes_entrega_service.add_hito(plan_id, hito_data, current_user.id)
        logger.info(f"Hito creado con ID: {hito.id}")

        flash(f'Hito "{hito.titulo}" agregado exitosamente', 'success')

        # Verify the hito was actually saved
        try:
            # Get a fresh plan to verify the hito was added
            from repositories.planes_entrega_repo import PlanesEntregaRepository
            repo = PlanesEntregaRepository()
            fresh_plan = repo.get_by_id_with_fresh_hitos(plan_id)
            if fresh_plan:
                logger.info(f"Verificación final: Plan {plan_id} tiene {len(fresh_plan.hitos)} hitos")
                for h in fresh_plan.hitos:
                    logger.info(f"  - Hito ID: {h.id}, Título: {h.titulo}")
            else:
                logger.error(f"No se pudo obtener el plan {plan_id} para verificación")
        except Exception as e:
            logger.warning(f"Error en verificación final: {str(e)}")

        # Use the stored contrato_id instead of accessing the potentially detached object
        return redirect(url_for('contratos.plan_entrega', contrato_id=contrato_id))

    except ValueError as e:
        logger.error(f"Error de validación agregando hito al plan {plan_id}: {str(e)}")
        flash(f'Error: {str(e)}', 'error')
        # Try to get contrato_id if we have it, otherwise fallback to index
        try:
            if 'contrato_id' in locals():
                return redirect(url_for('contratos.plan_entrega', contrato_id=contrato_id))
            else:
                plan = planes_entrega_service.get_plan_by_id(plan_id)
                if plan:
                    return redirect(url_for('contratos.plan_entrega', contrato_id=plan.contrato_id))
        except:
            pass
        return redirect(url_for('contratos.index'))
    except Exception as e:
        logger.error(f"Error agregando hito al plan {plan_id}: {str(e)}")
        logger.exception("Full traceback for agregar_hito error:")
        flash('Error interno al agregar hito', 'error')
        # Try to get contrato_id if we have it, otherwise fallback to index
        try:
            if 'contrato_id' in locals():
                return redirect(url_for('contratos.plan_entrega', contrato_id=contrato_id))
            else:
                plan = planes_entrega_service.get_plan_by_id(plan_id)
                if plan:
                    return redirect(url_for('contratos.plan_entrega', contrato_id=plan.contrato_id))
        except:
            pass
        return redirect(url_for('contratos.index'))

@contratos_bp.route('/api/proximos-hitos')
@require_login
def api_proximos_hitos():
    """API endpoint para obtener próximos hitos"""
    try:
        dias = request.args.get('dias', 7, type=int)
        hitos = planes_entrega_service.get_proximos_hitos(dias)

        return jsonify([{
            'id': h.id,
            'titulo': h.titulo,
            'fecha_programada': h.fecha_programada.isoformat(),
            'plan_nombre': h.plan_entrega.nombre,
            'contrato_numero': h.plan_entrega.contrato.numero_oc,
            'estado': h.estado.value
        } for h in hitos])

    except Exception as e:
        logger.error(f"Error en API próximos hitos: {str(e)}")
        return jsonify({'error': 'Error al cargar hitos'}), 500

@contratos_bp.route('/api/hitos-atrasados')
@require_login
def api_hitos_atrasados():
    """API endpoint para obtener hitos atrasados"""
    try:
        hitos = planes_entrega_service.get_hitos_atrasados()

        return jsonify([{
            'id': h.id,
            'titulo': h.titulo,
            'fecha_programada': h.fecha_programada.isoformat(),
            'dias_atraso': (datetime.now().date() - h.fecha_programada).days,
            'plan_nombre': h.plan_entrega.nombre,
            'contrato_numero': h.plan_entrega.contrato.numero_oc,
            'estado': h.estado.value
        } for h in hitos])

    except Exception as e:
        logger.error(f"Error en API hitos atrasados: {str(e)}")
        return jsonify({'error': 'Error al cargar hitos atrasados'}), 500

@contratos_bp.route('/<int:contrato_id>/eliminar', methods=['POST'])
@require_role(RolUsuario.ADMIN)
def eliminar(contrato_id):
    """Eliminar contrato"""
    try:
        # Get contrato info before deletion attempt
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('contratos.index'))
        
        success = contratos_service.delete_contrato(contrato_id)
        if success:
            # Check if it was soft deleted (archived) or hard deleted
            contrato_after = contratos_service.get_contrato_by_id(contrato_id)
            if contrato_after and contrato_after.archivado:
                flash(f'Contrato {contrato.numero_oc} archivado exitosamente (tenía dependencias)', 'warning')
            else:
                flash(f'Contrato {contrato.numero_oc} eliminado exitosamente', 'success')
        else:
            flash('Error al eliminar contrato', 'error')

    except Exception as e:
        logger.error(f"Error eliminando contrato {contrato_id}: {str(e)}")
        error_msg = str(e)
        
        # Provide more specific error messages
        if 'foreign key constraint' in error_msg.lower():
            flash('No se puede eliminar el contrato porque tiene registros relacionados (órdenes de fabricación, despachos, etc.)', 'error')
        elif 'violates foreign key constraint' in error_msg.lower():
            flash('No se puede eliminar el contrato porque está siendo usado por otros registros', 'error')
        else:
            flash(f'Error al eliminar contrato: {error_msg}', 'error')

    return redirect(url_for('contratos.index'))

@contratos_bp.route('/api/by-proyecto/<int:proyecto_id>')
@require_login
def api_by_proyecto(proyecto_id):
    """API endpoint para obtener contratos por proyecto"""
    try:
        contratos = contratos_service.get_contratos_by_proyecto(proyecto_id)
        return jsonify([{
            'id': c.id,
            'numero_oc': c.numero_oc,
            'estado': c.estado.value,
            'monto_total': float(c.monto_total) if c.monto_total else 0
        } for c in contratos])

    except Exception as e:
        logger.error(f"Error en API contratos por proyecto: {str(e)}")
        return jsonify({'error': 'Error al cargar contratos'}), 500

@contratos_bp.route('/api/by-cliente/<int:cliente_id>')
@require_login
def api_by_cliente(cliente_id):
    """API endpoint para obtener contratos por cliente"""
    try:
        contratos = contratos_service.get_contratos_by_cliente(cliente_id)
        return jsonify([{
            'id': c.id,
            'numero_oc': c.numero_oc,
            'estado': c.estado.value,
            'monto_total': float(c.monto_total) if c.monto_total else 0,
            'proyecto_nombre': c.proyecto.nombre
        } for c in contratos])

    except Exception as e:
        logger.error(f"Error en API contratos por cliente: {str(e)}")
        return jsonify({'error': 'Error al cargar contratos'}), 500

@contratos_bp.route('/api/users/active')
@login_required
def api_users_active():
    """Get active users for forms"""
    try:
        users = (db.session.query(User)
                .filter(User.activo == True)
                .order_by(User.first_name, User.last_name)
                .all())

        return jsonify([{
            'id': u.id,
            'nombre_completo': u.nombre_completo,
            'email': u.email
        } for u in users])

    except Exception as e:
        logger.error(f"Error en API usuarios activos: {str(e)}")
        return jsonify({'error': 'Error cargando usuarios'}), 500

@contratos_bp.route('/api/test-storage', methods=['GET'])
@require_role(RolUsuario.ADMIN)
def api_test_storage():
    """Test storage system functionality"""
    try:
        from services.storage_service import StorageService
        from adapters.storage_adapter import StorageAdapter
        import tempfile
        import os
        
        storage_service = StorageService()
        adapter = StorageAdapter()
        
        # Create a test file
        test_content = b"Test file content for storage verification"
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as temp_file:
            temp_file.write(test_content)
            temp_file_path = temp_file.name
        
        try:
            # Test upload
            with open(temp_file_path, 'rb') as f:
                storage_key = adapter.put_file(f, 'test/storage-test.txt', 'text/plain', 'test.txt')
            
            # Test file exists
            exists = adapter.file_exists(storage_key)
            
            # Clean up
            adapter.delete_file(storage_key)
            os.unlink(temp_file_path)
            
            return jsonify({
                'success': True,
                'message': 'Storage system is working correctly',
                'details': {
                    'upload_successful': True,
                    'file_exists_check': exists,
                    'storage_key': storage_key
                }
            })
            
        except Exception as e:
            # Clean up on error
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise e
            
    except Exception as e:
        logger.error(f"Storage test failed: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Storage test failed: {str(e)}'
        }), 500

@contratos_bp.route('/api/sincronizar-eventos-calendario', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def api_sincronizar_eventos_calendario():
    """API endpoint para sincronizar eventos del calendario desde hitos de planes de entrega"""
    try:
        from services.contrato_eventos_service import ContratoEventosService
        eventos_service = ContratoEventosService()

        success, mensaje, eventos_creados = eventos_service.generar_eventos_desde_hitos_plan(current_user.id)

        if success:
            return jsonify({
                'success': True,
                'message': mensaje,
                'eventos_creados': eventos_creados
            })
        else:
            return jsonify({
                'success': False,
                'message': mensaje
            }), 400

    except Exception as e:
        logger.error(f"Error sincronizando eventos del calendario: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error interno del servidor'
        }), 500

@contratos_bp.route('/api/<int:contrato_id>/adjuntos', methods=['GET'])
@login_required
def api_adjuntos(contrato_id):
    """API to get contract attachments"""
    try:
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            return jsonify({'error': 'Contrato no encontrado'}), 404

        adjuntos = []
        for adjunto in contrato.adjuntos:
            adjuntos.append({
                'id': adjunto.id,
                'filename': adjunto.filename,
                'tipo': adjunto.tipo.value,
                'size_bytes': adjunto.size_bytes,
                'created_at': adjunto.created_at.isoformat() if adjunto.created_at else None,
                'download_url': url_for('contratos.download_adjunto', contrato_id=contrato_id, adjunto_id=adjunto.id)
            })

        return jsonify(adjuntos)

    except Exception as e:
        logger.error(f"Error getting contract attachments: {str(e)}")
        return jsonify({'error': 'Error interno del servidor'}), 500

@contratos_bp.route('/api/<int:contrato_id>/hitos', methods=['GET'])
@login_required
def api_hitos_by_contrato(contrato_id):
    """API to get delivery milestones by contract"""
    try:
        contrato = contratos_service.get_contrato_by_id(contrato_id)
        if not contrato:
            return jsonify({'error': 'Contrato no encontrado'}), 404

        hitos = []
        if contrato.plan_entrega:
            for hito in contrato.plan_entrega.hitos:
                hitos.append({
                    'id': hito.id,
                    'descripcion': hito.descripcion,
                    'fecha_programada': hito.fecha_programada.isoformat() if hito.fecha_programada else None,
                    'estado': hito.estado.value,
                    'orden': hito.orden
                })

        return jsonify(hitos)

    except Exception as e:
        logger.error(f"Error getting contract milestones: {str(e)}")
        return jsonify({'error': 'Error interno del servidor'}), 500

@contratos_bp.route('/<int:contrato_id>/archivar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS)
def archivar_contrato(contrato_id):
    """Archivar un contrato (solo si está CERRADO)"""
    try:
        success = contratos_service.archivar_contrato(contrato_id)
        if success:
            flash('Contrato archivado exitosamente', 'success')
        else:
            flash('No se pudo archivar el contrato', 'error')
        
        return redirect(request.referrer or url_for('contratos.list_contratos'))
        
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(request.referrer or url_for('contratos.list_contratos'))
    except Exception as e:
        logger.error(f"Error archivando contrato {contrato_id}: {str(e)}")
        flash('Error archivando el contrato', 'error')
        return redirect(request.referrer or url_for('contratos.list_contratos'))

@contratos_bp.route('/<int:contrato_id>/desarchivar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS)
def desarchivar_contrato(contrato_id):
    """Desarchivar un contrato"""
    try:
        success = contratos_service.desarchivar_contrato(contrato_id)
        if success:
            flash('Contrato desarchivado exitosamente', 'success')
        else:
            flash('No se pudo desarchivar el contrato', 'error')
        
        return redirect(request.referrer or url_for('contratos.list_contratos'))
        
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(request.referrer or url_for('contratos.list_contratos'))
    except Exception as e:
        logger.error(f"Error desarchivando contrato {contrato_id}: {str(e)}")
        flash('Error desarchivando el contrato', 'error')
        return redirect(request.referrer or url_for('contratos.list_contratos'))

@contratos_bp.route('/archivar-cerrados', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def archivar_contratos_cerrados():
    """Archivar todos los contratos con estado CERRADO"""
    try:
        count = contratos_service.archivar_contratos_cerrados()
        if count > 0:
            flash(f'{count} contrato(s) cerrado(s) archivado(s) exitosamente', 'success')
        else:
            flash('No hay contratos cerrados para archivar', 'info')
        
        return redirect(request.referrer or url_for('contratos.list_contratos'))
        
    except Exception as e:
        logger.error(f"Error archivando contratos cerrados: {str(e)}")
        flash('Error archivando contratos cerrados', 'error')
        return redirect(request.referrer or url_for('contratos.list_contratos'))

@contratos_bp.route('/<int:contrato_id>/adjuntos/<int:adjunto_id>/descargar')
@require_login
def download_adjunto(contrato_id, adjunto_id):
    """Download contract attachment"""
    try:
        from flask import Response
        import subprocess
        import json
        
        # Get attachment record
        from repositories.contratos_repo import ContratoAdjuntosRepository
        adjuntos_repo = ContratoAdjuntosRepository()
        adjunto = adjuntos_repo.get_by_id(adjunto_id)
        
        if not adjunto or adjunto.contrato_id != contrato_id:
            flash('Archivo no encontrado', 'error')
            return redirect(url_for('contratos.detalle', contrato_id=contrato_id))
        
        # Download file from Replit Object Storage
        script = f"""
        const {{ Client }} = require('@replit/object-storage');
        
        async function downloadFile() {{
            try {{
                const client = new Client();
                const {{ ok, value, error }} = await client.downloadAsBytes('{adjunto.storage_key}');
                
                if (ok) {{
                    // Convert buffer to base64 for transport
                    const base64 = Buffer.from(value).toString('base64');
                    console.log(JSON.stringify({{ success: true, data: base64 }}));
                }} else {{
                    console.log(JSON.stringify({{ success: false, error: error?.message || 'Download failed' }}));
                }}
            }} catch (e) {{
                console.log(JSON.stringify({{ success: false, error: e.message }}));
            }}
        }}
        
        downloadFile();
        """
        
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
        
        if result.stdout:
            response_data = json.loads(result.stdout)
            if response_data.get('success'):
                import base64
                file_data = base64.b64decode(response_data['data'])
                
                return Response(
                    file_data,
                    mimetype=adjunto.mime_type,
                    headers={
                        'Content-Disposition': f'attachment; filename="{adjunto.filename}"'
                    }
                )
            else:
                flash(f'Error al descargar archivo: {response_data.get("error", "Error desconocido")}', 'error')
        else:
            flash('Error al acceder al sistema de almacenamiento', 'error')
        
        return redirect(url_for('contratos.detalle', contrato_id=contrato_id))
        
    except Exception as e:
        logger.error(f"Error downloading attachment {adjunto_id}: {str(e)}")
        flash('Error al descargar archivo', 'error')
        return redirect(url_for('contratos.detalle', contrato_id=contrato_id))