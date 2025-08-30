from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import joinedload
from app import db
from models import (Despacho, DespachoAdjunto, Proyecto, OrdenFabricacion, 
                   Cliente, User, EstadoDespacho)
from schemas.despachos import DespachoSearchFilters

class DespachosRepository:
    """Repository for Despacho operations"""
    
    @staticmethod
    def create(despacho_data: Dict[str, Any], created_by: str) -> Despacho:
        """Create a new despacho"""
        despacho = Despacho(**despacho_data)
        despacho.created_by = created_by
        db.session.add(despacho)
        db.session.flush()
        return despacho
    
    @staticmethod
    def get_by_id(despacho_id: int) -> Optional[Despacho]:
        """Get despacho by ID with related data"""
        return (db.session.query(Despacho)
                .options(
                    joinedload(Despacho.proyecto).joinedload(Proyecto.cliente),
                    joinedload(Despacho.orden_fabricacion),
                    joinedload(Despacho.responsable_user),
                    joinedload(Despacho.creator),
                    joinedload(Despacho.adjuntos)
                )
                .filter_by(id=despacho_id)
                .first())
    
    @staticmethod
    def get_by_numero(numero_despacho: str) -> Optional[Despacho]:
        """Get despacho by numero_despacho"""
        return db.session.query(Despacho).filter_by(numero_despacho=numero_despacho).first()
    
    @staticmethod
    def update(despacho: Despacho, update_data: Dict[str, Any]) -> Despacho:
        """Update despacho"""
        for key, value in update_data.items():
            if hasattr(despacho, key) and value is not None:
                setattr(despacho, key, value)
        db.session.flush()
        return despacho
    
    @staticmethod
    def delete(despacho: Despacho) -> bool:
        """Delete despacho (hard delete)"""
        db.session.delete(despacho)
        db.session.flush()
        return True
    
    @staticmethod
    def search(filters: DespachoSearchFilters) -> tuple[List[Despacho], int]:
        """
        Search despachos with filters and pagination
        
        Returns:
            Tuple of (despachos_list, total_count)
        """
        query = (db.session.query(Despacho)
                .options(
                    joinedload(Despacho.proyecto).joinedload(Proyecto.cliente),
                    joinedload(Despacho.orden_fabricacion),
                    joinedload(Despacho.responsable_user)
                ))
        
        # Apply filters
        conditions = []
        
        if filters.proyecto_id:
            conditions.append(Despacho.proyecto_id == filters.proyecto_id)
        
        if filters.of_id:
            conditions.append(Despacho.of_id == filters.of_id)
        
        if filters.numero_despacho:
            conditions.append(Despacho.numero_despacho.ilike(f"%{filters.numero_despacho}%"))
        
        if filters.estado:
            conditions.append(Despacho.estado == filters.estado)
        
        if filters.responsable:
            conditions.append(Despacho.responsable == filters.responsable)
        
        if filters.fecha_programada_desde:
            conditions.append(Despacho.fecha_programada >= filters.fecha_programada_desde)
        
        if filters.fecha_programada_hasta:
            conditions.append(Despacho.fecha_programada <= filters.fecha_programada_hasta)
        
        if conditions:
            query = query.filter(and_(*conditions))
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination
        offset = (filters.page - 1) * filters.per_page
        despachos = (query.order_by(Despacho.created_at.desc())
                    .offset(offset)
                    .limit(filters.per_page)
                    .all())
        
        return despachos, total_count
    
    @staticmethod
    def get_by_proyecto(proyecto_id: int) -> List[Despacho]:
        """Get all despachos for a proyecto"""
        return (db.session.query(Despacho)
                .filter_by(proyecto_id=proyecto_id)
                .order_by(Despacho.created_at.desc())
                .all())
    
    @staticmethod
    def count_by_status(status_list: List[str]) -> int:
        """Count despachos by status"""
        status_enums = [EstadoDespacho(status) for status in status_list]
        return (db.session.query(Despacho)
                .filter(Despacho.estado.in_(status_enums))
                .count())
    
    @staticmethod
    def count_by_proyecto_and_status(proyecto_id: int, status_list: List[str]) -> int:
        """Count despachos by proyecto and status"""
        status_enums = [EstadoDespacho(status) for status in status_list]
        return (db.session.query(Despacho)
                .filter(Despacho.proyecto_id == proyecto_id)
                .filter(Despacho.estado.in_(status_enums))
                .count())
    
    @staticmethod
    def get_pending_by_user(user_id: str, limit: int = 10) -> List[Despacho]:
        """Get pending despachos assigned to a user"""
        return (db.session.query(Despacho)
                .filter_by(responsable=user_id)
                .filter(Despacho.estado.in_([
                    EstadoDespacho.PROGRAMADO, EstadoDespacho.EN_TRANSPORTE
                ]))
                .order_by(Despacho.fecha_programada.asc())
                .limit(limit)
                .all())
    
    @staticmethod
    def exists_numero(numero_despacho: str, exclude_id: int = None) -> bool:
        """Check if numero_despacho already exists"""
        query = db.session.query(Despacho).filter_by(numero_despacho=numero_despacho)
        if exclude_id:
            query = query.filter(Despacho.id != exclude_id)
        return query.first() is not None
    
    @staticmethod
    def can_change_status(despacho: Despacho, new_status: EstadoDespacho) -> tuple[bool, str]:
        """
        Check if status change is allowed
        
        Returns:
            Tuple of (is_allowed, error_message)
        """
        current_status = despacho.estado
        
        # Define allowed transitions
        allowed_transitions = {
            EstadoDespacho.PROGRAMADO: [EstadoDespacho.EN_TRANSPORTE, EstadoDespacho.OBSERVADO],
            EstadoDespacho.EN_TRANSPORTE: [EstadoDespacho.ENTREGADO, EstadoDespacho.OBSERVADO],
            EstadoDespacho.ENTREGADO: [],  # Final state
            EstadoDespacho.OBSERVADO: [EstadoDespacho.PROGRAMADO, EstadoDespacho.EN_TRANSPORTE]
        }
        
        if new_status in allowed_transitions.get(current_status, []):
            return True, ""
        else:
            return False, f"No se puede cambiar de {current_status.value} a {new_status.value}"

class DespachoAdjuntosRepository:
    """Repository for DespachoAdjunto operations"""
    
    @staticmethod
    def create(adjunto_data: Dict[str, Any], created_by: str) -> DespachoAdjunto:
        """Create a new despacho adjunto"""
        adjunto = DespachoAdjunto(**adjunto_data)
        adjunto.created_by = created_by
        db.session.add(adjunto)
        db.session.flush()
        return adjunto
    
    @staticmethod
    def get_by_id(adjunto_id: int) -> Optional[DespachoAdjunto]:
        """Get adjunto by ID"""
        return db.session.get(DespachoAdjunto, adjunto_id)
    
    @staticmethod
    def get_by_despacho(despacho_id: int) -> List[DespachoAdjunto]:
        """Get all adjuntos for a despacho"""
        return (db.session.query(DespachoAdjunto)
                .filter_by(despacho_id=despacho_id)
                .order_by(DespachoAdjunto.created_at.desc())
                .all())
    
    @staticmethod
    def delete(adjunto: DespachoAdjunto) -> bool:
        """Delete adjunto"""
        db.session.delete(adjunto)
        db.session.flush()
        return True
