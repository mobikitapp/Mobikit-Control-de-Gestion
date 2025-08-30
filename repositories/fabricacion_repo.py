from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import joinedload
from app import db
from models import (OrdenFabricacion, OrdenFabricacionItem, Proyecto, 
                   Contrato, Cliente, User, EstadoOF)
from schemas.fabricacion import OrdenFabricacionSearchFilters

class FabricacionRepository:
    """Repository for OrdenFabricacion operations"""
    
    @staticmethod
    def create(of_data: Dict[str, Any], created_by: str) -> OrdenFabricacion:
        """Create a new orden de fabricacion"""
        of = OrdenFabricacion(**of_data)
        of.created_by = created_by
        db.session.add(of)
        db.session.flush()
        return of
    
    @staticmethod
    def get_by_id(of_id: int) -> Optional[OrdenFabricacion]:
        """Get OF by ID with related data"""
        return (db.session.query(OrdenFabricacion)
                .options(
                    joinedload(OrdenFabricacion.proyecto).joinedload(Proyecto.cliente),
                    joinedload(OrdenFabricacion.contrato),
                    joinedload(OrdenFabricacion.responsable_user),
                    joinedload(OrdenFabricacion.creator),
                    joinedload(OrdenFabricacion.items)
                )
                .filter_by(id=of_id)
                .first())
    
    @staticmethod
    def get_by_codigo(codigo: str) -> Optional[OrdenFabricacion]:
        """Get OF by codigo"""
        return db.session.query(OrdenFabricacion).filter_by(codigo=codigo).first()
    
    @staticmethod
    def update(of: OrdenFabricacion, update_data: Dict[str, Any]) -> OrdenFabricacion:
        """Update OF"""
        for key, value in update_data.items():
            if hasattr(of, key) and value is not None:
                setattr(of, key, value)
        db.session.flush()
        return of
    
    @staticmethod
    def delete(of: OrdenFabricacion) -> bool:
        """Delete OF (hard delete)"""
        db.session.delete(of)
        db.session.flush()
        return True
    
    @staticmethod
    def search(filters: OrdenFabricacionSearchFilters) -> tuple[List[OrdenFabricacion], int]:
        """
        Search OFs with filters and pagination
        
        Returns:
            Tuple of (ofs_list, total_count)
        """
        query = (db.session.query(OrdenFabricacion)
                .options(
                    joinedload(OrdenFabricacion.proyecto).joinedload(Proyecto.cliente),
                    joinedload(OrdenFabricacion.contrato),
                    joinedload(OrdenFabricacion.responsable_user)
                ))
        
        # Apply filters
        conditions = []
        
        if filters.proyecto_id:
            conditions.append(OrdenFabricacion.proyecto_id == filters.proyecto_id)
        
        if filters.contrato_id:
            conditions.append(OrdenFabricacion.contrato_id == filters.contrato_id)
        
        if filters.codigo:
            conditions.append(OrdenFabricacion.codigo.ilike(f"%{filters.codigo}%"))
        
        if filters.estado:
            conditions.append(OrdenFabricacion.estado == filters.estado)
        
        if filters.responsable:
            conditions.append(OrdenFabricacion.responsable == filters.responsable)
        
        if filters.fecha_planificada_desde:
            conditions.append(OrdenFabricacion.fecha_planificada >= filters.fecha_planificada_desde)
        
        if filters.fecha_planificada_hasta:
            conditions.append(OrdenFabricacion.fecha_planificada <= filters.fecha_planificada_hasta)
        
        if conditions:
            query = query.filter(and_(*conditions))
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination
        offset = (filters.page - 1) * filters.per_page
        ofs = (query.order_by(OrdenFabricacion.created_at.desc())
               .offset(offset)
               .limit(filters.per_page)
               .all())
        
        return ofs, total_count
    
    @staticmethod
    def get_by_proyecto(proyecto_id: int) -> List[OrdenFabricacion]:
        """Get all OFs for a proyecto"""
        return (db.session.query(OrdenFabricacion)
                .filter_by(proyecto_id=proyecto_id)
                .order_by(OrdenFabricacion.created_at.desc())
                .all())
    
    @staticmethod
    def count_by_status(status_list: List[str]) -> int:
        """Count OFs by status"""
        status_enums = [EstadoOF(status) for status in status_list]
        return (db.session.query(OrdenFabricacion)
                .filter(OrdenFabricacion.estado.in_(status_enums))
                .count())
    
    @staticmethod
    def count_by_proyecto_and_status(proyecto_id: int, status_list: List[str]) -> int:
        """Count OFs by proyecto and status"""
        status_enums = [EstadoOF(status) for status in status_list]
        return (db.session.query(OrdenFabricacion)
                .filter(OrdenFabricacion.proyecto_id == proyecto_id)
                .filter(OrdenFabricacion.estado.in_(status_enums))
                .count())
    
    @staticmethod
    def get_pending_by_user(user_id: str, limit: int = 10) -> List[OrdenFabricacion]:
        """Get pending OFs assigned to a user"""
        return (db.session.query(OrdenFabricacion)
                .filter_by(responsable=user_id)
                .filter(OrdenFabricacion.estado.in_([
                    EstadoOF.PLANIFICADA, EstadoOF.EN_PRODUCCION, EstadoOF.QA
                ]))
                .order_by(OrdenFabricacion.fecha_planificada.asc())
                .limit(limit)
                .all())
    
    @staticmethod
    def exists_codigo(codigo: str, exclude_id: int = None) -> bool:
        """Check if codigo already exists"""
        query = db.session.query(OrdenFabricacion).filter_by(codigo=codigo)
        if exclude_id:
            query = query.filter(OrdenFabricacion.id != exclude_id)
        return query.first() is not None
    
    @staticmethod
    def can_change_status(of: OrdenFabricacion, new_status: EstadoOF) -> tuple[bool, str]:
        """
        Check if status change is allowed
        
        Returns:
            Tuple of (is_allowed, error_message)
        """
        current_status = of.estado
        
        # Define allowed transitions
        allowed_transitions = {
            EstadoOF.PLANIFICADA: [EstadoOF.EN_PRODUCCION],
            EstadoOF.EN_PRODUCCION: [EstadoOF.QA, EstadoOF.PLANIFICADA],  # Can go back to planned
            EstadoOF.QA: [EstadoOF.TERMINADA, EstadoOF.EN_PRODUCCION],    # Can go back to production
            EstadoOF.TERMINADA: [EstadoOF.ENTREGADA],
            EstadoOF.ENTREGADA: []  # Final state
        }
        
        if new_status in allowed_transitions.get(current_status, []):
            return True, ""
        else:
            return False, f"No se puede cambiar de {current_status.value} a {new_status.value}"

