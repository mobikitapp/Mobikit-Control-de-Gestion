from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import joinedload
from sqlalchemy import and_
from datetime import datetime

from app import db
from models import (
    Area, AreaEstado, OrdenAreaProgreso, OrdenFabricacion, 
    TipoArea, User, Proyecto, Cliente
)


class AreasRepository:
    """Repository for Area operations"""
    
    @staticmethod
    def get_all_areas() -> List[Area]:
        """Get all areas ordered by sequence"""
        return (db.session.query(Area)
                .options(joinedload(Area.estados))
                .filter_by(activo=True)
                .order_by(Area.orden_secuencia.asc())
                .all())
    
    @staticmethod
    def get_area_by_id(area_id: int) -> Optional[Area]:
        """Get area by ID with states"""
        return (db.session.query(Area)
                .options(joinedload(Area.estados))
                .filter_by(id=area_id, activo=True)
                .first())
    
    @staticmethod
    def get_area_by_tipo(tipo: TipoArea) -> Optional[Area]:
        """Get area by type"""
        return (db.session.query(Area)
                .options(joinedload(Area.estados))
                .filter_by(tipo=tipo, activo=True)
                .first())
    
    @staticmethod
    def get_estados_by_area(area_id: int) -> List[AreaEstado]:
        """Get all states for an area"""
        return (db.session.query(AreaEstado)
                .filter_by(area_id=area_id, activo=True)
                .order_by(AreaEstado.orden_en_area.asc())
                .all())
    
    @staticmethod
    def get_estado_inicial(area_id: int) -> Optional[AreaEstado]:
        """Get initial state for an area"""
        return (db.session.query(AreaEstado)
                .filter_by(area_id=area_id, es_inicial=True, activo=True)
                .first())
    
    @staticmethod
    def get_estado_final(area_id: int) -> Optional[AreaEstado]:
        """Get final state for an area"""
        return (db.session.query(AreaEstado)
                .filter_by(area_id=area_id, es_final=True, activo=True)
                .first())


