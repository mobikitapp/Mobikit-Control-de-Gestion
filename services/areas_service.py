from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, date
import logging

from app import db
from models import (
    OrdenFabricacion, OrdenAreaProgreso, Area, AreaEstado, 
    TipoArea, EstadoOF, User, Proyecto, EstadoBodega
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
        Incluye validación especial para avance desde Bodega a Despacho
        """
        try:

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

            # VALIDACIÓN ESPECIAL: Avance desde BODEGA a DESPACHO
            if (current_area.tipo == TipoArea.BODEGA and 
                siguiente_area.tipo == TipoArea.DESPACHO):

                # Verificar que la OF está en estado 'programado_para_despacho'
                if current_progress.estado.codigo != EstadoBodega.PROGRAMADO_PARA_DESPACHO.value:
                    raise ValueError(
                        f"OF {orden_fabricacion_id} debe estar en estado 'programado_para_despacho' "
                        f"para avanzar a Despacho. Estado actual: {current_progress.estado.nombre}"
                    )

                # Verificar que la OF tiene un despacho asignado
                from models import DespachoOrdenFabricacion
                despacho_asignado = db.session.query(DespachoOrdenFabricacion).filter_by(
                    orden_fabricacion_id=orden_fabricacion_id
                ).first()

                if not despacho_asignado:
                    raise ValueError(
                        f"OF {orden_fabricacion_id} debe estar asignada a un despacho "
                        f"para avanzar al área de Despacho"
                    )

                logger.info(
                    f"Validación Bodega→Despacho exitosa para OF {orden_fabricacion_id}: "
                    f"Estado '{current_progress.estado.codigo}', "
                    f"Despacho {despacho_asignado.despacho_id}"
                )

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

    def add_nuevo_estado_bodega(self) -> bool:
        """
        Agrega el nuevo estado 'programado_para_despacho' al área de Bodega
        y actualiza el estado existente para que no sea final
        """
        try:
            # Obtener área de Bodega
            area_bodega = self.areas_repo.get_area_by_tipo(TipoArea.BODEGA)
            if not area_bodega:
                raise ValueError("Área de Bodega no encontrada")

            # Verificar si el estado ya existe
            estado_existente = db.session.query(AreaEstado).filter_by(
                area_id=area_bodega.id,
                codigo=EstadoBodega.PROGRAMADO_PARA_DESPACHO.value
            ).first()

            if estado_existente:
                logger.info("Estado 'programado_para_despacho' ya existe en Bodega")
                return True

            # Actualizar estado existente para que no sea final
            estado_listo = db.session.query(AreaEstado).filter_by(
                area_id=area_bodega.id,
                codigo=EstadoBodega.LISTO_PARA_DESPACHO.value
            ).first()

            if estado_listo:
                estado_listo.es_final = False

            # Crear nuevo estado
            nuevo_estado = AreaEstado(
                area_id=area_bodega.id,
                codigo=EstadoBodega.PROGRAMADO_PARA_DESPACHO.value,
                nombre='Programado para Despacho',
                descripcion='OF asignada a un despacho programado',
                orden_en_area=2,
                es_inicial=False,
                es_final=True,
                activo=True,
                color_hex='#fd7e14'  # Color naranja para diferenciar
            )

            db.session.add(nuevo_estado)
            db.session.commit()

            logger.info("Estado 'programado_para_despacho' agregado exitosamente al área de Bodega")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error agregando nuevo estado a Bodega: {str(e)}")
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
                                'glosa': o.orden_fabricacion.glosa,
                                'contrato_id': o.orden_fabricacion.contrato_id,
                                'proxima_entrega_contrato': self._get_proxima_entrega_contrato(o.orden_fabricacion),
                                'fecha_entrega_fabrica': o.orden_fabricacion.fecha_entrega_fabrica,
                                'fecha_entrega_embalaje': o.orden_fabricacion.fecha_entrega_embalaje,
                                'fecha_entrega_dinamica': self.get_dynamic_delivery_date(o.orden_fabricacion),
                                'fecha_entrega_embalaje': o.orden_fabricacion.fecha_entrega_embalaje,
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

    def _get_proxima_entrega_contrato(self, orden_fabricacion) -> Optional[date]:
        """
        Get the next delivery date from the contract/OC
        """
        try:
            if not orden_fabricacion.contrato:
                return None

            # Get the contract's plan de entrega
            if orden_fabricacion.contrato.plan_entrega:
                # Get next pending delivery milestone
                from models import HitoEntrega, EstadoHitoEntrega
                from datetime import date

                next_hito = (db.session.query(HitoEntrega)
                           .filter_by(plan_entrega_id=orden_fabricacion.contrato.plan_entrega.id)
                           .filter(HitoEntrega.estado == EstadoHitoEntrega.PENDIENTE)
                           .filter(HitoEntrega.fecha_programada >= date.today())
                           .order_by(HitoEntrega.fecha_programada.asc())
                           .first())

                if next_hito:
                    return next_hito.fecha_programada

            # Fallback to contract delivery date
            return orden_fabricacion.contrato.fecha_entrega_comprometida

        except Exception as e:
            logger.error(f"Error getting next delivery date: {str(e)}")
            return None

    def get_dynamic_delivery_date(self, orden_fabricacion) -> Optional[date]:
        """
        Get the appropriate delivery date based on the current area of the order
        """
        try:
            # Get current area
            current_progress = orden_fabricacion.area_progreso_actual
            if not current_progress or not current_progress.area:
                return None

            area_tipo = current_progress.area.tipo.value

            if area_tipo == 'fabrica':
                # In factory area, show factory delivery date
                return orden_fabricacion.fecha_entrega_fabrica
            elif area_tipo == 'embalaje':
                # In packaging area, show packaging delivery date
                return orden_fabricacion.fecha_entrega_embalaje
            elif area_tipo in ['bodega', 'despacho']:
                # In warehouse/dispatch areas, show contract delivery date
                return self._get_proxima_entrega_contrato(orden_fabricacion)
            else:
                # For other areas (pendientes), show factory delivery date as fallback
                return orden_fabricacion.fecha_entrega_fabrica

        except Exception as e:
            logger.error(f"Error getting dynamic delivery date: {str(e)}")
            return None

    def get_next_area_in_sequence(self, current_area_id: int) -> Optional[Area]:
        """Get the next area in the production sequence"""
        try:
            current_area = self.areas_repo.get_by_id(current_area_id)
            if not current_area:
                return None

            next_area = (db.session.query(Area)
                        .filter(Area.orden_secuencia == current_area.orden_secuencia + 1)
                        .filter(Area.activo == True)
                        .first())

            return next_area
        except Exception as e:
            logger.error(f"Error getting next area: {str(e)}")
            return None

    def get_next_action_description(self, of_id: int) -> str:
        """Get description of next action for an OF based on current state"""
        try:
            current_progress = self.progreso_repo.get_current_progress(of_id)
            if not current_progress:
                return "Iniciar Proceso"

            current_estado = current_progress.estado
            current_area = current_progress.area

            # If current state is final for the area, next action is to advance to next area
            if current_estado.es_final:
                next_area = self.get_next_area_in_sequence(current_area.id)
                if next_area:
                    if next_area.tipo.value == 'fabrica':
                        return "Enviar a Fabricación"
                    elif next_area.tipo.value == 'embalaje':
                        return "Enviar a Embalaje"
                    elif next_area.tipo.value == 'bodega':
                        return "Enviar a Bodega"
                    elif next_area.tipo.value == 'despacho':
                        return "Marcar como Despachado"
                    else:
                        return f"Avanzar a {next_area.nombre}"
                else:
                    return "Proceso Completo"
            else:
                # Next action is to advance state within current area
                estados_area = self.areas_repo.get_estados_by_area(current_area.id)
                next_estado = next(
                    (e for e in estados_area if e.orden_en_area == current_estado.orden_en_area + 1),
                    None
                )

                if next_estado:
                    # Custom action descriptions based on state transitions
                    action_map = {
                        'pendiente_aprobacion_diseño': 'Aprobar Diseño',
                        'aprobado': 'Enviar a Fabricación',
                        'enviado_a_fabricacion': 'Iniciar Seccionado',
                        'seccionando': 'Iniciar Enchapado',
                        'enchapando': 'Iniciar Mecanizado',
                        'mecanizando': 'Completar Fabricación',
                        'fabricacion_completa': 'Enviar a Embalaje',
                        'pendiente_de_embalar': 'Iniciar Embalaje',
                        'embalando': 'Completar Embalaje',
                        'embalaje_listo': 'Enviar a Bodega',
                        'listo_para_despacho': 'Despachar'
                    }

                    return action_map.get(current_estado.codigo, f"Cambiar a {next_estado.nombre}")
                else:
                    return "Sin acción disponible"

        except Exception as e:
            logger.error(f"Error getting next action description for OF {of_id}: {str(e)}")
            return "Avanzar"