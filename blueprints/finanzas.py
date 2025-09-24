"""
Módulo de Finanzas Simplificado
Enfocado en seguimiento de proyectos, contratos y estados de pago
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime, timedelta
from decimal import Decimal
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import joinedload
import logging

from app import db
from models import (
    Proyecto, Contrato, EstadoPago, Cliente, EstadoContrato,
    TipoEstadoPago, RolUsuario, CostoProyecto, CategoriaCosto
)
from services.inflacion_service import InflacionService
from services.finanzas_service import FinanzasService

logger = logging.getLogger(__name__)

finanzas_bp = Blueprint('finanzas', __name__)

def finanzas_required(f):
    """Decorador para requerir rol de finanzas"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Debe iniciar sesión para acceder a esta página', 'error')
            return redirect(url_for('auth.login'))

        if current_user.rol not in [RolUsuario.ADMIN, RolUsuario.GENERAL]:
            flash('No tiene permisos para acceder a finanzas', 'error')
            return redirect(url_for('index'))

        return f(*args, **kwargs)
    return decorated_function

@finanzas_bp.route('/')
@finanzas_bp.route('/dashboard')
@login_required
@finanzas_required
def dashboard():
    """Dashboard principal de finanzas - Lista de proyectos con contratos"""
    try:
        # Obtener solo proyectos activos que tengan al menos un contrato vigente
        proyectos = db.session.query(Proyecto).join(Contrato).filter(
            Proyecto.activo == True,
            Contrato.estado == EstadoContrato.VIGENTE
        ).options(
            joinedload(Proyecto.cliente),
            joinedload(Proyecto.contratos).joinedload(Contrato.estados_pago)
        ).distinct().order_by(Proyecto.nombre).all()

        # Usar FinanzasService para cálculos optimizados
        finanzas_service = FinanzasService()

        # Obtener todas las agregaciones de una vez para mejor rendimiento
        proyecto_ids = [p.id for p in proyectos]
        agregaciones_contratos = finanzas_service.get_contratos_aggregates(proyecto_ids)

        # Agrupar agregaciones por proyecto usando los datos corregidos
        agregaciones_por_proyecto = {}
        for agg in agregaciones_contratos:
            # Buscar el proyecto correspondiente al contrato
            for proyecto in proyectos:
                for contrato in proyecto.contratos:
                    if contrato.id == agg['contrato_id']:
                        proyecto_id = proyecto.id
                        if proyecto_id not in agregaciones_por_proyecto:
                            agregaciones_por_proyecto[proyecto_id] = []
                        agregaciones_por_proyecto[proyecto_id].append(agg)
                        break

        # Calcular resumen por proyecto con datos corregidos
        resumen_proyectos = []
        for proyecto in proyectos:
            # Usar agregaciones precalculadas
            agregaciones_proyecto = agregaciones_por_proyecto.get(proyecto.id, [])

            if not agregaciones_proyecto:
                continue

            # Sumar totales usando agregaciones corregidas
            total_contratos = sum(agg['monto_total'] for agg in agregaciones_proyecto)
            total_facturado = sum(agg['total_facturado'] for agg in agregaciones_proyecto)
            total_pagado = sum(agg['total_pagado'] for agg in agregaciones_proyecto)
            total_pendiente_facturar = sum(agg['pendiente_facturar'] for agg in agregaciones_proyecto)
            total_pendiente_cobrar = sum(agg['pendiente_cobro'] for agg in agregaciones_proyecto)
            total_ganancia_perdida_inflacion = 0
            tiene_contratos_uf = False

            # Verificar efectos de inflación UF
            for agg in agregaciones_proyecto:
                if agg['moneda_original'] == 'UF':
                    tiene_contratos_uf = True
                    # Calcular efectos de inflación para este contrato
                    contrato = next((c for c in proyecto.contratos if c.id == agg['contrato_id']), None)
                    if contrato:
                        resumen_inflacion = InflacionService.calcular_resumen_inflacion_contrato(contrato)
                        if resumen_inflacion.get('total_ganancia_perdida'):
                            total_ganancia_perdida_inflacion += float(resumen_inflacion['total_ganancia_perdida'])

            # Validar consistencia de datos
            if total_pagado > total_facturado:
                logger.warning(f"Inconsistencia en proyecto {proyecto.id}: pagado ({total_pagado}) > facturado ({total_facturado})")
                total_pagado = total_facturado

            resumen_proyectos.append({
                'proyecto': proyecto,
                'num_contratos': len(agregaciones_proyecto),
                'total_contratos': total_contratos,
                'total_facturado': total_facturado,
                'total_pagado': total_pagado,
                'total_pendiente_facturar': total_pendiente_facturar,
                'total_pendiente_cobrar': total_pendiente_cobrar,
                'avance_facturacion': (float(total_facturado) / float(total_contratos) * 100) if total_contratos > 0 else 0,
                'avance_cobro': (float(total_pagado) / float(total_contratos) * 100) if total_contratos > 0 else 0,
                'tiene_contratos_uf': tiene_contratos_uf,
                'ganancia_perdida_inflacion': total_ganancia_perdida_inflacion
            })

        # Calcular KPIs generales incluyendo efectos de inflación
        total_proyectos = len(proyectos)
        total_contratos_global = sum(r['total_contratos'] for r in resumen_proyectos)
        total_facturado_global = sum(r['total_facturado'] for r in resumen_proyectos)
        total_pagado_global = sum(r['total_pagado'] for r in resumen_proyectos)
        total_pendiente_global = sum(r['total_pendiente_facturar'] for r in resumen_proyectos)
        total_ganancia_perdida_inflacion_global = sum(r['ganancia_perdida_inflacion'] for r in resumen_proyectos)
        proyectos_con_uf = sum(1 for r in resumen_proyectos if r['tiene_contratos_uf'])

        # Agrupar proyectos por cliente para estructura desplegable
        proyectos_por_cliente = {}
        for proyecto in resumen_proyectos:
            cliente_nombre = proyecto['proyecto'].cliente.nombre if proyecto['proyecto'].cliente else 'Sin Cliente'
            if cliente_nombre not in proyectos_por_cliente:
                proyectos_por_cliente[cliente_nombre] = {
                    'nombre': cliente_nombre,
                    'proyectos': [],
                    'total_contratos': 0,
                    'total_facturado': 0,
                    'total_pagado': 0,
                    'total_pendiente_facturar': 0,
                    'total_pendiente_cobrar': 0,
                    'total_ganancia_perdida_inflacion': 0
                }

            proyectos_por_cliente[cliente_nombre]['proyectos'].append(proyecto)
            proyectos_por_cliente[cliente_nombre]['total_contratos'] += proyecto['total_contratos']
            proyectos_por_cliente[cliente_nombre]['total_facturado'] += proyecto['total_facturado']
            proyectos_por_cliente[cliente_nombre]['total_pagado'] += proyecto['total_pagado']
            proyectos_por_cliente[cliente_nombre]['total_pendiente_facturar'] += proyecto['total_pendiente_facturar']
            proyectos_por_cliente[cliente_nombre]['total_pendiente_cobrar'] += proyecto['total_pendiente_cobrar']
            proyectos_por_cliente[cliente_nombre]['total_ganancia_perdida_inflacion'] += proyecto['ganancia_perdida_inflacion']

        # Convertir a lista ordenada alfabéticamente por cliente
        clientes_ordenados = sorted(proyectos_por_cliente.values(), key=lambda x: x['nombre'])

        return render_template('finanzas/dashboard_simple.html',
                             resumen_proyectos=resumen_proyectos,
                             clientes_ordenados=clientes_ordenados,
                             total_proyectos=total_proyectos,
                             total_contratos=total_contratos_global,
                             total_facturado=total_facturado_global,
                             total_pagado=total_pagado_global,
                             total_pendiente=total_pendiente_global,
                             total_ganancia_perdida_inflacion=total_ganancia_perdida_inflacion_global,
                             proyectos_con_uf=proyectos_con_uf,
                             inflacion_service=InflacionService,
                             current_user=current_user)

    except Exception as e:
        logger.error(f"Error en dashboard financiero: {e}")
        flash('Error al cargar el dashboard financiero', 'error')
        return redirect(url_for('index'))

