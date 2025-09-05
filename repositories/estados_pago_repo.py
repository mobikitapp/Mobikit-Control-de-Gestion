
from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import joinedload
from app import db
from models import EstadoPago, TipoEstadoPago, EstadoPagoContrato, Proyecto, Contrato

class EstadosPagoRepository:
    """Repository for EstadoPago operations"""

    @staticmethod
    def create(estado_pago_data: Dict[str, Any], created_by: str) -> EstadoPago:
        """Create a new estado pago"""
        estado_pago = EstadoPago(**estado_pago_data)
        estado_pago.created_by = created_by
        db.session.add(estado_pago)
        db.session.flush()
        return estado_pago

    @staticmethod
    def get_by_id(estado_pago_id: int) -> Optional[EstadoPago]:
        """Get estado pago by ID with related data"""
        return (db.session.query(EstadoPago)
                .options(
                    joinedload(EstadoPago.proyecto),
                    joinedload(EstadoPago.contrato),
                    joinedload(EstadoPago.creator)
                )
                .filter_by(id=estado_pago_id)
                .first())

    @staticmethod
    def get_by_proyecto_id(proyecto_id: int) -> List[EstadoPago]:
        """Get all estados pago for a proyecto"""
        return (db.session.query(EstadoPago)
                .options(
                    joinedload(EstadoPago.contrato),
                    joinedload(EstadoPago.creator)
                )
                .filter_by(proyecto_id=proyecto_id, activo=True)
                .order_by(EstadoPago.fecha_programada.asc(), EstadoPago.created_at.asc())
                .all())

    @staticmethod
    def get_by_contrato_id(contrato_id: int) -> List[EstadoPago]:
        """Get all estados pago for a contrato"""
        return (db.session.query(EstadoPago)
                .options(
                    joinedload(EstadoPago.proyecto),
                    joinedload(EstadoPago.creator)
                )
                .filter_by(contrato_id=contrato_id, activo=True)
                .order_by(EstadoPago.fecha_programada.asc(), EstadoPago.created_at.asc())
                .all())

    @staticmethod
    def update(estado_pago: EstadoPago, update_data: Dict[str, Any]) -> EstadoPago:
        """Update estado pago"""
        for key, value in update_data.items():
            if hasattr(estado_pago, key) and value is not None:
                setattr(estado_pago, key, value)
        db.session.flush()
        return estado_pago

    @staticmethod
    def delete(estado_pago: EstadoPago) -> bool:
        """Soft delete estado pago"""
        estado_pago.activo = False
        db.session.flush()
        return True

    @staticmethod
    def get_montos_pagados_by_proyecto(proyecto_id: int) -> Dict[str, float]:
        """Get total amounts paid for a proyecto grouped by status"""
        estados = (db.session.query(EstadoPago)
                  .filter_by(proyecto_id=proyecto_id, activo=True)
                  .all())

        result = {
            'total_pagado': 0,
            'total_pendiente': 0,
            'total_parcial': 0,
            'total_ocs': 0,
            'total_estados_pago': 0
        }

        for estado in estados:
            monto = float(estado.monto_efectivo)
            
            if estado.estado == EstadoPagoContrato.PAGADO:
                result['total_pagado'] += monto
            elif estado.estado == EstadoPagoContrato.PENDIENTE:
                result['total_pendiente'] += monto
            elif estado.estado == EstadoPagoContrato.PARCIAL:
                result['total_parcial'] += monto

            if estado.tipo == TipoEstadoPago.ORDEN_COMPRA:
                result['total_ocs'] += monto
            else:
                result['total_estados_pago'] += monto

        return result

    @staticmethod
    def get_estadisticas_proyecto(proyecto_id: int) -> Dict[str, Any]:
        """Get payment statistics for a proyecto"""
        estados = EstadosPagoRepository.get_by_proyecto_id(proyecto_id)
        montos = EstadosPagoRepository.get_montos_pagados_by_proyecto(proyecto_id)
        
        total_estados = len(estados)
        estados_pagados = len([e for e in estados if e.estado == EstadoPagoContrato.PAGADO])
        estados_pendientes = len([e for e in estados if e.estado == EstadoPagoContrato.PENDIENTE])
        estados_parciales = len([e for e in estados if e.estado == EstadoPagoContrato.PARCIAL])
        
        return {
            'total_estados': total_estados,
            'estados_pagados': estados_pagados,
            'estados_pendientes': estados_pendientes,
            'estados_parciales': estados_parciales,
            'porcentaje_pagado': round((estados_pagados / total_estados * 100), 1) if total_estados > 0 else 0,
            **montos
        }

    @staticmethod
    def get_proximos_vencimientos(dias: int = 30) -> List[EstadoPago]:
        """Get estados pago that will expire in the next 'dias' days"""
        from datetime import date, timedelta
        fecha_limite = date.today() + timedelta(days=dias)
        
        return (db.session.query(EstadoPago)
                .options(
                    joinedload(EstadoPago.proyecto),
                    joinedload(EstadoPago.contrato)
                )
                .filter(
                    EstadoPago.activo == True,
                    EstadoPago.estado.in_([EstadoPagoContrato.PENDIENTE, EstadoPagoContrato.PARCIAL]),
                    EstadoPago.fecha_programada <= fecha_limite,
                    EstadoPago.fecha_programada >= date.today()
                )
                .order_by(EstadoPago.fecha_programada.asc())
                .all())
