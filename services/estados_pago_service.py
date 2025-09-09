
from typing import List, Optional, Dict, Any
from app import db
from repositories.estados_pago_repo import EstadosPagoRepository
from services.audit_service import AuditService, serialize_model
from models import EstadoPago, TipoEstadoPago, EstadoPagoContrato, Proyecto, Contrato, Cliente
import logging
from datetime import datetime, date
from decimal import Decimal

logger = logging.getLogger(__name__)

class EstadosPagoService:
    """Service for managing payment states"""
    
    def __init__(self):
        self.repo = EstadosPagoRepository()
        self.audit_service = AuditService()

    def get_estados_pago_by_proyecto(self, proyecto_id: int) -> List[EstadoPago]:
        """Get all payment states for a project"""
        try:
            return self.repo.get_by_proyecto_id(proyecto_id)
        except Exception as e:
            logger.error(f"Error getting estados pago for proyecto {proyecto_id}: {str(e)}")
            return []

    def get_estado_pago_by_id(self, estado_pago_id: int) -> Optional[EstadoPago]:
        """Get payment state by ID"""
        try:
            return self.repo.get_by_id(estado_pago_id)
        except Exception as e:
            logger.error(f"Error getting estado pago {estado_pago_id}: {str(e)}")
            return None

    def create_estado_pago_contrato(self, proyecto_id: int, contrato_id: int, descripcion: str,
                                  porcentaje_avance: Decimal, monto_estado_pago: Decimal,
                                  fecha_programada: Optional[date] = None, observaciones: Optional[str] = None,
                                  created_by: str = None) -> EstadoPago:
        """Create a contract payment state"""
        try:
            estado_pago_data = {
                'proyecto_id': proyecto_id,
                'contrato_id': contrato_id,
                'tipo': TipoEstadoPago.ESTADO_PAGO_CONTRATO,
                'descripcion': descripcion,
                'porcentaje_avance': porcentaje_avance,
                'monto_estado_pago': monto_estado_pago,
                'fecha_programada': fecha_programada,
                'observaciones': observaciones,
                'estado': EstadoPagoContrato.PENDIENTE,
                'facturado': False,
                'activo': True
            }

            estado_pago = self.repo.create(estado_pago_data, created_by or 'system')
            db.session.commit()

            # Audit log
            self.audit_service.log_create(
                table_name='estado_pago',
                record_id=estado_pago.id,
                new_data=serialize_model(estado_pago),
                user_id=created_by
            )

            logger.info(f"Created estado pago contrato {estado_pago.id} for proyecto {proyecto_id}")
            return estado_pago

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creating estado pago contrato: {str(e)}")
            raise

    def marcar_como_facturado(self, estado_pago_id: int, numero_factura: str, updated_by: str = None) -> bool:
        """Mark payment state as invoiced"""
        try:
            estado_pago = self.get_estado_pago_by_id(estado_pago_id)
            if not estado_pago:
                return False

            old_data = serialize_model(estado_pago)

            # Update estado pago
            update_data = {
                'facturado': True,
                'numero_factura': numero_factura,
                'fecha_facturado': datetime.utcnow().date()
            }

            # If it's PENDIENTE, move to FACTURADO
            if hasattr(estado_pago, 'estado') and estado_pago.estado == EstadoPagoContrato.PENDIENTE:
                update_data['estado'] = EstadoPagoContrato.FACTURADO

            estado_pago = self.repo.update(estado_pago, update_data)
            
            # Update contract financial totals if applicable
            if estado_pago.contrato_id:
                self._update_contract_financial_totals(estado_pago.contrato_id)

            db.session.commit()

            # Audit log
            self.audit_service.log_update(
                table_name='estado_pago',
                record_id=estado_pago_id,
                old_data=old_data,
                new_data=serialize_model(estado_pago),
                user_id=updated_by
            )

            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error marking estado pago as invoiced {estado_pago_id}: {str(e)}")
            return False

    def marcar_como_pagado(self, estado_pago_id: int, fecha_pago: Optional[date] = None, 
                          observaciones: Optional[str] = None) -> EstadoPago:
        """Mark payment state as paid"""
        try:
            estado_pago = self.get_estado_pago_by_id(estado_pago_id)
            if not estado_pago:
                raise ValueError("Estado de pago no encontrado")

            # Verify it's invoiced first
            if not estado_pago.facturado:
                raise ValueError("El estado de pago debe estar facturado antes de marcarlo como pagado")

            old_data = serialize_model(estado_pago)

            update_data = {
                'estado': EstadoPagoContrato.PAGADO,
                'fecha_pago': fecha_pago or datetime.utcnow().date()
            }

            if observaciones:
                current_obs = estado_pago.observaciones or ''
                update_data['observaciones'] = f"{current_obs}\n[PAGO] {observaciones}".strip()

            estado_pago = self.repo.update(estado_pago, update_data)
            
            # Update contract financial totals
            if estado_pago.contrato_id:
                self._update_contract_financial_totals(estado_pago.contrato_id)

            db.session.commit()

            # Audit log
            self.audit_service.log_update(
                table_name='estado_pago',
                record_id=estado_pago_id,
                old_data=old_data,
                new_data=serialize_model(estado_pago),
                user_id='system'
            )

            logger.info(f"Marked estado pago {estado_pago_id} as paid")
            return estado_pago

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error marking estado pago as paid {estado_pago_id}: {str(e)}")
            raise

    def delete_estado_pago(self, estado_pago_id: int) -> bool:
        """Delete (soft delete) payment state"""
        try:
            estado_pago = self.get_estado_pago_by_id(estado_pago_id)
            if not estado_pago:
                logger.warning(f"Estado pago {estado_pago_id} not found for deletion")
                return False

            # Store contract_id before deletion for financial update
            contrato_id = estado_pago.contrato_id
            old_data = serialize_model(estado_pago)
            
            # Perform soft delete
            success = self.repo.delete(estado_pago)
            
            if success:
                # Update contract financial totals after deletion
                if contrato_id:
                    self._update_contract_financial_totals(contrato_id)
                
                # Commit transaction
                db.session.commit()

                # Audit log
                self.audit_service.log_delete(
                    table_name='estado_pago',
                    record_id=estado_pago_id,
                    old_data=old_data,
                    user_id='system'
                )

                logger.info(f"Successfully deleted estado pago {estado_pago_id}")
                return True
            else:
                logger.warning(f"Failed to delete estado pago {estado_pago_id}")
                return False

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting estado pago {estado_pago_id}: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False

    def _update_contract_financial_totals(self, contrato_id: int):
        """Update contract financial totals based on payment states"""
        try:
            from models import Contrato, EstadoFacturacion
            contrato = Contrato.query.get(contrato_id)
            if not contrato:
                return

            # Get all active payment states for this contract
            estados_pago = self.repo.get_by_contrato_id(contrato_id)
            active_estados = [ep for ep in estados_pago if ep.activo]

            # Calculate totals
            total_facturado = sum(
                float(ep.monto_efectivo or 0) 
                for ep in active_estados 
                if ep.facturado
            )

            total_pagado = sum(
                float(ep.monto_efectivo or 0) 
                for ep in active_estados 
                if hasattr(ep, 'estado') and ep.estado == EstadoPagoContrato.PAGADO
            )

            # Update contract amounts
            contrato.monto_facturado = Decimal(str(total_facturado))
            contrato.monto_pagado = Decimal(str(total_pagado))

            # Update estado_facturacion based on amounts
            if total_facturado == 0:
                contrato.estado_facturacion = EstadoFacturacion.POR_FACTURAR
            elif total_facturado >= float(contrato.monto_total or 0):
                contrato.estado_facturacion = EstadoFacturacion.FACTURADO_TOTAL
            else:
                contrato.estado_facturacion = EstadoFacturacion.FACTURADO_PARCIAL

            db.session.flush()
            logger.info(f"Updated contract {contrato_id} financial totals - Facturado: ${total_facturado}, Pagado: ${total_pagado}")

        except Exception as e:
            logger.error(f"Error updating contract financial totals {contrato_id}: {str(e)}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")

    def sync_all_contracts_for_project(self, proyecto_id: int) -> int:
        """Sync financial totals for all contracts in a project"""
        try:
            from models import Contrato
            contratos = Contrato.query.filter_by(proyecto_id=proyecto_id).all()
            
            updated_count = 0
            for contrato in contratos:
                self._update_contract_financial_totals(contrato.id)
                updated_count += 1
            
            db.session.commit()
            return updated_count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error syncing contracts for project {proyecto_id}: {str(e)}")
            return 0