@finanzas_bp.route('/proyectos-terminados')
@login_required
@finanzas_required
def proyectos_terminados():
    """Vista de proyectos terminados con resumen financiero completo"""
    try:
        finanzas_service = FinanzasService()
        proyectos_terminados = finanzas_service.get_proyectos_terminados_resumen()

        # Calcular totales generales
        total_proyectos = len(proyectos_terminados)
        total_contratos_valor = sum(p['total_contratos'] for p in proyectos_terminados)
        total_facturado_valor = sum(p['total_facturado'] for p in proyectos_terminados)
        total_pagado_valor = sum(p['total_pagado'] for p in proyectos_terminados)
        total_costos_valor = sum(p['total_costos'] for p in proyectos_terminados)
        total_margen = sum(p['margen_bruto'] for p in proyectos_terminados)

        # Indicadores agregados
        proyectos_cerrados_financieramente = sum(1 for p in proyectos_terminados if p['proyecto_cerrado_financieramente'])
        porcentaje_cerrados = (float(proyectos_cerrados_financieramente) / float(total_proyectos) * 100) if total_proyectos > 0 else 0

        resumen_general = {
            'total_proyectos': total_proyectos,
            'proyectos_cerrados_financieramente': proyectos_cerrados_financieramente,
            'porcentaje_cerrados': porcentaje_cerrados,
            'total_contratos': total_contratos_valor,
            'total_facturado': total_facturado_valor,
            'total_pagado': total_pagado_valor,
            'total_costos': total_costos_valor,
            'margen_total': total_margen,
            'margen_promedio_pct': (float(total_margen) / float(total_facturado_valor) * 100) if total_facturado_valor > 0 else 0
        }

        return render_template('finanzas/proyectos_terminados.html', 
                             proyectos=proyectos_terminados,
                             resumen=resumen_general)

    except Exception as e:
        logger.error(f"Error cargando proyectos terminados: {str(e)}")
        flash(f'Error cargando proyectos terminados: {str(e)}', 'error')
        return redirect(url_for('finanzas.dashboard'))

