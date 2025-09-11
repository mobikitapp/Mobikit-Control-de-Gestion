from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from sqlalchemy import func, and_, or_, desc
from sqlalchemy.orm import joinedload
from app import db
from models import (
    Proyecto, Contrato, EstadoContrato, EstadoPago, TipoEstadoPago,
    EstadoComercial, Cliente, MovimientoFinanciero, TipoMovimiento,
    CentroCosto, TipoCentroCosto, ObjetivoMensual
)
import logging

logger = logging.getLogger(__name__)

class FinanzasService:
    """Servicio para gestión financiera general"""
    
    def get_dashboard_metrics(self) -> Dict:
        """Obtiene métricas principales para el dashboard financiero"""
        try:
            # Mes actual
            today = date.today()
            start_of_month = date(today.year, today.month, 1)
            
            # Total ingresos del mes
            ingresos_mes = db.session.query(
                func.sum(MovimientoFinanciero.monto)
            ).filter(
                MovimientoFinanciero.tipo == TipoMovimiento.INGRESO,
                MovimientoFinanciero.fecha >= start_of_month,
                MovimientoFinanciero.fecha <= today,
                MovimientoFinanciero.estado != 'CANCELADO'
            ).scalar() or Decimal(0)
            
            # Total egresos del mes
            egresos_mes = db.session.query(
                func.sum(MovimientoFinanciero.monto)
            ).filter(
                MovimientoFinanciero.tipo == TipoMovimiento.EGRESO,
                MovimientoFinanciero.fecha >= start_of_month,
                MovimientoFinanciero.fecha <= today,
                MovimientoFinanciero.estado != 'CANCELADO'
            ).scalar() or Decimal(0)
            
            # Proyectos activos
            proyectos_activos = Proyecto.query.filter(
                Proyecto.activo == True,
                Proyecto.estado_comercial.in_([
                    EstadoComercial.ADJUDICADO,
                    EstadoComercial.EN_DESARROLLO
                ])
            ).count()
            
            # Contratos vigentes
            contratos_vigentes = Contrato.query.filter(
                Contrato.estado == EstadoContrato.VIGENTE
            ).count()
            
            # Total por cobrar (facturas pendientes)
            por_cobrar = self._calcular_por_cobrar()
            
            # Total por pagar
            por_pagar = self._calcular_por_pagar()
            
            # Objetivo mensual
            objetivo = ObjetivoMensual.query.filter_by(
                año=today.year,
                mes=today.month
            ).first()
            
            objetivo_provision = objetivo.objetivo_provision if objetivo else Decimal(0)
            objetivo_instalacion = objetivo.objetivo_instalacion if objetivo else Decimal(0)
            objetivo_total = objetivo_provision + objetivo_instalacion
            
            # Calcular avance del objetivo
            facturado_mes = self._calcular_facturado_mes(today.year, today.month)
            avance_objetivo = (float(facturado_mes) / float(objetivo_total) * 100) if objetivo_total > 0 else 0
            
            return {
                'ingresos_mes': float(ingresos_mes),
                'egresos_mes': float(egresos_mes),
                'balance_mes': float(ingresos_mes - egresos_mes),
                'proyectos_activos': proyectos_activos,
                'contratos_vigentes': contratos_vigentes,
                'por_cobrar': float(por_cobrar),
                'por_pagar': float(por_pagar),
                'objetivo_mes': float(objetivo_total),
                'avance_objetivo': float(avance_objetivo),
                'facturado_mes': float(facturado_mes)
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo métricas del dashboard: {str(e)}")
            return {
                'ingresos_mes': 0,
                'egresos_mes': 0,
                'balance_mes': 0,
                'proyectos_activos': 0,
                'contratos_vigentes': 0,
                'por_cobrar': 0,
                'por_pagar': 0,
                'objetivo_mes': 0,
                'avance_objetivo': 0,
                'facturado_mes': 0
            }
    
    def get_resumen_proyectos(self) -> List[Dict]:
        """Obtiene resumen financiero de proyectos activos"""
        try:
            proyectos = Proyecto.query.filter(
                Proyecto.activo == True,
                Proyecto.estado_comercial.in_([
                    EstadoComercial.ADJUDICADO,
                    EstadoComercial.EN_DESARROLLO,
                    EstadoComercial.PRESUPUESTADO
                ])
            ).order_by(Proyecto.nombre).all()
            
            resumen = []
            for proyecto in proyectos:
                # Calcular totales del proyecto
                total_presupuestado = self._calcular_total_presupuestado(proyecto)
                total_facturado = self._calcular_total_facturado(proyecto)
                total_cobrado = self._calcular_total_cobrado(proyecto)
                total_costos = self._calcular_total_costos(proyecto)
                
                # Margen actual
                margen = total_facturado - total_costos if total_facturado > 0 else Decimal(0)
                margen_pct = float(float(margen) / float(total_facturado) * 100) if total_facturado > 0 else 0
                
                resumen.append({
                    'id': proyecto.id,
                    'nombre': proyecto.nombre,
                    'cliente': proyecto.cliente.nombre if proyecto.cliente else 'Sin cliente',
                    'estado': proyecto.estado_comercial.value if proyecto.estado_comercial else 'PENDIENTE',
                    'presupuestado': float(total_presupuestado),
                    'facturado': float(total_facturado),
                    'cobrado': float(total_cobrado),
                    'pendiente_cobro': float(total_facturado - total_cobrado),
                    'costos': float(total_costos),
                    'margen': float(margen),
                    'margen_pct': float(margen_pct),
                    'avance_facturacion': float(float(total_facturado) / float(total_presupuestado) * 100) if total_presupuestado > 0 else 0
                })
            
            return resumen
            
        except Exception as e:
            logger.error(f"Error obteniendo resumen de proyectos: {str(e)}")
            return []
    
    def get_cartera_pendiente(self) -> List[Dict]:
        """Obtiene listado de pagos pendientes - solo facturas por cobrar y contratos por facturar"""
        try:
            # Obtener agregaciones por contrato para calcular pendientes dinámicamente
            agregaciones = self.get_contratos_aggregates()
            
            cartera = []
            
            # Agregar contratos con monto pendiente por facturar
            for agg in agregaciones:
                if agg['pendiente_facturar'] > 0:
                    cartera.append({
                        'id': f"contrato_{agg['contrato_id']}_pendiente",
                        'proyecto': agg['proyecto_nombre'],
                        'cliente': agg['cliente_nombre'],
                        'numero_oc': agg['numero_oc'],
                        'tipo': 'POR_FACTURAR',
                        'monto': float(agg['pendiente_facturar']),
                        'fecha_programada': None,
                        'dias_vencimiento': 0,
                        'estado_vencimiento': 'pendiente'
                    })
            
            # Obtener facturas emitidas pero no cobradas (FACTURADO)
            estados_facturados = EstadoPago.query.filter(
                EstadoPago.tipo_estado == TipoEstadoPago.FACTURADO
            ).join(Contrato).join(Proyecto).order_by(
                EstadoPago.fecha_programada_pago
            ).all()
            
            # Agregar facturas por cobrar
            for estado in estados_facturados:
                dias_vencimiento = 0
                if estado.fecha_programada_pago:
                    dias_vencimiento = (estado.fecha_programada_pago - date.today()).days
                
                cartera.append({
                    'id': estado.id,
                    'proyecto': estado.contrato.proyecto.nombre if estado.contrato.proyecto else 'Sin proyecto',
                    'cliente': estado.contrato.proyecto.cliente.nombre if estado.contrato.proyecto and estado.contrato.proyecto.cliente else 'Sin cliente',
                    'numero_oc': estado.contrato.numero_oc,
                    'tipo': 'POR_COBRAR',
                    'monto': float(estado.monto) if estado.monto else 0,
                    'fecha_programada': estado.fecha_programada_pago.isoformat() if estado.fecha_programada_pago else None,
                    'dias_vencimiento': dias_vencimiento,
                    'estado_vencimiento': 'vencido' if dias_vencimiento < 0 else 'por_vencer' if dias_vencimiento <= 7 else 'vigente'
                })
            
            # Ordenar por fecha programada y días de vencimiento
            cartera.sort(key=lambda x: (x['dias_vencimiento'] if x['fecha_programada'] else 999, x['monto']), reverse=True)
            
            return cartera
            
        except Exception as e:
            logger.error(f"Error obteniendo cartera pendiente: {str(e)}")
            return []
    
    def get_centros_costo_con_resumen(self) -> List[Dict]:
        """Obtiene centros de costo con su resumen financiero"""
        try:
            centros = CentroCosto.query.filter_by(activo=True).all()
            
            resumen = []
            for centro in centros:
                # Calcular gastos del mes actual
                today = date.today()
                start_of_month = date(today.year, today.month, 1)
                
                gastos_mes = db.session.query(
                    func.sum(MovimientoFinanciero.monto)
                ).filter(
                    MovimientoFinanciero.centro_costo_id == centro.id,
                    MovimientoFinanciero.tipo == TipoMovimiento.EGRESO,
                    MovimientoFinanciero.fecha >= start_of_month,
                    MovimientoFinanciero.fecha <= today
                ).scalar() or Decimal(0)
                
                presupuesto = centro.presupuesto_mensual or Decimal(0)
                consumido_pct = (float(gastos_mes) / float(presupuesto) * 100) if presupuesto > 0 else 0
                
                resumen.append({
                    'id': centro.id,
                    'codigo': centro.codigo,
                    'nombre': centro.nombre,
                    'tipo': centro.tipo.value,
                    'proyecto': centro.proyecto.nombre if centro.proyecto else None,
                    'responsable': centro.responsable.nombre_completo if centro.responsable else None,
                    'presupuesto_mensual': float(presupuesto),
                    'gastos_mes': float(gastos_mes),
                    'disponible': float(presupuesto - gastos_mes),
                    'consumido_pct': float(consumido_pct)
                })
            
            return resumen
            
        except Exception as e:
            logger.error(f"Error obteniendo centros de costo: {str(e)}")
            return []
    
    # Métodos auxiliares privados
    def _calcular_por_cobrar(self) -> Decimal:
        """Calcula el total por cobrar"""
        try:
            # Buscar estados facturados pero no pagados
            total = db.session.query(
                func.sum(EstadoPago.monto)
            ).filter(
                EstadoPago.tipo_estado == TipoEstadoPago.FACTURADO
            ).scalar() or Decimal(0)
            
            return total
        except:
            return Decimal(0)
    
    def _calcular_por_pagar(self) -> Decimal:
        """Calcula el total por pagar"""
        try:
            # Por ahora retornamos 0, ya que no tenemos modelo de cuentas por pagar
            # Esto se puede expandir en el futuro
            return Decimal(0)
        except:
            return Decimal(0)
    
    def _calcular_facturado_mes(self, year: int, month: int) -> Decimal:
        """Calcula el total facturado en un mes"""
        try:
            start_date = date(year, month, 1)
            if month == 12:
                end_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, month + 1, 1) - timedelta(days=1)
            
            total = db.session.query(
                func.sum(EstadoPago.monto)
            ).filter(
                EstadoPago.tipo_estado == TipoEstadoPago.FACTURADO,
                EstadoPago.fecha_estado >= start_date,
                EstadoPago.fecha_estado <= end_date
            ).scalar() or Decimal(0)
            
            return total
        except:
            return Decimal(0)
    
    def _calcular_total_presupuestado(self, proyecto: Proyecto) -> Decimal:
        """Calcula el total presupuestado de un proyecto"""
        provision = proyecto.monto_provision_presupuestado or Decimal(0)
        instalacion = proyecto.monto_instalacion_presupuestado or Decimal(0)
        return provision + instalacion
    
    def _calcular_total_facturado(self, proyecto: Proyecto) -> Decimal:
        """Calcula el total facturado de un proyecto (solo estados FACTURADO y PAGADO)"""
        try:
            total = db.session.query(
                func.sum(EstadoPago.monto)
            ).join(Contrato).filter(
                Contrato.proyecto_id == proyecto.id,
                EstadoPago.tipo_estado.in_([
                    TipoEstadoPago.FACTURADO,
                    TipoEstadoPago.PAGADO
                ])
            ).scalar() or Decimal(0)
            return total
        except:
            return Decimal(0)
    
    def _calcular_total_cobrado(self, proyecto: Proyecto) -> Decimal:
        """Calcula el total cobrado de un proyecto"""
        try:
            total = Decimal(0)
            for contrato in proyecto.contratos:
                cobrado = db.session.query(
                    func.sum(EstadoPago.monto)
                ).filter(
                    EstadoPago.contrato_id == contrato.id,
                    EstadoPago.tipo_estado == TipoEstadoPago.PAGADO
                ).scalar() or Decimal(0)
                total += cobrado
            return total
        except:
            return Decimal(0)
    
    def _calcular_total_costos(self, proyecto: Proyecto) -> Decimal:
        """Calcula el total de costos de un proyecto"""
        try:
            total = db.session.query(
                func.sum(MovimientoFinanciero.monto)
            ).filter(
                MovimientoFinanciero.proyecto_id == proyecto.id,
                MovimientoFinanciero.tipo == TipoMovimiento.EGRESO
            ).scalar() or Decimal(0)
            return total
        except:
            return Decimal(0)
    
    def get_contratos_aggregates(self, proyecto_ids: Optional[List[int]] = None, solo_vigentes: bool = True) -> List[Dict]:
        """Obtiene agregaciones financieras por contrato con cálculos dinámicos
        
        Args:
            proyecto_ids: Lista opcional de IDs de proyectos específicos
            solo_vigentes: Si True, solo incluye contratos VIGENTES (default: True)
        """
        try:
            # Consulta simplificada - obtener contratos básicos primero
            query = db.session.query(
                Contrato.id,
                Contrato.numero_oc,
                Contrato.monto_total,
                Contrato.moneda_original,
                Contrato.estado,
                Proyecto.nombre.label('proyecto_nombre'),
                Proyecto.cliente_id,
                Proyecto.estado_comercial
            ).join(Proyecto)
            
            # Filtrar solo contratos vigentes por defecto
            if solo_vigentes:
                query = query.filter(Contrato.estado == EstadoContrato.VIGENTE)
            
            # Filtrar por proyectos específicos si se proporciona
            if proyecto_ids:
                query = query.filter(Proyecto.id.in_(proyecto_ids))
            
            contratos = query.all()
            
            # Calcular agregaciones manualmente para cada contrato (más confiable)
            agregaciones = []
            for contrato in contratos:
                # Calcular totales para este contrato
                estados = db.session.query(EstadoPago).filter(
                    EstadoPago.contrato_id == contrato.id
                ).all()
                
                total_facturado = sum(
                    float(estado.monto or 0) 
                    for estado in estados 
                    if estado.tipo_estado in [TipoEstadoPago.FACTURADO, TipoEstadoPago.PAGADO]
                )
                
                total_pagado = sum(
                    float(estado.monto or 0) 
                    for estado in estados 
                    if estado.tipo_estado == TipoEstadoPago.PAGADO
                )
                
                # Cálculos dinámicos
                monto_total = float(contrato.monto_total or 0)
                pendiente_facturar = max(0, monto_total - total_facturado)
                pendiente_cobro = max(0, total_facturado - total_pagado)
                
                agregaciones.append({
                    'contrato_id': contrato.id,
                    'numero_oc': contrato.numero_oc,
                    'proyecto_nombre': contrato.proyecto_nombre,
                    'cliente_nombre': 'Cliente',  # Se puede mejorar con JOIN si es necesario
                    'estado_contrato': contrato.estado.value if contrato.estado else 'SIN_ESTADO',
                    'estado_proyecto': contrato.estado_comercial.value if contrato.estado_comercial else 'SIN_ESTADO',
                    'monto_total': monto_total,
                    'moneda_original': contrato.moneda_original,
                    'total_facturado': total_facturado,
                    'total_pagado': total_pagado,
                    'pendiente_facturar': pendiente_facturar,
                    'pendiente_cobro': pendiente_cobro
                })
            
            return agregaciones
            
        except Exception as e:
            logger.error(f"Error obteniendo agregaciones de contratos: {str(e)}")
            return []
    
    def get_proyectos_terminados_resumen(self) -> List[Dict]:
        """Obtiene proyectos terminados con todos sus contratos cerrados y resumen financiero completo"""
        try:
            # Obtener proyectos TERMINADO con contratos CERRADOS
            query = db.session.query(
                Proyecto.id,
                Proyecto.nombre,
                Proyecto.centro_costo,
                Cliente.nombre.label('cliente_nombre')
            ).join(Cliente).filter(
                Proyecto.estado_comercial == EstadoComercial.TERMINADO
            )
            
            proyectos_terminados = []
            
            for proyecto in query.all():
                # Verificar que todos los contratos estén cerrados
                contratos = db.session.query(Contrato).filter(
                    Contrato.proyecto_id == proyecto.id
                ).all()
                
                # Solo incluir si TODOS los contratos están CERRADOS
                if not contratos or not all(c.estado == EstadoContrato.CERRADO for c in contratos):
                    continue
                
                # Obtener agregaciones para este proyecto (incluyendo contratos cerrados)
                agregaciones = self.get_contratos_aggregates(
                    proyecto_ids=[proyecto.id], 
                    solo_vigentes=False  # Incluir todos los estados para resumen final
                )
                
                if not agregaciones:
                    continue
                
                # Calcular resumen financiero completo
                total_contratos = sum(agg['monto_total'] for agg in agregaciones)
                total_facturado = sum(agg['total_facturado'] for agg in agregaciones)
                total_pagado = sum(agg['total_pagado'] for agg in agregaciones)
                
                # Calcular costos del proyecto
                total_costos = float(self._calcular_total_costos(Proyecto.query.get(proyecto.id)))
                
                # Calcular márgenes
                margen_bruto = total_facturado - total_costos
                margen_bruto_pct = (float(margen_bruto) / float(total_facturado) * 100) if total_facturado > 0 else 0
                
                # Indicadores de finalización
                facturacion_completa = total_facturado >= total_contratos * 0.95  # 95% tolerancia
                cobranza_completa = total_pagado >= total_facturado * 0.95  # 95% tolerancia
                
                proyectos_terminados.append({
                    'proyecto_id': proyecto.id,
                    'proyecto_nombre': proyecto.nombre,
                    'centro_costo': proyecto.centro_costo,
                    'cliente_nombre': proyecto.cliente_nombre,
                    'num_contratos': len(contratos),
                    'total_contratos': total_contratos,
                    'total_facturado': total_facturado,
                    'total_pagado': total_pagado,
                    'total_costos': total_costos,
                    'margen_bruto': margen_bruto,
                    'margen_bruto_pct': margen_bruto_pct,
                    'avance_facturacion': (float(total_facturado) / float(total_contratos) * 100) if total_contratos > 0 else 0,
                    'avance_cobranza': (float(total_pagado) / float(total_facturado) * 100) if total_facturado > 0 else 0,
                    'facturacion_completa': facturacion_completa,
                    'cobranza_completa': cobranza_completa,
                    'proyecto_cerrado_financieramente': facturacion_completa and cobranza_completa,
                    'contratos': [{
                        'numero_oc': agg['numero_oc'],
                        'monto_total': agg['monto_total'],
                        'moneda': agg['moneda_original'],
                        'estado': agg['estado_contrato']
                    } for agg in agregaciones]
                })
            
            return proyectos_terminados
            
        except Exception as e:
            logger.error(f"Error obteniendo proyectos terminados: {str(e)}")
            return []
    
    def get_totales_proyecto_dinamicos(self, proyecto_id: int) -> Dict:
        """Calcula totales financieros de un proyecto usando cálculos dinámicos"""
        try:
            # Obtener agregaciones para este proyecto
            agregaciones = self.get_contratos_aggregates([proyecto_id])
            
            # Sumar totales
            total_contratos = sum(agg['monto_total'] for agg in agregaciones)
            total_facturado = sum(agg['total_facturado'] for agg in agregaciones)
            total_pagado = sum(agg['total_pagado'] for agg in agregaciones)
            total_pendiente_facturar = sum(agg['pendiente_facturar'] for agg in agregaciones)
            total_pendiente_cobro = sum(agg['pendiente_cobro'] for agg in agregaciones)
            
            # Calcular porcentajes
            avance_facturacion = float(float(total_facturado) / float(total_contratos) * 100) if total_contratos > 0 else 0
            avance_cobro = float(float(total_pagado) / float(total_contratos) * 100) if total_contratos > 0 else 0
            
            return {
                'total_contratos': total_contratos,
                'total_facturado': total_facturado,
                'total_pagado': total_pagado,
                'total_pendiente_facturar': total_pendiente_facturar,
                'total_pendiente_cobro': total_pendiente_cobro,
                'avance_facturacion': avance_facturacion,
                'avance_cobro': avance_cobro,
                'num_contratos': len(agregaciones)
            }
            
        except Exception as e:
            logger.error(f"Error calculando totales dinámicos del proyecto {proyecto_id}: {str(e)}")
            return {
                'total_contratos': 0, 'total_facturado': 0, 'total_pagado': 0,
                'total_pendiente_facturar': 0, 'total_pendiente_cobro': 0,
                'avance_facturacion': 0, 'avance_cobro': 0, 'num_contratos': 0
            }