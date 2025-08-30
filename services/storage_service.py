from typing import BinaryIO, List, Dict, Any
from flask import current_app
from werkzeug.datastructures import FileStorage
from adapters.storage_adapter import StorageAdapter, StorageError
from services.audit_service import AuditService
from app import db
import logging

logger = logging.getLogger(__name__)

class StorageService:
    """
    High-level service for file storage operations
    Handles validation, uploading, and database record management
    """
    
    def __init__(self):
        self.adapter = StorageAdapter()
    
    def upload_file(self, file: FileStorage, entity_type: str, entity_id: int, 
                   sub_entity: str = None, file_type: str = None) -> Dict[str, Any]:
        """
        Upload a file and return metadata
        
        Args:
            file: Uploaded file
            entity_type: Type of entity (clientes, proyectos, etc.)
            entity_id: ID of the entity
            sub_entity: Sub-entity type (docs, qa, evidencias)
            file_type: Type of file for categorization
            
        Returns:
            Dictionary with file metadata
        """
        try:
            # Validate file
            max_size_mb = int(current_app.config.get('MAX_CONTENT_LENGTH', 25 * 1024 * 1024)) // (1024 * 1024)
            allowed_mimes = current_app.config.get('ALLOWED_MIME_TYPES', ['application/pdf', 'image/jpeg', 'image/png'])
            
            is_valid, error_msg = self.adapter.validate_file(
                file.stream, file.filename, max_size_mb, allowed_mimes
            )
            
            if not is_valid:
                raise StorageError(error_msg)
            
            # Generate storage path
            storage_path = self.adapter.generate_storage_path(
                entity_type, entity_id, sub_entity, file.filename
            )
            
            # Upload file
            storage_key = self.adapter.put_file(
                file.stream, storage_path, file.content_type, file.filename
            )
            
            # Get file size
            file.stream.seek(0, 2)
            size_bytes = file.stream.tell()
            file.stream.seek(0)
            
            # Prepare metadata
            metadata = {
                'storage_key': storage_key,
                'filename': file.filename,
                'mime_type': file.content_type,
                'size_bytes': size_bytes,
                'tipo': file_type
            }
            
            # Log the upload
            AuditService.log_action(
                f"{entity_type}_adjunto", 
                entity_id, 
                "CREATE", 
                datos_nuevos=metadata
            )
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise StorageError(f"Failed to upload file: {str(e)}")
    
    def delete_file(self, storage_key: str, entity_type: str, entity_id: int) -> bool:
        """
        Delete a file from storage
        
        Args:
            storage_key: Storage key of the file
            entity_type: Type of entity
            entity_id: ID of the entity
            
        Returns:
            True if deletion was successful
        """
        try:
            success = self.adapter.delete_file(storage_key)
            
            if success:
                # Log the deletion
                AuditService.log_action(
                    f"{entity_type}_adjunto", 
                    entity_id, 
                    "DELETE", 
                    datos_anteriores={'storage_key': storage_key}
                )
            
            return success
            
        except Exception as e:
            logger.error(f"Error deleting file: {str(e)}")
            raise StorageError(f"Failed to delete file: {str(e)}")
    
    def get_file_url(self, storage_key: str, expires_s: int = 3600) -> str:
        """
        Get URL for file access
        
        Args:
            storage_key: Storage key of the file
            expires_s: URL expiration time in seconds
            
        Returns:
            URL for file access
        """
        try:
            return self.adapter.get_url(storage_key, expires_s)
            
        except Exception as e:
            logger.error(f"Error generating file URL: {str(e)}")
            raise StorageError(f"Failed to generate file URL: {str(e)}")
    
    def validate_file_upload(self, file: FileStorage) -> tuple[bool, str]:
        """
        Validate file before upload
        
        Args:
            file: File to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not file or not file.filename:
            return False, "No file selected"
        
        max_size_mb = int(current_app.config.get('MAX_CONTENT_LENGTH', 25 * 1024 * 1024)) // (1024 * 1024)
        allowed_mimes = current_app.config.get('ALLOWED_MIME_TYPES', ['application/pdf', 'image/jpeg', 'image/png'])
        
        return self.adapter.validate_file(file.stream, file.filename, max_size_mb, allowed_mimes)
    
    def cleanup_orphaned_files(self, entity_type: str, valid_storage_keys: List[str]) -> int:
        """
        Clean up orphaned files that are no longer referenced in the database
        
        Args:
            entity_type: Type of entity
            valid_storage_keys: List of storage keys that should be kept
            
        Returns:
            Number of files deleted
        """
        # This would implement cleanup logic for orphaned files
        # For now, we'll just return 0 as a placeholder
        return 0