@finanzas_bp.route('/proyecto/<int:proyecto_id>')
@login_required
@finanzas_required
def detalle_proyecto(proyecto_id):
    """Vista detallada de un proyecto con sus contratos y estados de pago"""
    try:
        proyecto = db.session.query(Proyecto).options(
            joinedload(Proyecto.cliente),
            joinedload(Proyecto.contratos).joinedload(Contrato.estados_pago)
        ).filter_by(id=proyecto_id).first()

        if not proyecto:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('finanzas.dashboard'))

        # Obtener costos reales registrados del proyecto
        costos_registrados = db.session.query(CostoProyecto).filter_by(
            proyecto_id=proyecto_id
        ).order_by(CostoProyecto.fecha_registro.desc()).all()

        # Calcular totales
        total_ingresos = float(sum(c.monto_total or 0 for c in proyecto.contratos))

        # Usar costos reales si están disponibles, sino estimados
        if costos_registrados:
            total_costos = float(sum(costo.monto for costo in costos_registrados))
            costos_son_estimados = False

            # Resumen por categorías
            resumen_costos = {}
            for costo in costos_registrados:
                categoria = costo.categoria.value
                if categoria not in resumen_costos:
                    resumen_costos[categoria] = 0
                resumen_costos[categoria] += float(costo.monto)
        else:
            # Calcular costos estimados basados en márgenes de venta
            costo_estimado_provision = 0.0
            costo_estimado_instalacion = 0.0

            if proyecto.monto_provision_presupuestado and proyecto.margen_venta_provision:
                monto_provision = float(proyecto.monto_provision_presupuestado)
                margen_provision = float(proyecto.margen_venta_provision)
                costo_estimado_provision = monto_provision * (1 - margen_provision / 100)

            if proyecto.monto_instalacion_presupuestado and proyecto.margen_venta_instalacion:
                monto_instalacion = float(proyecto.monto_instalacion_presupuestado) 
                margen_instalacion = float(proyecto.margen_venta_instalacion)
                costo_estimado_instalacion = monto_instalacion * (1 - margen_instalacion / 100)

            total_costos = costo_estimado_provision + costo_estimado_instalacion
            costos_son_estimados = True
            resumen_costos = {
                'Provisión (estimado)': costo_estimado_provision,
                'Instalación (estimado)': costo_estimado_instalacion
            }

        margen = total_ingresos - total_costos
        margen_porcentaje = (float(margen) / float(total_ingresos) * 100) if total_ingresos > 0 else 0

        return render_template('finanzas/detalle_proyecto.html',
                             proyecto=proyecto,
                             costos_registrados=costos_registrados,
                             costos=costos_registrados,  # Para compatibilidad con template
                             resumen_costos=resumen_costos,
                             num_costos=len(costos_registrados),
                             total_ingresos=total_ingresos,
                             total_costos=total_costos,
                             margen=margen,
                             margen_porcentaje=margen_porcentaje,
                             costos_son_estimados=costos_son_estimados,
                             current_user=current_user)

    except Exception as e:
        logger.error(f"Error en detalle de proyecto: {e}")
        flash('Error al cargar el detalle del proyecto', 'error')
        return redirect(url_for('finanzas.dashboard'))

@finanzas_bp.route('/contrato/<int:contrato_id>/estados')
@login_required
@finanzas_required
def estados_pago_contrato(contrato_id):
    """Gestión de estados de pago de un contrato"""
    try:
        contrato = db.session.query(Contrato).options(
            joinedload(Contrato.proyecto).joinedload(Proyecto.cliente),
            joinedload(Contrato.estados_pago)
        ).filter_by(id=contrato_id).first()

        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('finanzas.dashboard'))

        # Usar FinanzasService para cálculos dinámicos
        finanzas_service = FinanzasService()
        agregaciones = finanzas_service.get_contratos_aggregates()

        # Encontrar agregación para este contrato
        agg_contrato = next((agg for agg in agregaciones if agg['contrato_id'] == contrato_id), None)

        if agg_contrato:
            total_facturado = Decimal(str(agg_contrato['total_facturado']))
            total_pagado = Decimal(str(agg_contrato['total_pagado']))
            total_pendiente = Decimal(str(agg_contrato['pendiente_facturar']))  # Calculado dinámicamente
        else:
            # Fallback a cálculo manual (sin incluir PENDIENTE_FACTURAR)
            total_facturado = sum(e.monto for e in contrato.estados_pago 
                                if e.tipo_estado in [TipoEstadoPago.FACTURADO, TipoEstadoPago.PAGADO])
            total_pagado = sum(e.monto for e in contrato.estados_pago 
                             if e.tipo_estado == TipoEstadoPago.PAGADO)
            total_contrato = contrato.monto_total or Decimal(0)
            total_pendiente = max(Decimal(0), total_contrato - total_facturado)

        return render_template('finanzas/estados_pago.html',
                             contrato=contrato,
                             total_facturado=total_facturado,
                             total_pagado=total_pagado,
                             total_pendiente=total_pendiente,
                             tipos_estado=TipoEstadoPago,
                             current_user=current_user)

    except Exception as e:
        logger.error(f"Error en estados de pago: {e}")
        flash('Error al cargar los estados de pago', 'error')
        return redirect(url_for('finanzas.dashboard'))

