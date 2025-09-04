from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import joinedload
from app import db
from models import (OrdenFabricacion, OrdenFabricacionItem, Proyecto,
                   Contrato, Cliente, User, OrdenAreaProgreso)
from schemas.fabricacion import OrdenFabricacionSearchFilters
from utils.enum_normalizer import EnumNormalizer
from constants.transitions import OF_TRANSITIONS, OF_ACTIVE_STATES, OF_SPECIAL_VALIDATIONS

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
                )
                .join(OrdenAreaProgreso, and_(
                    OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                    OrdenAreaProgreso.es_actual == True,
                    OrdenAreaProgreso.archivado == False
                )))

        # Apply filters
        conditions = []

        if filters.proyecto_id:
            conditions.append(OrdenFabricacion.proyecto_id == filters.proyecto_id)

        if filters.contrato_id:
            conditions.append(OrdenFabricacion.contrato_id == filters.contrato_id)

        if filters.codigo:
            conditions.append(OrdenFabricacion.codigo.ilike(f"%{filters.codigo}%"))

        if hasattr(filters, 'area_id') and filters.area_id:
            conditions.append(OrdenAreaProgreso.area_id == filters.area_id)

        if hasattr(filters, 'estado_id') and filters.estado_id:
            conditions.append(OrdenAreaProgreso.estado_id == filters.estado_id)

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
    def get_by_proyecto_id(proyecto_id: int) -> List[OrdenFabricacion]:
        """Get all ordenes for a project"""
        return (db.session.query(OrdenFabricacion)
                .filter_by(proyecto_id=proyecto_id)
                .order_by(OrdenFabricacion.created_at.desc())
                .all())

    @staticmethod
    def get_by_contrato_id(contrato_id: int) -> List[OrdenFabricacion]:
        """Get all ordenes for a contrato"""
        return (db.session.query(OrdenFabricacion)
                .filter_by(contrato_id=contrato_id)
                .order_by(OrdenFabricacion.created_at.desc())
                .all())

    @staticmethod
    def count_by_status(status_list: List[str]) -> int:
        """Count OFs by status"""
        # Return total count of all OFs
        return db.session.query(OrdenFabricacion).count()

    @staticmethod
    def count_by_proyecto_and_status(proyecto_id: int, status_list: List[str]) -> int:
        """Count OFs by proyecto and status"""
        # Return total count for the project
        return (db.session.query(OrdenFabricacion)
                .filter(OrdenFabricacion.proyecto_id == proyecto_id)
                .count())

    @staticmethod
    def get_pending_by_user(user_id: str, limit: int = 10) -> List[OrdenFabricacion]:
        """Get pending OFs assigned to a user"""
        # Get OFs for the user that are not completed
        from models import AreaEstado
        # Get the despachado (final) estado ID
        despachado_estado = db.session.query(AreaEstado).filter_by(codigo='despachado').first()

        if despachado_estado:
            return (db.session.query(OrdenFabricacion)
                    .filter_by(responsable=user_id)
                    .join(OrdenAreaProgreso)
                    .filter(OrdenAreaProgreso.estado_id != despachado_estado.id)
                    .order_by(OrdenFabricacion.fecha_planificada.asc())
                    .limit(limit)
                    .all())
        else:
            # Fallback if estado not found
            return (db.session.query(OrdenFabricacion)
                    .filter_by(responsable=user_id)
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
    def generate_next_codigo() -> str:
        """Generate next OP-xxxx codigo"""
        # Get the last OP code
        last_of = (db.session.query(OrdenFabricacion)
                   .filter(OrdenFabricacion.codigo.like('OP-%'))
                   .order_by(OrdenFabricacion.codigo.desc())
                   .first())

        if last_of:
            # Extract number from OP-xxxx format
            try:
                last_number = int(last_of.codigo.split('-')[1])
                next_number = last_number + 1
            except (IndexError, ValueError):
                next_number = 1
        else:
            next_number = 1

        return f"OP-{next_number:04d}"

    @staticmethod
    def can_change_status(of: OrdenFabricacion, new_status_id: int) -> tuple[bool, str]:
        """
        Check if status change is allowed within current area

        Returns:
            Tuple of (is_allowed, error_message)
        """
        # Get current area progress
        if not of.area_progreso_actual:
            return False, "La orden no tiene área asignada"

        # Check if new status belongs to current area
        from models import AreaEstado
        new_estado = db.session.get(AreaEstado, new_status_id)
        if not new_estado:
            return False, "Estado inválido"

        if new_estado.area_id != of.area_progreso_actual.area_id:
            return False, "El estado no pertenece al área actual"

        return True, ""

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