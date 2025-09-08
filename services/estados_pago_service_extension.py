
from typing import List, Optional, Dict, Any
from app import db
from repositories.estados_pago_repo import EstadosPagoRepository
from services.audit_service import AuditService, serialize_model
from models import EstadoPago, TipoEstadoPago, EstadoPagoContrato, Proyecto, Contrato, Cliente
import logging
from datetime import datetime, date
from decimal import Decimal

logger = logging.getLogger(__name__)

# Extension methods for EstadosPagoService
def get_proyectos_con_estados_pago_por_cliente(self) -> Dict[str, Any]:
    """Get all projects with payment states grouped by client"""
    try:
        # Get all active projects with contracts and payment states
        proyectos = (db.session.query(Proyecto)
                    .join(Cliente, Proyecto.cliente_id == Cliente.id)
                    .filter(Proyecto.activo == True)
                    .filter(Cliente.activo == True)
                    .order_by(Cliente.nombre, Proyecto.nombre)
                    .all())
        
        # Group by client
        resultado = {}
        for proyecto in proyectos:
            cliente_nombre = proyecto.cliente.nombre
            if cliente_nombre not in resultado:
                resultado[cliente_nombre] = {
                    'cliente': proyecto.cliente,
                    'proyectos': []
                }
            
            # Get payment states for this project
            estados_pago = self.repo.get_by_proyecto_id(proyecto.id)
            
            # Calculate payment summary
            total_monto = sum(ep.monto_efectivo for ep in estados_pago)
            total_pagado = sum(ep.monto_efectivo for ep in estados_pago if ep.estado == EstadoPagoContrato.PAGADO)
            total_facturado = sum(ep.monto_efectivo for ep in estados_pago if ep.facturado)
            
            proyecto_data = {
                'proyecto': proyecto,
                'estados_pago': estados_pago,
                'resumen': {
                    'total_monto': total_monto,
                    'total_pagado': total_pagado,
                    'total_facturado': total_facturado,
                    'total_pendiente': total_monto - total_pagado,
                    'porcentaje_pagado': (total_pagado / total_monto * 100) if total_monto > 0 else 0,
                    'porcentaje_facturado': (total_facturado / total_monto * 100) if total_monto > 0 else 0
                }
            }
            
            resultado[cliente_nombre]['proyectos'].append(proyecto_data)
        
        return resultado
        
    except Exception as e:
        logger.error(f"Error getting proyectos con estados pago por cliente: {str(e)}")
        raise

def marcar_como_facturado(self, estado_pago_id: int, numero_factura: str = None, 
                         fecha_facturacion: date = None, observaciones: str = None) -> EstadoPago:
    """Mark payment state as invoiced and update contract financial fields"""
    try:
        estado_pago = self.repo.get_by_id(estado_pago_id)
        if not estado_pago:
            raise ValueError(f"Estado de pago {estado_pago_id} no encontrado")
        
        # Store original data for audit
        datos_anteriores = serialize_model(estado_pago)
        
        # Update invoicing data
        update_data = {
            'facturado': True,
            'fecha_facturacion': fecha_facturacion or date.today(),
            'numero_factura': numero_factura,
            'observaciones': observaciones
        }
        
        # Update estado pago
        estado_pago_actualizado = self.repo.update(estado_pago, update_data)
        
        # ** INTEGRACIÓN FASE 1 ** - Actualizar campos financieros del contrato
        if estado_pago_actualizado.contrato_id:
            try:
                from services.contratos_financial_service import ContratosFinancialService
                financial_service = ContratosFinancialService()
                
                # Actualizar el contrato con el monto facturado del estado de pago
                monto_facturado = float(estado_pago_actualizado.monto_efectivo or 0)
                financial_service.update_contract_invoicing(
                    contrato_id=estado_pago_actualizado.contrato_id,
                    monto_facturado=monto_facturado,
                    numero_factura=numero_factura
                )
                
                logger.info(f"Campos financieros del contrato {estado_pago_actualizado.contrato_id} actualizados - Monto: ${monto_facturado}")
                
            except Exception as integration_error:
                logger.warning(f"Error actualizando campos financieros del contrato: {str(integration_error)}")
                # No interrumpimos el flujo principal si falla la integración
        
        # Commit transaction
        db.session.commit()
        
        # Log audit
        AuditService.log_action(
            'estados_pago', 
            estado_pago_id, 
            'UPDATE',
            datos_anteriores=datos_anteriores,
            datos_nuevos=serialize_model(estado_pago_actualizado)
        )
        
        logger.info(f"Estado de pago marcado como facturado: {estado_pago_id} - Factura: {numero_factura}")
        return estado_pago_actualizado
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error marcando estado pago como facturado {estado_pago_id}: {str(e)}")
        raise

def auto_crear_oc_desde_contrato(self, contrato_id: int, created_by: str) -> Optional[EstadoPago]:
    """Automatically create OC payment state from contract net amount"""
    try:
        contrato = Contrato.query.get(contrato_id)
        if not contrato:
            raise ValueError(f"Contrato {contrato_id} no encontrado")
        
        # Check if OC already exists for this contract
        existing_oc = (db.session.query(EstadoPago)
                      .filter_by(contrato_id=contrato_id, tipo=TipoEstadoPago.ORDEN_COMPRA)
                      .first())
        
        if existing_oc:
            logger.info(f"OC ya existe para contrato {contrato_id}")
            return existing_oc
        
        # Create OC automatically if contract has monto_total
        if contrato.monto_total and contrato.numero_oc:
            estado_pago = self.create_orden_compra(
                proyecto_id=contrato.proyecto_id,
                numero_oc=contrato.numero_oc,
                monto_neto=contrato.monto_total,
                fecha_programada=contrato.fecha_emision,
                observaciones=f"OC creada automáticamente desde contrato {contrato.numero_oc}",
                created_by=created_by
            )
            
            # Update the estado_pago to link to the contract
            self.repo.update(estado_pago, {'contrato_id': contrato_id})
            db.session.commit()
            
            logger.info(f"OC creada automáticamente para contrato {contrato_id}: {estado_pago.id}")
            return estado_pago
        
        return None
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error auto-creando OC desde contrato {contrato_id}: {str(e)}")
        raise

# Monkey patch these methods into EstadosPagoService
from services.estados_pago_service import EstadosPagoService
EstadosPagoService.get_proyectos_con_estados_pago_por_cliente = get_proyectos_con_estados_pago_por_cliente
EstadosPagoService.marcar_como_facturado = marcar_como_facturado
EstadosPagoService.auto_crear_oc_desde_contrato = auto_crear_oc_desde_contrato