@finanzas_bp.route('/contrato/<int:contrato_id>/estado/nuevo', methods=['GET', 'POST'])
@login_required
@finanzas_required
def nuevo_estado_pago(contrato_id):
    """Crear nuevo estado de pago para un contrato"""
    try:
        contrato = db.session.query(Contrato).options(
            joinedload(Contrato.proyecto)
        ).filter_by(id=contrato_id).first()

        if not contrato:
            flash('Contrato no encontrado', 'error')
            return redirect(url_for('finanzas.estados_pago_contrato', contrato_id=contrato_id))

        if request.method == 'POST':
            # Validar datos requeridos
            tipo_estado_str = request.form.get('tipo_estado')
            fecha_estado_str = request.form.get('fecha_estado')
            fecha_programada_str = request.form.get('fecha_programada_pago')

            if not tipo_estado_str or not fecha_estado_str:
                flash('Tipo de estado y fecha son requeridos', 'error')
                return redirect(url_for('finanzas.nuevo_estado_pago', contrato_id=contrato_id))

            # NUEVA VALIDACIÓN: Rechazar creación de PENDIENTE_FACTURAR
            if tipo_estado_str == 'PENDIENTE_FACTURAR':
                flash('Ya no es posible crear estados "Pendiente por Facturar" manualmente. Los montos pendientes se calculan automáticamente.', 'error')
                return redirect(url_for('finanzas.nuevo_estado_pago', contrato_id=contrato_id))

            # Determinar tipo de moneda del estado de pago
            moneda_tipo = request.form.get('moneda_tipo', 'CLP')

            # Crear nuevo estado de pago
            estado = EstadoPago()
            estado.contrato_id = contrato_id
            estado.tipo_estado = TipoEstadoPago[tipo_estado_str]
            estado.numero_documento = request.form.get('numero_documento')
            estado.fecha_estado = datetime.strptime(fecha_estado_str, '%Y-%m-%d').date()
            estado.descripcion = request.form.get('descripcion')
            estado.fecha_programada_pago = datetime.strptime(fecha_programada_str, '%Y-%m-%d').date() if fecha_programada_str else None
            estado.moneda_original = moneda_tipo
            estado.created_by = current_user.id

            # Configurar campos según el tipo de moneda (validación server-side)
            if moneda_tipo == 'UF':
                # Estado en UF - usar servicio UF para conversión server-side
                monto_uf_input = request.form.get('monto_uf', '0')
                if monto_uf_input:
                    estado.monto_uf = Decimal(monto_uf_input)

                    # Obtener valor UF server-side (no confiar en cliente)
                    from services.uf_conversion_service import UfConversionService
                    clp_amount = UfConversionService.convert_uf_to_clp(estado.monto_uf, estado.fecha_estado)
                    valor_uf_fecha = UfConversionService.get_uf_value_for_date(estado.fecha_estado)

                    if clp_amount and valor_uf_fecha:
                        estado.valor_uf_fecha_estado = valor_uf_fecha
                        estado.monto_clp_equivalente = clp_amount
                        estado.monto = clp_amount  # Monto principal en CLP
                        estado.fecha_conversion_uf = estado.fecha_estado
                    else:
                        flash('Error obteniendo valor UF para conversión', 'error')
                        return redirect(url_for('finanzas.nuevo_estado_pago', contrato_id=contrato_id))
                else:
                    flash('Monto UF es requerido para estados en UF', 'error')
                    return redirect(url_for('finanzas.nuevo_estado_pago', contrato_id=contrato_id))
            else:
                # Estado en CLP tradicional
                monto_clp_input = request.form.get('monto', '0')
                estado.monto = Decimal(monto_clp_input)

            db.session.add(estado)
            db.session.flush()  # Para obtener ID antes de commit

            # Calcular efectos de inflación si es aplicable
            if moneda_tipo == 'UF':
                try:
                    InflacionService.actualizar_ganancias_perdidas_estado(estado)
                except Exception as e:
                    logger.warning(f"Error calculando efectos inflación para estado {estado.id}: {e}")

            db.session.commit()

            flash(f'Estado de pago creado exitosamente', 'success')
            return redirect(url_for('finanzas.estados_pago_contrato', contrato_id=contrato_id))

        # Definir tipos de estado típicos para contratos
        tipos_comunes = ['ANTICIPO', 'AVANCE', 'RETENCION']

        # Calcular saldos disponibles correctos usando FinanzasService
        finanzas_service = FinanzasService()
        agregaciones = finanzas_service.get_contratos_aggregates()

        # Encontrar agregación para este contrato
        agg_contrato = next((agg for agg in agregaciones if agg['contrato_id'] == contrato_id), None)

        if agg_contrato:
            saldo_disponible_facturar = agg_contrato['pendiente_facturar']
            saldo_disponible_cobrar = agg_contrato['pendiente_cobro']
        else:
            # Fallback a cálculo manual
            total_contrato = contrato.monto_total or 0
            total_facturado = sum(e.monto for e in contrato.estados_pago 
                                if e.tipo_estado in [TipoEstadoPago.FACTURADO, TipoEstadoPago.PAGADO])
            total_pagado = sum(e.monto for e in contrato.estados_pago 
                             if e.tipo_estado == TipoEstadoPago.PAGADO)
            saldo_disponible_facturar = max(0, total_contrato - total_facturado)
            saldo_disponible_cobrar = max(0, total_facturado - total_pagado)

        return render_template('finanzas/nuevo_estado_pago.html',
                             contrato=contrato,
                             tipos_estado=TipoEstadoPago,
                             tipos_comunes=tipos_comunes,
                             saldo_disponible_facturar=saldo_disponible_facturar,
                             saldo_disponible_cobrar=saldo_disponible_cobrar,
                             current_user=current_user)

    except Exception as e:
        logger.error(f"Error creando estado de pago: {e}")
        db.session.rollback()
        flash('Error al crear el estado de pago', 'error')
        return redirect(url_for('finanzas.estados_pago_contrato', contrato_id=contrato_id))