class OrdenFabricacionItemRepository:
    """Repository for OrdenFabricacionItem operations"""
    
    @staticmethod
    def create(item_data: Dict[str, Any]) -> OrdenFabricacionItem:
        """Create a new OF item"""
        item = OrdenFabricacionItem(**item_data)
        db.session.add(item)
        db.session.flush()
        return item
    
    @staticmethod
    def get_by_id(item_id: int) -> Optional[OrdenFabricacionItem]:
        """Get item by ID"""
        return db.session.get(OrdenFabricacionItem, item_id)
    
    @staticmethod
    def get_by_of(of_id: int) -> List[OrdenFabricacionItem]:
        """Get all items for an OF"""
        return (db.session.query(OrdenFabricacionItem)
                .filter_by(of_id=of_id)
                .order_by(OrdenFabricacionItem.sku_codigo.asc())
                .all())
    
    @staticmethod
    def update(item: OrdenFabricacionItem, update_data: Dict[str, Any]) -> OrdenFabricacionItem:
        """Update item"""
        for key, value in update_data.items():
            if hasattr(item, key) and value is not None:
                setattr(item, key, value)
        db.session.flush()
        return item
    
    @staticmethod
    def delete(item: OrdenFabricacionItem) -> bool:
        """Delete item"""
        db.session.delete(item)
        db.session.flush()
        return True
    
    @staticmethod
    def delete_by_of(of_id: int) -> int:
        """Delete all items for an OF"""
        count = db.session.query(OrdenFabricacionItem).filter_by(of_id=of_id).count()
        db.session.query(OrdenFabricacionItem).filter_by(of_id=of_id).delete()
        db.session.flush()
        return count
