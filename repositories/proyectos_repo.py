from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import joinedload
from app import db
from models import Proyecto, Cliente, User, EstadoProyecto
from schemas.proyectos import ProyectoSearchFilters

class ProyectosRepository:
    """Repository for Proyecto operations"""
    
    @staticmethod
    def create(proyecto_data: Dict[str, Any], created_by: str) -> Proyecto:
        """Create a new proyecto"""
        proyecto = Proyecto(**proyecto_data)
        proyecto.created_by = created_by
        db.session.add(proyecto)
        db.session.flush()
        return proyecto
    
    @staticmethod
    def get_by_id(proyecto_id: int) -> Optional[Proyecto]:
        """Get proyecto by ID with related data"""
        return (db.session.query(Proyecto)
                .options(
                    joinedload(Proyecto.cliente),
                    joinedload(Proyecto.responsable_user),
                    joinedload(Proyecto.creator)
                )
                .filter_by(id=proyecto_id)
                .first())
    
    @staticmethod
    def update(proyecto: Proyecto, update_data: Dict[str, Any]) -> Proyecto:
        """Update proyecto"""
        for key, value in update_data.items():
            if hasattr(proyecto, key) and value is not None:
                setattr(proyecto, key, value)
        db.session.flush()
        return proyecto
    
    @staticmethod
    def delete(proyecto: Proyecto) -> bool:
        """Delete proyecto (hard delete)"""
        db.session.delete(proyecto)
        db.session.flush()
        return True
    
    @staticmethod
    def search(filters: ProyectoSearchFilters) -> tuple[List[Proyecto], int]:
        """
        Search proyectos with filters and pagination
        
        Returns:
            Tuple of (proyectos_list, total_count)
        """
        query = (db.session.query(Proyecto)
                .options(
                    joinedload(Proyecto.cliente),
                    joinedload(Proyecto.responsable_user)
                ))
        
        # Apply filters
        conditions = []
        
        if filters.cliente_id:
            conditions.append(Proyecto.cliente_id == filters.cliente_id)
        
        if filters.nombre:
            conditions.append(Proyecto.nombre.ilike(f"%{filters.nombre}%"))
        
        if filters.estado:
            conditions.append(Proyecto.estado == filters.estado)
        
        if filters.responsable:
            conditions.append(Proyecto.responsable == filters.responsable)
        
        if filters.fecha_inicio_desde:
            conditions.append(Proyecto.fecha_inicio >= filters.fecha_inicio_desde)
        
        if filters.fecha_inicio_hasta:
            conditions.append(Proyecto.fecha_inicio <= filters.fecha_inicio_hasta)
        
        if conditions:
            query = query.filter(and_(*conditions))
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination
        offset = (filters.page - 1) * filters.per_page
        proyectos = (query.order_by(Proyecto.created_at.desc())
                    .offset(offset)
                    .limit(filters.per_page)
                    .all())
        
        return proyectos, total_count
    
    @staticmethod
    def get_by_cliente(cliente_id: int) -> List[Proyecto]:
        """Get all proyectos for a cliente"""
        return (db.session.query(Proyecto)
                .filter_by(cliente_id=cliente_id)
                .order_by(Proyecto.created_at.desc())
                .all())
    
    @staticmethod
    def count_by_status(status_list: List[str]) -> int:
        """Count proyectos by status"""
        status_enums = [EstadoProyecto(status) for status in status_list]
        return (db.session.query(Proyecto)
                .filter(Proyecto.estado.in_(status_enums))
                .count())
    
    @staticmethod
    def count_by_cliente_and_status(cliente_id: int, status_list: List[str]) -> int:
        """Count proyectos by cliente and status"""
        status_enums = [EstadoProyecto(status) for status in status_list]
        return (db.session.query(Proyecto)
                .filter(Proyecto.cliente_id == cliente_id)
                .filter(Proyecto.estado.in_(status_enums))
                .count())
    
    @staticmethod
    def get_recent(limit: int = 10) -> List[Proyecto]:
        """Get recently created proyectos"""
        return (db.session.query(Proyecto)
                .options(
                    joinedload(Proyecto.cliente),
                    joinedload(Proyecto.responsable_user)
                )
                .order_by(Proyecto.created_at.desc())
                .limit(limit)
                .all())
    
    @staticmethod
    def get_by_responsable(responsable_id: str) -> List[Proyecto]:
        """Get proyectos assigned to a responsable"""
        return (db.session.query(Proyecto)
                .filter_by(responsable=responsable_id)
                .order_by(Proyecto.fecha_inicio.desc())
                .all())
    
    @staticmethod
    def get_with_stats(proyecto_id: int) -> Optional[Dict[str, Any]]:
        """Get proyecto with related statistics"""
        proyecto = ProyectosRepository.get_by_id(proyecto_id)
        if not proyecto:
            return None
        
        # Get statistics
        from repositories.contratos_repo import ContratosRepository
        from repositories.fabricacion_repo import FabricacionRepository
        from repositories.despachos_repo import DespachosRepository
        
        stats = {
            'total_contratos': len(proyecto.contratos),
            'contratos_vigentes': ContratosRepository.count_by_proyecto_and_status(
                proyecto_id, 'VIGENTE'
            ),
            'total_ofs': len(proyecto.ordenes_fabricacion),
            'ofs_en_produccion': FabricacionRepository.count_by_proyecto_and_status(
                proyecto_id, ['EN_PRODUCCION', 'QA']
            ),
            'total_despachos': len(proyecto.despachos),
            'despachos_pendientes': DespachosRepository.count_by_proyecto_and_status(
                proyecto_id, ['PROGRAMADO', 'EN_TRANSPORTE']
            )
        }
        
        return {
            'proyecto': proyecto,
            'stats': stats
        }