@finanzas_bp.route('/estado-pago/<int:estado_id>/editar', methods=['GET', 'POST'])
@login_required
@finanzas_required
def editar_estado_pago(estado_id):
    """Editar un estado de pago existente"""
    try:
        estado = db.session.query(EstadoPago).options(
            joinedload(EstadoPago.contrato).joinedload(Contrato.proyecto)
        ).filter_by(id=estado_id).first()

        if not estado:
            flash('Estado de pago no encontrado', 'error')
            return redirect(url_for('finanzas.dashboard'))

        contrato = estado.contrato

        if request.method == 'POST':
            # Validar datos requeridos
            tipo_estado_str = request.form.get('tipo_estado')
            fecha_estado_str = request.form.get('fecha_estado')
            fecha_programada_str = request.form.get('fecha_programada_pago')

            if not tipo_estado_str or not fecha_estado_str:
                flash('Tipo de estado y fecha son requeridos', 'error')
                return redirect(url_for('finanzas.editar_estado_pago', estado_id=estado_id))

            # VALIDACIÓN: Rechazar edición a PENDIENTE_FACTURAR
            if tipo_estado_str == 'PENDIENTE_FACTURAR':
                flash('Ya no es posible usar el estado "Pendiente por Facturar". Los montos pendientes se calculan automáticamente.', 'error')
                return redirect(url_for('finanzas.editar_estado_pago', estado_id=estado_id))

            # Determinar tipo de moneda del estado de pago
            moneda_tipo = request.form.get('moneda_tipo', 'CLP')

            # Actualizar estado de pago
            estado.tipo_estado = TipoEstadoPago[tipo_estado_str]
            estado.numero_documento = request.form.get('numero_documento')
            estado.fecha_estado = datetime.strptime(fecha_estado_str, '%Y-%m-%d').date()
            estado.descripcion = request.form.get('descripcion')
            estado.fecha_programada_pago = datetime.strptime(fecha_programada_str, '%Y-%m-%d').date() if fecha_programada_str else None
            estado.moneda_original = moneda_tipo

            # Configurar campos según el tipo de moneda
            if moneda_tipo == 'UF':
                # Estado en UF - usar servicio UF para conversión
                monto_uf_input = request.form.get('monto_uf', '0')
                if monto_uf_input:
                    estado.monto_uf = Decimal(monto_uf_input)

                    # Obtener valor UF server-side
                    from services.uf_conversion_service import UfConversionService
                    clp_amount = UfConversionService.convert_uf_to_clp(estado.monto_uf, estado.fecha_estado)
                    valor_uf_fecha = UfConversionService.get_uf_value_for_date(estado.fecha_estado)

                    if clp_amount and valor_uf_fecha:
                        estado.valor_uf_fecha_estado = valor_uf_fecha
                        estado.monto_clp_equivalente = clp_amount
                        estado.monto = clp_amount
                        estado.fecha_conversion_uf = estado.fecha_estado
                    else:
                        flash('Error obteniendo valor UF para conversión', 'error')
                        return redirect(url_for('finanzas.editar_estado_pago', estado_id=estado_id))
                else:
                    flash('Monto UF es requerido para estados en UF', 'error')
                    return redirect(url_for('finanzas.editar_estado_pago', estado_id=estado_id))
            else:
                # Estado en CLP tradicional
                monto_clp_input = request.form.get('monto', '0')
                estado.monto = Decimal(monto_clp_input)
                # Limpiar campos UF si cambia de UF a CLP
                estado.monto_uf = None
                estado.valor_uf_fecha_estado = None
                estado.monto_clp_equivalente = None
                estado.fecha_conversion_uf = None

            # Actualizar efectos de inflación si es aplicable
            if moneda_tipo == 'UF':
                try:
                    InflacionService.actualizar_ganancias_perdidas_estado(estado)
                except Exception as e:
                    logger.warning(f"Error calculando efectos inflación para estado {estado.id}: {e}")

            db.session.commit()

            flash(f'Estado de pago actualizado exitosamente', 'success')
            return redirect(url_for('finanzas.estados_pago_contrato', contrato_id=contrato.id))

        # Calcular saldos disponibles usando FinanzasService
        finanzas_service = FinanzasService()
        agregaciones = finanzas_service.get_contratos_aggregates()

        # Encontrar agregación para este contrato
        agg_contrato = next((agg for agg in agregaciones if agg['contrato_id'] == contrato.id), None)

        if agg_contrato:
            saldo_disponible_facturar = agg_contrato['pendiente_facturar']
            saldo_disponible_cobrar = agg_contrato['pendiente_cobro']
        else:
            # Fallback a cálculo manual
            total_contrato = contrato.monto_total or 0
            total_facturado = sum(e.monto for e in contrato.estados_pago 
                                if e.tipo_estado in [TipoEstadoPago.FACTURADO, TipoEstadoPago.PAGADO])
            total_pagado = sum(e.monto for e in contrato.estados_pago 
                             if e.tipo_estado == TipoEstadoPago.PAGADO)
            saldo_disponible_facturar = max(0, total_contrato - total_facturado)
            saldo_disponible_cobrar = max(0, total_facturado - total_pagado)

        # Sumar el monto del estado actual para mostrar saldo disponible correcto
        if estado.tipo_estado in [TipoEstadoPago.FACTURADO, TipoEstadoPago.PAGADO]:
            saldo_disponible_facturar += float(estado.monto or 0)
        if estado.tipo_estado == TipoEstadoPago.PAGADO:
            saldo_disponible_cobrar += float(estado.monto or 0)

        return render_template('finanzas/editar_estado_pago.html',
                             estado=estado,
                             contrato=contrato,
                             tipos_estado=TipoEstadoPago,
                             saldo_disponible_facturar=saldo_disponible_facturar,
                             saldo_disponible_cobrar=saldo_disponible_cobrar,
                             current_user=current_user)

    except Exception as e:
        logger.error(f"Error editando estado de pago: {e}")
        db.session.rollback()
        flash('Error al editar el estado de pago', 'error')
        return redirect(url_for('finanzas.dashboard'))

