from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

from app import db
from models import (
    OrdenFabricacion, OrdenAreaProgreso, Area, AreaEstado, 
    TipoArea, EstadoOF, User, Proyecto
)
from repositories.areas_repository import AreasRepository, OrdenAreaProgresoRepository
from services.audit_service import AuditService
from services.audit_service import serialize_model

logger = logging.getLogger(__name__)


class AreasService:
    """Service layer for Areas and OrdenAreaProgreso operations"""

    def __init__(self):
        self.areas_repo = AreasRepository()
        self.progreso_repo = OrdenAreaProgresoRepository()

    def initialize_orden_in_areas(self, orden_fabricacion_id: int, created_by: str) -> OrdenAreaProgreso:
        """
        Initialize a new OrdenFabricacion in the areas system
        Places it in the first area (Pendientes de Fabricación) with initial state
        """
        try:
            # Get the first area (Pendientes de Fabricación)  
            primera_area = self.areas_repo.get_area_by_tipo(TipoArea.PENDIENTES_FABRICACION)
            if not primera_area:
                raise ValueError("Área 'Pendientes de Fabricación' no encontrada")

            # Get initial state for this area
            estado_inicial = self.areas_repo.get_estado_inicial(primera_area.id)
            if not estado_inicial:
                raise ValueError("Estado inicial no encontrado para área 'Pendientes de Fabricación'")

            # Check if already exists
            existing_progress = self.progreso_repo.get_current_progress(orden_fabricacion_id)
            if existing_progress:
                raise ValueError(f"La orden {orden_fabricacion_id} ya está en el sistema de áreas")

            # Create progress record
            now = datetime.now()
            progress_data = {
                'orden_fabricacion_id': orden_fabricacion_id,
                'area_id': primera_area.id,
                'estado_id': estado_inicial.id,
                'fecha_ingreso_area': now,
                'fecha_cambio_estado': now,
                'es_actual': True,
                'created_by': created_by
            }

            progress = self.progreso_repo.create_progress(progress_data)
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'orden_area_progreso', 
                progress.id, 
                'CREATE',
                datos_nuevos=serialize_model(progress)
            )

            logger.info(f"Orden {orden_fabricacion_id} inicializada en sistema de áreas")
            return progress

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error inicializando orden en áreas: {str(e)}")
            raise

    def change_estado_in_area(self, orden_fabricacion_id: int, nuevo_estado_id: int, 
                             responsable_id: str = None, notas: str = None, 
                             tiempo_estimado_horas: float = None) -> OrdenAreaProgreso:
        """
        Change state within the same area
        """
        try:
            # Get current progress
            current_progress = self.progreso_repo.get_current_progress(orden_fabricacion_id)
            if not current_progress:
                raise ValueError(f"Orden {orden_fabricacion_id} no encontrada en sistema de áreas")

            # Get new state
            nuevo_estado = db.session.get(AreaEstado, nuevo_estado_id)
            if not nuevo_estado:
                raise ValueError("Estado no encontrado")

            # Validate state belongs to current area
            if nuevo_estado.area_id != current_progress.area_id:
                raise ValueError("El estado no pertenece al área actual")

            # Store original data for audit
            datos_anteriores = serialize_model(current_progress)

            # Update progress
            update_data = {
                'estado_id': nuevo_estado_id,
                'fecha_cambio_estado': datetime.now()
            }

            if responsable_id:
                update_data['responsable_area'] = responsable_id

            if notas:
                current_notas = current_progress.notas_area or ""
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
                update_data['notas_area'] = f"{current_notas}\n[{timestamp}] {nuevo_estado.nombre}: {notas}".strip()

            if tiempo_estimado_horas is not None:
                update_data['tiempo_estimado_horas'] = tiempo_estimado_horas

            updated_progress = self.progreso_repo.update_progress(current_progress, update_data)
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'orden_area_progreso',
                updated_progress.id,
                'UPDATE',
                datos_anteriores=datos_anteriores,
                datos_nuevos=serialize_model(updated_progress)
            )

            logger.info(f"Estado cambiado para orden {orden_fabricacion_id}: {nuevo_estado.nombre}")
            return updated_progress

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cambiando estado: {str(e)}")
            raise

    def advance_to_next_area(self, orden_fabricacion_id: int, created_by: str, 
                           responsable_id: str = None, notas: str = None) -> OrdenAreaProgreso:
        """
        Advance OrdenFabricacion to next area in sequence
        """
        try:
            # Validate that responsable is provided for area advance
            if not responsable_id or responsable_id.strip() == '':
                raise ValueError("Es obligatorio asignar un responsable para avanzar de área")

            # Get current progress
            current_progress = self.progreso_repo.get_current_progress(orden_fabricacion_id)
            if not current_progress:
                raise ValueError(f"Orden {orden_fabricacion_id} no encontrada en sistema de áreas")

            # Check if current state is final for the area
            if not current_progress.estado.es_final:
                raise ValueError(f"La orden debe completar el estado final del área actual antes de avanzar")

            # Get next area
            current_area = current_progress.area
            siguiente_area = (db.session.query(Area)
                            .filter_by(orden_secuencia=current_area.orden_secuencia + 1, activo=True)
                            .first())

            if not siguiente_area:
                raise ValueError("No hay siguiente área en la secuencia")

            # Get initial state for next area
            estado_inicial = self.areas_repo.get_estado_inicial(siguiente_area.id)
            if not estado_inicial:
                raise ValueError(f"Estado inicial no encontrado para área {siguiente_area.nombre}")

            # Mark current progress as not current (for history)
            current_progress.es_actual = False

            # Create new progress record for next area
            now = datetime.now()
            new_progress_data = {
                'orden_fabricacion_id': orden_fabricacion_id,
                'area_id': siguiente_area.id,
                'estado_id': estado_inicial.id,
                'fecha_ingreso_area': now,
                'fecha_cambio_estado': now,
                'responsable_area': responsable_id if responsable_id else None,
                'notas_area': notas if notas else None,
                'es_actual': True,
                'created_by': created_by
            }

            new_progress = self.progreso_repo.create_progress(new_progress_data)
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'orden_area_progreso',
                new_progress.id,
                'CREATE',
                datos_nuevos=serialize_model(new_progress)
            )

            logger.info(f"Orden {orden_fabricacion_id} avanzada a área {siguiente_area.nombre}")
            return new_progress

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error avanzando a siguiente área: {str(e)}")
            raise

    def archive_dispatch(self, orden_fabricacion_id: int) -> bool:
        """
        Archive a dispatched order (remove from active lists)
        """
        try:
            current_progress = self.progreso_repo.get_current_progress(orden_fabricacion_id)
            if not current_progress:
                raise ValueError(f"Orden {orden_fabricacion_id} no encontrada")

            # Verify it's in dispatch area with dispatched state
            if current_progress.area.tipo != TipoArea.DESPACHO:
                raise ValueError("Solo se pueden archivar órdenes en el área de Despacho")

            # Archive the progress record
            datos_anteriores = serialize_model(current_progress)
            archived_progress = self.progreso_repo.archive_progress(current_progress)
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'orden_area_progreso',
                archived_progress.id,
                'UPDATE',
                datos_anteriores=datos_anteriores,
                datos_nuevos=serialize_model(archived_progress)
            )

            logger.info(f"Orden {orden_fabricacion_id} archivada en despachos")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error archivando despacho: {str(e)}")
            raise

    def get_areas_dashboard_data(self) -> Dict[str, Any]:
        """
        Get comprehensive data for areas dashboard
        """
        try:
            # Get all areas with their orders
            areas = self.areas_repo.get_all_areas()

            # Get stats with fallback
            try:
                stats = self.progreso_repo.get_dashboard_stats()
            except Exception as e:
                logger.error(f"Error getting dashboard stats: {str(e)}")
                stats = {
                    'total_active': 0,
                    'overdue_count': 0,
                    'area_counts': []
                }

            dashboard_data = {
                'areas': [],
                'stats': stats
            }

            for area in areas:
                # Get orders in this area
                orders_in_area = self.progreso_repo.get_orders_in_area(area.id)

                # Group by state
                states_data = []
                for estado in area.estados:
                    orders_in_state = [o for o in orders_in_area if o.estado_id == estado.id]
                    states_data.append({
                        'estado': {
                            'id': estado.id,
                            'nombre': estado.nombre,
                            'codigo': estado.codigo,
                            'color_hex': estado.color_hex,
                            'es_inicial': estado.es_inicial,
                            'es_final': estado.es_final
                        },
                        'count': len(orders_in_state),
                        'orders': [
                            {
                                'id': o.orden_fabricacion.id,
                                'codigo': o.orden_fabricacion.codigo,
                                'proyecto_nombre': o.orden_fabricacion.proyecto.nombre,
                                'cliente_nombre': o.orden_fabricacion.proyecto.cliente.nombre,
                                'responsable_nombre': o.responsable_user.nombre_completo if o.responsable_user else None,
                                'fecha_ingreso_area': o.fecha_ingreso_area,
                                'fecha_cambio_estado': o.fecha_cambio_estado,
                                'tiempo_estimado_horas': float(o.tiempo_estimado_horas) if o.tiempo_estimado_horas else None
                            }
                            for o in orders_in_state
                        ]
                    })

                area_data = {
                    'area': {
                        'id': area.id,
                        'tipo': area.tipo.value,
                        'nombre': area.nombre,
                        'descripcion': area.descripcion,
                        'orden_secuencia': area.orden_secuencia,
                        'color_hex': area.color_hex
                    },
                    'total_count': len(orders_in_area),
                    'estados': states_data
                }

                dashboard_data['areas'].append(area_data)

            return dashboard_data

        except Exception as e:
            logger.error(f"Error obteniendo datos de dashboard: {str(e)}")
            raise

    def get_orden_area_history(self, orden_fabricacion_id: int) -> List[Dict[str, Any]]:
        """
        Get complete area transition history for an order
        """
        try:
            history = self.progreso_repo.get_progress_history(orden_fabricacion_id)

            return [
                {
                    'id': h.id,
                    'area': {
                        'nombre': h.area.nombre,
                        'tipo': h.area.tipo.value,
                        'color_hex': h.area.color_hex
                    },
                    'estado': {
                        'nombre': h.estado.nombre,
                        'codigo': h.estado.codigo,
                        'color_hex': h.estado.color_hex
                    },
                    'fecha_ingreso_area': h.fecha_ingreso_area,
                    'fecha_cambio_estado': h.fecha_cambio_estado,
                    'responsable_nombre': h.responsable_user.nombre_completo if h.responsable_user else None,
                    'tiempo_estimado_horas': float(h.tiempo_estimado_horas) if h.tiempo_estimado_horas else None,
                    'notas_area': h.notas_area,
                    'es_actual': h.es_actual,
                    'archivado': h.archivado,
                    'created_by_nombre': h.creator.nombre_completo if h.creator else None
                }
                for h in history
            ]

        except Exception as e:
            logger.error(f"Error obteniendo historial de áreas: {str(e)}")
            raise

    def get_my_pending_orders(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get orders assigned to a specific user
        """
        try:
            orders = self.progreso_repo.get_orders_by_responsable(user_id)

            return [
                {
                    'orden_fabricacion': {
                        'id': o.orden_fabricacion.id,
                        'codigo': o.orden_fabricacion.codigo,
                        'descripcion': o.orden_fabricacion.descripcion,
                        'proyecto_nombre': o.orden_fabricacion.proyecto.nombre,
                        'cliente_nombre': o.orden_fabricacion.proyecto.cliente.nombre
                    },
                    'area': {
                        'nombre': o.area.nombre,
                        'color_hex': o.area.color_hex
                    },
                    'estado': {
                        'nombre': o.estado.nombre,
                        'codigo': o.estado.codigo,
                        'color_hex': o.estado.color_hex
                    },
                    'fecha_cambio_estado': o.fecha_cambio_estado,
                    'tiempo_estimado_horas': float(o.tiempo_estimado_horas) if o.tiempo_estimado_horas else None,
                    'dias_sin_cambio': (datetime.now() - o.fecha_cambio_estado).days
                }
                for o in orders
            ]

        except Exception as e:
            logger.error(f"Error obteniendo órdenes pendientes del usuario: {str(e)}")
            raise