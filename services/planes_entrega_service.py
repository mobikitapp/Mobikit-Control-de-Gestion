from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, date
import logging

from app import db
from models import PlanEntrega, HitoEntrega, EstadoHitoEntrega, Contrato
from repositories.planes_entrega_repo import PlanesEntregaRepository, HitosEntregaRepository
from repositories.contratos_repo import ContratosRepository
from services.audit_service import AuditService, serialize_model
from sqlalchemy import func
from sqlalchemy.orm import joinedload

logger = logging.getLogger(__name__)

class PlanesEntregaService:
    """Service layer for PlanEntrega operations"""

    def __init__(self):
        self.repo = PlanesEntregaRepository()
        self.hitos_repo = HitosEntregaRepository()
        self.contratos_repo = ContratosRepository()

    def create_plan_with_hitos(self, plan_data: Dict[str, Any], hitos_data: List[Dict[str, Any]], 
                               created_by: str) -> PlanEntrega:
        """
        Create a new plan de entrega with hitos in a single transaction

        Args:
            plan_data: Plan data dictionary
            hitos_data: List of hito data dictionaries
            created_by: User ID who is creating the plan

        Returns:
            Created PlanEntrega instance
        """
        try:
            # Validate contrato exists
            contrato = self.contratos_repo.get_by_id(plan_data['contrato_id'])
            if not contrato:
                raise ValueError(f"Contrato {plan_data['contrato_id']} no encontrado")

            # Check if contrato already has a plan
            existing_plan = self.repo.get_by_contrato_id(plan_data['contrato_id'])
            if existing_plan:
                raise ValueError(f"El contrato {plan_data['contrato_id']} ya tiene un plan de entrega")

            # Create plan
            plan = self.repo.create(plan_data, created_by)

            # Create hitos
            for i, hito_data in enumerate(hitos_data):
                hito_data['plan_entrega_id'] = plan.id
                if 'orden' not in hito_data:
                    hito_data['orden'] = i + 1
                self.hitos_repo.create(hito_data, created_by)

            # Commit transaction
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'planes_entrega', 
                plan.id, 
                'CREATE', 
                datos_nuevos=serialize_model(plan)
            )

            logger.info(f"Plan de entrega creado: {plan.id} - {plan.nombre}")
            return plan

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando plan de entrega: {str(e)}")
            raise

    def get_plan_by_id(self, plan_id: int) -> Optional[PlanEntrega]:
        """Get plan de entrega by ID"""
        return self.repo.get_by_id(plan_id)

    def get_plan_by_contrato_id(self, contrato_id: int) -> Optional[PlanEntrega]:
        """Get plan de entrega by contrato ID"""
        return self.repo.get_by_contrato_id(contrato_id)

    def update_plan(self, plan_id: int, update_data: Dict[str, Any]) -> PlanEntrega:
        """
        Update plan de entrega

        Args:
            plan_id: Plan ID to update
            update_data: Data to update

        Returns:
            Updated PlanEntrega instance
        """
        try:
            plan = self.repo.get_by_id(plan_id)
            if not plan:
                raise ValueError(f"Plan de entrega {plan_id} no encontrado")

            # Store original data for audit
            datos_anteriores = serialize_model(plan)

            # Update plan
            plan_actualizado = self.repo.update(plan, update_data)

            # Commit transaction
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'planes_entrega', 
                plan_id, 
                'UPDATE',
                datos_anteriores=datos_anteriores,
                datos_nuevos=serialize_model(plan_actualizado)
            )

            logger.info(f"Plan de entrega actualizado: {plan_id} - {plan_actualizado.nombre}")
            return plan_actualizado

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error actualizando plan de entrega {plan_id}: {str(e)}")
            raise

    def add_hito(self, plan_id: int, hito_data: Dict[str, Any], created_by: str) -> HitoEntrega:
        """Add new milestone to delivery plan"""
        try:
            plan = self.repo.get_by_id(plan_id)
            if not plan:
                raise ValueError(f"Plan de entrega {plan_id} no encontrado")

            logger.info(f"Plan encontrado: {plan.nombre}, hitos actuales: {len(plan.hitos)}")

            # Get next order number
            max_orden = db.session.query(func.coalesce(func.max(HitoEntrega.orden), 0)).filter_by(plan_entrega_id=plan_id).scalar()
            hito_data['orden'] = max_orden + 1

            logger.info(f"Próximo orden para hito: {hito_data['orden']}")

            # Validate required fields
            if not hito_data.get('titulo'):
                raise ValueError("Título del hito es requerido")
            if not hito_data.get('fecha_programada'):
                raise ValueError("Fecha programada es requerida")

            # Parse date if it's a string
            if isinstance(hito_data['fecha_programada'], str):
                try:
                    hito_data['fecha_programada'] = datetime.strptime(hito_data['fecha_programada'], '%Y-%m-%d').date()
                except ValueError as e:
                    logger.error(f"Error parsing date: {hito_data['fecha_programada']}")
                    raise ValueError(f"Formato de fecha inválido: {hito_data['fecha_programada']}")

            hito_data['plan_entrega_id'] = plan_id
            logger.info(f"Creando hito con datos: {hito_data}")
            
            hito = self.hitos_repo.create(hito_data, created_by)
            logger.info(f"Hito creado con ID: {hito.id}")

            # Force flush to ensure data is written to DB
            db.session.flush()
            
            # Verify hito was created
            verify_hito = db.session.query(HitoEntrega).filter_by(id=hito.id).first()
            if not verify_hito:
                raise Exception(f"Hito {hito.id} no se pudo verificar después del flush")
            
            logger.info(f"Hito verificado en base de datos: {verify_hito.titulo}")

            # Sync with calendar events
            try:
                from services.contrato_eventos_service import ContratoEventosService
                eventos_service = ContratoEventosService()
                eventos_service.actualizar_evento_desde_hito(hito.id)
            except Exception as e:
                logger.warning(f"Error sincronizando evento para nuevo hito {hito.id}: {str(e)}")

            # Commit the transaction
            db.session.commit()
            logger.info(f"Transacción completada exitosamente para hito {hito.id}")

            # Log audit (after commit to ensure data integrity)
            try:
                AuditService.log_action(
                    'hitos_entrega', 
                    hito.id, 
                    'CREATE', 
                    datos_nuevos=serialize_model(hito)
                )
            except Exception as e:
                logger.warning(f"Error en audit log: {str(e)}")

            # Expire all objects from session to force fresh queries
            db.session.expire_all()
            
            # Verify hito exists with direct query
            verify_hito_direct = db.session.query(HitoEntrega).filter_by(id=hito.id).first()
            if verify_hito_direct:
                logger.info(f"Direct hito verification successful: ID {verify_hito_direct.id}, Título: {verify_hito_direct.titulo}")
            else:
                logger.error(f"CRITICAL: Hito {hito.id} not found in direct verification!")
            
            # Count total hitos for plan with direct query
            total_hitos_direct = db.session.query(HitoEntrega).filter_by(plan_entrega_id=plan_id).count()
            logger.info(f"Direct count verification: Plan {plan_id} has {total_hitos_direct} total hitos")
            
            # List all hitos for debugging
            all_hitos_direct = (db.session.query(HitoEntrega)
                               .filter_by(plan_entrega_id=plan_id)
                               .order_by(HitoEntrega.orden, HitoEntrega.fecha_programada)
                               .all())
            
            logger.info(f"All hitos for plan {plan_id}:")
            for h in all_hitos_direct:
                logger.info(f"  - Hito ID: {h.id}, Título: {h.titulo}, Orden: {h.orden}")
            
            logger.info(f"Hito agregado al plan {plan_id}: {hito.titulo}")
            return hito

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error agregando hito al plan {plan_id}: {str(e)}")
            logger.exception("Full traceback for add_hito error:")
            raise

    def update_hito(self, hito_id: int, update_data: Dict[str, Any]) -> HitoEntrega:
        """
        Update hito de entrega

        Args:
            hito_id: Hito ID to update
            update_data: Data to update

        Returns:
            Updated HitoEntrega instance
        """
        try:
            hito = self.hitos_repo.get_by_id(hito_id)
            if not hito:
                raise ValueError(f"Hito de entrega {hito_id} no encontrado")

            # Store original data for audit
            datos_anteriores = serialize_model(hito)

            # Update hito
            hito_actualizado = self.hitos_repo.update(hito, update_data)

            # Commit transaction
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'hitos_entrega', 
                hito_id, 
                'UPDATE',
                datos_anteriores=datos_anteriores,
                datos_nuevos=serialize_model(hito_actualizado)
            )

            logger.info(f"Hito de entrega actualizado: {hito_id} - {hito_actualizado.titulo}")
            return hito_actualizado

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error actualizando hito de entrega {hito_id}: {str(e)}")
            raise

    def completar_hito(self, hito_id: int, notas: str, completed_by: str) -> HitoEntrega:
        """Mark milestone as completed"""
        try:
            hito = self.hitos_repo.get_by_id(hito_id)
            if not hito:
                raise ValueError(f"Hito {hito_id} no encontrado")

            if hito.estado == EstadoHitoEntrega.COMPLETADO:
                raise ValueError("El hito ya está completado")

            update_data = {
                'estado': EstadoHitoEntrega.COMPLETADO,
                'fecha_completado': datetime.now(),
                'notas_completado': notas,
                'completado_por': completed_by
            }

            hito_actualizado = self.hitos_repo.update(hito, update_data)

            # Sync with calendar events
            try:
                from services.contrato_eventos_service import ContratoEventosService
                eventos_service = ContratoEventosService()
                eventos_service.actualizar_evento_desde_hito(hito_id)
            except Exception as e:
                logger.warning(f"Error sincronizando evento para hito {hito_id}: {str(e)}")

            db.session.commit()

            logger.info(f"Hito completado: {hito_id}")
            return hito_actualizado

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error completando hito {hito_id}: {str(e)}")
            raise

    def get_proximos_hitos(self, dias: int = 7) -> List[HitoEntrega]:
        """Get upcoming hitos within specified days"""
        return self.hitos_repo.get_proximos_hitos(dias)

    def get_hitos_atrasados(self) -> List[HitoEntrega]:
        """Get overdue hitos and mark them as atrasados"""
        try:
            hitos_atrasados = self.hitos_repo.get_hitos_atrasados()

            # Update status to ATRASADO
            for hito in hitos_atrasados:
                if hito.estado == EstadoHitoEntrega.PENDIENTE:
                    self.hitos_repo.update(hito, {'estado': EstadoHitoEntrega.ATRASADO})

            db.session.commit()
            return hitos_atrasados

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error obteniendo hitos atrasados: {str(e)}")
            raise

    def delete_plan(self, plan_id: int) -> bool:
        """
        Delete plan de entrega and all its hitos

        Args:
            plan_id: Plan ID to delete

        Returns:
            True if successful
        """
        try:
            plan = self.repo.get_by_id(plan_id)
            if not plan:
                raise ValueError(f"Plan de entrega {plan_id} no encontrado")

            # Delete plan (cascade will delete hitos)
            self.repo.delete(plan)

            # Commit transaction
            db.session.commit()

            # Log audit
            AuditService.log_action(
                'planes_entrega', 
                plan_id, 
                'DELETE'
            )

            logger.info(f"Plan de entrega eliminado: {plan_id}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error eliminando plan de entrega {plan_id}: {str(e)}")
            raise

    def update_plan_hitos(self, plan_id: int, titulos: List[str], descripciones: List[str], 
                          fechas: List[str], hito_ids: List[str], updated_by: str) -> None:
        """
        Update plan hitos - updates existing ones and creates new ones as needed
        
        Args:
            plan_id: Plan ID
            titulos: List of hito titles
            descripciones: List of hito descriptions
            fechas: List of hito dates
            hito_ids: List of existing hito IDs (empty string for new hitos)
            updated_by: User ID making the changes
        """
        try:
            plan = self.repo.get_by_id(plan_id)
            if not plan:
                raise ValueError(f"Plan de entrega {plan_id} no encontrado")

            existing_hito_ids = set()
            
            # Process each hito
            for i, titulo in enumerate(titulos):
                if not titulo.strip():
                    continue
                    
                descripcion = descripciones[i] if i < len(descripciones) else ''
                fecha = fechas[i] if i < len(fechas) else None
                hito_id_str = hito_ids[i] if i < len(hito_ids) else ''
                
                # Parse date
                fecha_programada = None
                if fecha:
                    try:
                        fecha_programada = datetime.strptime(fecha, '%Y-%m-%d').date()
                    except ValueError:
                        continue
                
                if hito_id_str and hito_id_str.isdigit():
                    # Update existing hito
                    hito_id = int(hito_id_str)
                    existing_hito_ids.add(hito_id)
                    
                    hito = self.hitos_repo.get_by_id(hito_id)
                    if hito and hito.plan_entrega_id == plan_id:
                        # Only update if not completed
                        if hito.estado == EstadoHitoEntrega.PENDIENTE or hito.estado == EstadoHitoEntrega.ATRASADO:
                            update_data = {
                                'titulo': titulo.strip(),
                                'descripcion': descripcion,
                                'fecha_programada': fecha_programada,
                                'orden': i + 1
                            }
                            self.hitos_repo.update(hito, update_data)
                else:
                    # Create new hito
                    hito_data = {
                        'plan_entrega_id': plan_id,
                        'titulo': titulo.strip(),
                        'descripcion': descripcion,
                        'fecha_programada': fecha_programada,
                        'orden': i + 1
                    }
                    self.hitos_repo.create(hito_data, updated_by)
            
            # Delete hitos that were removed (only if they're not completed)
            all_hitos = self.hitos_repo.get_by_plan_id(plan_id)
            for hito in all_hitos:
                if (hito.id not in existing_hito_ids and 
                    hito.estado == EstadoHitoEntrega.PENDIENTE):
                    self.hitos_repo.delete(hito)
            
            db.session.commit()
            logger.info(f"Hitos actualizados para plan {plan_id}")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error actualizando hitos del plan {plan_id}: {str(e)}")
            raise

    def get_estadisticas_plan(self, plan_id: int) -> Dict[str, Any]:
        """
        Get statistics for a plan de entrega

        Args:
            plan_id: Plan ID

        Returns:
            Dictionary with statistics
        """
        plan = self.repo.get_by_id(plan_id)
        if not plan:
            raise ValueError(f"Plan de entrega {plan_id} no encontrado")

        hitos = plan.hitos
        total_hitos = len(hitos)
        hitos_completados = len([h for h in hitos if h.estado == EstadoHitoEntrega.COMPLETADO])
        hitos_atrasados = len([h for h in hitos if h.estado == EstadoHitoEntrega.ATRASADO])
        hitos_pendientes = len([h for h in hitos if h.estado == EstadoHitoEntrega.PENDIENTE])

        progreso_porcentaje = (hitos_completados / total_hitos * 100) if total_hitos > 0 else 0

        # Find next milestone
        hitos_pendientes_ordenados = [h for h in hitos 
                                    if h.estado == EstadoHitoEntrega.PENDIENTE]
        hitos_pendientes_ordenados.sort(key=lambda x: (x.fecha_programada, x.orden))
        proximo_hito = hitos_pendientes_ordenados[0] if hitos_pendientes_ordenados else None

        return {
            'total_hitos': total_hitos,
            'hitos_completados': hitos_completados,
            'hitos_atrasados': hitos_atrasados,
            'hitos_pendientes': hitos_pendientes,
            'progreso_porcentaje': round(progreso_porcentaje, 1),
            'proximo_hito': proximo_hito
        }