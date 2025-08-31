from typing import List, Tuple
from datetime import datetime, timedelta
from sqlalchemy import and_

from app import db
from models import Contrato, EventoEntrega, EstadoContrato, TipoEvento, EstadoEvento, PrioridadEvento


class ContratoEventosService:
    """Service to manage automatic event generation from contracts"""

    def generar_eventos_desde_contratos(self, usuario_id: str) -> Tuple[bool, str, int]:
        """Generate delivery events from contracts with delivery dates"""
        try:
            eventos_creados = 0
            
            # Get contracts with delivery dates that don't have events yet
            contratos_sin_eventos = (
                db.session.query(Contrato)
                .filter(
                    and_(
                        Contrato.fecha_entrega_comprometida.isnot(None),
                        Contrato.estado == EstadoContrato.VIGENTE,
                        ~Contrato.eventos_entrega.any()  # No events exist yet
                    )
                )
                .all()
            )
            
            for contrato in contratos_sin_eventos:
                # Create delivery event
                evento_id = self._generate_evento_id()
                
                nuevo_evento = EventoEntrega()
                nuevo_evento.id = evento_id
                nuevo_evento.contrato_id = contrato.id
                nuevo_evento.proyecto_id = contrato.proyecto_id
                nuevo_evento.titulo = f"Entrega - {contrato.numero_oc}"
                nuevo_evento.descripcion = f"Fecha de entrega comprometida para orden de compra {contrato.numero_oc}"
                nuevo_evento.fecha_evento = contrato.fecha_entrega_comprometida
                nuevo_evento.tipo_evento = TipoEvento.ENTREGA
                nuevo_evento.estado = EstadoEvento.PENDIENTE
                nuevo_evento.prioridad = PrioridadEvento.ALTA
                nuevo_evento.recordatorio_dias = 3  # 3 days before
                nuevo_evento.created_by = usuario_id
                
                db.session.add(nuevo_evento)
                eventos_creados += 1
            
            if eventos_creados > 0:
                db.session.commit()
                return True, f"Se crearon {eventos_creados} eventos de entrega automáticamente", eventos_creados
            else:
                return True, "No hay contratos con fechas de entrega que requieran eventos", 0
                
        except Exception as e:
            db.session.rollback()
            return False, f"Error al generar eventos: {str(e)}", 0

    def actualizar_evento_desde_contrato(self, contrato_id: int) -> Tuple[bool, str]:
        """Update or create event when contract delivery date changes"""
        try:
            contrato = db.session.query(Contrato).filter_by(id=contrato_id).first()
            if not contrato:
                return False, "Contrato no encontrado"
            
            # Find existing event for this contract
            evento_existente = (
                db.session.query(EventoEntrega)
                .filter_by(contrato_id=contrato.id)
                .first()
            )
            
            if contrato.fecha_entrega_comprometida:
                if evento_existente:
                    # Update existing event
                    evento_existente.fecha_evento = contrato.fecha_entrega_comprometida
                    evento_existente.titulo = f"Entrega - {contrato.numero_oc}"
                    evento_existente.updated_at = datetime.now()
                    mensaje = "Evento de entrega actualizado"
                else:
                    # Create new event
                    evento_id = self._generate_evento_id()
                    
                    nuevo_evento = EventoEntrega()
                    nuevo_evento.id = evento_id
                    nuevo_evento.contrato_id = contrato.id
                    nuevo_evento.proyecto_id = contrato.proyecto_id
                    nuevo_evento.titulo = f"Entrega - {contrato.numero_oc}"
                    nuevo_evento.descripcion = f"Fecha de entrega comprometida para orden de compra {contrato.numero_oc}"
                    nuevo_evento.fecha_evento = contrato.fecha_entrega_comprometida
                    nuevo_evento.tipo_evento = TipoEvento.ENTREGA
                    nuevo_evento.estado = EstadoEvento.PENDIENTE
                    nuevo_evento.prioridad = PrioridadEvento.ALTA
                    nuevo_evento.recordatorio_dias = 3
                    nuevo_evento.created_by = "system"
                    
                    db.session.add(nuevo_evento)
                    mensaje = "Evento de entrega creado"
            else:
                if evento_existente:
                    # Remove event if no delivery date
                    db.session.delete(evento_existente)
                    mensaje = "Evento de entrega eliminado (sin fecha de entrega)"
                else:
                    mensaje = "Sin cambios necesarios"
            
            db.session.commit()
            return True, mensaje
            
        except Exception as e:
            db.session.rollback()
            return False, f"Error: {str(e)}"

    def get_contratos_con_entregas_pendientes(self) -> List[Contrato]:
        """Get contracts with pending delivery dates"""
        return (
            db.session.query(Contrato)
            .filter(
                and_(
                    Contrato.fecha_entrega_comprometida.isnot(None),
                    Contrato.estado == EstadoContrato.VIGENTE,
                    Contrato.fecha_entrega_comprometida >= datetime.now().date()
                )
            )
            .order_by(Contrato.fecha_entrega_comprometida)
            .all()
        )

    def get_entregas_proximas(self, dias: int = 7) -> List[EventoEntrega]:
        """Get delivery events in the next X days"""
        fecha_limite = datetime.now().date() + timedelta(days=dias)
        
        return (
            db.session.query(EventoEntrega)
            .filter(
                and_(
                    EventoEntrega.tipo_evento == TipoEvento.ENTREGA,
                    EventoEntrega.estado == EstadoEvento.PENDIENTE,
                    EventoEntrega.fecha_evento <= fecha_limite,
                    EventoEntrega.fecha_evento >= datetime.now().date()
                )
            )
            .order_by(EventoEntrega.fecha_evento)
            .all()
        )

    def get_entregas_vencidas(self) -> List[EventoEntrega]:
        """Get overdue delivery events"""
        return (
            db.session.query(EventoEntrega)
            .filter(
                and_(
                    EventoEntrega.tipo_evento == TipoEvento.ENTREGA,
                    EventoEntrega.estado == EstadoEvento.PENDIENTE,
                    EventoEntrega.fecha_evento < datetime.now().date()
                )
            )
            .order_by(EventoEntrega.fecha_evento)
            .all()
        )

    def _generate_evento_id(self) -> str:
        """Generate unique event ID"""
        timestamp = str(int(datetime.now().timestamp()))
        return f"evt_entrega_{timestamp}"