@finanzas_bp.route('/estado-pago/<int:estado_id>/eliminar', methods=['DELETE'])
@login_required
@finanzas_required
def eliminar_estado_pago(estado_id):
    """Eliminar un estado de pago"""
    try:
        estado = db.session.query(EstadoPago).filter_by(id=estado_id).first()

        if not estado:
            return jsonify({'success': False, 'message': 'Estado de pago no encontrado'}), 404

        contrato_id = estado.contrato_id
        
        # Verificar permisos (solo admin o creador puede eliminar)
        if current_user.rol != RolUsuario.ADMIN and estado.created_by != current_user.id:
            return jsonify({'success': False, 'message': 'No tiene permisos para eliminar este estado'}), 403

        db.session.delete(estado)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Estado de pago eliminado exitosamente'})

    except Exception as e:
        logger.error(f"Error eliminando estado de pago: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Error al eliminar el estado de pago'}), 500

@finanzas_bp.route('/proyecto/<int:proyecto_id>/costos')
@login_required
@finanzas_required
def costos_proyecto(proyecto_id):
    """Lista de costos registrados del proyecto"""
    try:
        proyecto = db.session.query(Proyecto).options(
            joinedload(Proyecto.cliente)
        ).filter_by(id=proyecto_id).first()

        if not proyecto:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('finanzas.dashboard'))

        # Obtener costos del proyecto ordenados por fecha
        costos = db.session.query(CostoProyecto).filter_by(
            proyecto_id=proyecto_id
        ).order_by(CostoProyecto.fecha_registro.desc()).all()

        # Calcular totales por categoría
        resumen_categorias = {}
        total_costos = 0

        for costo in costos:
            categoria = costo.categoria.value
            monto = float(costo.monto)

            if categoria not in resumen_categorias:
                resumen_categorias[categoria] = {
                    'categoria': categoria,
                    'total': 0,
                    'cantidad': 0
                }

            resumen_categorias[categoria]['total'] += monto
            resumen_categorias[categoria]['cantidad'] += 1
            total_costos += monto

        return render_template('finanzas/costos_proyecto.html',
                             proyecto=proyecto,
                             costos=costos,
                             resumen_categorias=list(resumen_categorias.values()),
                             total_costos=total_costos,
                             categorias=CategoriaCosto,
                             current_user=current_user)

    except Exception as e:
        logger.error(f"Error en costos del proyecto: {e}")
        flash('Error al cargar los costos del proyecto', 'error')
        return redirect(url_for('finanzas.dashboard'))

@finanzas_bp.route('/proyecto/<int:proyecto_id>/costo/nuevo', methods=['GET', 'POST'])
@login_required
@finanzas_required
def nuevo_costo_proyecto(proyecto_id):
    """Registrar nuevo costo desde ERP"""
    try:
        proyecto = db.session.query(Proyecto).options(
            joinedload(Proyecto.cliente)
        ).filter_by(id=proyecto_id).first()

        if not proyecto:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('finanzas.dashboard'))

        if request.method == 'POST':
            # Validar datos del formulario
            categoria_str = request.form.get('categoria')
            descripcion = request.form.get('descripcion', '').strip()
            monto_str = request.form.get('monto', '0')
            fecha_registro_str = request.form.get('fecha_registro')

            # Campos opcionales
            codigo_erp = request.form.get('codigo_erp', '').strip()
            documento_referencia = request.form.get('documento_referencia', '').strip()
            proveedor = request.form.get('proveedor', '').strip()

            # Validaciones
            if not categoria_str or not descripcion or not fecha_registro_str:
                flash('Categoría, descripción y fecha son requeridos', 'error')
                return redirect(url_for('finanzas.nuevo_costo_proyecto', proyecto_id=proyecto_id))

            try:
                # Validar categoria usando enum
                categoria = CategoriaCosto[categoria_str]
                monto = Decimal(monto_str.replace(',', ''))  # Remover separadores de miles
                fecha_registro = datetime.strptime(fecha_registro_str, '%Y-%m-%d').date()

                if monto <= 0:
                    flash('El monto debe ser mayor a 0', 'error')
                    return redirect(url_for('finanzas.nuevo_costo_proyecto', proyecto_id=proyecto_id))

                # Validar fecha no futura
                if fecha_registro > datetime.now().date():
                    flash('La fecha no puede ser futura', 'error')
                    return redirect(url_for('finanzas.nuevo_costo_proyecto', proyecto_id=proyecto_id))

            except (ValueError, KeyError) as e:
                flash(f'Error en los datos ingresados: {str(e)}', 'error')
                return redirect(url_for('finanzas.nuevo_costo_proyecto', proyecto_id=proyecto_id))

            # Crear nuevo costo
            costo = CostoProyecto(
                proyecto_id=proyecto_id,
                categoria=categoria,
                descripcion=descripcion,
                monto=monto,
                fecha_registro=fecha_registro,
                codigo_erp=codigo_erp if codigo_erp else None,
                documento_referencia=documento_referencia if documento_referencia else None,
                proveedor=proveedor if proveedor else None,
                created_by=current_user.id
            )

            db.session.add(costo)
            db.session.commit()

            flash(f'Costo registrado exitosamente: {categoria.value} - ${monto:,.0f}', 'success')
            return redirect(url_for('finanzas.costos_proyecto', proyecto_id=proyecto_id))

        return render_template('finanzas/nuevo_costo.html',
                             proyecto=proyecto,
                             categorias=CategoriaCosto,
                             current_user=current_user)

    except Exception as e:
        logger.error(f"Error registrando costo: {e}")
        db.session.rollback()
        flash('Error al registrar el costo', 'error')
        return redirect(url_for('finanzas.costos_proyecto', proyecto_id=proyecto_id))

