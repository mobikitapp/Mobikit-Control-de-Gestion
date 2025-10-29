from typing import List, Optional, Dict, Any
from sqlalchemy import and_, or_, func
from sqlalchemy.orm import joinedload
from app import db
from models import Proyecto, Cliente, User
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
        from models import Contrato, EstadoContrato
        
        # Create subquery to count active contracts
        contrato_count_subquery = (
            db.session.query(
                Contrato.proyecto_id,
                func.count(Contrato.id).label('contratos_activos_count')
            )
            .filter(Contrato.estado == EstadoContrato.VIGENTE)
            .group_by(Contrato.proyecto_id)
            .subquery()
        )
        
        # Base query - siempre incluir proyectos activos
        query = (db.session.query(Proyecto)
                .options(
                    joinedload(Proyecto.cliente),
                    joinedload(Proyecto.responsable_user),
                    joinedload(Proyecto.vendedor_user),
                    joinedload(Proyecto.contratos)
                )
                .filter(Proyecto.activo == True)  # Solo proyectos activos
                .outerjoin(contrato_count_subquery, Proyecto.id == contrato_count_subquery.c.proyecto_id))

        # Apply filters only when they have actual values
        conditions = []

        # Filter by cliente only if cliente_id is provided and valid
        if hasattr(filters, 'cliente_id') and filters.cliente_id and filters.cliente_id > 0:
            conditions.append(Proyecto.cliente_id == filters.cliente_id)

        # Filter by nombre only if provided and not empty
        if hasattr(filters, 'nombre') and filters.nombre and filters.nombre.strip():
            conditions.append(Proyecto.nombre.ilike(f"%{filters.nombre.strip()}%"))

        # Filter by vendedor only if vendedor_id is provided and not empty
        if hasattr(filters, 'vendedor_id') and filters.vendedor_id and filters.vendedor_id.strip():
            conditions.append(Proyecto.vendedor_id == filters.vendedor_id.strip())

        # Filter by fecha_inicio_desde only if provided
        if hasattr(filters, 'fecha_inicio_desde') and filters.fecha_inicio_desde:
            conditions.append(Proyecto.fecha_inicio >= filters.fecha_inicio_desde)

        # Filter by fecha_inicio_hasta only if provided
        if hasattr(filters, 'fecha_inicio_hasta') and filters.fecha_inicio_hasta:
            conditions.append(Proyecto.fecha_inicio <= filters.fecha_inicio_hasta)

        # Filter by estado_comercial only if provided and not empty
        if hasattr(filters, 'estado_comercial') and filters.estado_comercial and filters.estado_comercial.strip():
            from models import EstadoComercial
            try:
                estado_enum = EstadoComercial(filters.estado_comercial.strip())
                conditions.append(Proyecto.estado_comercial == estado_enum)
            except ValueError:
                # Si el estado no es válido, ignorar el filtro
                pass

        # Apply conditions only if there are any
        if conditions:
            query = query.filter(and_(*conditions))

        # Get total count before pagination
        total_count = query.count()

        # Validar página - si no hay resultados, establecer página 1
        if total_count == 0:
            return [], 0

        # Calcular número máximo de páginas
        max_pages = max(1, (total_count + filters.per_page - 1) // filters.per_page)
        
        # Si la página solicitada es mayor al máximo, usar la última página
        page_to_use = min(filters.page, max_pages)
        
        # Apply ordering and pagination
        offset = (page_to_use - 1) * filters.per_page
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
        """Count proyectos by commercial status"""
        from models import EstadoComercial
        status_enums = [EstadoComercial(status) for status in status_list]
        return (db.session.query(Proyecto)
                .filter(Proyecto.estado_comercial.in_(status_enums))
                .count())

    @staticmethod
    def count_by_cliente_and_status(cliente_id: int, status_list: List[str]) -> int:
        """Count proyectos by cliente and commercial status"""
        from models import EstadoComercial
        status_enums = [EstadoComercial(status) for status in status_list]
        return (db.session.query(Proyecto)
                .filter(Proyecto.cliente_id == cliente_id)
                .filter(Proyecto.estado_comercial.in_(status_enums))
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
        """Get proyectos by responsable"""
        return (db.session.query(Proyecto)
                .options(
                    joinedload(Proyecto.cliente),
                    joinedload(Proyecto.responsable_user),
                    joinedload(Proyecto.vendedor_user)
                )
                .filter_by(responsable_id=responsable_id)
                .order_by(Proyecto.created_at.desc())
                .all())

    @staticmethod
    def get_active() -> List[Proyecto]:
        """Get all active proyectos"""
        return (db.session.query(Proyecto)
                .options(
                    joinedload(Proyecto.cliente),
                    joinedload(Proyecto.responsable_user),
                    joinedload(Proyecto.vendedor_user)
                )
                .join(Cliente)
                .filter(Cliente.activo == True)
                .order_by(Proyecto.nombre)
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