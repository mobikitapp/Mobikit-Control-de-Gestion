from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, date
import logging

from app import db
from models import PlanEntrega, HitoEntrega, EstadoHitoEntrega, Contrato
from repositories.planes_entrega_repo import PlanesEntregaRepository, HitosEntregaRepository
from repositories.contratos_repo import ContratosRepository
from services.audit_service import AuditService, serialize_model

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
        """
        Add hito to plan de entrega
        
        Args:
            plan_id: Plan ID
            hito_data: Hito data dictionary
            created_by: User ID who is creating the hito
            
        Returns:
            Created HitoEntrega instance
        """
        try:
            plan = self.repo.get_by_id(plan_id)
            if not plan:
                raise ValueError(f"Plan de entrega {plan_id} no encontrado")
            
            hito_data['plan_entrega_id'] = plan_id
            
            # If no order specified, set to next available
            if 'orden' not in hito_data:
                existing_hitos = self.hitos_repo.get_by_plan_id(plan_id)
                max_orden = max([h.orden for h in existing_hitos], default=0)
                hito_data['orden'] = max_orden + 1
            
            # Create hito
            hito = self.hitos_repo.create(hito_data, created_by)
            
            # Commit transaction
            db.session.commit()
            
            logger.info(f"Hito agregado al plan {plan_id}: {hito.titulo}")
            return hito
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error agregando hito al plan {plan_id}: {str(e)}")
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
    
    def completar_hito(self, hito_id: int, notas_completado: str, completado_por: str) -> HitoEntrega:
        """
        Mark hito as completed
        
        Args:
            hito_id: Hito ID to complete
            notas_completado: Completion notes
            completado_por: User ID who is completing the hito
            
        Returns:
            Updated HitoEntrega instance
        """
        try:
            hito = self.hitos_repo.get_by_id(hito_id)
            if not hito:
                raise ValueError(f"Hito de entrega {hito_id} no encontrado")
            
            if hito.estado == EstadoHitoEntrega.COMPLETADO:
                raise ValueError("El hito ya está completado")
            
            # Update hito
            update_data = {
                'estado': EstadoHitoEntrega.COMPLETADO,
                'fecha_completado': datetime.utcnow(),
                'notas_completado': notas_completado,
                'completado_por': completado_por
            }
            
            hito_actualizado = self.hitos_repo.update(hito, update_data)
            
            # Check if all hitos in plan are completed
            hitos_plan = self.hitos_repo.get_by_plan_id(hito.plan_entrega_id)
            todos_completados = all(h.estado == EstadoHitoEntrega.COMPLETADO for h in hitos_plan)
            
            if todos_completados:
                logger.info(f"Todos los hitos del plan {hito.plan_entrega_id} han sido completados")
            
            # Commit transaction
            db.session.commit()
            
            logger.info(f"Hito completado: {hito_id} - {hito_actualizado.titulo}")
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