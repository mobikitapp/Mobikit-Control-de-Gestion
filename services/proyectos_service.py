from typing import List, Optional, Dict, Any
from app import db
from repositories.proyectos_repo import ProyectosRepository
from repositories.clientes_repo import ClientesRepository
from services.audit_service import AuditService, serialize_model
from schemas.proyectos import ProyectoSearchFilters
from models import Proyecto
import logging

logger = logging.getLogger(__name__)

class ProyectosService:
    """Service layer for Proyecto operations"""

    def __init__(self):
        self.repo = ProyectosRepository()
        self.clientes_repo = ClientesRepository()

    def create_proyecto(self, proyecto_data: Dict[str, Any], created_by: str) -> Proyecto:
        """
        Create a new proyecto with validation and audit logging

        Args:
            proyecto_data: Proyecto data dictionary
            created_by: User ID who is creating the proyecto

        Returns:
            Created Proyecto instance
        """
        try:
            # Validate cliente exists and is active
            cliente = self.clientes_repo.get_by_id(proyecto_data['cliente_id'])
            if not cliente:
                raise ValueError(f"Cliente {proyecto_data['cliente_id']} no encontrado")
            if not cliente.activo:
                raise ValueError(f"Cliente {cliente.nombre} está inactivo")

            # Create proyecto
            proyecto = self.repo.create(proyecto_data, created_by)

            # Create automatic vendor task if vendor is assigned
            self._crear_tarea_vendedor_automatica(proyecto, created_by)

            # Commit transaction
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'proyectos', 
                proyecto.id, 
                'CREATE', 
                datos_nuevos=serialize_model(proyecto)
            )

            logger.info(f"Proyecto creado: {proyecto.id} - {proyecto.nombre}")
            return proyecto

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando proyecto: {str(e)}")
            raise

    def _crear_tarea_vendedor_automatica(self, proyecto, created_by: str):
        """Create automatic vendor task when project is created"""
        if not proyecto.vendedor_id:
            return

        # Import here to avoid circular imports
        from models import TareaComercial

        # Check if task already exists
        existing = (db.session.query(TareaComercial)
                   .filter_by(proyecto_id=proyecto.id, 
                             titulo="Completar información de presupuesto")
                   .filter_by(completada=False)
                   .first())

        if not existing:
            tarea = TareaComercial()
            tarea.proyecto_id = proyecto.id
            tarea.vendedor_id = proyecto.vendedor_id
            tarea.titulo = "Completar información de presupuesto"
            tarea.descripcion = "Completar monto de provisión presupuestado, margen de venta provisión, monto de instalación presupuestado y margen de venta instalación para el proyecto"
            tarea.created_by = created_by
            tarea.completada = False
            db.session.add(tarea)
            logger.info(f"Tarea automática creada para vendedor {proyecto.vendedor_id} en proyecto {proyecto.id}")

    def get_proyecto_by_id(self, proyecto_id: int) -> Optional[Proyecto]:
        """Get proyecto by ID with related data"""
        return self.repo.get_by_id(proyecto_id)

    def get_proyecto_with_stats(self, proyecto_id: int) -> Optional[Dict[str, Any]]:
        """Get proyecto with additional statistics"""
        try:
            proyecto = self.repo.get_by_id(proyecto_id)
            if not proyecto:
                return None

            # Calculate additional statistics with error handling
            stats = {
                'total_contratos': len(proyecto.contratos) if proyecto.contratos else 0,
                'total_ordenes_fabricacion': len(proyecto.ordenes_fabricacion) if proyecto.ordenes_fabricacion else 0,
                'total_despachos': len(proyecto.despachos) if proyecto.despachos else 0,
                'ordenes_por_estado': self._get_ordenes_por_estado(proyecto.ordenes_fabricacion),
                'progreso_fabricacion': self._calcular_progreso_fabricacion(proyecto.ordenes_fabricacion)
            }

            return {
                'proyecto': proyecto,
                'stats': stats
            }
        except Exception as e:
            logger.error(f"Error calculating stats for proyecto {proyecto_id}: {str(e)}")
            # Return basic proyecto data without stats if there's an error
            proyecto = self.repo.get_by_id(proyecto_id)
            return {
                'proyecto': proyecto,
                'stats': {
                    'total_contratos': 0,
                    'total_ordenes_fabricacion': 0,
                    'total_despachos': 0,
                    'ordenes_por_estado': {},
                    'progreso_fabricacion': 0
                }
            } if proyecto else None

    def update_proyecto(self, proyecto_id: int, update_data: Dict[str, Any]) -> Proyecto:
        """
        Update proyecto with validation and audit logging

        Args:
            proyecto_id: Proyecto ID to update
            update_data: Dictionary with fields to update

        Returns:
            Updated Proyecto instance
        """
        try:
            proyecto = self.repo.get_by_id(proyecto_id)
            if not proyecto:
                raise ValueError(f"Proyecto {proyecto_id} no encontrado")

            # Store original data for audit
            datos_anteriores = serialize_model(proyecto)

            # Validate cliente if updating cliente_id
            if 'cliente_id' in update_data and update_data['cliente_id'] != proyecto.cliente_id:
                cliente = self.clientes_repo.get_by_id(update_data['cliente_id'])
                if not cliente:
                    raise ValueError(f"Cliente {update_data['cliente_id']} no encontrado")
                if not cliente.activo:
                    raise ValueError(f"Cliente {cliente.nombre} está inactivo")

            # Update proyecto
            proyecto_actualizado = self.repo.update(proyecto, update_data)

            # Commit transaction
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'proyectos', 
                proyecto_id, 
                'UPDATE',
                datos_anteriores=datos_anteriores,
                datos_nuevos=serialize_model(proyecto_actualizado)
            )

            logger.info(f"Proyecto actualizado: {proyecto_id} - {proyecto_actualizado.nombre}")
            return proyecto_actualizado

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error actualizando proyecto {proyecto_id}: {str(e)}")
            raise

    def delete_proyecto(self, proyecto_id: int) -> bool:
        """
        Delete proyecto with cascade validation

        Args:
            proyecto_id: Proyecto ID to delete

        Returns:
            True if deletion was successful
        """
        try:
            proyecto = self.repo.get_by_id(proyecto_id)
            if not proyecto:
                raise ValueError(f"Proyecto {proyecto_id} no encontrado")

            # Check if proyecto has related records
            if proyecto.contratos:
                raise ValueError("No se puede eliminar el proyecto porque tiene contratos asociados")
            if proyecto.ordenes_fabricacion:
                raise ValueError("No se puede eliminar el proyecto porque tiene órdenes de fabricación asociadas")
            if proyecto.despachos:
                raise ValueError("No se puede eliminar el proyecto porque tiene despachos asociados")

            # Store original data for audit
            datos_anteriores = serialize_model(proyecto)

            # Delete proyecto
            success = self.repo.delete(proyecto)

            if success:
                # Commit transaction
                db.session.commit()

                # Log audit
                AuditService.log_action(
                    'proyectos', 
                    proyecto_id, 
                    'DELETE',
                    datos_anteriores=datos_anteriores
                )

                logger.info(f"Proyecto eliminado: {proyecto_id} - {proyecto.nombre}")
                return True

            return False

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error eliminando proyecto {proyecto_id}: {str(e)}")
            raise

    def search_proyectos(self, filters: ProyectoSearchFilters) -> tuple[List[Proyecto], int]:
        """
        Search proyectos with filters and pagination

        Args:
            filters: Search filters

        Returns:
            Tuple of (proyectos_list, total_count)
        """
        try:
            return self.repo.search(filters)
        except Exception as e:
            logger.error(f"Error buscando proyectos: {str(e)}")
            raise

    def get_proyectos_by_cliente(self, cliente_id: int) -> List[Proyecto]:
        """Get all proyectos for a cliente"""
        try:
            return self.repo.get_by_cliente(cliente_id)
        except Exception as e:
            logger.error(f"Error obteniendo proyectos del cliente {cliente_id}: {str(e)}")
            raise

    def count_proyectos_by_status(self, status_list: List[str]) -> int:
        """Count proyectos by status"""
        try:
            return self.repo.count_by_status(status_list)
        except Exception as e:
            logger.error(f"Error contando proyectos por estado: {str(e)}")
            raise

    def get_recent_proyectos(self, limit: int = 10) -> List[Proyecto]:
        """Get recently created proyectos"""
        try:
            return self.repo.get_recent(limit)
        except Exception as e:
            logger.error(f"Error obteniendo proyectos recientes: {str(e)}")
            raise

    def get_proyectos_by_responsable(self, responsable_id: str) -> List[Proyecto]:
        """Get proyectos assigned to a responsable"""
        try:
            return self.repo.get_by_responsable(responsable_id)
        except Exception as e:
            logger.error(f"Error obteniendo proyectos del responsable {responsable_id}: {str(e)}")
            raise

    def get_active_proyectos(self) -> List[Proyecto]:
        """Get all active proyectos"""
        try:
            return self.repo.get_active()
        except Exception as e:
            logger.error(f"Error obteniendo proyectos activos: {str(e)}")
            raise

    def _get_ordenes_por_estado(self, ordenes):
        """Group ordenes by their current estado"""
        estados = {}
        try:
            for orden in ordenes:
                try:
                    estado_actual = orden.estado_actual
                    estado_key = estado_actual.nombre if estado_actual else 'Sin estado'
                    estados[estado_key] = estados.get(estado_key, 0) + 1
                except Exception:
                    # If there's an error accessing estado, count as 'Sin estado'
                    estados['Sin estado'] = estados.get('Sin estado', 0) + 1
        except Exception:
            pass
        return estados

    def _calcular_progreso_fabricacion(self, ordenes):
        """Calculate overall fabrication progress"""
        try:
            if not ordenes:
                return 0

            # Count ordenes in final states vs total
            ordenes_completadas = 0
            for orden in ordenes:
                try:
                    estado_actual = orden.estado_actual
                    if estado_actual and hasattr(estado_actual, 'es_final') and estado_actual.es_final:
                        ordenes_completadas += 1
                except Exception:
                    # If error accessing estado, don't count as completed
                    pass

            return round((ordenes_completadas / len(ordenes)) * 100, 1) if ordenes else 0
        except Exception:
            return 0