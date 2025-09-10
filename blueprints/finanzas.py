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
    Proyecto, Contrato, EstadoPago, Cliente,
    TipoEstadoPago, RolUsuario, CostoProyecto, CategoriaCosto
)
from services.inflacion_service import InflacionService

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
        # Obtener todos los proyectos activos con sus contratos
        proyectos = db.session.query(Proyecto).filter(
            Proyecto.activo == True
        ).options(
            joinedload(Proyecto.cliente),
            joinedload(Proyecto.contratos).joinedload(Contrato.estados_pago)
        ).order_by(Proyecto.nombre).all()
        
        # Calcular resumen por proyecto con efectos de inflación UF
        resumen_proyectos = []
        for proyecto in proyectos:
            # Calcular totales de contratos
            total_contratos = sum(c.monto_total or 0 for c in proyecto.contratos)
            total_facturado = 0
            total_pagado = 0
            total_pendiente = 0
            total_ganancia_perdida_inflacion = 0
            tiene_contratos_uf = False
            
            for contrato in proyecto.contratos:
                # Verificar si tiene contratos UF
                if contrato.moneda_original == 'UF':
                    tiene_contratos_uf = True
                    # Calcular efectos de inflación para este contrato
                    resumen_inflacion = InflacionService.calcular_resumen_inflacion_contrato(contrato)
                    if resumen_inflacion.get('total_ganancia_perdida'):
                        total_ganancia_perdida_inflacion += float(resumen_inflacion['total_ganancia_perdida'])
                
                for estado in contrato.estados_pago:
                    if estado.tipo_estado == TipoEstadoPago.FACTURADO:
                        total_facturado += estado.monto or 0
                    elif estado.tipo_estado == TipoEstadoPago.PAGADO:
                        total_pagado += estado.monto or 0
                    elif estado.tipo_estado == TipoEstadoPago.PENDIENTE_FACTURAR:
                        total_pendiente += estado.monto or 0
            
            resumen_proyectos.append({
                'proyecto': proyecto,
                'num_contratos': len(proyecto.contratos),
                'total_contratos': total_contratos,
                'total_facturado': total_facturado,
                'total_pagado': total_pagado,
                'total_pendiente': total_pendiente,
                'avance_facturacion': (total_facturado / total_contratos * 100) if total_contratos > 0 else 0,
                'avance_cobro': (total_pagado / total_contratos * 100) if total_contratos > 0 else 0,
                'tiene_contratos_uf': tiene_contratos_uf,
                'ganancia_perdida_inflacion': total_ganancia_perdida_inflacion
            })
        
        # Calcular KPIs generales incluyendo efectos de inflación
        total_proyectos = len(proyectos)
        total_contratos_global = sum(r['total_contratos'] for r in resumen_proyectos)
        total_facturado_global = sum(r['total_facturado'] for r in resumen_proyectos)
        total_pagado_global = sum(r['total_pagado'] for r in resumen_proyectos)
        total_pendiente_global = sum(r['total_pendiente'] for r in resumen_proyectos)
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
                    'total_pendiente': 0,
                    'total_ganancia_perdida_inflacion': 0
                }
            
            proyectos_por_cliente[cliente_nombre]['proyectos'].append(proyecto)
            proyectos_por_cliente[cliente_nombre]['total_contratos'] += proyecto['num_contratos']
            proyectos_por_cliente[cliente_nombre]['total_facturado'] += proyecto['total_facturado']
            proyectos_por_cliente[cliente_nombre]['total_pagado'] += proyecto['total_pagado']
            proyectos_por_cliente[cliente_nombre]['total_pendiente'] += proyecto['total_pendiente']
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
                             current_user=current_user)
                             
    except Exception as e:
        logger.error(f"Error en dashboard financiero: {e}")
        flash('Error al cargar el dashboard financiero', 'error')
        return redirect(url_for('index'))

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
        margen_porcentaje = (margen / total_ingresos * 100) if total_ingresos > 0 else 0
        
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
        
        # Calcular resumen de estados
        total_contrato = contrato.monto_total or 0
        total_facturado = sum(e.monto for e in contrato.estados_pago 
                            if e.tipo_estado == TipoEstadoPago.FACTURADO)
        total_pagado = sum(e.monto for e in contrato.estados_pago 
                         if e.tipo_estado == TipoEstadoPago.PAGADO)
        total_pendiente = sum(e.monto for e in contrato.estados_pago 
                            if e.tipo_estado == TipoEstadoPago.PENDIENTE_FACTURAR)
        
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
        
        return render_template('finanzas/nuevo_estado_pago.html',
                             contrato=contrato,
                             tipos_estado=TipoEstadoPago,
                             tipos_comunes=tipos_comunes,
                             current_user=current_user)
                             
    except Exception as e:
        logger.error(f"Error creando estado de pago: {e}")
        db.session.rollback()
        flash('Error al crear el estado de pago', 'error')
        return redirect(url_for('finanzas.estados_pago_contrato', contrato_id=contrato_id))

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
            margen_porcentaje = (margen / total_contratos * 100) if total_contratos > 0 else 0
            
            analisis.append({
                'proyecto': proyecto,
                'cliente': proyecto.cliente.nombre if proyecto.cliente else 'Sin cliente',
                'total_contratos': total_contratos,
                'total_facturado': total_facturado,
                'total_pagado': total_pagado,
                'total_costos': total_costos,
                'margen': margen,
                'margen_porcentaje': margen_porcentaje,
                'avance_facturacion': (total_facturado / total_contratos * 100) if total_contratos > 0 else 0,
                'avance_cobro': (total_pagado / total_contratos * 100) if total_contratos > 0 else 0
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