from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, date
from sqlalchemy import func
from app import db
from models import Contrato, Proyecto, Cliente, EstadoFacturacion, EstadoPagoContrato
from repositories.contratos_repo import ContratosRepository
from services.contratos_service import ContratosService
import logging

logger = logging.getLogger(__name__)

class ContratosFinancialService(ContratosService):
    """
    Extensión del servicio de contratos con funcionalidades financieras para Fase 1
    Sistema de seguimiento financiero integral sin impactar operaciones existentes
    """

    def __init__(self):
        super().__init__()

    def get_financial_summary_by_project(self, proyecto_id: int) -> Dict[str, Any]:
        """
        Obtiene resumen financiero completo de un proyecto
        
        Returns:
            Dictionary con métricas financieras del proyecto
        """
        try:
            contratos = self.repo.get_by_proyecto(proyecto_id)
            
            if not contratos:
                return self._empty_financial_summary()
            
            # Calcular totales
            total_contratado = sum(float(c.monto_total or 0) for c in contratos)
            total_facturado = sum(float(c.monto_facturado or 0) for c in contratos)  
            total_pagado = sum(float(c.monto_pagado or 0) for c in contratos)
            
            # Calcular saldos
            saldo_por_facturar = total_contratado - total_facturado
            saldo_por_cobrar = total_facturado - total_pagado
            
            # Calcular porcentajes
            porcentaje_facturado = (total_facturado / total_contratado * 100) if total_contratado > 0 else 0
            porcentaje_cobrado = (total_pagado / total_facturado * 100) if total_facturado > 0 else 0
            
            # Estados de contratos
            estados_facturacion = self._count_by_estado_facturacion(contratos)
            estados_pago = self._count_by_estado_pago(contratos)
            
            return {
                'total_contratos': len(contratos),
                'montos': {
                    'total_contratado': total_contratado,
                    'total_facturado': total_facturado,
                    'total_pagado': total_pagado,
                    'saldo_por_facturar': saldo_por_facturar,
                    'saldo_por_cobrar': saldo_por_cobrar
                },
                'porcentajes': {
                    'facturado': round(porcentaje_facturado, 1),
                    'cobrado': round(porcentaje_cobrado, 1)
                },
                'estados': {
                    'facturacion': estados_facturacion,
                    'pago': estados_pago
                },
                'contratos_detalle': [self._contrato_to_financial_summary(c) for c in contratos]
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo resumen financiero del proyecto {proyecto_id}: {str(e)}")
            return self._empty_financial_summary()

    def get_contracts_requiring_invoicing(self) -> List[Dict[str, Any]]:
        """
        Obtiene contratos que requieren facturación (estado POR_FACTURAR o FACTURADO_PARCIAL)
        
        Returns:
            Lista de contratos pendientes de facturación
        """
        try:
            contratos = db.session.query(Contrato).join(Proyecto).join(Cliente).filter(
                Contrato.estado_facturacion.in_([
                    EstadoFacturacion.POR_FACTURAR, 
                    EstadoFacturacion.FACTURADO_PARCIAL
                ])
            ).order_by(Contrato.fecha_vencimiento.asc()).all()
            
            return [self._contrato_to_invoicing_summary(c) for c in contratos]
            
        except Exception as e:
            logger.error(f"Error obteniendo contratos por facturar: {str(e)}")
            return []

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """
        Obtiene resumen general de cartera de clientes
        
        Returns:
            Resumen ejecutivo de cartera
        """
        try:
            # Obtener todos los contratos con información básica
            contratos = db.session.query(Contrato).join(Proyecto).join(Cliente).all()
            
            if not contratos:
                return self._empty_portfolio_summary()
                
            # Calcular totales globales
            total_contratado = sum(float(c.monto_total or 0) for c in contratos)
            total_facturado = sum(float(c.monto_facturado or 0) for c in contratos)
            total_pagado = sum(float(c.monto_pagado or 0) for c in contratos)
            
            # Análisis por cliente
            clientes_summary = self._analyze_by_client(contratos)
            
            # Análisis de vencimientos (simulado para Fase 1)
            vencimientos = self._analyze_payment_due_dates(contratos)
            
            return {
                'totales_globales': {
                    'total_contratado': total_contratado,
                    'total_facturado': total_facturado,
                    'total_pagado': total_pagado,
                    'saldo_por_facturar': total_contratado - total_facturado,
                    'saldo_por_cobrar': total_facturado - total_pagado
                },
                'por_cliente': clientes_summary,
                'vencimientos': vencimientos,
                'estados_globales': {
                    'facturacion': self._count_by_estado_facturacion(contratos),
                    'pago': self._count_by_estado_pago(contratos)
                }
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo resumen de cartera: {str(e)}")
            return self._empty_portfolio_summary()

    def update_contract_invoicing(self, contrato_id: int, monto_facturado: float, 
                                 numero_factura: Optional[str] = None) -> bool:
        """
        Actualiza información de facturación de un contrato
        
        Args:
            contrato_id: ID del contrato
            monto_facturado: Monto a agregar como facturado
            numero_factura: Número de factura (opcional)
            
        Returns:
            True si se actualizó correctamente
        """
        try:
            contrato = self.repo.get_by_id(contrato_id)
            if not contrato:
                raise ValueError(f"Contrato {contrato_id} no encontrado")
                
            nuevo_monto_facturado = float(contrato.monto_facturado or 0) + monto_facturado
            monto_total = float(contrato.monto_total or 0)
            
            # Determinar nuevo estado de facturación
            if nuevo_monto_facturado >= monto_total:
                nuevo_estado = EstadoFacturacion.FACTURADO_TOTAL
            elif nuevo_monto_facturado > 0:
                nuevo_estado = EstadoFacturacion.FACTURADO_PARCIAL
            else:
                nuevo_estado = EstadoFacturacion.POR_FACTURAR
                
            # Actualizar contrato
            update_data = {
                'monto_facturado': nuevo_monto_facturado,
                'estado_facturacion': nuevo_estado
            }
            
            if numero_factura:
                # Para Fase 1, almacenar en notas si no hay campo específico
                notas_actuales = contrato.notas or ""
                update_data['notas'] = f"{notas_actuales}\nFactura: {numero_factura}".strip()
            
            self.repo.update(contrato, update_data)
            db.session.commit()
            
            logger.info(f"Facturación actualizada para contrato {contrato_id}: ${monto_facturado}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error actualizando facturación del contrato {contrato_id}: {str(e)}")
            return False

    def update_contract_payment(self, contrato_id: int, monto_pagado: float) -> bool:
        """
        Actualiza información de pago de un contrato
        
        Args:
            contrato_id: ID del contrato
            monto_pagado: Monto a agregar como pagado
            
        Returns:
            True si se actualizó correctamente
        """
        try:
            contrato = self.repo.get_by_id(contrato_id)
            if not contrato:
                raise ValueError(f"Contrato {contrato_id} no encontrado")
                
            nuevo_monto_pagado = float(contrato.monto_pagado or 0) + monto_pagado
            monto_facturado = float(contrato.monto_facturado or 0)
            
            # Determinar nuevo estado de pago
            if nuevo_monto_pagado >= monto_facturado:
                nuevo_estado = EstadoPagoContrato.PAGADO_TOTAL
            elif nuevo_monto_pagado > 0:
                nuevo_estado = EstadoPagoContrato.PAGO_PARCIAL
            else:
                nuevo_estado = EstadoPagoContrato.PENDIENTE
                
            # Actualizar contrato
            update_data = {
                'monto_pagado': nuevo_monto_pagado,
                'estado_pago': nuevo_estado
            }
            
            self.repo.update(contrato, update_data)
            db.session.commit()
            
            logger.info(f"Pago actualizado para contrato {contrato_id}: ${monto_pagado}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error actualizando pago del contrato {contrato_id}: {str(e)}")
            return False

    # Métodos auxiliares privados
    
    def _empty_financial_summary(self) -> Dict[str, Any]:
        """Retorna estructura vacía de resumen financiero"""
        return {
            'total_contratos': 0,
            'montos': {'total_contratado': 0, 'total_facturado': 0, 'total_pagado': 0, 
                      'saldo_por_facturar': 0, 'saldo_por_cobrar': 0},
            'porcentajes': {'facturado': 0, 'cobrado': 0},
            'estados': {'facturacion': {}, 'pago': {}},
            'contratos_detalle': []
        }
    
    def _empty_portfolio_summary(self) -> Dict[str, Any]:
        """Retorna estructura vacía de resumen de cartera"""
        return {
            'totales_globales': {'total_contratado': 0, 'total_facturado': 0, 'total_pagado': 0,
                               'saldo_por_facturar': 0, 'saldo_por_cobrar': 0},
            'por_cliente': [],
            'vencimientos': {'vencidos': 0, 'por_vencer_30_dias': 0, 'futuro': 0},
            'estados_globales': {'facturacion': {}, 'pago': {}}
        }
    
    def _count_by_estado_facturacion(self, contratos: List[Contrato]) -> Dict[str, int]:
        """Cuenta contratos por estado de facturación"""
        estados = {}
        for contrato in contratos:
            estado = contrato.estado_facturacion.value if contrato.estado_facturacion else 'POR_FACTURAR'
            estados[estado] = estados.get(estado, 0) + 1
        return estados
    
    def _count_by_estado_pago(self, contratos: List[Contrato]) -> Dict[str, int]:
        """Cuenta contratos por estado de pago"""  
        estados = {}
        for contrato in contratos:
            estado = contrato.estado_pago.value if contrato.estado_pago else 'PENDIENTE'
            estados[estado] = estados.get(estado, 0) + 1
        return estados
    
    def _contrato_to_financial_summary(self, contrato: Contrato) -> Dict[str, Any]:
        """Convierte contrato a resumen financiero"""
        return {
            'id': contrato.id,
            'numero_oc': contrato.numero_oc,
            'monto_total': float(contrato.monto_total or 0),
            'monto_facturado': float(contrato.monto_facturado or 0),
            'monto_pagado': float(contrato.monto_pagado or 0),
            'estado_facturacion': contrato.estado_facturacion.value if contrato.estado_facturacion else 'POR_FACTURAR',
            'estado_pago': contrato.estado_pago.value if contrato.estado_pago else 'PENDIENTE',
            'saldo_por_facturar': contrato.saldo_por_facturar,
            'saldo_por_cobrar': contrato.saldo_por_cobrar,
            'porcentaje_facturado': contrato.porcentaje_facturado,
            'porcentaje_pagado': contrato.porcentaje_pagado
        }
    
    def _contrato_to_invoicing_summary(self, contrato: Contrato) -> Dict[str, Any]:
        """Convierte contrato a resumen de facturación"""
        return {
            'contrato_id': contrato.id,
            'numero_oc': contrato.numero_oc,
            'cliente': contrato.proyecto.cliente.nombre,
            'proyecto': contrato.proyecto.nombre,
            'monto_total': float(contrato.monto_total or 0),
            'monto_facturado': float(contrato.monto_facturado or 0),
            'saldo_por_facturar': contrato.saldo_por_facturar,
            'estado_facturacion': contrato.estado_facturacion.value,
            'fecha_vencimiento': contrato.fecha_vencimiento.isoformat() if contrato.fecha_vencimiento else None
        }
    
    def _analyze_by_client(self, contratos: List[Contrato]) -> List[Dict[str, Any]]:
        """Analiza contratos agrupados por cliente"""
        clientes = {}
        
        for contrato in contratos:
            cliente_id = contrato.proyecto.cliente.id
            cliente_nombre = contrato.proyecto.cliente.nombre
            
            if cliente_id not in clientes:
                clientes[cliente_id] = {
                    'cliente_nombre': cliente_nombre,
                    'total_contratado': 0,
                    'total_facturado': 0, 
                    'total_pagado': 0,
                    'cantidad_contratos': 0
                }
            
            clientes[cliente_id]['total_contratado'] += float(contrato.monto_total or 0)
            clientes[cliente_id]['total_facturado'] += float(contrato.monto_facturado or 0)
            clientes[cliente_id]['total_pagado'] += float(contrato.monto_pagado or 0)
            clientes[cliente_id]['cantidad_contratos'] += 1
        
        # Convertir a lista y agregar saldos calculados
        resultado = []
        for cliente_data in clientes.values():
            cliente_data['saldo_por_facturar'] = cliente_data['total_contratado'] - cliente_data['total_facturado']
            cliente_data['saldo_por_cobrar'] = cliente_data['total_facturado'] - cliente_data['total_pagado']
            resultado.append(cliente_data)
            
        return sorted(resultado, key=lambda x: x['saldo_por_cobrar'], reverse=True)
    
    def _analyze_payment_due_dates(self, contratos: List[Contrato]) -> Dict[str, int]:
        """Análisis básico de vencimientos (simulado para Fase 1)"""
        # Por ahora retornamos estructura básica
        # En fases futuras se implementará análisis real de vencimientos
        return {
            'vencidos': 0,
            'por_vencer_30_dias': 0, 
            'futuro': len(contratos)
        }