@finanzas_bp.route('/reportes')
@login_required
@finanzas_required
def reportes():
    """Vista de reportes financieros disponibles"""
    return render_template('finanzas/reportes_simple.html',
                         current_user=current_user)

@finanzas_bp.route('/proyecto/<int:proyecto_id>/resumen-financiero')
@login_required
@finanzas_required
def resumen_financiero_proyecto(proyecto_id):
    """Resumen financiero detallado e imprimible del proyecto"""
    try:
        from datetime import date
        from services.inflacion_service import InflacionService

        proyecto = db.session.query(Proyecto).options(
            joinedload(Proyecto.cliente),
            joinedload(Proyecto.contratos).joinedload(Contrato.estados_pago)
        ).filter_by(id=proyecto_id).first()

        if not proyecto:
            flash('Proyecto no encontrado', 'error')
            return redirect(url_for('finanzas.dashboard'))

        # === INGRESOS DEL PROYECTO ===
        
        # Obtener contratos y calcular totales
        contratos_detalle = []
        total_contratos_clp = Decimal(0)
        total_diferencia_uf = Decimal(0)
        
        for contrato in proyecto.contratos:
            contrato_info = {
                'numero_oc': contrato.numero_oc,
                'tipo': contrato.tipo_documento.value,
                'monto_original': float(contrato.monto_total or 0),
                'moneda_original': contrato.moneda_original,
                'diferencia_uf': 0
            }
            
            # Si el contrato fue en UF, calcular diferencia por inflación
            if contrato.moneda_original == 'UF':
                resumen_inflacion = InflacionService.calcular_resumen_inflacion_contrato(contrato)
                if resumen_inflacion.get('total_ganancia_perdida'):
                    contrato_info['diferencia_uf'] = float(resumen_inflacion['total_ganancia_perdida'])
                    total_diferencia_uf += Decimal(str(contrato_info['diferencia_uf']))
            
            contratos_detalle.append(contrato_info)
            total_contratos_clp += Decimal(str(contrato_info['monto_original']))

        total_ingresos_proyecto = total_contratos_clp + total_diferencia_uf

        # === COSTOS DEL PROYECTO ===
        
        # Obtener costos registrados del ERP
        costos_registrados = db.session.query(CostoProyecto).filter_by(
            proyecto_id=proyecto_id
        ).order_by(CostoProyecto.fecha_registro.desc()).all()

        # Agrupar costos por categoría
        costos_por_categoria = {}
        total_costos_reales = Decimal(0)
        
        for costo in costos_registrados:
            categoria = costo.categoria.value
            if categoria not in costos_por_categoria:
                costos_por_categoria[categoria] = {
                    'total': Decimal(0),
                    'registros': []
                }
            
            costos_por_categoria[categoria]['total'] += costo.monto
            costos_por_categoria[categoria]['registros'].append(costo)
            total_costos_reales += costo.monto

        # === CÁLCULOS DE MÁRGENES ===
        
        # Margen operacional (ingresos - costos provisión/materiales)
        costo_provision_materiales = costos_por_categoria.get('MATERIALES_PROVISION', {}).get('total', Decimal(0))
        resultado_operacional = total_ingresos_proyecto - costo_provision_materiales
        margen_operacional_pct = (float(resultado_operacional) / float(total_ingresos_proyecto) * 100) if total_ingresos_proyecto > 0 else 0

        # Margen presupuestado provisión
        margen_presupuestado_provision = Decimal(0)
        if proyecto.monto_provision_presupuestado and proyecto.margen_venta_provision:
            monto_provision = Decimal(str(proyecto.monto_provision_presupuestado))
            margen_provision = Decimal(str(proyecto.margen_venta_provision))
            margen_presupuestado_provision = monto_provision * (margen_provision / 100)
        
        diferencia_margen_operacional = resultado_operacional - margen_presupuestado_provision

        # Otros costos
        costo_instalacion = costos_por_categoria.get('INSTALACION', {}).get('total', Decimal(0))
        costo_flete = costos_por_categoria.get('FLETES_DESPACHO', {}).get('total', Decimal(0))
        costo_garantias = costos_por_categoria.get('GARANTIAS_SERVICIO', {}).get('total', Decimal(0))
        costo_otros = sum(
            info['total'] for cat, info in costos_por_categoria.items() 
            if cat not in ['MATERIALES_PROVISION', 'INSTALACION', 'FLETES_DESPACHO', 'GARANTIAS_SERVICIO']
        )

        total_gastos = costo_instalacion + costo_flete + costo_garantias + costo_otros

        # Resultado final
        resultado_final = total_ingresos_proyecto - total_costos_reales
        margen_final_pct = (float(resultado_final) / float(total_ingresos_proyecto) * 100) if total_ingresos_proyecto > 0 else 0

        # Margen general presupuestado (provisión + instalación)
        margen_presupuestado_instalacion = Decimal(0)
        if proyecto.monto_instalacion_presupuestado and proyecto.margen_venta_instalacion:
            monto_instalacion = Decimal(str(proyecto.monto_instalacion_presupuestado))
            margen_instalacion = Decimal(str(proyecto.margen_venta_instalacion))
            margen_presupuestado_instalacion = monto_instalacion * (margen_instalacion / 100)

        margen_presupuestado_total = margen_presupuestado_provision + margen_presupuestado_instalacion

        

        # Preparar datos para el template
        resumen_datos = {
            'proyecto': proyecto,
            'fecha_reporte': date.today(),
            'contratos_detalle': contratos_detalle,
            'total_contratos_clp': float(total_contratos_clp),
            'total_diferencia_uf': float(total_diferencia_uf),
            'total_ingresos_proyecto': float(total_ingresos_proyecto),
            
            # Costos por categoría
            'costo_provision_materiales': float(costo_provision_materiales),
            'costo_instalacion': float(costo_instalacion),
            'costo_flete': float(costo_flete),
            'costo_garantias': float(costo_garantias),
            'costo_otros': float(costo_otros),
            'total_gastos': float(total_gastos),
            'total_costos_reales': float(total_costos_reales),
            
            # Resultados y márgenes
            'resultado_operacional': float(resultado_operacional),
            'margen_operacional_pct': margen_operacional_pct,
            'margen_presupuestado_provision': float(margen_presupuestado_provision),
            'diferencia_margen_operacional': float(diferencia_margen_operacional),
            
            'resultado_final': float(resultado_final),
            'margen_final_pct': margen_final_pct,
            'margen_presupuestado_total': float(margen_presupuestado_total),
            
            # Datos adicionales
            'costos_por_categoria': {cat: float(info['total']) for cat, info in costos_por_categoria.items()},
            'hay_costos_registrados': len(costos_registrados) > 0,
            'num_costos_registrados': len(costos_registrados)
        }

        return render_template('finanzas/resumen_financiero_proyecto.html',
                             resumen=resumen_datos,
                             current_user=current_user)

    except Exception as e:
        logger.error(f"Error en resumen financiero del proyecto {proyecto_id}: {e}")
        flash('Error al generar el resumen financiero del proyecto', 'error')
        return redirect(url_for('finanzas.detalle_proyecto', proyecto_id=proyecto_id))

