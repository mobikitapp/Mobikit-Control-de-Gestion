from typing import List, Optional, Dict, Any
from datetime import datetime
from app import db
from repositories.fabricacion_repo import FabricacionRepository, OrdenFabricacionItemRepository
from repositories.proyectos_repo import ProyectosRepository
from repositories.contratos_repo import ContratosRepository
from services.audit_service import AuditService, serialize_model
from services.areas_service import AreasService
from schemas.fabricacion import OrdenFabricacionSearchFilters
from models import (
    OrdenFabricacion, OrdenAreaProgreso, AreaEstado, TipoArea, EstadoBodega, Despacho, 
    DespachoOrdenFabricacion, TipoDespacho, Proyecto
)
from constants.transitions import OF_SPECIAL_VALIDATIONS
import logging

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.proyectos_service import ProyectosService
    from services.contratos_service import ContratosService

logger = logging.getLogger(__name__)

class FabricacionService:
    """Service layer for OrdenFabricacion operations"""

    def __init__(self):
        self.repo = FabricacionRepository()
        self.items_repo = OrdenFabricacionItemRepository()
        self.proyectos_repo = ProyectosRepository()
        self.contratos_repo = ContratosRepository()
        self.areas_service = AreasService()
    
    def get_by_proyecto(self, proyecto_id: int) -> List[OrdenFabricacion]:
        """
        Get all ordenes de fabricacion for a proyecto
        
        Args:
            proyecto_id: ID of the proyecto
            
        Returns:
            List of OrdenFabricacion instances
        """
        try:
            return self.repo.get_by_proyecto_id(proyecto_id)
        except Exception as e:
            logger.error(f"Error getting OFs for proyecto {proyecto_id}: {str(e)}")
            return []

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
            proyecto_id = of_data['proyecto_id']
            proyecto = self.proyectos_repo.get_by_id(proyecto_id)
            if not proyecto:
                raise ValueError(f"Proyecto {proyecto_id} no encontrado")

            # Validate contrato if provided
            contrato_id = of_data.get('contrato_id')
            if contrato_id:
                contrato = self.contratos_repo.get_by_id(contrato_id)
                if not contrato:
                    raise ValueError(f"Contrato {contrato_id} no encontrado")
                if contrato.proyecto_id != proyecto_id:
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
            try:
                # Try to update project status if method exists
                if hasattr(proyectos_service, 'actualizar_estado_automatico'):
                    proyectos_service.actualizar_estado_automatico(proyecto_id, 'en_desarrollo')
                elif hasattr(proyectos_service, 'update_status'):
                    proyectos_service.update_status(proyecto_id, 'EN_DESARROLLO')
            except Exception as e:
                logger.warning(f"Could not auto-update project status: {e}")
                # Continue execution even if status update fails

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
            proyecto_id = update_data.get('proyecto_id', of.proyecto_id)
            if 'proyecto_id' in update_data and update_data['proyecto_id'] != of.proyecto_id:
                proyecto = self.proyectos_repo.get_by_id(update_data['proyecto_id'])
                if not proyecto:
                    raise ValueError(f"Proyecto {update_data['proyecto_id']} no encontrado")

            # Validate contrato if updating contrato_id
            contrato_id = update_data.get('contrato_id')
            if 'contrato_id' in update_data:
                if contrato_id and contrato_id != of.contrato_id:
                    contrato = self.contratos_repo.get_by_id(contrato_id)
                    if not contrato:
                        raise ValueError(f"Contrato {contrato_id} no encontrado")


                    if contrato.proyecto_id != proyecto_id:
                        raise ValueError("El contrato no pertenece al proyecto especificado")

            # Remove codigo from update data - codes are auto-generated and not editable
            update_data.pop('codigo', None)

            # Update OF
            of_actualizada = self.repo.update(of, update_data)

            # Commit transaction
            db.session.commit()

            # Update contract status if contract_id was changed
            if contrato_id and contrato_id != of.contrato_id and contrato_id != 'None':
                from services.contratos_service import ContratosService
                contratos_service = ContratosService()
                try:
                    # Try to update contract status if method exists
                    if hasattr(contratos_service, 'actualizar_estado_automatico'):
                        contratos_service.actualizar_estado_automatico(contrato_id, 'en_desarrollo')
                    elif hasattr(contratos_service, 'update_status'):
                        contratos_service.update_status(contrato_id, 'VIGENTE')
                except Exception as e:
                    logger.warning(f"Could not auto-update contract status: {e}")
                    # Continue execution even if status update fails

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
            ofs_list, total_count = self.repo.search(filters)
            
            # Add next action description to each OF
            for of in ofs_list:
                try:
                    of.next_action_description = self.areas_service.get_next_action_description(of.id)
                except Exception as e:
                    logger.warning(f"Error getting next action for OF {of.id}: {str(e)}")
                    of.next_action_description = "Avanzar"
            
            return ofs_list, total_count
        except Exception as e:
            logger.error(f"Error buscando OFs: {str(e)}")
            raise

    def get_ordenes_by_proyecto(self, proyecto_id: int) -> List[OrdenFabricacion]:
        """Get all ordenes for a proyecto"""
        return self.repo.get_by_proyecto_id(proyecto_id)

    def get_ordenes_by_contrato(self, contrato_id: int) -> List[OrdenFabricacion]:
        """Get all ordenes for a contrato"""
        return self.repo.get_by_contrato_id(contrato_id)

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

                # Check if the target state requires special validations (e.g., cantidad_tableros for SECCIONANDO)
                if next_estado.codigo in OF_SPECIAL_VALIDATIONS:
                    validations = OF_SPECIAL_VALIDATIONS[next_estado.codigo]
                    if "required_fields" in validations:
                        # Check each required field in the OF
                        for field in validations["required_fields"]:
                            field_value = getattr(of, field, None)
                            if field_value is None or (isinstance(field_value, (int, float)) and field_value <= 0):
                                validation_message = validations.get("validation_message", f"El campo {field} es obligatorio")
                                return False, validation_message

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

    def get_ofs_disponibles_para_despacho(self, contrato_id: int) -> List[OrdenFabricacion]:
        """
        Obtiene las OFs de un contrato que están disponibles para despacho
        
        NUEVA LÓGICA DE DISPONIBILIDAD:
        - Mostrar TODAS las OFs del contrato, sin importar área o estado
        - Si OF NO está asignada a ningún despacho: DISPONIBLE
        - Si OF está asignada con tipo TOTAL: NO DISPONIBLE
        - Si OF está asignada con tipo PARCIAL: DISPONIBLE (para despachos adicionales)
        
        Args:
            contrato_id: ID del contrato
            
        Returns:
            Lista de OFs disponibles para despacho (sin duplicados)
        """
        try:
            # Obtener todas las OFs del contrato (sin filtros de área o estado)
            ofs_contrato = self.get_ordenes_by_contrato(contrato_id)
            ofs_disponibles = []
            ofs_processed_ids = set()  # Track processed OF IDs to avoid duplicates
            
            for of in ofs_contrato:
                # Skip if already processed (avoid duplicates)
                if of.id in ofs_processed_ids:
                    continue
                ofs_processed_ids.add(of.id)
                
                # Obtener progreso actual (opcional, para información)
                progreso_actual = db.session.query(OrdenAreaProgreso).filter_by(
                    orden_fabricacion_id=of.id,
                    es_actual=True
                ).first()
                
                # LÓGICA PRINCIPAL: Verificar asignaciones a despachos existentes
                from models import DespachoOrdenFabricacion, TipoDespacho, EstadoDespacho
                
                # Buscar asignaciones existentes de esta OF a despachos
                asignaciones_existentes = db.session.query(DespachoOrdenFabricacion).join(
                    Despacho, DespachoOrdenFabricacion.despacho_id == Despacho.id
                ).filter(
                    DespachoOrdenFabricacion.orden_fabricacion_id == of.id,
                    # Solo considerar despachos no entregados (que aún están activos)
                    Despacho.estado != EstadoDespacho.ENTREGADO
                ).all()
                
                # Determinar si la OF está disponible según las asignaciones
                of_disponible = True
                tiene_despacho_total = False
                tiene_despachos_parciales = False
                
                for asignacion in asignaciones_existentes:
                    if asignacion.tipo_despacho == TipoDespacho.TOTAL:
                        # Si hay un despacho TOTAL activo, la OF no está disponible
                        tiene_despacho_total = True
                        of_disponible = False
                        break
                    elif asignacion.tipo_despacho == TipoDespacho.PARCIAL:
                        # Si tiene despachos parciales, sigue disponible
                        tiene_despachos_parciales = True
                
                if not of_disponible:
                    logger.debug(f"OF {of.codigo} no disponible: asignada a despacho TOTAL activo")
                    continue
                
                # Agregar información del progreso y despachos como atributos temporales
                setattr(of, '_progreso_actual_temp', progreso_actual)
                setattr(of, 'area_actual_nombre', progreso_actual.area.nombre if progreso_actual and progreso_actual.area else "Sin área asignada")
                setattr(of, 'estado_actual_nombre', progreso_actual.estado.nombre if progreso_actual and progreso_actual.estado else "Sin estado")
                setattr(of, 'tiene_despachos_parciales', tiene_despachos_parciales)
                setattr(of, 'tiene_despacho_total', tiene_despacho_total)
                
                # Calcular información de despachos previos (para mostrar en UI)
                cantidad_despachada_total = sum(
                    asignacion.cantidad_despachada 
                    for asignacion in asignaciones_existentes
                ) if asignaciones_existentes else 0
                
                setattr(of, 'cantidad_despachada_previa', cantidad_despachada_total)
                setattr(of, 'cantidad_disponible_despacho', (of.cantidad_tableros or 0) - cantidad_despachada_total)
                
                ofs_disponibles.append(of)
            
            # Sort by codigo for consistent ordering
            ofs_disponibles.sort(key=lambda x: x.codigo)
            
            logger.info(f"Encontradas {len(ofs_disponibles)} OFs únicas disponibles para despacho del contrato {contrato_id}")
            return ofs_disponibles
            
        except Exception as e:
            logger.error(f"Error obteniendo OFs disponibles para despacho del contrato {contrato_id}: {str(e)}")
            return []

    def get_archived_orders(self, page: int = 1, per_page: int = 20, 
                           cliente_id: int = None, proyecto_id: int = None, 
                           codigo: str = None) -> tuple[List[OrdenFabricacion], int]:
        """
        Get archived orders with pagination and filters
        """
        try:
            from models import OrdenFabricacion, OrdenAreaProgreso, Proyecto, Cliente
            from sqlalchemy import and_, desc
            from sqlalchemy.orm import joinedload

            # Base query for archived orders
            query = (db.session.query(OrdenFabricacion)
                    .join(OrdenAreaProgreso, and_(
                        OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                        OrdenAreaProgreso.archivado == True,
                        OrdenAreaProgreso.es_actual == True
                    ))
                    .options(
                        joinedload(OrdenFabricacion.proyecto).joinedload(Proyecto.cliente),
                        joinedload(OrdenFabricacion.contrato),
                        joinedload(OrdenFabricacion.area_progresos)
                    ))

            # Apply filters
            conditions = []

            if cliente_id:
                query = query.join(Proyecto, OrdenFabricacion.proyecto_id == Proyecto.id)
                conditions.append(Proyecto.cliente_id == cliente_id)

            if proyecto_id:
                conditions.append(OrdenFabricacion.proyecto_id == proyecto_id)

            if codigo:
                conditions.append(OrdenFabricacion.codigo.ilike(f"%{codigo}%"))

            if conditions:
                query = query.filter(and_(*conditions))

            # Get total count
            total_count = query.count()

            # Apply pagination and ordering
            orders = (query.order_by(desc(OrdenFabricacion.updated_at))
                     .offset((page - 1) * per_page)
                     .limit(per_page)
                     .all())

            return orders, total_count

        except Exception as e:
            logger.error(f"Error getting archived orders: {str(e)}")
            return [], 0

    def get_despachos_sin_ofs(self) -> List[Despacho]:
        """
        Obtener despachos programados que no tienen órdenes de fabricación asociadas
        
        Returns:
            Lista de despachos sin OFs
        """
        try:
            from models import DespachoOrdenFabricacion, EstadoDespacho
            from sqlalchemy.orm import joinedload
            
            # Buscar despachos que no tienen registros en DespachoOrdenFabricacion
            # y que están en estado PROGRAMADO
            despachos_sin_ofs = (db.session.query(Despacho)
                .outerjoin(DespachoOrdenFabricacion, 
                          DespachoOrdenFabricacion.despacho_id == Despacho.id)
                .filter(DespachoOrdenFabricacion.id.is_(None))  # No tienen OFs asociadas
                .filter(Despacho.estado == EstadoDespacho.PROGRAMADO)  # Solo programados
                .options(
                    joinedload(Despacho.proyecto).joinedload(Proyecto.cliente),
                    joinedload(Despacho.contrato)
                )
                .order_by(Despacho.fecha_programada.asc(), Despacho.created_at.desc())
                .all())
            
            logger.info(f"Encontrados {len(despachos_sin_ofs)} despachos programados sin OFs")
            return despachos_sin_ofs
            
        except Exception as e:
            logger.error(f"Error obteniendo despachos sin OFs: {str(e)}")
            return []

    def create_orden_fabricacion_for_despacho(self, despacho_id: int, created_by: str) -> OrdenFabricacion:
        """
        Crear una orden de fabricación específica para un despacho y vincularlas
        
        Args:
            despacho_id: ID del despacho
            created_by: Usuario que crea la OF
            
        Returns:
            OrdenFabricacion creada
        """
        try:
            # Obtener el despacho
            despacho = db.session.query(Despacho).options(
                joinedload(Despacho.proyecto),
                joinedload(Despacho.contrato)
            ).filter_by(id=despacho_id).first()
            
            if not despacho:
                raise ValueError(f"Despacho {despacho_id} no encontrado")
            
            # Verificar que el despacho no tenga OFs ya asociadas
            from models import DespachoOrdenFabricacion
            existing_ofs = db.session.query(DespachoOrdenFabricacion).filter_by(
                despacho_id=despacho_id
            ).count()
            
            if existing_ofs > 0:
                raise ValueError("El despacho ya tiene órdenes de fabricación asociadas")
            
            # Crear datos de la OF basados en el despacho
            of_data = {
                'proyecto_id': despacho.proyecto_id,
                'contrato_id': despacho.contrato_id,
                'descripcion': f"OF para despacho {despacho.numero_despacho}",
                'glosa': f"Orden generada automáticamente para despacho {despacho.numero_despacho}",
                'fecha_entrega_fabrica': despacho.fecha_programada,
                'fecha_planificada': despacho.fecha_programada,
                'responsable': created_by,
                'notas': f"OF creada desde despacho {despacho.numero_despacho} - {despacho.destino}",
                'cantidad_tableros': 1  # Valor por defecto, se puede editar después
            }
            
            # Crear la OF usando el método existente
            of = self.create_orden_fabricacion(of_data, created_by)
            
            # Crear la vinculación en DespachoOrdenFabricacion
            from models import TipoDespacho
            despacho_of = DespachoOrdenFabricacion(
                despacho_id=despacho_id,
                orden_fabricacion_id=of.id,
                tipo_despacho=TipoDespacho.TOTAL,
                cantidad_despachada=1,
                cantidad_total=1,
                observaciones=f"OF creada automáticamente para despacho {despacho.numero_despacho}",
                created_by=created_by
            )
            db.session.add(despacho_of)
            db.session.commit()
            
            # Log audit
            AuditService.log_action(
                'despachos',
                despacho_id,
                'CREATE_OF_LINK',
                datos_nuevos={
                    'of_id': of.id,
                    'of_codigo': of.codigo,
                    'despacho_numero': despacho.numero_despacho
                }
            )
            
            logger.info(f"OF {of.codigo} creada y vinculada al despacho {despacho.numero_despacho}")
            return of
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando OF para despacho {despacho_id}: {str(e)}")
            raise