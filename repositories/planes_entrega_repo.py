from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import joinedload
from app import db
from models import PlanEntrega, HitoEntrega, EstadoHitoEntrega
from schemas.planes_entrega import PlanEntregaSearchFilters

class PlanesEntregaRepository:
    """Repository for PlanEntrega operations"""
    
    @staticmethod
    def create(plan_data: Dict[str, Any], created_by: str) -> PlanEntrega:
        """Create a new plan de entrega"""
        plan = PlanEntrega(**plan_data)
        plan.created_by = created_by
        db.session.add(plan)
        db.session.flush()
        return plan
    
    @staticmethod
    def get_by_id(plan_id: int) -> Optional[PlanEntrega]:
        """Get plan de entrega by ID with related data"""
        return (db.session.query(PlanEntrega)
                .options(
                    joinedload(PlanEntrega.hitos).joinedload(HitoEntrega.completado_por_user),
                    joinedload(PlanEntrega.contrato),
                    joinedload(PlanEntrega.creator)
                )
                .filter_by(id=plan_id)
                .first())
    
    @staticmethod
    def get_by_contrato_id(contrato_id: int) -> Optional[PlanEntrega]:
        """Get plan de entrega by contrato ID"""
        return (db.session.query(PlanEntrega)
                .options(
                    joinedload(PlanEntrega.hitos).joinedload(HitoEntrega.completado_por_user),
                    joinedload(PlanEntrega.contrato)
                )
                .filter_by(contrato_id=contrato_id)
                .first())
    
    @staticmethod
    def update(plan: PlanEntrega, update_data: Dict[str, Any]) -> PlanEntrega:
        """Update plan de entrega"""
        for key, value in update_data.items():
            if hasattr(plan, key) and value is not None:
                setattr(plan, key, value)
        db.session.flush()
        return plan
    
    @staticmethod
    def delete(plan: PlanEntrega) -> bool:
        """Delete plan de entrega (hard delete)"""
        db.session.delete(plan)
        db.session.flush()
        return True
    
    @staticmethod
    def search(filters: PlanEntregaSearchFilters) -> tuple[List[PlanEntrega], int]:
        """
        Search planes de entrega with filters and pagination
        
        Returns:
            Tuple of (planes_list, total_count)
        """
        query = (db.session.query(PlanEntrega)
                .options(
                    joinedload(PlanEntrega.hitos),
                    joinedload(PlanEntrega.contrato)
                ))
        
        # Apply filters
        conditions = []
        
        if filters.contrato_id:
            conditions.append(PlanEntrega.contrato_id == filters.contrato_id)
        
        if filters.activo is not None:
            conditions.append(PlanEntrega.activo == filters.activo)
        
        if filters.estado_hito:
            query = query.join(HitoEntrega)
            conditions.append(HitoEntrega.estado == filters.estado_hito)
        
        if filters.fecha_desde:
            query = query.join(HitoEntrega)
            conditions.append(HitoEntrega.fecha_programada >= filters.fecha_desde)
        
        if filters.fecha_hasta:
            query = query.join(HitoEntrega)
            conditions.append(HitoEntrega.fecha_programada <= filters.fecha_hasta)
        
        if conditions:
            query = query.filter(and_(*conditions))
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination
        offset = (filters.page - 1) * filters.per_page
        planes = (query.order_by(PlanEntrega.created_at.desc())
                .offset(offset)
                .limit(filters.per_page)
                .all())
        
        return planes, total_count


class HitosEntregaRepository:
    """Repository for HitoEntrega operations"""
    
    @staticmethod
    def create(hito_data: Dict[str, Any], created_by: str) -> HitoEntrega:
        """Create a new hito de entrega"""
        # Create hito with explicit fields to avoid any field mapping issues
        hito = HitoEntrega(
            plan_entrega_id=hito_data['plan_entrega_id'],
            titulo=hito_data['titulo'],
            descripcion=hito_data.get('descripcion'),
            fecha_programada=hito_data['fecha_programada'],
            orden=hito_data.get('orden', 1),
            estado=EstadoHitoEntrega.PENDIENTE,
            created_by=created_by
        )
        db.session.add(hito)
        db.session.flush()
        
        # Ensure the hito has an ID after flush
        if not hito.id:
            raise Exception("Hito was not properly created - no ID assigned")
        
        return hito
    
    @staticmethod
    def get_by_id(hito_id: int) -> Optional[HitoEntrega]:
        """Get hito de entrega by ID with related data"""
        return (db.session.query(HitoEntrega)
                .options(
                    joinedload(HitoEntrega.plan_entrega),
                    joinedload(HitoEntrega.completado_por_user),
                    joinedload(HitoEntrega.creator)
                )
                .filter_by(id=hito_id)
                .first())
    
    @staticmethod
    def get_by_plan_id(plan_id: int) -> List[HitoEntrega]:
        """Get all hitos for a plan de entrega"""
        return (db.session.query(HitoEntrega)
                .filter_by(plan_entrega_id=plan_id)
                .order_by(HitoEntrega.orden, HitoEntrega.fecha_programada)
                .all())
    
    @staticmethod
    def update(hito: HitoEntrega, update_data: Dict[str, Any]) -> HitoEntrega:
        """Update hito de entrega"""
        for key, value in update_data.items():
            if hasattr(hito, key) and value is not None:
                setattr(hito, key, value)
        db.session.flush()
        return hito
    
    @staticmethod
    def delete(hito: HitoEntrega) -> bool:
        """Delete hito de entrega (hard delete)"""
        db.session.delete(hito)
        db.session.flush()
        return True
    
    @staticmethod
    def get_proximos_hitos(dias: int = 7) -> List[HitoEntrega]:
        """Get upcoming hitos within specified days"""
        from datetime import date, timedelta
        
        fecha_limite = date.today() + timedelta(days=dias)
        
        return (db.session.query(HitoEntrega)
                .options(
                    joinedload(HitoEntrega.plan_entrega).joinedload(PlanEntrega.contrato)
                )
                .filter(
                    and_(
                        HitoEntrega.fecha_programada <= fecha_limite,
                        HitoEntrega.fecha_programada >= date.today(),
                        HitoEntrega.estado == EstadoHitoEntrega.PENDIENTE
                    )
                )
                .order_by(HitoEntrega.fecha_programada)
                .all())
    
    @staticmethod
    def get_hitos_atrasados() -> List[HitoEntrega]:
        """Get overdue hitos"""
        from datetime import date
        
        return (db.session.query(HitoEntrega)
                .options(
                    joinedload(HitoEntrega.plan_entrega).joinedload(PlanEntrega.contrato)
                )
                .filter(
                    and_(
                        HitoEntrega.fecha_programada < date.today(),
                        HitoEntrega.estado == EstadoHitoEntrega.PENDIENTE
                    )
                )
                .order_by(HitoEntrega.fecha_programada)
                .all())