from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from pydantic import ValidationError
from werkzeug.utils import secure_filename
from datetime import datetime
from app import db
from replit_auth import require_login, require_role
from models import RolUsuario
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
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS)
def crear():
    """Crear nuevo contrato"""
    try:
        # Validate form data
        form_data = request.form.to_dict()
        contrato_data = ContratoCreate(**form_data)

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
                cantidad_hitos = int(form_data.get('cantidad_hitos', 2))
                hitos_data = []

                for i in range(1, cantidad_hitos + 1):
                    titulo = form_data.get(f'hito_titulo_{i}', '')
                    fecha = form_data.get(f'hito_fecha_{i}', '')
                    descripcion = form_data.get(f'hito_descripcion_{i}', '')

                    if titulo and fecha:
                        hitos_data.append({
                            'titulo': titulo,
                            'descripcion': descripcion,
                            'fecha_programada': fecha,
                            'orden': i
                        })

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
        proyectos = proyectos_service.get_active_proyectos()
        return render_template('contratos/form.html',
                             contrato=contrato,
                             clientes=clientes,
                             proyectos=proyectos,
                             current_user=current_user,
                             title=f"Editar Contrato / OC - {contrato.numero_oc}")
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
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
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

@contratos_bp.route('/hitos/<int:hito_id>/completar', methods=['POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.OPERACIONES, RolUsuario.LOGISTICA)
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
@require_role(RolUsuario.ADMIN, RolUsuario.VENTAS, RolUsuario.OPERACIONES)
def agregar_hito(plan_id):
    """Agregar nuevo hito al plan de entrega"""
    try:
        hito_data = {
            'titulo': request.form.get('titulo'),
            'descripcion': request.form.get('descripcion'),
            'fecha_programada': request.form.get('fecha_programada')
        }

        hito = planes_entrega_service.add_hito(plan_id, hito_data, current_user.id)

        flash(f'Hito "{hito.titulo}" agregado exitosamente', 'success')

        # Get contrato_id for redirect
        plan = planes_entrega_service.get_plan_by_id(plan_id)
        return redirect(url_for('contratos.plan_entrega',
                              contrato_id=plan.contrato_id))

    except Exception as e:
        logger.error(f"Error agregando hito al plan {plan_id}: {str(e)}")
        flash('Error al agregar hito', 'error')
        return redirect(request.referrer or url_for('contratos.index'))

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
        success = contratos_service.delete_contrato(contrato_id)
        if success:
            flash('Contrato eliminado exitosamente', 'success')
        else:
            flash('Error al eliminar contrato', 'error')

    except Exception as e:
        logger.error(f"Error eliminando contrato {contrato_id}: {str(e)}")
        flash('Error al eliminar contrato', 'error')

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