class OrdenAreaProgresoRepository:
    """Repository for OrdenAreaProgreso operations"""
    
    @staticmethod
    def get_current_progress(orden_fabricacion_id: int) -> Optional[OrdenAreaProgreso]:
        """Get current area progress for an OF"""
        return (db.session.query(OrdenAreaProgreso)
                .options(
                    joinedload(OrdenAreaProgreso.area),
                    joinedload(OrdenAreaProgreso.estado),
                    joinedload(OrdenAreaProgreso.responsable_user)
                )
                .filter_by(
                    orden_fabricacion_id=orden_fabricacion_id,
                    es_actual=True,
                    archivado=False
                )
                .first())
    
    @staticmethod
    def get_progress_history(orden_fabricacion_id: int) -> List[OrdenAreaProgreso]:
        """Get complete progress history for an OF"""
        return (db.session.query(OrdenAreaProgreso)
                .options(
                    joinedload(OrdenAreaProgreso.area),
                    joinedload(OrdenAreaProgreso.estado),
                    joinedload(OrdenAreaProgreso.responsable_user),
                    joinedload(OrdenAreaProgreso.creator)
                )
                .filter_by(orden_fabricacion_id=orden_fabricacion_id)
                .order_by(OrdenAreaProgreso.fecha_ingreso_area.asc())
                .all())
    
    @staticmethod
    def get_orders_in_area(area_id: int, archivado: bool = False) -> List[OrdenAreaProgreso]:
        """Get all OFs currently in a specific area"""
        return (db.session.query(OrdenAreaProgreso)
                .options(
                    joinedload(OrdenAreaProgreso.orden_fabricacion)
                    .joinedload(OrdenFabricacion.proyecto)
                    .joinedload(Proyecto.cliente),
                    joinedload(OrdenAreaProgreso.estado),
                    joinedload(OrdenAreaProgreso.responsable_user)
                )
                .filter_by(
                    area_id=area_id,
                    es_actual=True,
                    archivado=archivado
                )
                .order_by(OrdenAreaProgreso.fecha_ingreso_area.asc())
                .all())
    
    @staticmethod
    def get_orders_by_estado(estado_id: int, archivado: bool = False) -> List[OrdenAreaProgreso]:
        """Get all OFs in a specific state"""
        return (db.session.query(OrdenAreaProgreso)
                .options(
                    joinedload(OrdenAreaProgreso.orden_fabricacion)
                    .joinedload(OrdenFabricacion.proyecto)
                    .joinedload(Proyecto.cliente),
                    joinedload(OrdenAreaProgreso.responsable_user)
                )
                .filter_by(
                    estado_id=estado_id,
                    es_actual=True,
                    archivado=archivado
                )
                .order_by(OrdenAreaProgreso.fecha_cambio_estado.asc())
                .all())
    
    @staticmethod
    def get_orders_by_responsable(responsable_id: str, archivado: bool = False) -> List[OrdenAreaProgreso]:
        """Get all OFs assigned to a user"""
        return (db.session.query(OrdenAreaProgreso)
                .options(
                    joinedload(OrdenAreaProgreso.orden_fabricacion)
                    .joinedload(OrdenFabricacion.proyecto)
                    .joinedload(Proyecto.cliente),
                    joinedload(OrdenAreaProgreso.area),
                    joinedload(OrdenAreaProgreso.estado)
                )
                .filter_by(
                    responsable_area=responsable_id,
                    es_actual=True,
                    archivado=archivado
                )
                .order_by(OrdenAreaProgreso.fecha_cambio_estado.asc())
                .all())
    
    @staticmethod
    def create_progress(progress_data: Dict[str, Any]) -> OrdenAreaProgreso:
        """Create new area progress record"""
        progress = OrdenAreaProgreso(**progress_data)
        db.session.add(progress)
        db.session.flush()
        return progress
    
    @staticmethod
    def update_progress(progress: OrdenAreaProgreso, update_data: Dict[str, Any]) -> OrdenAreaProgreso:
        """Update area progress"""
        for key, value in update_data.items():
            if hasattr(progress, key) and value is not None:
                setattr(progress, key, value)
        db.session.flush()
        return progress
    
    @staticmethod
    def archive_progress(progress: OrdenAreaProgreso) -> OrdenAreaProgreso:
        """Archive a progress record (for dispatch archiving)"""
        progress.archivado = True
        db.session.flush()
        return progress
    
    @staticmethod
    def get_dashboard_stats() -> Dict[str, Any]:
        """Get statistics for areas dashboard"""
        stats = {}
        
        # Get count by area
        area_counts = (db.session.query(Area.nombre, Area.color_hex, 
                                      db.func.count(OrdenAreaProgreso.id).label('count'))
                      .join(OrdenAreaProgreso, Area.id == OrdenAreaProgreso.area_id)
                      .filter(OrdenAreaProgreso.es_actual == True)
                      .filter(OrdenAreaProgreso.archivado == False)
                      .group_by(Area.id, Area.nombre, Area.color_hex, Area.orden_secuencia)
                      .order_by(Area.orden_secuencia)
                      .all())
        
        stats['area_counts'] = [
            {
                'nombre': nombre,
                'color': color_hex,
                'count': count
            }
            for nombre, color_hex, count in area_counts
        ]
        
        # Get overdue orders (más de X días sin cambios)
        overdue_days = 7
        overdue_date = datetime.now() - datetime.timedelta(days=overdue_days)
        
        overdue_count = (db.session.query(OrdenAreaProgreso)
                        .filter(OrdenAreaProgreso.es_actual == True)
                        .filter(OrdenAreaProgreso.archivado == False)
                        .filter(OrdenAreaProgreso.fecha_cambio_estado < overdue_date)
                        .count())
        
        stats['overdue_count'] = overdue_count
        
        # Total active orders
        total_active = (db.session.query(OrdenAreaProgreso)
                       .filter(OrdenAreaProgreso.es_actual == True)
                       .filter(OrdenAreaProgreso.archivado == False)
                       .count())
        
        stats['total_active'] = total_active
        
        return stats
    
    @staticmethod
    def can_transition_to_area(current_area_id: int, target_area_id: int) -> Tuple[bool, str]:
        """Check if transition between areas is allowed"""
        current_area = AreasRepository.get_area_by_id(current_area_id)
        target_area = AreasRepository.get_area_by_id(target_area_id)
        
        if not current_area or not target_area:
            return False, "Área no encontrada"
        
        # Sequential flow only - can only move to next area
        if target_area.orden_secuencia != current_area.orden_secuencia + 1:
            # Allow backwards movement for corrections (admin only logic can be added later)
            if target_area.orden_secuencia < current_area.orden_secuencia:
                return True, f"Movimiento hacia atrás desde {current_area.nombre} a {target_area.nombre}"
            else:
                return False, f"Solo se puede avanzar al siguiente área secuencialmente"
        
        return True, f"Transición válida de {current_area.nombre} a {target_area.nombre}"