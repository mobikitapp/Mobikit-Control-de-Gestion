from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import current_user, login_required
from app import db
from replit_auth import require_login, require_role
from models import (
    RolUsuario, Proyecto, Contrato, EstadoContrato, EstadoPago, 
    EstadoComercial, ObjetivoMensual, MovimientoFinanciero, 
    CuentaBancaria, CentroCosto, TipoMovimiento
)
from services.finanzas_service import FinanzasService
from services.tesoreria_service import TesoreriaService
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

finanzas_bp = Blueprint('finanzas', __name__)
finanzas_service = FinanzasService()
tesoreria_service = TesoreriaService()

@finanzas_bp.route('/')
@finanzas_bp.route('/dashboard')
@require_login
def dashboard():
    """Dashboard principal del módulo de finanzas"""
    try:
        # Obtener métricas del dashboard
        metricas = finanzas_service.get_dashboard_metrics()
        
        # Obtener resumen por proyectos activos
        resumen_proyectos = finanzas_service.get_resumen_proyectos()
        
        # Obtener flujo de caja del mes actual
        flujo_caja = tesoreria_service.get_flujo_caja_mensual()
        
        # Obtener estado de cartera (pagos pendientes)
        cartera_pendiente = finanzas_service.get_cartera_pendiente()
        
        return render_template('finanzas/dashboard.html',
                             metricas=metricas,
                             resumen_proyectos=resumen_proyectos,
                             flujo_caja=flujo_caja,
                             cartera_pendiente=cartera_pendiente,
                             current_user=current_user,
                             title="Dashboard Financiero")
    except Exception as e:
        logger.error(f"Error en dashboard financiero: {str(e)}")
        flash('Error al cargar el dashboard financiero', 'error')
        return redirect(url_for('index'))

@finanzas_bp.route('/tesoreria')
@require_login
def tesoreria():
    """Vista principal de tesorería"""
    try:
        # Obtener cuentas bancarias
        cuentas = tesoreria_service.get_cuentas_bancarias()
        
        # Obtener movimientos recientes
        movimientos = tesoreria_service.get_movimientos_recientes(limit=50)
        
        # Obtener saldo total
        saldo_total = tesoreria_service.get_saldo_total()
        
        return render_template('finanzas/tesoreria/index.html',
                             cuentas=cuentas,
                             movimientos=movimientos,
                             saldo_total=saldo_total,
                             current_user=current_user,
                             title="Tesorería")
    except Exception as e:
        logger.error(f"Error en tesorería: {str(e)}")
        flash('Error al cargar tesorería', 'error')
        return redirect(url_for('finanzas.dashboard'))

@finanzas_bp.route('/tesoreria/movimiento/nuevo', methods=['GET', 'POST'])
@require_role(RolUsuario.ADMIN, RolUsuario.GENERAL)
def nuevo_movimiento():
    """Crear nuevo movimiento financiero"""
    if request.method == 'GET':
        try:
            # Obtener datos para el formulario
            cuentas = tesoreria_service.get_cuentas_bancarias()
            proyectos = Proyecto.query.filter_by(activo=True).all()
            centros_costo = CentroCosto.query.filter_by(activo=True).all()
            
            return render_template('finanzas/tesoreria/form_movimiento.html',
                                 cuentas=cuentas,
                                 proyectos=proyectos,
                                 centros_costo=centros_costo,
                                 current_user=current_user,
                                 title="Nuevo Movimiento")
        except Exception as e:
            logger.error(f"Error cargando formulario de movimiento: {str(e)}")
            flash('Error al cargar formulario', 'error')
            return redirect(url_for('finanzas.tesoreria'))
    
    # POST - Crear movimiento
    try:
        data = {
            'fecha': datetime.strptime(request.form.get('fecha'), '%Y-%m-%d').date(),
            'tipo': request.form.get('tipo'),
            'monto': Decimal(request.form.get('monto', '0')),
            'descripcion': request.form.get('descripcion'),
            'cuenta_bancaria_id': int(request.form.get('cuenta_bancaria_id')) if request.form.get('cuenta_bancaria_id') else None,
            'proyecto_id': int(request.form.get('proyecto_id')) if request.form.get('proyecto_id') else None,
            'centro_costo_id': int(request.form.get('centro_costo_id')) if request.form.get('centro_costo_id') else None,
            'referencia': request.form.get('referencia'),
            'created_by': current_user.id
        }
        
        movimiento = tesoreria_service.crear_movimiento(data)
        
        flash(f'Movimiento registrado exitosamente', 'success')
        return redirect(url_for('finanzas.tesoreria'))
        
    except ValueError as e:
        flash(f'Error en los datos: {str(e)}', 'error')
        return redirect(url_for('finanzas.nuevo_movimiento'))
    except Exception as e:
        logger.error(f"Error creando movimiento: {str(e)}")
        flash('Error al crear movimiento', 'error')
        return redirect(url_for('finanzas.nuevo_movimiento'))

