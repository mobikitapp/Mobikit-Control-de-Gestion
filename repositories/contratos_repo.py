from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import joinedload
from app import db
from models import Contrato, ContratoAdjunto, Proyecto, Cliente, User, EstadoContrato, PlanEntrega, HitoEntrega
from schemas.contratos import ContratoSearchFilters

class ContratosRepository:
    """Repository for Contrato operations"""
    
    @staticmethod
    def create(contrato_data: Dict[str, Any], created_by: str) -> Contrato:
        """Create a new contrato"""
        contrato = Contrato(**contrato_data)
        contrato.created_by = created_by
        db.session.add(contrato)
        db.session.flush()
        return contrato
    
    @staticmethod
    def get_by_id(contrato_id: int) -> Optional[Contrato]:
        """Get contrato by ID with related data"""
        return (db.session.query(Contrato)
                .options(
                    joinedload(Contrato.proyecto).joinedload(Proyecto.cliente),
                    joinedload(Contrato.adjuntos),
                    joinedload(Contrato.creator)
                )
                .filter_by(id=contrato_id)
                .first())
    
    @staticmethod
    def get_by_numero_oc(numero_oc: str) -> Optional[Contrato]:
        """Get contrato by numero_oc"""
        return db.session.query(Contrato).filter_by(numero_oc=numero_oc).first()
    
    @staticmethod
    def update(contrato: Contrato, update_data: Dict[str, Any]) -> Contrato:
        """Update contrato"""
        for key, value in update_data.items():
            if hasattr(contrato, key) and value is not None:
                setattr(contrato, key, value)
        db.session.flush()
        return contrato
    
    @staticmethod
    def delete(contrato: Contrato) -> bool:
        """Delete contrato (hard delete)"""
        db.session.delete(contrato)
        db.session.flush()
        return True
    
    @staticmethod
    def search(filters: ContratoSearchFilters) -> tuple[List[Contrato], int]:
        """
        Search contratos with filters and pagination
        
        Returns:
            Tuple of (contratos_list, total_count)
        """
        query = (db.session.query(Contrato)
                .options(
                    joinedload(Contrato.proyecto).joinedload(Proyecto.cliente),
                    joinedload(Contrato.adjuntos),
                    joinedload(Contrato.plan_entrega).joinedload(PlanEntrega.hitos),
                    joinedload(Contrato.ordenes_fabricacion)
                ))
        
        # Apply filters
        conditions = []
        
        if filters.proyecto_id:
            conditions.append(Contrato.proyecto_id == filters.proyecto_id)
        
        if filters.numero_oc:
            conditions.append(Contrato.numero_oc.ilike(f"%{filters.numero_oc}%"))
        
        if filters.estado:
            conditions.append(Contrato.estado == filters.estado)
        
        if filters.moneda:
            conditions.append(Contrato.moneda == filters.moneda)
        
        if filters.fecha_emision_desde:
            conditions.append(Contrato.fecha_emision >= filters.fecha_emision_desde)
        
        if filters.fecha_emision_hasta:
            conditions.append(Contrato.fecha_emision <= filters.fecha_emision_hasta)
        
        if conditions:
            query = query.filter(and_(*conditions))
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination
        offset = (filters.page - 1) * filters.per_page
        contratos = (query.order_by(Contrato.created_at.desc())
                    .offset(offset)
                    .limit(filters.per_page)
                    .all())
        
        return contratos, total_count
    
    @staticmethod
    def get_by_proyecto(proyecto_id: int) -> List[Contrato]:
        """Get all contratos for a proyecto"""
        return (db.session.query(Contrato)
                .filter_by(proyecto_id=proyecto_id)
                .order_by(Contrato.created_at.desc())
                .all())
    
    @staticmethod
    def count_by_status(status: str) -> int:
        """Count contratos by status"""
        status_enum = EstadoContrato(status)
        return db.session.query(Contrato).filter_by(estado=status_enum).count()
    
    @staticmethod
    def count_by_proyecto_and_status(proyecto_id: int, status: str) -> int:
        """Count contratos by proyecto and status"""
        status_enum = EstadoContrato(status)
        return (db.session.query(Contrato)
                .filter_by(proyecto_id=proyecto_id, estado=status_enum)
                .count())
    
    @staticmethod
    def count_by_cliente_and_status(cliente_id: int, status: str) -> int:
        """Count contratos by cliente and status"""
        status_enum = EstadoContrato(status)
        return (db.session.query(Contrato)
                .join(Proyecto)
                .filter(Proyecto.cliente_id == cliente_id)
                .filter(Contrato.estado == status_enum)
                .count())
    
    @staticmethod
    def exists_numero_oc(numero_oc: str, exclude_id: int = None) -> bool:
        """Check if numero_oc already exists"""
        query = db.session.query(Contrato).filter_by(numero_oc=numero_oc)
        if exclude_id:
            query = query.filter(Contrato.id != exclude_id)
        return query.first() is not None
    
    @staticmethod
    def can_change_status(contrato: Contrato, new_status: EstadoContrato) -> tuple[bool, str]:
        """
        Check if status change is allowed
        
        Returns:
            Tuple of (is_allowed, error_message)
        """
        current_status = contrato.estado
        
        # Define allowed transitions
        allowed_transitions = {
            EstadoContrato.BORRADOR: [EstadoContrato.VIGENTE, EstadoContrato.ANULADO],
            EstadoContrato.VIGENTE: [EstadoContrato.CERRADO, EstadoContrato.ANULADO],
            EstadoContrato.CERRADO: [],  # No transitions from closed
            EstadoContrato.ANULADO: []   # No transitions from cancelled
        }
        
        if new_status in allowed_transitions.get(current_status, []):
            return True, ""
        else:
            return False, f"No se puede cambiar de {current_status.value} a {new_status.value}"

class ContratoAdjuntosRepository:
    """Repository for ContratoAdjunto operations"""
    
    @staticmethod
    def create(adjunto_data: Dict[str, Any], created_by: str) -> ContratoAdjunto:
        """Create a new contrato adjunto"""
        adjunto = ContratoAdjunto(**adjunto_data)
        adjunto.created_by = created_by
        db.session.add(adjunto)
        db.session.flush()
        return adjunto
    
    @staticmethod
    def get_by_id(adjunto_id: int) -> Optional[ContratoAdjunto]:
        """Get adjunto by ID"""
        return db.session.get(ContratoAdjunto, adjunto_id)
    
    @staticmethod
    def get_by_contrato(contrato_id: int) -> List[ContratoAdjunto]:
        """Get all adjuntos for a contrato"""
        return (db.session.query(ContratoAdjunto)
                .filter_by(contrato_id=contrato_id)
                .order_by(ContratoAdjunto.created_at.desc())
                .all())
    
    @staticmethod
    def delete(adjunto: ContratoAdjunto) -> bool:
        """Delete adjunto"""
        db.session.delete(adjunto)
        db.session.flush()
        return True
