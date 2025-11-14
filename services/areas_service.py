from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta, date
import logging
from sqlalchemy.orm import joinedload

from app import db
from models import (
    OrdenFabricacion, OrdenAreaProgreso, Area, AreaEstado, 
    TipoArea, EstadoOF, User, Proyecto, EstadoBodega
)
from repositories.areas_repository import AreasRepository, OrdenAreaProgresoRepository
from services.audit_service import AuditService
from services.audit_service import serialize_model
from constants.transitions import OF_SPECIAL_VALIDATIONS

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

    def _calcular_tiempo_en_area(self, progreso: 'OrdenAreaProgreso') -> float:
        """
        Calcula el tiempo total que una OF pasó en un área específica (en horas)
        """
        try:
            if not progreso.fecha_ingreso_area:
                return 0.0
            
            ahora = datetime.now()
            tiempo_transcurrido = ahora - progreso.fecha_ingreso_area
            
            # Convertir a horas (incluyendo decimales)
            horas_totales = tiempo_transcurrido.total_seconds() / 3600
            
            # Redondear a 2 decimales
            return round(horas_totales, 2)
            
        except Exception as e:
            logger.error(f"Error calculando tiempo en área: {str(e)}")
            return 0.0

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

            # Check if the target state requires special validations (e.g., cantidad_tableros for SECCIONANDO)
            if nuevo_estado.codigo in OF_SPECIAL_VALIDATIONS:
                validations = OF_SPECIAL_VALIDATIONS[nuevo_estado.codigo]
                if "required_fields" in validations:
                    # Get the OF to check required fields
                    from repositories.fabricacion_repo import FabricacionRepository
                    fabricacion_repo = FabricacionRepository()
                    of = fabricacion_repo.get_by_id(orden_fabricacion_id)
                    
                    if not of:
                        raise ValueError(f"Orden de fabricación {orden_fabricacion_id} no encontrada")
                    
                    # Check each required field
                    for field in validations["required_fields"]:
                        field_value = getattr(of, field, None)
                        if field_value is None or (isinstance(field_value, (int, float)) and field_value <= 0):
                            validation_message = validations.get("validation_message", f"El campo {field} es obligatorio")
                            raise ValueError(validation_message)

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
            
            # Send notification
            try:
                from services.notification_service import notification_service
                from models import User
                user = db.session.get(User, responsable_id) if responsable_id else None
                if user:
                    area = db.session.get(Area, updated_progress.area_id)
                    area_nombre = area.nombre if area else "Área desconocida"
                    notification_service.notify_of_status_change(
                        orden_fabricacion_id, nuevo_estado.nombre, area_nombre, user
                    )
            except Exception as e:
                logger.warning(f"Error enviando notificación de cambio de estado: {str(e)}")
            
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

            # This validation should only apply for direct calls to advance_to_next_area
            # For smart_advance, this logic is handled there
            if not current_progress.estado.es_final:
                raise ValueError(f"La orden debe completar el estado final del área actual antes de avanzar área. Use smart_advance para avance automático.")

            # Get next area by orden_secuencia
            current_area = current_progress.area
            next_orden_secuencia = current_area.orden_secuencia + 1
            from models import Area
            next_area = db.session.query(Area).filter_by(orden_secuencia=next_orden_secuencia).first()

            if not next_area:
                raise ValueError("No hay siguiente área en la secuencia")

            # VALIDACIÓN ESPECIAL: Avance AUTOMÁTICO desde BODEGA a DESPACHO
            # Solo aplica cuando la OF está en estado PROGRAMADO_PARA_DESPACHO
            # Para avances manuales normales, no aplicar esta validación estricta
            if (current_area.tipo == TipoArea.BODEGA and 
                next_area.tipo == TipoArea.DESPACHO and
                current_progress.estado.codigo == EstadoBodega.PROGRAMADO_PARA_DESPACHO.value):

                # Para OFs en estado PROGRAMADO_PARA_DESPACHO, verificar que tienen despacho asignado
                from models import DespachoOrdenFabricacion
                despacho_asignado = db.session.query(DespachoOrdenFabricacion).filter_by(
                    orden_fabricacion_id=orden_fabricacion_id
                ).first()

                if not despacho_asignado:
                    raise ValueError(
                        f"OF {orden_fabricacion_id} debe estar asignada a un despacho "
                        f"para avanzar al área de Despacho desde estado programado"
                    )

                logger.info(
                    f"Validación Bodega→Despacho (programado) exitosa para OF {orden_fabricacion_id}: "
                    f"Despacho {despacho_asignado.despacho_id}"
                )

            # Get initial state for next area
            estado_inicial = self.areas_repo.get_estado_inicial(next_area.id)
            if not estado_inicial:
                raise ValueError(f"Estado inicial no encontrado para área {next_area.nombre}")

            # Mark current progress as not current (for history)
            current_progress.es_actual = False
            # TODO: Agregar tiempo_total_area_horas cuando la base de datos esté sincronizada

            # Create new progress record for next area
            now = datetime.now()
            new_progress_data = {
                'orden_fabricacion_id': orden_fabricacion_id,
                'area_id': next_area.id,
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

            logger.info(f"Orden {orden_fabricacion_id} avanzada a área {next_area.nombre}")
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
                        'orders': sorted([
                            {
                                'id': o.orden_fabricacion.id,
                                'codigo': o.orden_fabricacion.codigo,
                                'proyecto_nombre': o.orden_fabricacion.proyecto.nombre,
                                'cliente_nombre': o.orden_fabricacion.proyecto.cliente.nombre,
                                'glosa': o.orden_fabricacion.glosa or 'Sin glosa especificada',
                                'contrato_id': o.orden_fabricacion.contrato_id,
                                'proxima_entrega_contrato': self._get_proxima_entrega_contrato(o.orden_fabricacion),
                                'fecha_entrega_fabrica': o.orden_fabricacion.fecha_entrega_fabrica,
                                'fecha_entrega_embalaje': o.orden_fabricacion.fecha_entrega_embalaje,
                                'fecha_entrega_dinamica': self.get_dynamic_delivery_date(o.orden_fabricacion),
                                'fecha_ingreso_area': o.fecha_ingreso_area,
                                'fecha_cambio_estado': o.fecha_cambio_estado,
                                'tiempo_estimado_horas': float(o.tiempo_estimado_horas) if o.tiempo_estimado_horas else None,
                                'responsable_nombre': o.responsable_user.nombre_completo if o.responsable_user else None,
                                'next_action_description': self.get_next_action_description(o.orden_fabricacion.id),
                                'prioridad': o.orden_fabricacion.prioridad.value if o.orden_fabricacion.prioridad else 'media',
                                'prioridad_numerica': o.orden_fabricacion.prioridad_numerica or 3
                            }
                            for o in orders_in_state
                        ], key=lambda x: (
                            x['prioridad_numerica'],  # First sort by priority (lower number = higher priority)
                            x['fecha_entrega_dinamica'] or datetime(2099, 12, 31).date()  # Then by delivery date (nulls last)
                        ))
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
            current_area = self.areas_repo.get_area_by_id(current_area_id)
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

    def get_current_area_for_order(self, orden_id: int):
        """Get current area for an order"""
        try:
            current_progress = self.progreso_repo.get_current_progress(orden_id)
            if current_progress and current_progress.area:
                return current_progress.area
            return None
        except Exception as e:
            logger.error(f"Error getting current area for order {orden_id}: {str(e)}")
            return None

    def smart_advance_orden(self, orden_fabricacion_id: int, created_by: str, 
                           responsable_id: str = None, notas: str = None) -> OrdenAreaProgreso:
        """
        Intelligent advancement: determines whether to advance state within area 
        or advance to next area based on current state
        """
        try:
            # Get current progress
            current_progress = self.progreso_repo.get_current_progress(orden_fabricacion_id)
            if not current_progress:
                raise ValueError(f"Orden {orden_fabricacion_id} no encontrada en sistema de áreas")

            current_estado = current_progress.estado
            current_area = current_progress.area

            # If current state is final for the area, advance to next area
            if current_estado.es_final:
                logger.info(f"OF {orden_fabricacion_id} en estado final '{current_estado.nombre}' - avanzando a siguiente área")
                return self.advance_to_next_area(
                    orden_fabricacion_id=orden_fabricacion_id,
                    created_by=created_by,
                    responsable_id=responsable_id,
                    notas=notas
                )
            else:
                # Not in final state, advance to next state within same area
                logger.info(f"OF {orden_fabricacion_id} en estado intermedio '{current_estado.nombre}' - avanzando a siguiente estado")
                
                # Find next state in the same area
                next_estado = None
                for estado in current_area.estados:
                    if estado.orden_en_area > current_estado.orden_en_area:
                        if not next_estado or estado.orden_en_area < next_estado.orden_en_area:
                            next_estado = estado

                if not next_estado:
                    raise ValueError(f"No hay siguiente estado disponible en el área {current_area.nombre}")

                # Advance to next state within same area
                return self.change_estado_in_area(
                    orden_fabricacion_id=orden_fabricacion_id,
                    nuevo_estado_id=next_estado.id,
                    responsable_id=responsable_id,
                    notas=notas,
                    tiempo_estimado_horas=None
                )

        except Exception as e:
            logger.error(f"Error en smart advance para orden {orden_fabricacion_id}: {str(e)}")
            raise

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

    def force_change_estado_area(self, orden_fabricacion_id: int, area_id: int, estado_id: int,
                                 created_by: str, responsable_id: str = None, 
                                 notas: str = None) -> OrdenAreaProgreso:
        """
        Force change area and state directly without validating sequential transitions.
        Only for authorized users (admin, general).
        
        Args:
            orden_fabricacion_id: ID of the order
            area_id: Target area ID
            estado_id: Target state ID
            created_by: User ID performing the change
            responsable_id: Optional responsible user ID
            notas: Optional notes explaining the change
            
        Returns:
            Updated or new OrdenAreaProgreso instance
            
        Raises:
            ValueError: If validation fails or state doesn't belong to area
        """
        try:
            # Get current progress
            current_progress = self.progreso_repo.get_current_progress(orden_fabricacion_id)
            if not current_progress:
                raise ValueError(f"Orden {orden_fabricacion_id} no encontrada en sistema de áreas")

            # Get target area and state
            target_area = db.session.get(Area, area_id)
            if not target_area:
                raise ValueError(f"Área {area_id} no encontrada")

            target_estado = db.session.get(AreaEstado, estado_id)
            if not target_estado:
                raise ValueError(f"Estado {estado_id} no encontrado")

            # Validate state belongs to target area
            if target_estado.area_id != target_area.id:
                raise ValueError(f"El estado '{target_estado.nombre}' no pertenece al área '{target_area.nombre}'")

            # Prevent no-op transitions
            if current_progress.area_id == area_id and current_progress.estado_id == estado_id:
                raise ValueError("La orden ya está en el área y estado seleccionados")

            # Apply special validations for target state BEFORE making any changes
            if target_estado.codigo in OF_SPECIAL_VALIDATIONS:
                validations = OF_SPECIAL_VALIDATIONS[target_estado.codigo]
                if "required_fields" in validations:
                    from repositories.fabricacion_repo import FabricacionRepository
                    fabricacion_repo = FabricacionRepository()
                    of = fabricacion_repo.get_by_id(orden_fabricacion_id)
                    
                    if not of:
                        raise ValueError(f"Orden de fabricación {orden_fabricacion_id} no encontrada")
                    
                    for field in validations["required_fields"]:
                        field_value = getattr(of, field, None)
                        if field_value is None or (isinstance(field_value, (int, float)) and field_value <= 0):
                            validation_message = validations.get("validation_message", f"El campo {field} es obligatorio")
                            raise ValueError(validation_message)

            # Store original data for audit
            datos_anteriores = serialize_model(current_progress)

            now = datetime.now()
            is_same_area = current_progress.area_id == area_id

            # Add notes with force change marker
            force_change_note = f"[CAMBIO DIRECTO] Desde {current_progress.area.nombre}/{current_progress.estado.nombre} a {target_area.nombre}/{target_estado.nombre}"
            if notas:
                timestamp = now.strftime('%Y-%m-%d %H:%M')
                full_notes = f"{force_change_note}\n[{timestamp}] {notas}"
            else:
                full_notes = force_change_note

            if is_same_area:
                # Update existing progress record within same area
                update_data = {
                    'estado_id': estado_id,
                    'fecha_cambio_estado': now,
                    'notas_area': full_notes
                }
                
                if responsable_id:
                    update_data['responsable_area'] = responsable_id

                updated_progress = self.progreso_repo.update_progress(current_progress, update_data)
                db.session.commit()

                # Log audit with force change marker
                AuditService.log_action(
                    'orden_area_progreso',
                    updated_progress.id,
                    'FORCE_CHANGE',
                    datos_anteriores=datos_anteriores,
                    datos_nuevos=serialize_model(updated_progress)
                )

                logger.info(
                    f"Cambio directo realizado (misma área) para orden {orden_fabricacion_id}: "
                    f"{current_progress.estado.nombre} -> {target_estado.nombre} por usuario {created_by}"
                )

                # Send notification
                try:
                    from services.notification_service import notification_service
                    from models import User
                    user = db.session.get(User, responsable_id) if responsable_id else None
                    if user:
                        notification_service.notify_of_status_change(
                            orden_fabricacion_id, target_estado.nombre, target_area.nombre, user
                        )
                except Exception as e:
                    logger.warning(f"Error enviando notificación de cambio directo: {str(e)}")

                return updated_progress
            else:
                # Changing to different area - create new progress record
                # Mark current progress as not current
                current_progress.es_actual = False

                # Create new progress record with target area/state
                new_progress_data = {
                    'orden_fabricacion_id': orden_fabricacion_id,
                    'area_id': area_id,
                    'estado_id': estado_id,
                    'fecha_ingreso_area': now,
                    'fecha_cambio_estado': now,
                    'responsable_area': responsable_id if responsable_id else current_progress.responsable_area,
                    'es_actual': True,
                    'created_by': created_by,
                    'notas_area': full_notes
                }

                new_progress = self.progreso_repo.create_progress(new_progress_data)
                db.session.commit()

                # Log audit with force change marker
                AuditService.log_action(
                    'orden_area_progreso',
                    new_progress.id,
                    'FORCE_CHANGE',
                    datos_anteriores=datos_anteriores,
                    datos_nuevos=serialize_model(new_progress)
                )

                logger.info(
                    f"Cambio directo realizado para orden {orden_fabricacion_id}: "
                    f"{current_progress.area.nombre}/{current_progress.estado.nombre} -> "
                    f"{target_area.nombre}/{target_estado.nombre} por usuario {created_by}"
                )

                # Send notification
                try:
                    from services.notification_service import notification_service
                    from models import User
                    user = db.session.get(User, responsable_id) if responsable_id else None
                    if user:
                        notification_service.notify_of_status_change(
                            orden_fabricacion_id, target_estado.nombre, target_area.nombre, user
                        )
                except Exception as e:
                    logger.warning(f"Error enviando notificación de cambio directo: {str(e)}")

                return new_progress

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error en cambio directo para orden {orden_fabricacion_id}: {str(e)}")
            raise

    def get_all_orders_by_delivery_date(self) -> List[Dict[str, Any]]:
        """
        Get all active orders from all areas ordered by delivery date
        """
        try:
            # Get all active orders from all areas
            all_orders = (db.session.query(OrdenAreaProgreso)
                         .options(
                             joinedload(OrdenAreaProgreso.orden_fabricacion)
                             .joinedload(OrdenFabricacion.proyecto)
                             .joinedload(Proyecto.cliente),
                             joinedload(OrdenAreaProgreso.area),
                             joinedload(OrdenAreaProgreso.estado),
                             joinedload(OrdenAreaProgreso.responsable_user)
                         )
                         .filter_by(es_actual=True, archivado=False)
                         .all())

            formatted_orders = []
            for progreso in all_orders:
                of = progreso.orden_fabricacion
                
                # Get dynamic delivery date
                fecha_entrega_dinamica = self.get_dynamic_delivery_date(of)
                
                formatted_order = {
                    'id': of.id,
                    'codigo': of.codigo,
                    'proyecto_nombre': of.proyecto.nombre,
                    'cliente_nombre': of.proyecto.cliente.nombre,
                    'glosa': of.glosa or 'Sin glosa especificada',
                    'contrato_id': of.contrato_id,
                    'fecha_entrega_dinamica': fecha_entrega_dinamica,
                    'fecha_entrega_fabrica': of.fecha_entrega_fabrica,
                    'fecha_entrega_embalaje': of.fecha_entrega_embalaje,
                    'fecha_ingreso_area': progreso.fecha_ingreso_area,
                    'fecha_cambio_estado': progreso.fecha_cambio_estado,
                    'tiempo_estimado_horas': float(progreso.tiempo_estimado_horas) if progreso.tiempo_estimado_horas else None,
                    'responsable_nombre': progreso.responsable_user.nombre_completo if progreso.responsable_user else None,
                    'next_action_description': self.get_next_action_description(of.id),
                    'prioridad': of.prioridad.value if of.prioridad else 'media',
                    'prioridad_numerica': of.prioridad_numerica or 3,
                    'area': {
                        'id': progreso.area.id,
                        'nombre': progreso.area.nombre,
                        'tipo': progreso.area.tipo.value,
                        'color_hex': progreso.area.color_hex,
                        'orden_secuencia': progreso.area.orden_secuencia
                    },
                    'estado': {
                        'id': progreso.estado.id,
                        'nombre': progreso.estado.nombre,
                        'codigo': progreso.estado.codigo,
                        'color_hex': progreso.estado.color_hex,
                        'es_final': progreso.estado.es_final
                    }
                }
                formatted_orders.append(formatted_order)

            # Sort by priority first, then by delivery date
            formatted_orders.sort(key=lambda x: (
                x['prioridad_numerica'],  # Lower number = higher priority
                x['fecha_entrega_dinamica'] or datetime(2099, 12, 31).date()  # Nulls last
            ))

            return formatted_orders

        except Exception as e:
            logger.error(f"Error obteniendo todas las órdenes por fecha de entrega: {str(e)}")
            raise