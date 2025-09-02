from typing import List, Optional, Dict, Any
from app import db
from repositories.clientes_repo import ClientesRepository
from services.audit_service import AuditService, serialize_model
from schemas.clientes import ClienteSearchFilters
from models import Cliente
import logging

logger = logging.getLogger(__name__)

class ClientesService:
    """Service layer for Cliente operations"""
    
    def __init__(self):
        self.repo = ClientesRepository()
    
    def create_cliente(self, cliente_data: Dict[str, Any], created_by: str) -> Cliente:
        """
        Create a new cliente with audit logging
        
        Args:
            cliente_data: Cliente data dictionary
            created_by: User ID who is creating the cliente
            
        Returns:
            Created Cliente instance
        """
        try:
            # Check if RUT already exists
            if self.repo.exists_rut(cliente_data['rut']):
                raise ValueError(f"Ya existe un cliente con RUT {cliente_data['rut']}")
            
            # Create cliente
            cliente = self.repo.create(cliente_data, created_by)
            
            # Commit transaction
            db.session.commit()
            
            # Log audit
            AuditService.log_action(
                'clientes', 
                cliente.id, 
                'CREATE', 
                datos_nuevos=serialize_model(cliente)
            )
            
            logger.info(f"Cliente creado: {cliente.id} - {cliente.nombre}")
            return cliente
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando cliente: {str(e)}")
            raise
    
    def get_cliente_by_id(self, cliente_id: int) -> Optional[Cliente]:
        """Get cliente by ID"""
        return self.repo.get_by_id(cliente_id)
    
    def get_cliente_with_stats(self, cliente_id: int) -> Optional[Dict[str, Any]]:
        """Get cliente with related statistics"""
        return self.repo.get_with_stats(cliente_id)
    
    def update_cliente(self, cliente_id: int, update_data: Dict[str, Any]) -> Cliente:
        """
        Update cliente with audit logging
        
        Args:
            cliente_id: Cliente ID to update
            update_data: Dictionary with fields to update
            
        Returns:
            Updated Cliente instance
        """
        try:
            cliente = self.repo.get_by_id(cliente_id)
            if not cliente:
                raise ValueError(f"Cliente {cliente_id} no encontrado")
            
            # Store original data for audit
            datos_anteriores = serialize_model(cliente)
            
            # Check RUT uniqueness if updating RUT
            if 'rut' in update_data and update_data['rut'] != cliente.rut:
                if self.repo.exists_rut(update_data['rut'], exclude_id=cliente_id):
                    raise ValueError(f"Ya existe un cliente con RUT {update_data['rut']}")
            
            # Update cliente
            cliente_actualizado = self.repo.update(cliente, update_data)
            
            # Commit transaction
            db.session.commit()
            
            # Log audit
            AuditService.log_action(
                'clientes', 
                cliente_id, 
                'UPDATE',
                datos_anteriores=datos_anteriores,
                datos_nuevos=serialize_model(cliente_actualizado)
            )
            
            logger.info(f"Cliente actualizado: {cliente_id} - {cliente_actualizado.nombre}")
            return cliente_actualizado
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error actualizando cliente {cliente_id}: {str(e)}")
            raise
    
    def delete_cliente(self, cliente_id: int) -> bool:
        """
        Soft delete cliente (set activo = False)
        
        Args:
            cliente_id: Cliente ID to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            cliente = self.repo.get_by_id(cliente_id)
            if not cliente:
                raise ValueError(f"Cliente {cliente_id} no encontrado")
            
            # Store original data for audit
            datos_anteriores = serialize_model(cliente)
            
            # Soft delete
            success = self.repo.delete(cliente)
            
            if success:
                # Commit transaction
                db.session.commit()
                
                # Log audit
                AuditService.log_action(
                    'clientes', 
                    cliente_id, 
                    'DELETE',
                    datos_anteriores=datos_anteriores
                )
                
                logger.info(f"Cliente eliminado: {cliente_id} - {cliente.nombre}")
                return True
            
            return False
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error eliminando cliente {cliente_id}: {str(e)}")
            raise
    
    def search_clientes(self, filters: ClienteSearchFilters) -> tuple[List[Cliente], int]:
        """
        Search clientes with filters and pagination
        
        Args:
            filters: Search filters
            
        Returns:
            Tuple of (clientes_list, total_count)
        """
        try:
            return self.repo.search(filters)
        except Exception as e:
            logger.error(f"Error buscando clientes: {str(e)}")
            raise
    
    def get_active_clientes(self) -> List[Cliente]:
        """Get all active clientes"""
        try:
            return self.repo.get_all_active()
        except Exception as e:
            logger.error(f"Error obteniendo clientes activos: {str(e)}")
            raise
    
    def count_active_clientes(self) -> int:
        """Count active clientes"""
        try:
            return self.repo.count_active()
        except Exception as e:
            logger.error(f"Error contando clientes activos: {str(e)}")
            raise
    
    def get_recent_clientes(self, limit: int = 10) -> List[Cliente]:
        """Get recently created clientes"""
        try:
            return self.repo.get_recent(limit)
        except Exception as e:
            logger.error(f"Error obteniendo clientes recientes: {str(e)}")
            raise
    
    def get_clientes_with_active_projects(self) -> List[Dict[str, Any]]:
        """Get all active clientes with their active projects"""
        try:
            return self.repo.get_all_with_active_projects()
        except Exception as e:
            logger.error(f"Error obteniendo clientes con proyectos activos: {str(e)}")
            raise

