
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
            datos_nuevos = serialize_model(estado_pago)
            if datos_nuevos:
                AuditService.log_action(
                    'estados_pago', 
                    estado_pago.id, 
                    'CREATE', 
                    datos_nuevos=datos_nuevos
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
            datos_nuevos = serialize_model(estado_pago_actualizado)
            if datos_anteriores and datos_nuevos:
                AuditService.log_action(
                    'estados_pago', 
                    estado_pago_id, 
                    'UPDATE',
                    datos_anteriores=datos_anteriores,
                    datos_nuevos=datos_nuevos
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
                if datos_anteriores:
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
        """Calculate financial KPI using updated contract totals for synchronization"""
        try:
            proyecto = Proyecto.query.get(proyecto_id)
            if not proyecto:
                return {'avance_porcentaje': 0, 'estado': 'sin_proyecto'}

            # Calculate total budget (provision + installation)
            presupuesto_provision = proyecto.monto_provision_presupuestado or Decimal('0')
            presupuesto_instalacion = proyecto.monto_instalacion_presupuestado or Decimal('0')
            presupuesto_total = presupuesto_provision + presupuesto_instalacion

            # Use updated contract totals (synchronized with treasury operations)
            contratos = Contrato.query.filter_by(proyecto_id=proyecto_id).all()
            
            monto_contratado_total = Decimal('0')
            monto_facturado_total = Decimal('0')
            monto_pagado_total = Decimal('0')
            
            for contrato in contratos:
                monto_contratado_total += contrato.monto_total or Decimal('0')
                monto_facturado_total += contrato.monto_facturado or Decimal('0')
                monto_pagado_total += contrato.monto_pagado or Decimal('0')
            
            # Calculate pending amounts
            monto_pendiente_total = monto_facturado_total - monto_pagado_total
            monto_parcial_total = monto_contratado_total - monto_facturado_total

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

            # Get original estadisticas for compatibility
            estadisticas = self.repo.get_estadisticas_proyecto(proyecto_id)

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
        """Mark estado pago as paid with state validation"""
        try:
            if fecha_pago is None:
                fecha_pago = datetime.now().date()

            # Get estado pago first to access contrato_id
            estado_pago = self.repo.get_by_id(estado_pago_id)
            if not estado_pago:
                raise ValueError(f"Estado de pago {estado_pago_id} no encontrado")
            
            # Validate state transition: must be invoiced before being marked as paid
            if not estado_pago.facturado:
                raise ValueError("El estado de pago debe estar facturado antes de marcarlo como pagado")
            
            # Check if already paid
            if estado_pago.estado == EstadoPagoContrato.PAGADO:
                raise ValueError("El estado de pago ya está marcado como pagado")

            # Store original data for audit
            datos_anteriores = serialize_model(estado_pago)

            update_data = {
                'estado': EstadoPagoContrato.PAGADO,
                'fecha_pago': fecha_pago
            }
            
            if observaciones:
                update_data['observaciones'] = observaciones

            # Update the payment state
            updated_estado = self.repo.update(estado_pago, update_data)
            
            # Update contract financial totals if it's a contract payment state
            if updated_estado and updated_estado.contrato_id:
                self._update_contract_financial_totals(updated_estado.contrato_id)
            
            # Commit the transaction
            db.session.commit()
            
            # Log audit
            datos_nuevos = serialize_model(updated_estado)
            if datos_anteriores and datos_nuevos:
                AuditService.log_action(
                    'estados_pago', 
                    estado_pago_id, 
                    'UPDATE',
                    datos_anteriores=datos_anteriores,
                    datos_nuevos=datos_nuevos
                )
            
            logger.info(f"Estado de pago marcado como pagado: {estado_pago_id}")
            return updated_estado

        except Exception as e:
            db.session.rollback()
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
        """Marcar un estado de pago como facturado con validación de estado"""
        try:
            estado_pago = self.repo.get_by_id(estado_pago_id)
            if not estado_pago:
                logger.error(f"Estado de pago {estado_pago_id} no encontrado")
                return False
            
            # Check if already invoiced
            if estado_pago.facturado:
                logger.warning(f"Estado de pago {estado_pago_id} ya está facturado")
                return False
            
            # Check if already paid (shouldn't happen but safeguard)
            if estado_pago.estado == EstadoPagoContrato.PAGADO:
                logger.error(f"No se puede facturar un estado de pago que ya está pagado")
                return False
            
            # Store original data for audit
            datos_anteriores = serialize_model(estado_pago)
            
            # Actualizar campos de facturación
            update_data = {
                'facturado': True,
                'fecha_facturacion': datetime.now().date(),
                'numero_factura': numero_factura or '',
                'updated_by': updated_by,
                'updated_at': datetime.utcnow()
            }
            
            # Update the payment state
            updated_estado = self.repo.update(estado_pago, update_data)
            
            # Actualizar totales financieros del contrato
            if updated_estado.contrato_id:
                self._update_contract_financial_totals(updated_estado.contrato_id)
            
            # Commit the transaction
            db.session.commit()
            
            # Log audit
            datos_nuevos = serialize_model(updated_estado)
            if datos_anteriores and datos_nuevos:
                AuditService.log_action(
                    'estados_pago', 
                    estado_pago.id, 
                    'UPDATE',
                    datos_anteriores=datos_anteriores,
                    datos_nuevos=datos_nuevos
                )
            
            logger.info(f"Estado de pago {estado_pago_id} marcado como facturado")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error marcando estado de pago {estado_pago_id} como facturado: {str(e)}")
            return False
    
    def _update_contract_financial_totals(self, contrato_id: int):
        """Update contract financial totals based on payment states"""
        try:
            from models import Contrato, TipoDocumento, PendienteFacturar, EstadoPendienteFacturar
            from decimal import Decimal
            
            # Get contract
            contrato = db.session.query(Contrato).get(contrato_id)
            if not contrato:
                logger.error(f"Contrato {contrato_id} no encontrado para actualizar totales")
                return
            
            total_facturado = Decimal('0')
            total_pagado = Decimal('0')
            
            if contrato.tipo_documento == TipoDocumento.CONTRATO:
                # Para contratos regulares: usar estados de pago
                estados_pago = self.repo.get_by_contrato_id(contrato_id)
                
                for ep in estados_pago:
                    monto = Decimal(str(ep.monto_efectivo or 0))
                    
                    # Check if it's invoiced
                    if hasattr(ep, 'facturado') and ep.facturado:
                        total_facturado += monto
                    
                    # Check if it's paid - safer access to enum value
                    if ep.estado and hasattr(ep.estado, 'value') and ep.estado.value == 'PAGADO':
                        total_pagado += monto
                        
            elif contrato.tipo_documento == TipoDocumento.ORDEN_COMPRA:
                # Para OCs: usar pendientes de facturar
                pendientes = PendienteFacturar.query.filter_by(contrato_id=contrato_id).all()
                
                for pendiente in pendientes:
                    monto = Decimal(str(pendiente.monto_neto or 0))
                    
                    # Check if it's invoiced or paid
                    if pendiente.estado in [EstadoPendienteFacturar.FACTURADO, EstadoPendienteFacturar.PAGADO]:
                        total_facturado += monto
                    
                    # Check if it's paid
                    if pendiente.estado == EstadoPendienteFacturar.PAGADO:
                        total_pagado += monto
            
            # Update contract fields
            contrato.monto_facturado = total_facturado
            contrato.monto_pagado = total_pagado
            
            # Update audit fields
            contrato.updated_at = datetime.utcnow()
            contrato.updated_by = 'system_sync'
            
            db.session.add(contrato)
            # Don't commit here - let the caller handle the transaction
            
            logger.info(f"Totales financieros actualizados para contrato {contrato_id} ({contrato.tipo_documento.value}): "
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
