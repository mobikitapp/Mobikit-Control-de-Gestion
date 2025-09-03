from typing import List, Optional, Dict, Any
from datetime import datetime
from werkzeug.datastructures import FileStorage
from app import db
from repositories.despachos_repo import DespachosRepository, DespachoAdjuntosRepository
from repositories.proyectos_repo import ProyectosRepository
from repositories.fabricacion_repo import FabricacionRepository
from services.audit_service import AuditService, serialize_model
from services.storage_service import StorageService
from schemas.despachos import DespachoSearchFilters
from models import Despacho, DespachoAdjunto, EstadoDespacho, TipoAdjunto
import logging

logger = logging.getLogger(__name__)

class DespachosService:
    """Service layer for Despacho operations"""
    
    def __init__(self):
        self.repo = DespachosRepository()
        self.adjuntos_repo = DespachoAdjuntosRepository()
        self.proyectos_repo = ProyectosRepository()
        self.fabricacion_repo = FabricacionRepository()
        self.storage_service = StorageService()
    
    def create_despacho(self, despacho_data: Dict[str, Any], created_by: str) -> Despacho:
        """
        Create a new despacho with validation and audit logging
        
        Args:
            despacho_data: Despacho data dictionary
            created_by: User ID who is creating the despacho
            
        Returns:
            Created Despacho instance
        """
        try:
            # Validate proyecto exists
            proyecto = self.proyectos_repo.get_by_id(despacho_data['proyecto_id'])
            if not proyecto:
                raise ValueError(f"Proyecto {despacho_data['proyecto_id']} no encontrado")
            
            # Validate hito_entrega if provided
            if despacho_data.get('hito_entrega_id'):
                from models import HitoEntrega
                hito = db.session.query(HitoEntrega).filter_by(id=despacho_data['hito_entrega_id']).first()
                if not hito:
                    raise ValueError(f"Hito de entrega {despacho_data['hito_entrega_id']} no encontrado")
            
            # Check if numero_despacho already exists
            if self.repo.exists_numero(despacho_data['numero_despacho']):
                raise ValueError(f"Ya existe un despacho con número {despacho_data['numero_despacho']}")
            
            # Separate ordenes_fabricacion from despacho_data
            ordenes_fabricacion = despacho_data.pop('ordenes_fabricacion', [])
            
            # Create despacho
            despacho = self.repo.create(despacho_data, created_by)
            
            # Create associated DespachoOrdenFabricacion records
            if ordenes_fabricacion:
                from models import DespachoOrdenFabricacion, TipoDespacho
                
                for of_data in ordenes_fabricacion:
                    despacho_of = DespachoOrdenFabricacion(
                        despacho_id=despacho.id,
                        orden_fabricacion_id=of_data['orden_fabricacion_id'],
                        tipo_despacho=TipoDespacho(of_data['tipo_despacho']),
                        cantidad_despachada=of_data['cantidad_despachada'],
                        cantidad_total=of_data['cantidad_total'],
                        observaciones=of_data.get('observaciones'),
                        created_by=created_by
                    )
                    db.session.add(despacho_of)
            
            # Commit transaction
            db.session.commit()
            
            # Log audit
            AuditService.log_action(
                'despachos', 
                despacho.id, 
                'CREATE', 
                datos_nuevos=serialize_model(despacho)
            )
            
            logger.info(f"Despacho creado: {despacho.id} - {despacho.numero_despacho}")
            return despacho
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando despacho: {str(e)}")
            raise
    
    def create_despacho_with_files(self, despacho_data: Dict[str, Any], 
                                   files: List[FileStorage], created_by: str) -> Despacho:
        """
        Create despacho with file uploads in a single transaction
        
        Args:
            despacho_data: Despacho data dictionary
            files: List of uploaded files
            created_by: User ID who is creating the despacho
            
        Returns:
            Created Despacho instance
        """
        try:
            # Create despacho
            despacho = self.create_despacho(despacho_data, created_by)
            
            # Upload files
            for file in files:
                if file and file.filename:
                    self.add_despacho_attachment(despacho.id, file, 'foto', created_by)
            
            logger.info(f"Despacho creado con {len(files)} archivos: {despacho.numero_despacho}")
            return despacho
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando despacho con archivos: {str(e)}")
            raise
    
    def get_despacho_by_id(self, despacho_id: int) -> Optional[Despacho]:
        """Get despacho by ID with related data"""
        return self.repo.get_by_id(despacho_id)
    
    def update_despacho(self, despacho_id: int, update_data: Dict[str, Any]) -> Despacho:
        """
        Update despacho with validation and audit logging
        
        Args:
            despacho_id: Despacho ID to update
            update_data: Dictionary with fields to update
            
        Returns:
            Updated Despacho instance
        """
        try:
            despacho = self.repo.get_by_id(despacho_id)
            if not despacho:
                raise ValueError(f"Despacho {despacho_id} no encontrado")
            
            # Store original data for audit
            datos_anteriores = serialize_model(despacho)
            
            # Validate proyecto if updating proyecto_id
            if 'proyecto_id' in update_data and update_data['proyecto_id'] != despacho.proyecto_id:
                proyecto = self.proyectos_repo.get_by_id(update_data['proyecto_id'])
                if not proyecto:
                    raise ValueError(f"Proyecto {update_data['proyecto_id']} no encontrado")
            
            # Validate hito_entrega if updating hito_entrega_id
            if 'hito_entrega_id' in update_data:
                if update_data['hito_entrega_id'] and update_data['hito_entrega_id'] != despacho.hito_entrega_id:
                    from models import HitoEntrega
                    hito = db.session.query(HitoEntrega).filter_by(id=update_data['hito_entrega_id']).first()
                    if not hito:
                        raise ValueError(f"Hito de entrega {update_data['hito_entrega_id']} no encontrado")
            
            # Check numero_despacho uniqueness if updating numero_despacho
            if 'numero_despacho' in update_data and update_data['numero_despacho'] != despacho.numero_despacho:
                if self.repo.exists_numero(update_data['numero_despacho'], exclude_id=despacho_id):
                    raise ValueError(f"Ya existe un despacho con número {update_data['numero_despacho']}")
            
            # Update despacho
            despacho_actualizado = self.repo.update(despacho, update_data)
            
            # Commit transaction
            db.session.commit()
            
            # Log audit
            AuditService.log_action(
                'despachos', 
                despacho_id, 
                'UPDATE',
                datos_anteriores=datos_anteriores,
                datos_nuevos=serialize_model(despacho_actualizado)
            )
            
            logger.info(f"Despacho actualizado: {despacho_id} - {despacho_actualizado.numero_despacho}")
            return despacho_actualizado
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error actualizando despacho {despacho_id}: {str(e)}")
            raise
    
    def change_despacho_status(self, despacho_id: int, new_status: EstadoDespacho, 
                              observaciones: str = None) -> bool:
        """
        Change despacho status with business rules validation
        
        Args:
            despacho_id: Despacho ID
            new_status: New status enum
            observaciones: Optional observations for the status change
            
        Returns:
            True if status change was successful
        """
        try:
            despacho = self.repo.get_by_id(despacho_id)
            if not despacho:
                raise ValueError(f"Despacho {despacho_id} no encontrado")
            
            # Validate status transition
            can_change, error_msg = self.repo.can_change_status(despacho, new_status)
            if not can_change:
                raise ValueError(error_msg)
            
            # Store original data for audit
            datos_anteriores = serialize_model(despacho)
            
            # Update status and timestamps
            update_data = {'estado': new_status}
            
            # Set appropriate timestamp based on new status
            now = datetime.now()
            if new_status == EstadoDespacho.EN_TRANSPORTE and not despacho.fecha_envio:
                update_data['fecha_envio'] = now
            elif new_status == EstadoDespacho.ENTREGADO and not despacho.fecha_entrega:
                update_data['fecha_entrega'] = now
            
            # Add observations if provided
            if observaciones:
                current_obs = despacho.observaciones or ""
                update_data['observaciones'] = f"{current_obs}\n[{now.strftime('%Y-%m-%d %H:%M')}] {new_status.value}: {observaciones}".strip()
            
            # Update despacho
            despacho_actualizado = self.repo.update(despacho, update_data)
            
            # Commit transaction
            db.session.commit()
            
            # Log audit
            AuditService.log_action(
                'despachos', 
                despacho_id, 
                'UPDATE',
                datos_anteriores=datos_anteriores,
                datos_nuevos=serialize_model(despacho_actualizado)
            )
            
            logger.info(f"Estado de despacho cambiado: {despacho_id} -> {new_status.value}")
            return True
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cambiando estado de despacho {despacho_id}: {str(e)}")
            raise
    
    def add_despacho_attachment(self, despacho_id: int, file: FileStorage, 
                               tipo: str, created_by: str) -> DespachoAdjunto:
        """
        Add attachment to despacho
        
        Args:
            despacho_id: Despacho ID
            file: Uploaded file
            tipo: Type of attachment
            created_by: User ID who is uploading
            
        Returns:
            Created DespachoAdjunto instance
        """
        try:
            despacho = self.repo.get_by_id(despacho_id)
            if not despacho:
                raise ValueError(f"Despacho {despacho_id} no encontrado")
            
            # Upload file
            file_metadata = self.storage_service.upload_file(
                file, 'despachos', despacho_id, 'evidencias', tipo
            )
            
            # Create adjunto record
            adjunto_data = {
                'despacho_id': despacho_id,
                'storage_key': file_metadata['storage_key'],
                'filename': file_metadata['filename'],
                'mime_type': file_metadata['mime_type'],
                'size_bytes': file_metadata['size_bytes'],
                'tipo': TipoAdjunto(tipo)
            }
            
            adjunto = self.adjuntos_repo.create(adjunto_data, created_by)
            
            # Commit transaction
            db.session.commit()
            
            logger.info(f"Adjunto agregado al despacho {despacho_id}: {file.filename}")
            return adjunto
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error agregando adjunto al despacho {despacho_id}: {str(e)}")
            raise
    
    def delete_despacho_attachment(self, adjunto_id: int) -> int:
        """
        Delete despacho attachment
        
        Args:
            adjunto_id: Adjunto ID to delete
            
        Returns:
            Despacho ID of the deleted attachment
        """
        try:
            adjunto = self.adjuntos_repo.get_by_id(adjunto_id)
            if not adjunto:
                raise ValueError(f"Adjunto {adjunto_id} no encontrado")
            
            despacho_id = adjunto.despacho_id
            
            # Delete file from storage
            self.storage_service.delete_file(adjunto.storage_key, 'despachos', despacho_id)
            
            # Delete adjunto record
            self.adjuntos_repo.delete(adjunto)
            
            # Commit transaction
            db.session.commit()
            
            logger.info(f"Adjunto eliminado del despacho {despacho_id}: {adjunto.filename}")
            return despacho_id
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error eliminando adjunto {adjunto_id}: {str(e)}")
            raise
    
    def delete_despacho(self, despacho_id: int) -> bool:
        """
        Delete despacho with validation
        
        Args:
            despacho_id: Despacho ID to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            despacho = self.repo.get_by_id(despacho_id)
            if not despacho:
                raise ValueError(f"Despacho {despacho_id} no encontrado")
            
            # Check if despacho can be deleted (business rules)
            if despacho.estado == EstadoDespacho.ENTREGADO:
                raise ValueError("No se puede eliminar un despacho que ya fue entregado")
            
            # Store original data for audit
            datos_anteriores = serialize_model(despacho)
            
            # Delete adjuntos first
            for adjunto in despacho.adjuntos:
                self.storage_service.delete_file(adjunto.storage_key, 'despachos', despacho_id)
                self.adjuntos_repo.delete(adjunto)
            
            # Delete despacho
            success = self.repo.delete(despacho)
            
            if success:
                # Commit transaction
                db.session.commit()
                
                # Log audit
                AuditService.log_action(
                    'despachos', 
                    despacho_id, 
                    'DELETE',
                    datos_anteriores=datos_anteriores
                )
                
                logger.info(f"Despacho eliminado: {despacho_id} - {despacho.numero_despacho}")
                return True
            
            return False
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error eliminando despacho {despacho_id}: {str(e)}")
            raise
    
    def search_despachos(self, filters: DespachoSearchFilters) -> tuple[List[Despacho], int]:
        """
        Search despachos with filters and pagination
        
        Args:
            filters: Search filters
            
        Returns:
            Tuple of (despachos_list, total_count)
        """
        try:
            return self.repo.search(filters)
        except Exception as e:
            logger.error(f"Error buscando despachos: {str(e)}")
            raise

