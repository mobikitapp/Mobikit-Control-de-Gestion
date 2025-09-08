
from typing import List, Optional, Dict, Any
from app import db
from repositories.estados_pago_repo import EstadosPagoRepository
from services.audit_service import AuditService, serialize_model
from models import EstadoPago, TipoEstadoPago, EstadoPagoContrato, Proyecto, Contrato
import logging
from datetime import datetime, date
from decimal import Decimal

logger = logging.getLogger(__name__)

class EstadosPagoService:
    """Service layer for EstadoPago operations"""

    def __init__(self):
        self.repo = EstadosPagoRepository()

    def create_estado_pago(self, estado_pago_data: Dict[str, Any], created_by: str) -> EstadoPago:
        """Create a new estado pago with validation and audit logging"""
        try:
            # Validate proyecto exists
            proyecto = Proyecto.query.get(estado_pago_data['proyecto_id'])
            if not proyecto:
                raise ValueError(f"Proyecto {estado_pago_data['proyecto_id']} no encontrado")

            # Validate contrato if provided
            if estado_pago_data.get('contrato_id'):
                contrato = Contrato.query.get(estado_pago_data['contrato_id'])
                if not contrato:
                    raise ValueError(f"Contrato {estado_pago_data['contrato_id']} no encontrado")
                if contrato.proyecto_id != estado_pago_data['proyecto_id']:
                    raise ValueError("El contrato no pertenece al proyecto especificado")

            # Validate required fields based on tipo
            tipo = TipoEstadoPago(estado_pago_data['tipo'])
            if tipo == TipoEstadoPago.ORDEN_COMPRA:
                if not estado_pago_data.get('numero_oc'):
                    raise ValueError("Número de OC es requerido para estados de pago tipo OC")
                if not estado_pago_data.get('monto_neto'):
                    raise ValueError("Monto neto es requerido para estados de pago tipo OC")
            else:
                if not estado_pago_data.get('descripcion'):
                    raise ValueError("Descripción es requerida para estados de pago de contrato")
                if not estado_pago_data.get('monto_estado_pago'):
                    raise ValueError("Monto del estado de pago es requerido")

            # Create estado pago
            estado_pago = self.repo.create(estado_pago_data, created_by)

            # Commit transaction
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'estados_pago', 
                estado_pago.id, 
                'CREATE', 
                datos_nuevos=serialize_model(estado_pago)
            )

            logger.info(f"Estado de pago creado: {estado_pago.id} - {estado_pago.titulo_display}")
            return estado_pago

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando estado de pago: {str(e)}")
            raise

    def get_estado_pago_by_id(self, estado_pago_id: int) -> Optional[EstadoPago]:
        """Get estado pago by ID"""
        return self.repo.get_by_id(estado_pago_id)

    def get_estados_pago_by_proyecto(self, proyecto_id: int) -> List[EstadoPago]:
        """Get all estados pago for a proyecto"""
        return self.repo.get_by_proyecto_id(proyecto_id)

    def update_estado_pago(self, estado_pago_id: int, update_data: Dict[str, Any]) -> EstadoPago:
        """Update estado pago with validation and audit logging"""
        try:
            estado_pago = self.repo.get_by_id(estado_pago_id)
            if not estado_pago:
                raise ValueError(f"Estado de pago {estado_pago_id} no encontrado")

            # Store original data for audit
            datos_anteriores = serialize_model(estado_pago)

            # Update estado pago
            estado_pago_actualizado = self.repo.update(estado_pago, update_data)

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

            logger.info(f"Estado de pago actualizado: {estado_pago_id}")
            return estado_pago_actualizado

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error actualizando estado de pago {estado_pago_id}: {str(e)}")
            raise

    def delete_estado_pago(self, estado_pago_id: int) -> bool:
        """Delete estado pago with validation"""
        try:
            estado_pago = self.repo.get_by_id(estado_pago_id)
            if not estado_pago:
                raise ValueError(f"Estado de pago {estado_pago_id} no encontrado")

            # Store original data for audit
            datos_anteriores = serialize_model(estado_pago)

            # Soft delete estado pago
            success = self.repo.delete(estado_pago)

            if success:
                # Commit transaction
                db.session.commit()

                # Log audit
                AuditService.log_action(
                    'estados_pago', 
                    estado_pago_id, 
                    'DELETE',
                    datos_anteriores=datos_anteriores
                )

                logger.info(f"Estado de pago eliminado: {estado_pago_id}")
                return True

            return False

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error eliminando estado de pago {estado_pago_id}: {str(e)}")
            raise

    def calcular_kpi_financiero_proyecto(self, proyecto_id: int) -> Dict[str, Any]:
        """Calculate financial KPI with new payment tracking logic"""
        try:
            proyecto = Proyecto.query.get(proyecto_id)
            if not proyecto:
                return {'avance_porcentaje': 0, 'estado': 'sin_proyecto'}

            # Calculate total budget (provision + installation)
            presupuesto_provision = proyecto.monto_provision_presupuestado or Decimal('0')
            presupuesto_instalacion = proyecto.monto_instalacion_presupuestado or Decimal('0')
            presupuesto_total = presupuesto_provision + presupuesto_instalacion

            # Get payment tracking data
            estadisticas = self.repo.get_estadisticas_proyecto(proyecto_id)
            
            # Total amount through payments (OC + Contract payments)
            monto_pagado_total = Decimal(str(estadisticas['total_pagado']))
            monto_pendiente_total = Decimal(str(estadisticas['total_pendiente']))
            monto_parcial_total = Decimal(str(estadisticas['total_parcial']))
            
            # Total contracted amount (all payment states)
            monto_contratado_total = monto_pagado_total + monto_pendiente_total + monto_parcial_total

            # Calculate percentage and status
            if presupuesto_total > 0:
                # Calculate based on contracted amount vs budget
                avance_porcentaje = float((monto_contratado_total / presupuesto_total) * 100)
                
                # Calculate payment completion percentage
                porcentaje_cobrado = float((monto_pagado_total / monto_contratado_total) * 100) if monto_contratado_total > 0 else 0
                
                if avance_porcentaje <= 100:
                    estado = 'dentro_presupuesto'
                elif avance_porcentaje <= 110:
                    estado = 'alerta'
                else:
                    estado = 'sobre_presupuesto'
            else:
                avance_porcentaje = 0
                porcentaje_cobrado = 0
                estado = 'sin_presupuesto' if monto_contratado_total > 0 else 'sin_datos'

            return {
                'presupuesto_total': float(presupuesto_total),
                'presupuesto_provision': float(presupuesto_provision),
                'presupuesto_instalacion': float(presupuesto_instalacion),
                'monto_contratado': float(monto_contratado_total),
                'monto_pagado': float(monto_pagado_total),
                'monto_pendiente': float(monto_pendiente_total),
                'monto_parcial': float(monto_parcial_total),
                'avance_porcentaje': round(avance_porcentaje, 1),
                'porcentaje_cobrado': round(porcentaje_cobrado, 1),
                'estado': estado,
                'diferencia': float(monto_contratado_total - presupuesto_total),
                'estadisticas_pago': estadisticas
            }

        except Exception as e:
            logger.error(f"Error calculando KPI financiero: {str(e)}")
            return {'avance_porcentaje': 0, 'estado': 'error'}

    def get_proximos_vencimientos(self, dias: int = 30) -> List[EstadoPago]:
        """Get estados pago that will expire soon"""
        return self.repo.get_proximos_vencimientos(dias)

    def marcar_como_pagado(self, estado_pago_id: int, fecha_pago: date = None, observaciones: str = None) -> EstadoPago:
        """Mark estado pago as paid"""
        try:
            if fecha_pago is None:
                fecha_pago = datetime.now().date()

            # Get estado pago first to access contrato_id
            estado_pago = self.repo.get_by_id(estado_pago_id)
            if not estado_pago:
                raise ValueError(f"Estado de pago {estado_pago_id} no encontrado")

            update_data = {
                'estado': EstadoPagoContrato.PAGADO,
                'fecha_pago': fecha_pago
            }
            
            if observaciones:
                update_data['observaciones'] = observaciones

            # Update the payment state
            updated_estado = self.update_estado_pago(estado_pago_id, update_data)
            
            # Update contract financial totals if it's a contract payment state
            if updated_estado and updated_estado.contrato_id:
                self._update_contract_financial_totals(updated_estado.contrato_id)
            
            return updated_estado

        except Exception as e:
            logger.error(f"Error marcando estado de pago como pagado {estado_pago_id}: {str(e)}")
            raise

    def create_orden_compra(self, proyecto_id: int, numero_oc: str, monto_neto: Decimal, 
                          fecha_programada: date = None, observaciones: str = None, 
                          created_by: str = None) -> EstadoPago:
        """Create an Orden de Compra payment state"""
        estado_pago_data = {
            'proyecto_id': proyecto_id,
            'tipo': TipoEstadoPago.ORDEN_COMPRA,
            'numero_oc': numero_oc,
            'monto_neto': monto_neto,
            'fecha_programada': fecha_programada or datetime.now().date(),
            'observaciones': observaciones,
            'estado': EstadoPagoContrato.PENDIENTE
        }
        
        return self.create_estado_pago(estado_pago_data, created_by)

    def create_estado_pago_contrato(self, proyecto_id: int, contrato_id: int, descripcion: str,
                                  porcentaje_avance: Decimal, monto_estado_pago: Decimal,
                                  fecha_programada: date = None, observaciones: str = None,
                                  created_by: str = None) -> EstadoPago:
        """Create a contract payment state"""
        estado_pago_data = {
            'proyecto_id': proyecto_id,
            'contrato_id': contrato_id,
            'tipo': TipoEstadoPago.ESTADO_PAGO_CONTRATO,
            'descripcion': descripcion,
            'porcentaje_avance': porcentaje_avance,
            'monto_estado_pago': monto_estado_pago,
            'fecha_programada': fecha_programada or datetime.now().date(),
            'observaciones': observaciones,
            'estado': EstadoPagoContrato.PENDIENTE
        }
        
        return self.create_estado_pago(estado_pago_data, created_by)
    
    def marcar_como_facturado(self, estado_pago_id: int, numero_factura: str, updated_by: str) -> bool:
        """Marcar un estado de pago como facturado"""
        try:
            estado_pago = self.repo.get_by_id(estado_pago_id)
            if not estado_pago:
                logger.error(f"Estado de pago {estado_pago_id} no encontrado")
                return False
            
            # Actualizar campos de facturación
            estado_pago.facturado = True
            estado_pago.fecha_facturacion = datetime.now().date()
            if numero_factura:
                estado_pago.numero_factura = numero_factura
                
            # Actualizar auditoría
            estado_pago.updated_at = datetime.utcnow()
            estado_pago.updated_by = updated_by
            
            db.session.add(estado_pago)
            db.session.commit()
            
            # Log audit
            AuditService.log_action(
                'estados_pago', 
                estado_pago.id, 
                'UPDATE', 
                datos_nuevos={'facturado': True, 'numero_factura': numero_factura}
            )
            
            # Actualizar totales financieros del contrato
            if estado_pago.contrato_id:
                self._update_contract_financial_totals(estado_pago.contrato_id)
            
            logger.info(f"Estado de pago {estado_pago_id} marcado como facturado")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error marcando estado de pago {estado_pago_id} como facturado: {str(e)}")
            return False
    
    def _update_contract_financial_totals(self, contrato_id: int):
        """Update contract financial totals based on payment states"""
        try:
            from models import Contrato
            from decimal import Decimal
            
            # Get contract
            contrato = db.session.query(Contrato).get(contrato_id)
            if not contrato:
                logger.error(f"Contrato {contrato_id} no encontrado para actualizar totales")
                return
            
            # Get all payment states for this contract
            estados_pago = self.repo.get_by_contrato(contrato_id)
            
            # Calculate totals
            total_facturado = sum(
                float(ep.monto_estado_pago or 0) 
                for ep in estados_pago 
                if ep.facturado and ep.monto_estado_pago
            )
            
            total_pagado = sum(
                float(ep.monto_estado_pago or 0) 
                for ep in estados_pago 
                if ep.estado.value == 'PAGADO' and ep.monto_estado_pago
            )
            
            # Update contract fields
            contrato.monto_facturado = Decimal(str(total_facturado))
            contrato.monto_pagado = Decimal(str(total_pagado))
            
            # Update audit fields
            contrato.updated_at = datetime.utcnow()
            contrato.updated_by = 'system_sync'
            
            db.session.add(contrato)
            # Don't commit here - let the caller handle the transaction
            
            logger.info(f"Totales financieros actualizados para contrato {contrato_id}: "
                       f"Facturado={total_facturado}, Pagado={total_pagado}")
            
        except Exception as e:
            logger.error(f"Error actualizando totales financieros del contrato {contrato_id}: {str(e)}")
            raise
    
    def sync_all_contracts_for_project(self, proyecto_id: int):
        """Sync all contract financial totals for a specific project - manual fix method"""
        try:
            from models import Contrato
            
            # Get all contracts for the project
            contratos = db.session.query(Contrato).filter_by(proyecto_id=proyecto_id).all()
            
            updated_count = 0
            for contrato in contratos:
                self._update_contract_financial_totals(contrato.id)
                updated_count += 1
            
            db.session.commit()
            logger.info(f"Successfully synced {updated_count} contracts for project {proyecto_id}")
            return updated_count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error syncing contracts for project {proyecto_id}: {str(e)}")
            raise
