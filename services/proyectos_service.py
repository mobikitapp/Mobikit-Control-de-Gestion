from typing import List, Optional, Dict, Any
from app import db
from repositories.proyectos_repo import ProyectosRepository
from repositories.clientes_repo import ClientesRepository
from services.audit_service import AuditService, serialize_model
from services.uf_conversion_service import UfConversionService
from schemas.proyectos import ProyectoSearchFilters
from models import Proyecto, OrdenFabricacion, Contrato, EstadoContrato # Imported models used in the change
import logging
from datetime import datetime, date
from decimal import Decimal

logger = logging.getLogger(__name__)

class ProyectosService:
    """Service layer for Proyecto operations"""

    def __init__(self):
        self.repo = ProyectosRepository()
        self.clientes_repo = ClientesRepository()
        # Assuming contratos_repo is available, as it's used in the change
        from repositories.contratos_repo import ContratosRepository
        self.contratos_repo = ContratosRepository()
        from models import EstadoContrato  # Import here to avoid circular imports
        self.uf_service = UfConversionService()

    def _process_uf_conversion(self, proyecto_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process UF conversion for proyecto budget data if applicable
        
        Args:
            proyecto_data: Proyecto data dictionary
            
        Returns:
            Processed proyecto data with UF conversion
        """
        # Check if any UF amounts are provided
        monto_provision_uf = proyecto_data.get('monto_provision_presupuestado_uf')
        monto_instalacion_uf = proyecto_data.get('monto_instalacion_presupuestado_uf')
        
        # If any UF field is provided, process conversions
        if monto_provision_uf or monto_instalacion_uf:
            try:
                valor_uf_actual = self.uf_service.get_current_uf_value()
                conversiones_realizadas = []
                
                # Convert provision budget from UF to CLP
                if monto_provision_uf:
                    monto_provision_uf_decimal = Decimal(str(monto_provision_uf))
                    monto_provision_clp = self.uf_service.convert_uf_to_clp(monto_provision_uf_decimal)
                    proyecto_data['monto_provision_presupuestado'] = monto_provision_clp
                    conversiones_realizadas.append(f"Provisión: {monto_provision_uf} UF = ${monto_provision_clp:,.0f} CLP")
                
                # Convert installation budget from UF to CLP  
                if monto_instalacion_uf:
                    monto_instalacion_uf_decimal = Decimal(str(monto_instalacion_uf))
                    monto_instalacion_clp = self.uf_service.convert_uf_to_clp(monto_instalacion_uf_decimal)
                    proyecto_data['monto_instalacion_presupuestado'] = monto_instalacion_clp
                    conversiones_realizadas.append(f"Instalación: {monto_instalacion_uf} UF = ${monto_instalacion_clp:,.0f} CLP")
                
                # Store UF conversion metadata
                proyecto_data['valor_uf_presupuesto'] = valor_uf_actual
                proyecto_data['fecha_conversion_uf_presupuesto'] = date.today()
                
                logger.info(f"Conversiones UF presupuesto: {'; '.join(conversiones_realizadas)} (UF: ${valor_uf_actual:,.2f})")
                
            except Exception as e:
                logger.error(f"Error en conversión UF presupuesto: {str(e)}")
                raise ValueError(f"Error al convertir presupuestos UF: {str(e)}")
        
        return proyecto_data

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

            # Process UF conversion if applicable
            proyecto_data = self._process_uf_conversion(proyecto_data)

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
            
            # Send notification
            try:
                from services.notification_service import notification_service
                from models import User
                user = db.session.get(User, created_by)
                if user:
                    notification_service.notify_new_project(proyecto.id, user)
            except Exception as e:
                logger.warning(f"Error enviando notificación de nuevo proyecto: {str(e)}")

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
            tarea.descripcion = "Completar montos netos de venta (provisión e instalación) y márgenes de ganancia para el proyecto. Los montos deben ser precios finales al cliente, no costos."
            tarea.created_by = created_by
            tarea.completada = False
            db.session.add(tarea)
            logger.info(f"Tarea automática creada para vendedor {proyecto.vendedor_id} en proyecto {proyecto.id}")

    def get_proyecto_by_id(self, proyecto_id: int) -> Optional[Proyecto]:
        """Get proyecto by ID with related data"""
        return self.repo.get_by_id(proyecto_id)

    def get_proyecto_with_stats(self, proyecto_id: int) -> Optional[Dict[str, Any]]:
        """Get proyecto with detailed statistics"""
        try:
            proyecto = self.get_proyecto_by_id(proyecto_id)
            if not proyecto:
                return None

            # Get ordenes de fabricacion with proper error handling
            ordenes = []
            try:
                ordenes = db.session.query(OrdenFabricacion).filter_by(
                    proyecto_id=proyecto_id
                ).all()
            except Exception as e:
                logger.warning(f"Error loading ordenes for proyecto {proyecto_id}: {str(e)}")
                ordenes = []

            # Calculate statistics with error handling
            stats = {
                'total_ordenes': len(ordenes),
                'ordenes_por_estado': self._get_ordenes_por_estado_safe(ordenes),
                'progreso_fabricacion': self._calcular_progreso_fabricacion_safe(ordenes),
                'contratos_asociados': self._get_contratos_count(proyecto_id),
                'despachos_realizados': self._get_despachos_count(proyecto_id),
                # New financial KPIs - always recalculate from treasury data
                'kpi_financiero': self.calculate_financial_kpi_with_treasury(proyecto_id),
                # New efficiency metrics by area
                'eficiencia_por_area': self._calcular_eficiencia_por_area(proyecto_id),
                # New delivery KPIs - on-time delivery and average delay days
                'kpi_entregas': self._calcular_kpi_entregas(proyecto_id),
                # New board cutting statistics
                'estadisticas_tableros': self._calcular_estadisticas_tableros(proyecto_id),
                # New operational parameter recommendations
                'recomendaciones_operacionales': self._calcular_recomendaciones_operacionales(proyecto_id)
            }

            return {
                'proyecto': proyecto,
                'stats': stats
            }

        except Exception as e:
            logger.error(f"Error obteniendo proyecto con stats {proyecto_id}: {str(e)}")
            # Return basic project data without stats if there's an error
            proyecto = self.get_proyecto_by_id(proyecto_id)
            if proyecto:
                return {
                    'proyecto': proyecto,
                    'stats': {
                        'total_ordenes': 0,
                        'ordenes_por_estado': {},
                        'progreso_fabricacion': 0,
                        'contratos_asociados': 0,
                        'despachos_realizados': 0,
                        'kpi_financiero': {'avance_porcentaje': 0, 'estado': 'sin_datos'},
                        'eficiencia_por_area': {}
                    }
                }
            return None

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

            # Apply automatic estado changes based on business rules
            self._aplicar_cambios_automaticos_estado(proyecto_actualizado, update_data)

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

    def add_project_attachment(self, proyecto_id: int, file, tipo: str, descripcion: str, created_by: str):
        """
        Add attachment to project

        Args:
            proyecto_id: Project ID
            file: Uploaded file
            tipo: Type of attachment
            descripcion: Description of the attachment
            created_by: User ID who is uploading

        Returns:
            Created ProyectoAdjunto instance
        """
        try:
            from repositories.proyecto_adjuntos_repo import ProyectoAdjuntosRepository
            from services.storage_service import StorageService
            from models import TipoAdjunto

            proyecto = self.get_proyecto_by_id(proyecto_id)
            if not proyecto:
                raise ValueError(f"Proyecto {proyecto_id} no encontrado")

            # Upload file
            storage_service = StorageService()
            file_metadata = storage_service.upload_file_for_entity(
                file, 'proyectos', proyecto_id, 'docs', tipo
            )

            # Create adjunto record
            adjuntos_repo = ProyectoAdjuntosRepository()
            adjunto_data = {
                'proyecto_id': proyecto_id,
                'storage_key': file_metadata['storage_key'],
                'filename': file_metadata['filename'],
                'mime_type': file_metadata['mime_type'],
                'size_bytes': file_metadata['size_bytes'],
                'tipo': TipoAdjunto(tipo),
                'descripcion': descripcion
            }

            adjunto = adjuntos_repo.create(adjunto_data, created_by)

            # Commit transaction
            db.session.commit()

            logger.info(f"Adjunto agregado al proyecto {proyecto_id}: {file.filename}")
            return adjunto

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error adding attachment to proyecto {proyecto_id}: {str(e)}")
            raise

    def get_project_attachments(self, proyecto_id: int):
        """Get all attachments for a project"""
        try:
            from repositories.proyecto_adjuntos_repo import ProyectoAdjuntosRepository
            adjuntos_repo = ProyectoAdjuntosRepository()
            return adjuntos_repo.get_by_proyecto_id(proyecto_id)
        except Exception as e:
            logger.error(f"Error getting attachments for proyecto {proyecto_id}: {str(e)}")
            return []

    def delete_project_attachment(self, adjunto_id: int, user_id: str) -> bool:
        """Delete project attachment"""
        try:
            from repositories.proyecto_adjuntos_repo import ProyectoAdjuntosRepository
            from services.storage_service import StorageService

            adjuntos_repo = ProyectoAdjuntosRepository()
            adjunto = adjuntos_repo.get_by_id(adjunto_id)

            if not adjunto:
                raise ValueError(f"Adjunto {adjunto_id} no encontrado")

            # Delete from storage
            storage_service = StorageService()
            try:
                storage_service.delete_file(adjunto.storage_key)
            except Exception as storage_error:
                logger.warning(f"Error deleting file from storage: {storage_error}")

            # Delete from database
            success = adjuntos_repo.delete(adjunto)

            if success:
                db.session.commit()
                logger.info(f"Adjunto {adjunto_id} eliminado del proyecto {adjunto.proyecto_id}")
                return True

            return False

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting proyecto attachment {adjunto_id}: {str(e)}")
            raise

    def _aplicar_cambios_automaticos_estado(self, proyecto, update_data):
        """Apply automatic estado changes based on business rules"""
        try:
            from models import EstadoComercial

            # Rule 1: If monto_provision_presupuestado is set and estado is PENDIENTE_PRESUPUESTO, 
            # change to PRESUPUESTADO
            if (proyecto.estado_comercial == EstadoComercial.PENDIENTE_PRESUPUESTO and 
                proyecto.monto_provision_presupuestado and 
                proyecto.monto_provision_presupuestado > 0):

                proyecto.estado_comercial = EstadoComercial.PRESUPUESTADO
                logger.info(f"Auto-cambio: Proyecto {proyecto.id} cambiado a PRESUPUESTADO por agregar monto provisión")

                # Add note about automatic change
                nota_automatica = f"[{datetime.now().strftime('%d/%m/%Y %H:%M')}] Cambio automático a PRESUPUESTADO por ingreso de monto de provisión"
                if proyecto.notas_comerciales:
                    proyecto.notas_comerciales += f"\n{nota_automatica}"
                else:
                    proyecto.notas_comerciales = nota_automatica

        except Exception as e:
            logger.warning(f"Error aplicando cambios automáticos de estado: {str(e)}")

    def cambiar_estado_por_contrato_creado(self, proyecto_id: int):
        """Change proyecto estado to EN_DESARROLLO when contract/order is created"""
        try:
            from models import EstadoComercial

            proyecto = self.get_proyecto_by_id(proyecto_id)
            if not proyecto:
                return

            # Only change if not already in EN_DESARROLLO or TERMINADO
            if proyecto.estado_comercial not in [EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]:

                # Store original data for audit
                datos_anteriores = serialize_model(proyecto)

                proyecto.estado_comercial = EstadoComercial.EN_DESARROLLO

                # Add note about automatic change
                nota_automatica = f"[{datetime.now().strftime('%d/%m/%Y %H:%M')}] Cambio automático a EN_DESARROLLO por creación de contrato/orden"
                if proyecto.notas_comerciales:
                    proyecto.notas_comerciales += f"\n{nota_automatica}"
                else:
                    proyecto.notas_comerciales = nota_automatica

                db.session.commit()

                # Log audit
                from services.audit_service import AuditService
                AuditService.log_action(
                    'proyectos', 
                    proyecto_id, 
                    'UPDATE',
                    datos_anteriores=datos_anteriores,
                    datos_nuevos=serialize_model(proyecto)
                )

                logger.info(f"Auto-cambio: Proyecto {proyecto_id} cambiado a EN_DESARROLLO por creación de contrato/orden")

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error en cambio automático de estado por contrato: {str(e)}")

    def _count_contratos_vigentes(self, proyecto):
        """Count active contracts safely"""
        try:
            if not hasattr(proyecto, 'contratos') or not proyecto.contratos:
                return 0

            vigentes = 0
            for contrato in proyecto.contratos:
                try:
                    if hasattr(contrato, 'estado') and contrato.estado and contrato.estado.value == 'VIGENTE':
                        vigentes += 1
                except Exception:
                    continue
            return vigentes
        except Exception:
            return 0

    def _count_ofs_en_produccion(self, proyecto):
        """Count manufacturing orders in production safely"""
        try:
            if not hasattr(proyecto, 'ordenes_fabricacion') or not proyecto.ordenes_fabricacion:
                return 0

            en_produccion = 0
            for orden in proyecto.ordenes_fabricacion:
                try:
                    # Check if orden has area_progreso_actual and is not in final state
                    if hasattr(orden, 'area_progreso_actual') and orden.area_progreso_actual:
                        progreso = orden.area_progreso_actual
                        if hasattr(progreso, 'estado') and progreso.estado:
                            if not getattr(progreso.estado, 'es_final', False):
                                en_produccion += 1
                        elif hasattr(progreso, 'area') and progreso.area:
                            if getattr(progreso.area, 'tipo', None) != 'despacho':
                                en_produccion += 1
                    elif hasattr(orden, 'estado'):
                        # Fallback to orden estado if available
                        if orden.estado and orden.estado.value not in ['completada', 'despachada']:
                            en_produccion += 1
                except Exception:
                    continue
            return en_produccion
        except Exception:
            return 0

    def _get_ordenes_por_estado_safe(self, ordenes):
        """Group ordenes by their current estado safely"""
        estados = {}
        try:
            if not ordenes:
                return estados

            for orden in ordenes:
                estado_key = 'Sin estado'
                try:
                    # Try to get current area progress
                    if hasattr(orden, 'area_progreso_actual') and orden.area_progreso_actual:
                        progreso = orden.area_progreso_actual
                        if hasattr(progreso, 'estado') and progreso.estado:
                            estado_key = progreso.estado.nombre
                        elif hasattr(progreso, 'area') and progreso.area:
                            estado_key = f"En {progreso.area.nombre}"
                    elif hasattr(orden, 'estado') and orden.estado:
                        # Fallback to orden estado
                        estado_key = orden.estado.value.replace('_', ' ').title()
                except Exception:
                    pass

                estados[estado_key] = estados.get(estado_key, 0) + 1
        except Exception:
            pass
        return estados

    def _calcular_progreso_fabricacion_safe(self, ordenes):
        """Calculate overall fabrication progress safely"""
        try:
            if not ordenes:
                return 0

            ordenes_completadas = 0
            for orden in ordenes:
                try:
                    # Check if orden is completed
                    if hasattr(orden, 'area_progreso_actual') and orden.area_progreso_actual:
                        progreso = orden.area_progreso_actual
                        if hasattr(progreso, 'estado') and progreso.estado:
                            if getattr(progreso.estado, 'es_final', False):
                                ordenes_completadas += 1
                        elif hasattr(progreso, 'area') and progreso.area:
                            if getattr(progreso.area, 'tipo', None) == 'despacho':
                                ordenes_completadas += 1
                    elif hasattr(orden, 'estado') and orden.estado:
                        # Fallback to orden estado
                        if orden.estado.value in ['completada', 'despachada']:
                            ordenes_completadas += 1
                except Exception:
                    continue

            return round((ordenes_completadas / len(ordenes)) * 100, 1)
        except Exception:
            return 0

    def _get_contratos_count(self, proyecto_id):
        """Get count of contracts for project"""
        try:
            from models import Contrato
            return Contrato.query.filter_by(proyecto_id=proyecto_id).count()
        except Exception as e:
            logger.warning(f"Error counting contratos for proyecto {proyecto_id}: {str(e)}")
            return 0

    def _get_despachos_count(self, proyecto_id):
        """Get count of dispatches for project"""
        try:
            from models import Despacho
            return Despacho.query.filter_by(proyecto_id=proyecto_id).count()
        except Exception as e:
            logger.warning(f"Error counting despachos for proyecto {proyecto_id}: {str(e)}")
            return 0

    def get_contratos_activos_by_proyecto(self, proyecto_id: int) -> List[Contrato]:
        """Get active contracts for a proyecto with delivery plan info"""
        try:
            from repositories.planes_entrega_repo import PlanesEntregaRepository, HitosEntregaRepository
            from models import EstadoHitoEntrega

            contratos = self.contratos_repo.get_contratos_activos_by_proyecto(proyecto_id)
            planes_repo = PlanesEntregaRepository()
            hitos_repo = HitosEntregaRepository()

            # Add delivery plan info to each contract
            for contrato in contratos:
                plan = planes_repo.get_by_contrato_id(contrato.id)
                contrato.proximo_hito = None
                contrato.fecha_proxima_entrega = None

                if plan:
                    # Get next pending milestone
                    hitos_pendientes = [h for h in plan.hitos 
                                      if h.estado == EstadoHitoEntrega.PENDIENTE]
                    if hitos_pendientes:
                        # Sort by date and order
                        hitos_pendientes.sort(key=lambda x: (x.fecha_programada, x.orden))
                        contrato.proximo_hito = hitos_pendientes[0]
                        contrato.fecha_proxima_entrega = hitos_pendientes[0].fecha_programada

            return contratos
        except Exception as e:
            logger.error(f"Error obteniendo contratos activos del proyecto {proyecto_id}: {str(e)}")
            raise

    def count_contratos_activos_by_proyecto(self, proyecto_id: int) -> int:
        """Count active contracts for a project"""
        try:
            from models import Contrato, EstadoContrato
            return (db.session.query(Contrato)
                   .filter_by(proyecto_id=proyecto_id)
                   .filter_by(estado=EstadoContrato.VIGENTE)
                   .count())
        except Exception as e:
            logger.error(f"Error contando contratos activos del proyecto {proyecto_id}: {str(e)}")
            return 0

    def _calcular_kpi_financiero(self, proyecto) -> Dict[str, Any]:
        """Calculate financial KPI using treasury integration logic"""
        try:
            if not proyecto:
                return {'estado': 'sin_proyecto'}

            # Use the same logic as treasury integration for consistency
            return self.calculate_financial_kpi_with_treasury(proyecto.id)

        except Exception as e:
            logger.error(f"Error calculando KPI financiero: {str(e)}")
            return {'estado': 'error'}

    def _calcular_eficiencia_por_area(self, proyecto_id: int) -> Dict[str, Any]:
        """Calculate efficiency metrics by area: Pendientes, Fábrica, Embalaje, Bodega"""
        try:
            from models import OrdenAreaProgreso, Area, TipoArea
            from sqlalchemy import func
            from datetime import datetime, timedelta

            # Get all area progress for this project's orders
            progresos = (db.session.query(OrdenAreaProgreso)
                        .join(OrdenAreaProgreso.orden_fabricacion)
                        .filter(OrdenAreaProgreso.orden_fabricacion.has(proyecto_id=proyecto_id))
                        .join(Area)
                        .all())

            if not progresos:
                return {}

            # Group by area type and calculate metrics
            areas_metricas = {}
            area_tipos = {
                'PENDIENTES_FABRICACION': 'Pendientes Fabricación',
                'FABRICA': 'Fábrica', 
                'EMBALAJE': 'Embalaje',
                'BODEGA': 'Bodega'
            }

            for tipo_key, nombre_area in area_tipos.items():
                try:
                    # Get all progress records for this area type
                    area_progresos = [p for p in progresos 
                                    if hasattr(p.area, 'tipo') and 
                                       p.area.tipo and 
                                       p.area.tipo.value == tipo_key]

                    if not area_progresos:
                        areas_metricas[nombre_area] = {
                            'tiempo_promedio_horas': 0,
                            'ordenes_procesadas': 0,
                            'ordenes_actualmente': 0
                        }
                        continue

                    # Calculate average time in area (completed ones)
                    tiempos_completados = []
                    ordenes_actuales = 0

                    for progreso in area_progresos:
                        if progreso.es_actual:
                            ordenes_actuales += 1

                        # For completed area progress, calculate time spent
                        if not progreso.es_actual and progreso.fecha_ingreso_area and progreso.fecha_cambio_estado:
                            tiempo_en_area = progreso.fecha_cambio_estado - progreso.fecha_ingreso_area
                            tiempos_completados.append(tiempo_en_area.total_seconds() / 3600)  # Convert to hours

                    tiempo_promedio = sum(tiempos_completados) / len(tiempos_completados) if tiempos_completados else 0

                    areas_metricas[nombre_area] = {
                        'tiempo_promedio_horas': round(tiempo_promedio, 1),
                        'ordenes_procesadas': len(tiempos_completados),
                        'ordenes_actualmente': ordenes_actuales
                    }

                except Exception as area_e:
                    logger.warning(f"Error calculando métricas para área {nombre_area}: {str(area_e)}")
                    areas_metricas[nombre_area] = {
                        'tiempo_promedio_horas': 0,
                        'ordenes_procesadas': 0,
                        'ordenes_actualmente': 0
                    }

            return areas_metricas

        except Exception as e:
            logger.error(f"Error calculando eficiencia por área: {str(e)}")
            return {}

    def _calcular_kpi_entregas(self, proyecto_id: int) -> Dict[str, Any]:
        """Calculate delivery KPIs: on-time delivery percentage and average delay days"""
        try:
            from models import OrdenFabricacion, Despacho, HitoEntrega
            from datetime import datetime, date

            # Initialize metrics
            entregas_a_tiempo = 0
            entregas_con_atraso = 0
            dias_atraso_total = 0
            entregas_evaluadas = 0

            # === ANÁLISIS DE ÓRDENES DE FABRICACIÓN ===
            ordenes = OrdenFabricacion.query.filter_by(proyecto_id=proyecto_id).all()
            
            for orden in ordenes:
                try:
                    # Check if order has planned date and completion date
                    fecha_planificada = orden.fecha_planificada
                    fecha_completada = None
                    
                    # Try to get actual completion date from various sources
                    if orden.fecha_fin:
                        fecha_completada = orden.fecha_fin.date() if isinstance(orden.fecha_fin, datetime) else orden.fecha_fin
                    elif orden.fecha_entrega_embalaje:
                        fecha_completada = orden.fecha_entrega_embalaje
                    elif orden.fecha_entrega_fabrica:
                        fecha_completada = orden.fecha_entrega_fabrica

                    if fecha_planificada and fecha_completada:
                        entregas_evaluadas += 1
                        
                        # Calculate delay in days
                        if isinstance(fecha_completada, datetime):
                            fecha_completada = fecha_completada.date()
                        if isinstance(fecha_planificada, datetime):
                            fecha_planificada = fecha_planificada.date()
                            
                        dias_diferencia = (fecha_completada - fecha_planificada).days
                        
                        if dias_diferencia <= 0:  # On time or early
                            entregas_a_tiempo += 1
                        else:  # Late delivery
                            entregas_con_atraso += 1
                            dias_atraso_total += dias_diferencia

                except Exception as orden_e:
                    logger.warning(f"Error evaluando entrega para orden {orden.id}: {str(orden_e)}")
                    continue

            # === ANÁLISIS DE DESPACHOS ===
            despachos = Despacho.query.filter_by(proyecto_id=proyecto_id).all()
            
            for despacho in despachos:
                try:
                    fecha_programada = despacho.fecha_programada
                    fecha_entrega = despacho.fecha_entrega
                    
                    if fecha_programada and fecha_entrega:
                        entregas_evaluadas += 1
                        
                        # Calculate delay in days
                        if isinstance(fecha_entrega, datetime):
                            fecha_entrega = fecha_entrega.date()
                        if isinstance(fecha_programada, datetime):
                            fecha_programada = fecha_programada.date()
                            
                        dias_diferencia = (fecha_entrega - fecha_programada).days
                        
                        if dias_diferencia <= 0:  # On time or early
                            entregas_a_tiempo += 1
                        else:  # Late delivery
                            entregas_con_atraso += 1
                            dias_atraso_total += dias_diferencia

                except Exception as despacho_e:
                    logger.warning(f"Error evaluando entrega para despacho {despacho.id}: {str(despacho_e)}")
                    continue

            # === ANÁLISIS DE HITOS DE ENTREGA ===
            from models import PlanEntrega, Contrato
            hitos = HitoEntrega.query\
                .join(PlanEntrega, HitoEntrega.plan_entrega_id == PlanEntrega.id)\
                .join(Contrato, PlanEntrega.contrato_id == Contrato.id)\
                .filter(Contrato.proyecto_id == proyecto_id)\
                .all()
            
            for hito in hitos:
                try:
                    fecha_programada = hito.fecha_programada
                    fecha_completado = hito.fecha_completado
                    
                    if fecha_programada and fecha_completado:
                        entregas_evaluadas += 1
                        
                        # Calculate delay in days
                        if isinstance(fecha_completado, datetime):
                            fecha_completado = fecha_completado.date()
                        if isinstance(fecha_programada, datetime):
                            fecha_programada = fecha_programada.date()
                            
                        dias_diferencia = (fecha_completado - fecha_programada).days
                        
                        if dias_diferencia <= 0:  # On time or early
                            entregas_a_tiempo += 1
                        else:  # Late delivery
                            entregas_con_atraso += 1
                            dias_atraso_total += dias_diferencia

                except Exception as hito_e:
                    logger.warning(f"Error evaluando hito {hito.id}: {str(hito_e)}")
                    continue

            # Calculate final metrics
            if entregas_evaluadas == 0:
                return {
                    'entregas_a_tiempo_porcentaje': 0,
                    'promedio_dias_atraso': 0,
                    'entregas_evaluadas': 0,
                    'entregas_a_tiempo': 0,
                    'entregas_con_atraso': 0,
                    'estado': 'sin_datos'
                }

            porcentaje_entregas_a_tiempo = round((entregas_a_tiempo / entregas_evaluadas) * 100, 1)
            promedio_dias_atraso = round(dias_atraso_total / entregas_con_atraso, 1) if entregas_con_atraso > 0 else 0

            # Determine delivery performance status
            if porcentaje_entregas_a_tiempo >= 90:
                estado_entregas = 'excelente'
            elif porcentaje_entregas_a_tiempo >= 75:
                estado_entregas = 'bueno'
            elif porcentaje_entregas_a_tiempo >= 60:
                estado_entregas = 'regular'
            else:
                estado_entregas = 'deficiente'

            return {
                'entregas_a_tiempo_porcentaje': porcentaje_entregas_a_tiempo,
                'promedio_dias_atraso': promedio_dias_atraso,
                'entregas_evaluadas': entregas_evaluadas,
                'entregas_a_tiempo': entregas_a_tiempo,
                'entregas_con_atraso': entregas_con_atraso,
                'estado': estado_entregas,
                'total_dias_atraso': dias_atraso_total
            }

        except Exception as e:
            logger.error(f"Error calculando KPI de entregas: {str(e)}")
            return {
                'entregas_a_tiempo_porcentaje': 0,
                'promedio_dias_atraso': 0,
                'entregas_evaluadas': 0,
                'entregas_a_tiempo': 0,
                'entregas_con_atraso': 0,
                'estado': 'error'
            }

    def get_project_stats(self, proyecto_id: int) -> Dict[str, Any]:
        """
        Obtiene estadísticas completas del proyecto incluyendo KPI financiero y eficiencia por área
        """
        try:
            from models import Contrato, OrdenFabricacion, Despacho, EstadoPago
            from schemas.contratos import EstadoContratoEnum
            from schemas.fabricacion import EstadoOrdenFabricacion
            from services.treasury_integration_service import TreasuryIntegrationService

            proyecto = self.get_by_id(proyecto_id)
            if not proyecto:
                return {}

            stats = {}

            # Basic project statistics
            contratos = Contrato.query.filter_by(proyecto_id=proyecto_id).all()
            ordenes = OrdenFabricacion.query.filter_by(proyecto_id=proyecto_id).all()
            despachos = Despacho.query.filter_by(proyecto_id=proyecto_id).all()

            stats['total_contratos'] = len(contratos)
            stats['contratos_vigentes'] = len([c for c in contratos if c.estado == EstadoContratoEnum.VIGENTE])
            stats['total_ordenes'] = len(ordenes)
            stats['despachos_realizados'] = len(despachos)

            # Órdenes por estado
            ordenes_por_estado = {}
            for orden in ordenes:
                estado = orden.estado.value if orden.estado else 'sin_estado'
                ordenes_por_estado[estado] = ordenes_por_estado.get(estado, 0) + 1

            stats['ordenes_por_estado'] = ordenes_por_estado

            # Financial KPI calculation using Treasury data
            stats['kpi_financiero'] = self.calculate_financial_kpi_with_treasury(proyecto_id)

            # Efficiency by area
            stats['eficiencia_por_area'] = self._calculate_area_efficiency(proyecto_id)

            return stats

        except Exception as e:
            logger.error(f"Error getting project stats for {proyecto_id}: {str(e)}")
            return {}

    def calculate_financial_kpi_with_treasury(self, proyecto_id: int) -> Dict[str, Any]:
        """
        Calcula KPI financiero del proyecto alineado con módulo de finanzas
        """
        try:
            from models import Contrato, EstadoPago, TipoDocumento, Proyecto, TipoEstadoPago
            from schemas.contratos import EstadoContratoEnum

            # Obtener proyecto para presupuesto
            proyecto = Proyecto.query.get(proyecto_id)
            if not proyecto:
                return {'estado': 'sin_proyecto'}

            # Calcular presupuesto total (ingresos esperados)
            presupuesto_provision = float(proyecto.monto_provision_presupuestado or 0)
            presupuesto_instalacion = float(proyecto.monto_instalacion_presupuestado or 0)
            presupuesto_total = presupuesto_provision + presupuesto_instalacion
            
            # Calcular costos estimados basados en márgenes de venta (alineado con finanzas)
            costo_estimado_provision = 0.0
            costo_estimado_instalacion = 0.0
            
            if proyecto.monto_provision_presupuestado and proyecto.margen_venta_provision:
                monto_provision = float(proyecto.monto_provision_presupuestado)
                margen_provision = float(proyecto.margen_venta_provision)
                costo_estimado_provision = monto_provision * (1 - margen_provision / 100)
            
            if proyecto.monto_instalacion_presupuestado and proyecto.margen_venta_instalacion:
                monto_instalacion = float(proyecto.monto_instalacion_presupuestado) 
                margen_instalacion = float(proyecto.margen_venta_instalacion)
                costo_estimado_instalacion = monto_instalacion * (1 - margen_instalacion / 100)
                
            costos_estimados_total = costo_estimado_provision + costo_estimado_instalacion
            margen_esperado = presupuesto_total - costos_estimados_total

            # Obtener contratos vigentes (separar por tipo)
            contratos_regulares = Contrato.query.filter_by(
                proyecto_id=proyecto_id,
                estado=EstadoContratoEnum.VIGENTE,
                tipo_documento=TipoDocumento.CONTRATO
            ).all()

            ordenes_compra = Contrato.query.filter_by(
                proyecto_id=proyecto_id,
                estado=EstadoContratoEnum.VIGENTE,
                tipo_documento=TipoDocumento.ORDEN_COMPRA
            ).all()

            # Calcular totales de contratos regulares
            total_contratos_regulares = sum(float(c.monto_total or 0) for c in contratos_regulares)

            # Calcular totales de órdenes de compra
            total_ordenes_compra = sum(float(oc.monto_total or 0) for oc in ordenes_compra)

            total_contratado = total_contratos_regulares + total_ordenes_compra

            if total_contratado == 0:
                return {
                    'estado': 'sin_datos',
                    'presupuesto_total': presupuesto_total,
                    'monto_contratado': 0,
                    'monto_facturado': 0,
                    'monto_pagado': 0,
                    'monto_pendiente': 0,
                    'monto_parcial': 0,
                    'porcentaje_facturado': 0,
                    'porcentaje_cobrado': 0
                }

            # === CONTRATOS REGULARES ===
            # Obtener estados de pago para contratos regulares
            monto_facturado_contratos = 0
            monto_pagado_contratos = 0

            if contratos_regulares:
                estados_pago_contratos = EstadoPago.query.filter(
                    EstadoPago.contrato_id.in_([c.id for c in contratos_regulares])
                ).all()

                monto_facturado_contratos = sum(
                    float(ep.monto or 0) for ep in estados_pago_contratos 
                    if ep.tipo_estado in [TipoEstadoPago.FACTURADO, TipoEstadoPago.PAGADO]
                )

                monto_pagado_contratos = sum(
                    float(ep.monto or 0) for ep in estados_pago_contratos 
                    if ep.tipo_estado == TipoEstadoPago.PAGADO
                )

            # === ÓRDENES DE COMPRA ===
            # Por ahora usar estados de pago de OCs como contratos regulares
            monto_facturado_ocs = 0
            monto_pagado_ocs = 0

            if ordenes_compra:
                estados_pago_ocs = EstadoPago.query.filter(
                    EstadoPago.contrato_id.in_([oc.id for oc in ordenes_compra])
                ).all()

                monto_facturado_ocs = sum(
                    float(ep.monto or 0) for ep in estados_pago_ocs 
                    if ep.tipo_estado in [TipoEstadoPago.FACTURADO, TipoEstadoPago.PAGADO]
                )

                monto_pagado_ocs = sum(
                    float(ep.monto or 0) for ep in estados_pago_ocs 
                    if ep.tipo_estado == TipoEstadoPago.PAGADO
                )

            # === TOTALES COMBINADOS ===
            monto_facturado_total = monto_facturado_contratos + monto_facturado_ocs
            monto_pagado_total = monto_pagado_contratos + monto_pagado_ocs

            # Calcular porcentajes
            porcentaje_facturado = (monto_facturado_total / total_contratado * 100) if total_contratado > 0 else 0
            # Porcentaje cobrado debe ser sobre el total contratado para ser consistente
            porcentaje_cobrado = (monto_pagado_total / total_contratado * 100) if total_contratado > 0 else 0

            # Montos pendientes
            monto_pendiente = total_contratado - monto_pagado_total
            monto_por_facturar = total_contratado - monto_facturado_total
            monto_facturado_no_cobrado = monto_facturado_total - monto_pagado_total
            monto_parcial = 0  # Para futuras implementaciones de pagos parciales

            # Determinar estado basado en presupuesto vs contratado
            if presupuesto_total > 0:
                porcentaje_contratado = (total_contratado / presupuesto_total) * 100
                if porcentaje_contratado <= 100:
                    estado = 'dentro_presupuesto'
                elif porcentaje_contratado <= 110:
                    estado = 'alerta'
                else:
                    estado = 'sobre_presupuesto'
            else:
                estado = 'sin_presupuesto' if total_contratado > 0 else 'sin_datos'

            # Calcular margen real vs esperado (alineado con finanzas)
            margen_real = total_contratado - costos_estimados_total
            margen_porcentaje = (margen_real / total_contratado * 100) if total_contratado > 0 else 0

            return {
                'estado': estado,
                'presupuesto_total': presupuesto_total,
                'monto_contratado': total_contratado,
                'monto_facturado': monto_facturado_total,
                'monto_pagado': monto_pagado_total,
                'monto_pendiente': monto_pendiente,
                'monto_parcial': monto_parcial,
                'porcentaje_facturado': round(porcentaje_facturado, 1),
                'porcentaje_cobrado': round(porcentaje_cobrado, 1),
                # Campos alineados con módulo de finanzas
                'costos_estimados': costos_estimados_total,
                'margen_esperado': margen_esperado,
                'margen_real': margen_real,
                'margen_porcentaje': round(margen_porcentaje, 1),
                'costos_son_estimados': True,
                'desglose': {
                    'contratos_regulares': {
                        'monto_total': total_contratos_regulares,
                        'monto_facturado': monto_facturado_contratos,
                        'monto_pagado': monto_pagado_contratos
                    },
                    'ordenes_compra': {
                        'monto_total': total_ordenes_compra,
                        'monto_facturado': monto_facturado_ocs,
                        'monto_pagado': monto_pagado_ocs
                    }
                }
            }

        except Exception as e:
            logger.error(f"Error calculating financial KPI with treasury data for project {proyecto_id}: {str(e)}")
            return {'estado': 'error'}

    

    def get_proyectos_financial_summary(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Obtiene resumen financiero de proyectos para dashboard usando datos de tesorería
        """
        try:
            from models import Proyecto, Cliente, Contrato, EstadoPago, TipoDocumento, TipoEstadoPago
            from schemas.contratos import EstadoContratoEnum

            proyectos = db.session.query(Proyecto, Cliente)\
                .join(Cliente, Proyecto.cliente_id == Cliente.id)\
                .filter(Proyecto.activo == True)\
                .limit(limit)\
                .all()

            resultado = []
            for proyecto, cliente in proyectos:
                # Obtener contratos regulares vigentes
                contratos_regulares = Contrato.query.filter_by(
                    proyecto_id=proyecto.id,
                    estado=EstadoContratoEnum.VIGENTE,
                    tipo_documento=TipoDocumento.CONTRATO
                ).all()

                # Obtener órdenes de compra vigentes
                ordenes_compra = Contrato.query.filter_by(
                    proyecto_id=proyecto.id,
                    estado=EstadoContratoEnum.VIGENTE,
                    tipo_documento=TipoDocumento.ORDEN_COMPRA
                ).all()

                total_contratos = len(contratos_regulares) + len(ordenes_compra)

                if total_contratos == 0:
                    continue

                # === CONTRATOS REGULARES ===
                total_contratado_regulares = sum(float(c.monto_total or 0) for c in contratos_regulares)
                total_facturado_contratos = 0
                total_pagado_contratos = 0

                if contratos_regulares:
                    estados_pago_contratos = EstadoPago.query.filter(
                        EstadoPago.contrato_id.in_([c.id for c in contratos_regulares])
                    ).all()

                    total_facturado_contratos = sum(
                        float(ep.monto or 0) for ep in estados_pago_contratos 
                        if ep.tipo_estado in [TipoEstadoPago.FACTURADO, TipoEstadoPago.PAGADO]
                    )

                    total_pagado_contratos = sum(
                        float(ep.monto or 0) for ep in estados_pago_contratos 
                        if ep.tipo_estado == TipoEstadoPago.PAGADO
                    )

                # === ÓRDENES DE COMPRA ===
                total_contratado_ocs = sum(float(oc.monto_total or 0) for oc in ordenes_compra)
                total_facturado_ocs = 0
                total_pagado_ocs = 0

                if ordenes_compra:
                    estados_pago_ocs = EstadoPago.query.filter(
                        EstadoPago.contrato_id.in_([oc.id for oc in ordenes_compra])
                    ).all()

                    total_facturado_ocs = sum(
                        float(ep.monto or 0) for ep in estados_pago_ocs 
                        if ep.tipo_estado in [TipoEstadoPago.FACTURADO, TipoEstadoPago.PAGADO]
                    )

                    total_pagado_ocs = sum(
                        float(ep.monto or 0) for ep in estados_pago_ocs 
                        if ep.tipo_estado == TipoEstadoPago.PAGADO
                    )

                # === TOTALES COMBINADOS ===
                total_contratado = total_contratado_regulares + total_contratado_ocs
                total_facturado = total_facturado_contratos + total_facturado_ocs
                total_pagado = total_pagado_contratos + total_pagado_ocs
                saldo_por_cobrar = total_contratado - total_pagado

                # Calcular porcentajes
                porcentaje_facturado = (total_facturado / total_contratado * 100) if total_contratado > 0 else 0
                porcentaje_cobrado = (total_pagado / total_contratado * 100) if total_contratado > 0 else 0

                resumen = {
                    'total_contratos': total_contratos,
                    'montos': {
                        'total_contratado': total_contratado,
                        'total_facturado': total_facturado,
                        'total_pagado': total_pagado,
                        'saldo_por_cobrar': saldo_por_cobrar
                    },
                    'porcentajes': {
                        'facturado': porcentaje_facturado,
                        'cobrado': porcentaje_cobrado
                    },
                    'desglose': {
                        'contratos_regulares': {
                            'cantidad': len(contratos_regulares),
                            'monto_total': total_contratado_regulares,
                            'monto_facturado': total_facturado_contratos,
                            'monto_pagado': total_pagado_contratos
                        },
                        'ordenes_compra': {
                            'cantidad': len(ordenes_compra),
                            'monto_total': total_contratado_ocs,
                            'monto_facturado': total_facturado_ocs,
                            'monto_pagado': total_pagado_ocs
                        }
                    }
                }

                resultado.append({
                    'proyecto': proyecto,
                    'resumen': resumen
                })

            return resultado

        except Exception as e:
            logger.error(f"Error getting financial summary: {str(e)}")
            return []

    def _calcular_estadisticas_tableros(self, proyecto_id: int) -> Dict[str, Any]:
        """Calculate board cutting statistics including total boards, ratios, and days per board"""
        try:
            from models import OrdenFabricacion
            from datetime import datetime

            # Get all orders for the project
            ordenes = OrdenFabricacion.query.filter_by(proyecto_id=proyecto_id).all()

            # Initialize metrics
            total_tableros = 0
            tableros_fabrica = 0
            tableros_embalaje = 0
            dias_fabrica_total = 0
            dias_embalaje_total = 0
            ordenes_fabrica_procesadas = 0
            ordenes_embalaje_procesadas = 0

            for orden in ordenes:
                try:
                    # Count total boards
                    if orden.cantidad_tableros:
                        total_tableros += orden.cantidad_tableros
                        
                        # Analyze Factory area (Fábrica)
                        if orden.fecha_entrega_fabrica and orden.fecha_inicio:
                            dias_en_fabrica = (orden.fecha_entrega_fabrica - orden.fecha_inicio).days
                            if dias_en_fabrica > 0:
                                tableros_fabrica += orden.cantidad_tableros
                                dias_fabrica_total += dias_en_fabrica
                                ordenes_fabrica_procesadas += 1

                        # Analyze Packaging area (Embalaje)
                        if orden.fecha_entrega_embalaje and orden.fecha_entrega_fabrica:
                            dias_en_embalaje = (orden.fecha_entrega_embalaje - orden.fecha_entrega_fabrica).days
                            if dias_en_embalaje > 0:
                                tableros_embalaje += orden.cantidad_tableros
                                dias_embalaje_total += dias_en_embalaje
                                ordenes_embalaje_procesadas += 1

                except Exception as orden_e:
                    logger.warning(f"Error procesando tableros para orden {orden.id}: {str(orden_e)}")
                    continue

            # Calculate ratios and averages
            tableros_por_dia_fabrica = 0
            dias_por_tablero_fabrica = 0
            if ordenes_fabrica_procesadas > 0 and dias_fabrica_total > 0:
                tableros_por_dia_fabrica = round(tableros_fabrica / dias_fabrica_total, 2)
                dias_por_tablero_fabrica = round(dias_fabrica_total / tableros_fabrica, 2)

            tableros_por_dia_embalaje = 0 
            dias_por_tablero_embalaje = 0
            if ordenes_embalaje_procesadas > 0 and dias_embalaje_total > 0:
                tableros_por_dia_embalaje = round(tableros_embalaje / dias_embalaje_total, 2)
                dias_por_tablero_embalaje = round(dias_embalaje_total / tableros_embalaje, 2)

            return {
                'total_tableros': total_tableros,
                'tableros_fabrica': tableros_fabrica,
                'tableros_embalaje': tableros_embalaje,
                'tableros_por_dia_fabrica': tableros_por_dia_fabrica,
                'tableros_por_dia_embalaje': tableros_por_dia_embalaje,
                'dias_por_tablero_fabrica': dias_por_tablero_fabrica,
                'dias_por_tablero_embalaje': dias_por_tablero_embalaje,
                'ordenes_procesadas_fabrica': ordenes_fabrica_procesadas,
                'ordenes_procesadas_embalaje': ordenes_embalaje_procesadas,
                'estado': 'calculado' if total_tableros > 0 else 'sin_datos'
            }

        except Exception as e:
            logger.error(f"Error calculando estadísticas de tableros: {str(e)}")
            return {
                'total_tableros': 0,
                'tableros_fabrica': 0,
                'tableros_embalaje': 0,
                'tableros_por_dia_fabrica': 0,
                'tableros_por_dia_embalaje': 0,
                'dias_por_tablero_fabrica': 0,
                'dias_por_tablero_embalaje': 0,
                'ordenes_procesadas_fabrica': 0,
                'ordenes_procesadas_embalaje': 0,
                'estado': 'error'
            }

    def _calcular_recomendaciones_operacionales(self, proyecto_id: int) -> Dict[str, Any]:
        """Generate operational parameter recommendations based on real OF data by project type"""
        try:
            from models import OrdenFabricacion, Proyecto, TipoProyecto
            from sqlalchemy import func
            from datetime import datetime

            # Get current project data
            proyecto = Proyecto.query.get(proyecto_id)
            if not proyecto:
                return {'estado': 'proyecto_no_encontrado'}

            proyecto_tipo = proyecto.tipo_proyecto if proyecto.tipo_proyecto else TipoProyecto.ESTANDAR

            # Get historical data from similar projects (same type)
            proyectos_similares = Proyecto.query.filter_by(tipo_proyecto=proyecto_tipo).all()
            proyecto_ids = [p.id for p in proyectos_similares]

            if not proyecto_ids:
                return {'estado': 'sin_datos_historicos'}

            # Analyze historical performance for this project type
            ordenes_historicas = OrdenFabricacion.query.filter(
                OrdenFabricacion.proyecto_id.in_(proyecto_ids),
                OrdenFabricacion.fecha_inicio.isnot(None),
                OrdenFabricacion.cantidad_tableros.isnot(None)
            ).all()

            if not ordenes_historicas:
                return {'estado': 'sin_datos_ordenes'}

            # Calculate averages for this project type
            tiempos_fabrica = []
            tiempos_embalaje = []
            tableros_por_orden = []
            
            for orden in ordenes_historicas:
                try:
                    if orden.cantidad_tableros:
                        tableros_por_orden.append(orden.cantidad_tableros)

                    # Factory time analysis
                    if orden.fecha_inicio and orden.fecha_entrega_fabrica:
                        dias_fabrica = (orden.fecha_entrega_fabrica - orden.fecha_inicio).days
                        if dias_fabrica > 0:
                            tiempos_fabrica.append(dias_fabrica)

                    # Packaging time analysis
                    if orden.fecha_entrega_fabrica and orden.fecha_entrega_embalaje:
                        dias_embalaje = (orden.fecha_entrega_embalaje - orden.fecha_entrega_fabrica).days
                        if dias_embalaje > 0:
                            tiempos_embalaje.append(dias_embalaje)

                except Exception as orden_e:
                    logger.warning(f"Error analizando orden histórica {orden.id}: {str(orden_e)}")
                    continue

            # Generate recommendations based on statistical analysis
            recomendaciones = {
                'tipo_proyecto': proyecto_tipo.value if proyecto_tipo else 'ESTANDAR',
                'ordenes_analizadas': len(ordenes_historicas),
                'parametros_recomendados': {}
            }

            if tiempos_fabrica:
                promedio_fabrica = sum(tiempos_fabrica) / len(tiempos_fabrica)
                recomendaciones['parametros_recomendados']['dias_fabrica_recomendados'] = round(promedio_fabrica, 1)

            if tiempos_embalaje:
                promedio_embalaje = sum(tiempos_embalaje) / len(tiempos_embalaje)
                recomendaciones['parametros_recomendados']['dias_embalaje_recomendados'] = round(promedio_embalaje, 1)

            if tableros_por_orden:
                promedio_tableros = sum(tableros_por_orden) / len(tableros_por_orden)
                recomendaciones['parametros_recomendados']['tableros_promedio_por_orden'] = round(promedio_tableros, 1)

            # Calculate efficiency recommendations based on historical data
            if tiempos_fabrica and tableros_por_orden:
                # Get overlapping data points for accurate ratio calculation
                ratios_fabrica = []
                for i, orden in enumerate(ordenes_historicas):
                    if (orden.fecha_inicio and orden.fecha_entrega_fabrica and 
                        orden.cantidad_tableros and orden.cantidad_tableros > 0):
                        dias = (orden.fecha_entrega_fabrica - orden.fecha_inicio).days
                        if dias > 0:
                            ratio = orden.cantidad_tableros / dias
                            ratios_fabrica.append(ratio)

                if ratios_fabrica:
                    tableros_por_dia_optimo = sum(ratios_fabrica) / len(ratios_fabrica)
                    recomendaciones['parametros_recomendados']['tableros_por_dia_fabrica_objetivo'] = round(tableros_por_dia_optimo, 2)

            # Add project-specific recommendations based on type
            if proyecto_tipo == TipoProyecto.SOCIAL:
                recomendaciones['observaciones'] = [
                    'Proyectos sociales suelen requerir mayor control de calidad',
                    'Considerar tiempos adicionales para revisiones'
                ]
            elif proyecto_tipo == TipoProyecto.ESPECIAL:
                recomendaciones['observaciones'] = [
                    'Proyectos especiales requieren diseños personalizados',
                    'Planificar tiempo adicional para prototipos'
                ]
            else:  # ESTANDAR
                recomendaciones['observaciones'] = [
                    'Proyectos estándar permiten optimización de procesos',
                    'Usar templates y procesos estandarizados'
                ]

            recomendaciones['estado'] = 'generado'
            return recomendaciones

        except Exception as e:
            logger.error(f"Error generando recomendaciones operacionales: {str(e)}")
            return {
                'estado': 'error',
                'tipo_proyecto': 'DESCONOCIDO',
                'ordenes_analizadas': 0,
                'parametros_recomendados': {},
                'observaciones': []
            }