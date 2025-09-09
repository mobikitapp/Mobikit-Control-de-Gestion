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
    TipoEstadoPago, RolUsuario
)

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
        
        # Calcular resumen por proyecto
        resumen_proyectos = []
        for proyecto in proyectos:
            # Calcular totales de contratos
            total_contratos = sum(c.monto_total or 0 for c in proyecto.contratos)
            total_facturado = 0
            total_pagado = 0
            total_pendiente = 0
            
            for contrato in proyecto.contratos:
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
                'avance_cobro': (total_pagado / total_contratos * 100) if total_contratos > 0 else 0
            })
        
        # Calcular KPIs generales
        total_proyectos = len(proyectos)
        total_contratos_global = sum(r['total_contratos'] for r in resumen_proyectos)
        total_facturado_global = sum(r['total_facturado'] for r in resumen_proyectos)
        total_pagado_global = sum(r['total_pagado'] for r in resumen_proyectos)
        total_pendiente_global = sum(r['total_pendiente'] for r in resumen_proyectos)
        
        return render_template('finanzas/dashboard_simple.html',
                             resumen_proyectos=resumen_proyectos,
                             total_proyectos=total_proyectos,
                             total_contratos=total_contratos_global,
                             total_facturado=total_facturado_global,
                             total_pagado=total_pagado_global,
                             total_pendiente=total_pendiente_global,
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
        proyecto = db.session.query(Proyecto).filter(
            Proyecto.id == proyecto_id
        ).options(
            joinedload(Proyecto.cliente),
            joinedload(Proyecto.contratos).joinedload(Contrato.estados_pago)
        ).first_or_404()
        
        # Obtener costos manuales del proyecto (tabla se creará si es necesaria)
        costos = []  # Por ahora vacío hasta implementar tabla de costos
        
        # Calcular totales
        total_ingresos = float(sum(c.monto_total or 0 for c in proyecto.contratos))
        
        # Calcular costos estimados basados en márgenes de venta hasta que se ingresen costos reales
        if not costos:  # Si no hay costos reales, usar estimados
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
        else:
            total_costos = sum(c.get('monto', 0) for c in costos)
            costos_son_estimados = False
        
        margen = total_ingresos - total_costos
        margen_porcentaje = (margen / total_ingresos * 100) if total_ingresos > 0 else 0
        
        return render_template('finanzas/detalle_proyecto.html',
                             proyecto=proyecto,
                             costos=costos,
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
        contrato = db.session.query(Contrato).filter(
            Contrato.id == contrato_id
        ).options(
            joinedload(Contrato.proyecto).joinedload(Proyecto.cliente),
            joinedload(Contrato.estados_pago)
        ).first_or_404()
        
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
        contrato = db.session.query(Contrato).filter(
            Contrato.id == contrato_id
        ).options(
            joinedload(Contrato.proyecto)
        ).first_or_404()
        
        if request.method == 'POST':
            # Crear nuevo estado de pago
            estado = EstadoPago(
                contrato_id=contrato_id,
                tipo_estado=TipoEstadoPago[request.form.get('tipo_estado')],
                numero_documento=request.form.get('numero_documento'),
                fecha_estado=datetime.strptime(request.form.get('fecha_estado'), '%Y-%m-%d').date(),
                monto=Decimal(request.form.get('monto', 0)),
                descripcion=request.form.get('descripcion'),
                fecha_programada_pago=datetime.strptime(request.form.get('fecha_programada_pago'), '%Y-%m-%d').date() if request.form.get('fecha_programada_pago') else None,
                created_by=current_user.id
            )
            
            db.session.add(estado)
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

@finanzas_bp.route('/proyecto/<int:proyecto_id>/costos', methods=['GET', 'POST'])
@login_required
@finanzas_required
def costos_proyecto(proyecto_id):
    """Gestión de costos manuales del proyecto"""
    try:
        proyecto = db.session.query(Proyecto).filter(
            Proyecto.id == proyecto_id
        ).first_or_404()
        
        if request.method == 'POST':
            # Aquí se implementará el guardado de costos cuando se cree la tabla
            flash('Funcionalidad de costos en desarrollo', 'info')
            return redirect(url_for('finanzas.costos_proyecto', proyecto_id=proyecto_id))
        
        # Por ahora solo mostrar la vista vacía
        costos = []
        total_costos = 0
        
        return render_template('finanzas/costos_proyecto.html',
                             proyecto=proyecto,
                             costos=costos,
                             total_costos=total_costos,
                             current_user=current_user)
                             
    except Exception as e:
        logger.error(f"Error en costos del proyecto: {e}")
        flash('Error al cargar los costos del proyecto', 'error')
        return redirect(url_for('finanzas.dashboard'))

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