@finanzas_bp.route('/reporte/analisis-proyectos')
@login_required
@finanzas_required
def reporte_analisis_proyectos():
    """Reporte de análisis financiero de proyectos"""
    try:
        # Obtener proyectos con análisis financiero
        proyectos = db.session.query(Proyecto).filter(
            Proyecto.activo == True
        ).options(
            joinedload(Proyecto.cliente),
            joinedload(Proyecto.contratos).joinedload(Contrato.estados_pago)
        ).all()

        analisis = []
        for proyecto in proyectos:
            # Calcular ingresos
            total_contratos = float(sum(c.monto_total or 0 for c in proyecto.contratos))
            total_facturado = float(sum(estado.monto or 0 for contrato in proyecto.contratos for estado in contrato.estados_pago if estado.tipo_estado == TipoEstadoPago.FACTURADO))
            total_pagado = float(sum(estado.monto or 0 for contrato in proyecto.contratos for estado in contrato.estados_pago if estado.tipo_estado == TipoEstadoPago.PAGADO))

            # Calcular costos estimados basados en márgenes de venta del proyecto
            # Si no hay costos reales del ERP, usar los estimados
            costo_estimado_provision = 0.0
            costo_estimado_instalacion = 0.0

            if proyecto.monto_provision_presupuestado and proyecto.margen_venta_provision:
                monto_provision = float(proyecto.monto_provision_presupuestado)
                margen_provision = float(proyecto.margen_venta_provision)
                costo_estimado_provision = monto_provision * (1 - margen_provision / 100)

            if proyecto.monto_instalacion_presupuestado and proyecto.margen_venta_instalacion:
                monto_instalacion = float(proyecto.monto_instalacion_presupuestado) 
                margen_instalacion = float(proyecto.margen_venta_instalacion)
                costo_estimado_instalacion = monto_instalacion * (1 - margen_instalacion / 100)

            total_costos = costo_estimado_provision + costo_estimado_instalacion
            margen = total_contratos - total_costos
            margen_porcentaje = (float(margen) / float(total_contratos) * 100) if total_contratos > 0 else 0

            analisis.append({
                'proyecto': proyecto,
                'cliente': proyecto.cliente.nombre if proyecto.cliente else 'Sin cliente',
                'total_contratos': total_contratos,
                'total_facturado': total_facturado,
                'total_pagado': total_pagado,
                'total_costos': total_costos,
                'margen': margen,
                'margen_porcentaje': margen_porcentaje,
                'avance_facturacion': (float(total_facturado) / float(total_contratos) * 100) if total_contratos > 0 else 0,
                'avance_cobro': (float(total_pagado) / float(total_contratos) * 100) if total_contratos > 0 else 0
            })

        # Ordenar por margen
        analisis.sort(key=lambda x: x['margen'], reverse=True)

        return render_template('finanzas/reporte_analisis.html',
                             analisis=analisis,
                             current_user=current_user)

    except Exception as e:
        logger.error(f"Error en reporte de análisis: {e}")
        flash('Error al generar el reporte', 'error')
        return redirect(url_for('finanzas.reportes'))