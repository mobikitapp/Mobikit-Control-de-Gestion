from typing import List, Optional, Dict, Any
from datetime import datetime
from app import db
from repositories.fabricacion_repo import FabricacionRepository, OrdenFabricacionItemRepository
from repositories.proyectos_repo import ProyectosRepository
from repositories.contratos_repo import ContratosRepository
from services.audit_service import AuditService, serialize_model
from schemas.fabricacion import OrdenFabricacionSearchFilters
from models import OrdenFabricacion, EstadoOF
import logging

logger = logging.getLogger(__name__)

class FabricacionService:
    """Service layer for OrdenFabricacion operations"""
    
    def __init__(self):
        self.repo = FabricacionRepository()
        self.items_repo = OrdenFabricacionItemRepository()
        self.proyectos_repo = ProyectosRepository()
        self.contratos_repo = ContratosRepository()
    
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
            
            # Force initial state to PENDIENTE_APROBACION_DISENO
            of_data['estado'] = EstadoOF.PENDIENTE_APROBACION_DISENO.value
            
            # Extract items data
            items_data = of_data.pop('items', [])
            
            # Create OF
            of = self.repo.create(of_data, created_by)
            
            # Create items
            for item_data in items_data:
                item_data['of_id'] = of.id
                self.items_repo.create(item_data)
            
            # Commit transaction
            db.session.commit()
            
            # Log audit
            AuditService.log_action(
                'ordenes_fabricacion', 
                of.id, 
                'CREATE', 
                datos_nuevos=serialize_model(of)
            )
            
            logger.info(f"OF creada: {of.id} - {of.codigo} con {len(items_data)} items")
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
    
    def change_of_status(self, of_id: int, new_status: EstadoOF, notas: str = None) -> bool:
        """
        Change OF status with business rules validation
        
        Args:
            of_id: OF ID
            new_status: New status enum
            notas: Optional notes for the status change
            
        Returns:
            True if status change was successful
        """
        try:
            of = self.repo.get_by_id(of_id)
            if not of:
                raise ValueError(f"OF {of_id} no encontrada")
            
            # Special validation for SECCIONANDO state
            if new_status == EstadoOF.SECCIONANDO:
                if not of.cantidad_tableros or of.cantidad_tableros <= 0:
                    raise ValueError("La cantidad de tableros es obligatoria y debe ser mayor a 0 para cambiar a estado seccionando")
            
            # Validate status transition
            can_change, error_msg = self.repo.can_change_status(of, new_status)
            if not can_change:
                raise ValueError(error_msg)
            
            # Store original data for audit
            datos_anteriores = serialize_model(of)
            
            # Update status and timestamps
            update_data = {'estado': new_status}
            
            # Set appropriate timestamp based on new status
            now = datetime.now()
            if new_status == EstadoOF.ENVIADO_A_FABRICACION and not of.fecha_inicio:
                update_data['fecha_inicio'] = now
            elif new_status == EstadoOF.FABRICACION_COMPLETA and not of.fecha_qc:
                update_data['fecha_qc'] = now
            elif new_status == EstadoOF.LISTO_PARA_DESPACHO and not of.fecha_fin:
                update_data['fecha_fin'] = now
            
            # Add notes if provided
            if notas:
                current_notes = of.notas or ""
                update_data['notas'] = f"{current_notes}\n[{now.strftime('%Y-%m-%d %H:%M')}] {new_status.value}: {notas}".strip()
            
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
            
            logger.info(f"Estado de OF cambiado: {of_id} -> {new_status.value}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cambiando estado de OF {of_id}: {str(e)}")
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
            if of.estado in [EstadoOF.ENVIADO_A_FABRICACION, EstadoOF.SECCIONANDO, EstadoOF.ENCHAPANDO, EstadoOF.MECANIZANDO, EstadoOF.FABRICACION_COMPLETA, EstadoOF.LISTO_PARA_DESPACHO, EstadoOF.DESPACHADO]:
                raise ValueError("No se puede eliminar una OF que está en producción o terminada")
            
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
    
    def get_pending_ofs_by_user(self, user_id: str, limit: int = 10) -> List[OrdenFabricacion]:
        """Get pending OFs assigned to a user"""
        try:
            return self.repo.get_pending_by_user(user_id, limit)
        except Exception as e:
            logger.error(f"Error obteniendo OFs pendientes del usuario {user_id}: {str(e)}")
            raise

