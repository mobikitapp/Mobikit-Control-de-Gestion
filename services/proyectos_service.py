from typing import List, Optional, Dict, Any
from app import db
from repositories.proyectos_repo import ProyectosRepository
from repositories.clientes_repo import ClientesRepository
from services.audit_service import AuditService, serialize_model
from schemas.proyectos import ProyectoSearchFilters
from models import Proyecto, OrdenFabricacion, Contrato, EstadoContrato # Imported models used in the change
import logging
from datetime import datetime

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
                # New financial KPIs
                'kpi_financiero': self._calcular_kpi_financiero(proyecto),
                # New efficiency metrics by area
                'eficiencia_por_area': self._calcular_eficiencia_por_area(proyecto_id)
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
        """Calculate financial KPI: Contracts vs Budget Provision"""
        try:
            from models import Contrato, EstadoContrato
            from decimal import Decimal

            if not proyecto:
                return {'avance_porcentaje': 0, 'estado': 'sin_proyecto'}

            # Get total amount from active contracts
            monto_contratado = Decimal('0')
            contratos_vigentes = (db.session.query(Contrato)
                                .filter_by(proyecto_id=proyecto.id)
                                .filter_by(estado=EstadoContrato.VIGENTE)
                                .all())
            
            for contrato in contratos_vigentes:
                if contrato.monto_total:
                    monto_contratado += contrato.monto_total

            # Get budget provision
            provision_presupuestada = proyecto.monto_provision_presupuestado or Decimal('0')

            # Calculate percentage and status
            if provision_presupuestada > 0:
                avance_porcentaje = float((monto_contratado / provision_presupuestada) * 100)
                
                if avance_porcentaje <= 100:
                    estado = 'dentro_presupuesto'
                elif avance_porcentaje <= 110:
                    estado = 'alerta'
                else:
                    estado = 'sobre_presupuesto'
            else:
                avance_porcentaje = 0
                estado = 'sin_provision' if monto_contratado > 0 else 'sin_datos'

            return {
                'monto_contratado': float(monto_contratado),
                'provision_presupuestada': float(provision_presupuestada),
                'avance_porcentaje': round(avance_porcentaje, 1),
                'estado': estado,
                'diferencia': float(monto_contratado - provision_presupuestada)
            }

        except Exception as e:
            logger.error(f"Error calculando KPI financiero: {str(e)}")
            return {'avance_porcentaje': 0, 'estado': 'error'}

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