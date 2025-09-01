from typing import List, Optional, Dict, Any
from datetime import datetime
from app import db
from repositories.fabricacion_repo import FabricacionRepository, OrdenFabricacionItemRepository
from repositories.proyectos_repo import ProyectosRepository
from repositories.contratos_repo import ContratosRepository
from services.audit_service import AuditService, serialize_model
from services.areas_service import AreasService
from schemas.fabricacion import OrdenFabricacionSearchFilters
from models import OrdenFabricacion
import logging

logger = logging.getLogger(__name__)

class FabricacionService:
    """Service layer for OrdenFabricacion operations"""

    def __init__(self):
        self.repo = FabricacionRepository()
        self.items_repo = OrdenFabricacionItemRepository()
        self.proyectos_repo = ProyectosRepository()
        self.contratos_repo = ContratosRepository()
        self.areas_service = AreasService()

    def create_orden_fabricacion(self, of_data: Dict[str, Any], created_by: str) -> OrdenFabricacion:
        """
        Create a new orden de fabricacion with items and audit logging

        Args:
            of_data: OF data dictionary including items
            created_by: User ID who is creating the OF

        Returns:
            Created OrdenFabricacion instance
        """
        try:
            # Validate proyecto exists
            proyecto = self.proyectos_repo.get_by_id(of_data['proyecto_id'])
            if not proyecto:
                raise ValueError(f"Proyecto {of_data['proyecto_id']} no encontrado")

            # Validate contrato if provided
            if of_data.get('contrato_id'):
                contrato = self.contratos_repo.get_by_id(of_data['contrato_id'])
                if not contrato:
                    raise ValueError(f"Contrato {of_data['contrato_id']} no encontrado")
                if contrato.proyecto_id != of_data['proyecto_id']:
                    raise ValueError("El contrato no pertenece al proyecto especificado")

            # Always generate automatic codigo for generic orders
            of_data['codigo'] = self.repo.generate_next_codigo()

            # Remove estado if present (no longer used)
            of_data.pop('estado', None)

            # Extract items data
            items_data = of_data.pop('items', [])

            # Create OF
            of = self.repo.create(of_data, created_by)

            # Create items
            for item_data in items_data:
                item_data['of_id'] = of.id
                self.items_repo.create(item_data)

            # Initialize in areas system with initial state
            self.areas_service.initialize_orden_in_areas(of.id, created_by)

            # Commit transaction
            db.session.commit()

            # Auto-change proyecto estado to EN_DESARROLLO
            from services.proyectos_service import ProyectosService
            proyectos_service = ProyectosService()
            proyectos_service.cambiar_estado_por_contrato_creado(of.proyecto_id)

            # Log audit
            AuditService.log_action(
                'ordenes_fabricacion', 
                of.id, 
                'CREATE', 
                datos_nuevos=serialize_model(of)
            )

            logger.info(f"Orden de fabricación creada: {of.id} - {of.codigo}")
            return of

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando OF: {str(e)}")
            raise

    def get_orden_fabricacion_by_id(self, of_id: int) -> Optional[OrdenFabricacion]:
        """Get OF by ID with related data"""
        return self.repo.get_by_id(of_id)

    def update_orden_fabricacion(self, of_id: int, update_data: Dict[str, Any]) -> OrdenFabricacion:
        """
        Update orden de fabricacion with validation and audit logging

        Args:
            of_id: OF ID to update
            update_data: Dictionary with fields to update

        Returns:
            Updated OrdenFabricacion instance
        """
        try:
            of = self.repo.get_by_id(of_id)
            if not of:
                raise ValueError(f"OF {of_id} no encontrada")

            # Store original data for audit
            datos_anteriores = serialize_model(of)

            # Validate proyecto if updating proyecto_id
            if 'proyecto_id' in update_data and update_data['proyecto_id'] != of.proyecto_id:
                proyecto = self.proyectos_repo.get_by_id(update_data['proyecto_id'])
                if not proyecto:
                    raise ValueError(f"Proyecto {update_data['proyecto_id']} no encontrado")

            # Validate contrato if updating contrato_id
            if 'contrato_id' in update_data:
                if update_data['contrato_id'] and update_data['contrato_id'] != of.contrato_id:
                    contrato = self.contratos_repo.get_by_id(update_data['contrato_id'])
                    if not contrato:
                        raise ValueError(f"Contrato {update_data['contrato_id']} no encontrado")

                    proyecto_id = update_data.get('proyecto_id', of.proyecto_id)
                    if contrato.proyecto_id != proyecto_id:
                        raise ValueError("El contrato no pertenece al proyecto especificado")

            # Remove codigo from update data - codes are auto-generated and not editable
            update_data.pop('codigo', None)

            # Update OF
            of_actualizada = self.repo.update(of, update_data)

            # Commit transaction
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'ordenes_fabricacion', 
                of_id, 
                'UPDATE',
                datos_anteriores=datos_anteriores,
                datos_nuevos=serialize_model(of_actualizada)
            )

            logger.info(f"OF actualizada: {of_id} - {of_actualizada.codigo}")
            return of_actualizada

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error actualizando OF {of_id}: {str(e)}")
            raise

    def change_estado_area(self, of_id: int, nuevo_estado_id: int, responsable_id: str = None, notas: str = None) -> bool:
        """
        Change estado within the same area using AreasService

        Args:
            of_id: OF ID
            nuevo_estado_id: New estado ID within the same area
            responsable_id: Optional responsible user ID
            notas: Optional notes for the status change

        Returns:
            True if status change was successful
        """
        try:
            of = self.repo.get_by_id(of_id)
            if not of:
                raise ValueError(f"OF {of_id} no encontrada")

            # Use AreasService to change estado
            self.areas_service.change_estado_in_area(
                of_id, 
                nuevo_estado_id, 
                responsable_id=responsable_id, 
                notas=notas
            )

            logger.info(f"Estado de OF cambiado: {of_id} -> estado_id {nuevo_estado_id}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cambiando estado de OF {of_id}: {str(e)}")
            raise

    def advance_to_next_area(self, of_id: int, created_by: str, responsable_id: str = None, notas: str = None) -> bool:
        """
        Advance OF to next area in the workflow

        Args:
            of_id: OF ID
            created_by: User ID who is advancing the OF
            responsable_id: Optional responsible user ID for the new area
            notas: Optional notes

        Returns:
            True if advance was successful
        """
        try:
            of = self.repo.get_by_id(of_id)
            if not of:
                raise ValueError(f"OF {of_id} no encontrada")

            # Use AreasService to advance to next area
            self.areas_service.advance_to_next_area(
                of_id,
                created_by,
                responsable_id=responsable_id,
                notas=notas
            )

            logger.info(f"OF {of_id} avanzada a siguiente área")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error avanzando OF {of_id} a siguiente área: {str(e)}")
            raise

    def delete_orden_fabricacion(self, of_id: int) -> bool:
        """
        Delete orden de fabricacion with cascade validation

        Args:
            of_id: OF ID to delete

        Returns:
            True if deletion was successful
        """
        try:
            of = self.repo.get_by_id(of_id)
            if not of:
                raise ValueError(f"OF {of_id} no encontrada")

            # Check if OF can be deleted (business rules)
            # Check if OF has advanced beyond initial state
            progreso = of.area_progreso_actual
            if progreso:
                # Can only delete if in initial area (Pendientes) and initial state
                if progreso.area.tipo.value != 'PENDIENTES_FABRICACION' or not progreso.estado.es_inicial:
                    raise ValueError("No se puede eliminar una OF que ha avanzado en el proceso de fabricación")

            # Check if OF has related despachos
            if of.despachos:
                raise ValueError("No se puede eliminar la OF porque tiene despachos asociados")

            # Store original data for audit
            datos_anteriores = serialize_model(of)

            # Delete items first
            self.items_repo.delete_by_of(of_id)

            # Delete OF
            success = self.repo.delete(of)

            if success:
                # Commit transaction
                db.session.commit()

                # Log audit
                AuditService.log_action(
                    'ordenes_fabricacion', 
                    of_id, 
                    'DELETE',
                    datos_anteriores=datos_anteriores
                )

                logger.info(f"OF eliminada: {of_id} - {of.codigo}")
                return True

            return False

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error eliminando OF {of_id}: {str(e)}")
            raise

    def search_ordenes_fabricacion(self, filters: OrdenFabricacionSearchFilters) -> tuple[List[OrdenFabricacion], int]:
        """
        Search OFs with filters and pagination

        Args:
            filters: Search filters

        Returns:
            Tuple of (ofs_list, total_count)
        """
        try:
            return self.repo.search(filters)
        except Exception as e:
            logger.error(f"Error buscando OFs: {str(e)}")
            raise

    def get_ordenes_by_proyecto(self, proyecto_id: int) -> List[OrdenFabricacion]:
        """Get all OFs for a proyecto"""
        try:
            return self.repo.get_by_proyecto(proyecto_id)
        except Exception as e:
            logger.error(f"Error obteniendo OFs del proyecto {proyecto_id}: {str(e)}")
            raise

    def smart_advance_orden(self, of_id: int, created_by: str, responsable_id: str = None, notas: str = None) -> tuple[bool, str]:
        """
        Smart advance function that determines whether to advance state within area or move to next area

        Args:
            of_id: OF ID
            created_by: User ID who is advancing the OF
            responsable_id: Optional responsible user ID
            notas: Optional notes

        Returns:
            Tuple of (success, message)
        """
        try:
            of = self.repo.get_by_id(of_id)
            if not of:
                return False, f"OF {of_id} no encontrada"

            # Get current progress
            from repositories.areas_repository import OrdenAreaProgresoRepository
            progreso_repo = OrdenAreaProgresoRepository()
            current_progress = progreso_repo.get_current_progress(of_id)

            if not current_progress:
                return False, "Orden no encontrada en sistema de áreas"

            # Check if current state is final for the area
            if current_progress.estado.es_final:
                # Current state is final, advance to next area
                try:
                    self.areas_service.advance_to_next_area(
                        of_id,
                        created_by,
                        responsable_id=responsable_id,
                        notas=notas
                    )
                    return True, f"Orden avanzada a la siguiente área exitosamente"
                except ValueError as e:
                    if "No hay siguiente área" in str(e):
                        return False, "La orden ya está en el área final del proceso"
                    return False, str(e)
            else:
                # Current state is not final, advance to next state within area
                from repositories.areas_repository import AreasRepository
                areas_repo = AreasRepository()
                estados_area = areas_repo.get_estados_by_area(current_progress.area_id)

                # Find next state in sequence
                current_orden = current_progress.estado.orden_en_area
                next_estado = next(
                    (e for e in estados_area if e.orden_en_area == current_orden + 1),
                    None
                )

                if not next_estado:
                    return False, "No hay siguiente estado en el área actual"

                self.areas_service.change_estado_in_area(
                    of_id, 
                    next_estado.id, 
                    responsable_id=responsable_id, 
                    notas=notas
                )
                return True, f"Estado actualizado a '{next_estado.nombre}' exitosamente"

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error en avance inteligente de OF {of_id}: {str(e)}")
            return False, str(e)

    def get_pending_ofs_by_user(self, user_id: str, limit: int = 10) -> List[OrdenFabricacion]:
        """Get pending OFs assigned to a user"""
        try:
            return self.repo.get_pending_by_user(user_id, limit)
        except Exception as e:
            logger.error(f"Error obteniendo OFs pendientes del usuario {user_id}: {str(e)}")
            raise