@finanzas_bp.route('/centros-costo')
@require_login
def centros_costo():
    """Vista de centros de costo"""
    try:
        centros = finanzas_service.get_centros_costo_con_resumen()
        
        return render_template('finanzas/centros_costo/index.html',
                             centros=centros,
                             current_user=current_user,
                             title="Centros de Costo")
    except Exception as e:
        logger.error(f"Error en centros de costo: {str(e)}")
        flash('Error al cargar centros de costo', 'error')
        return redirect(url_for('finanzas.dashboard'))

@finanzas_bp.route('/reportes')
@require_login
def reportes():
    """Vista principal de reportes financieros"""
    try:
        return render_template('finanzas/reportes/index.html',
                             current_user=current_user,
                             title="Reportes Financieros")
    except Exception as e:
        logger.error(f"Error en reportes: {str(e)}")
        flash('Error al cargar reportes', 'error')
        return redirect(url_for('finanzas.dashboard'))

@finanzas_bp.route('/reportes/flujo-caja')
@require_login
def reporte_flujo_caja():
    """Reporte de flujo de caja"""
    try:
        # Obtener parámetros de fecha
        fecha_inicio = request.args.get('fecha_inicio')
        fecha_fin = request.args.get('fecha_fin')
        
        if not fecha_inicio:
            # Por defecto, último mes
            fecha_fin = date.today()
            fecha_inicio = fecha_fin - timedelta(days=30)
        else:
            fecha_inicio = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
            fecha_fin = datetime.strptime(fecha_fin, '%Y-%m-%d').date() if fecha_fin else date.today()
        
        # Obtener datos del flujo de caja
        flujo_caja = tesoreria_service.get_flujo_caja_periodo(fecha_inicio, fecha_fin)
        
        return render_template('finanzas/reportes/flujo_caja.html',
                             flujo_caja=flujo_caja,
                             fecha_inicio=fecha_inicio,
                             fecha_fin=fecha_fin,
                             current_user=current_user,
                             title="Reporte Flujo de Caja")
    except Exception as e:
        logger.error(f"Error en reporte flujo de caja: {str(e)}")
        flash('Error al generar reporte', 'error')
        return redirect(url_for('finanzas.reportes'))

@finanzas_bp.route('/api/dashboard-data')
@require_login
def api_dashboard_data():
    """API para obtener datos del dashboard (para actualización AJAX)"""
    try:
        metricas = finanzas_service.get_dashboard_metrics()
        return jsonify(metricas)
    except Exception as e:
        logger.error(f"Error en API dashboard: {str(e)}")
        return jsonify({'error': 'Error al obtener datos'}), 500

@finanzas_bp.route('/api/flujo-caja/<int:year>/<int:month>')
@require_login
def api_flujo_caja_mes(year, month):
    """API para obtener flujo de caja de un mes específico"""
    try:
        flujo_caja = tesoreria_service.get_flujo_caja_mes(year, month)
        return jsonify(flujo_caja)
    except Exception as e:
        logger.error(f"Error en API flujo caja: {str(e)}")
        return jsonify({'error': 'Error al obtener flujo de caja'}), 500