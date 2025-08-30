import os
import uuid
from typing import BinaryIO, Optional
from datetime import datetime, timedelta
import mimetypes
import logging

logger = logging.getLogger(__name__)

class StorageAdapter:
    """
    Adapter for Replit Storage service
    Provides file upload, download and deletion capabilities
    """
    
    def __init__(self):
        self.base_url = os.environ.get("STORAGE_BASE_URL", "")
        self.bucket = os.environ.get("STORAGE_BUCKET", "manufacturing-app")
        
    def generate_storage_path(self, entity_type: str, entity_id: int, 
                            sub_entity: str = None, filename: str = None) -> str:
        """
        Generate standardized storage path
        
        Args:
            entity_type: Type of entity (clientes, proyectos, contratos, etc.)
            entity_id: ID of the entity
            sub_entity: Sub-entity type (docs, qa, evidencias)
            filename: Original filename
            
        Returns:
            Storage path following the defined structure
        """
        parts = [entity_type, str(entity_id)]
        
        if sub_entity:
            parts.append(sub_entity)
            
        if filename:
            # Generate unique filename to avoid conflicts
            file_ext = os.path.splitext(filename)[1]
            unique_filename = f"{uuid.uuid4().hex}{file_ext}"
            parts.append(unique_filename)
            
        return "/".join(parts)
    
    def put_file(self, file_stream: BinaryIO, path: str, 
                content_type: str = None, filename: str = None) -> str:
        """
        Upload file to storage
        
        Args:
            file_stream: File stream to upload
            path: Storage path
            content_type: MIME type of the file
            filename: Original filename for MIME type detection
            
        Returns:
            Storage key for the uploaded file
        """
        try:
            # Auto-detect content type if not provided
            if not content_type and filename:
                content_type, _ = mimetypes.guess_type(filename)
                
            if not content_type:
                content_type = 'application/octet-stream'
            
            # For now, we'll use a simple file system storage
            # In production, this would integrate with Replit Storage API
            storage_key = f"{self.bucket}/{path}"
            
            # Create directory structure
            full_path = f"uploads/{storage_key}"
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Write file
            with open(full_path, 'wb') as f:
                f.write(file_stream.read())
                
            logger.info(f"File uploaded successfully: {storage_key}")
            return storage_key
            
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise StorageError(f"Failed to upload file: {str(e)}")
    
    def get_url(self, key: str, expires_s: int = 3600) -> str:
        """
        Get signed URL for file access
        
        Args:
            key: Storage key
            expires_s: URL expiration time in seconds
            
        Returns:
            Signed URL for file access
        """
        try:
            # For development, return a simple file URL
            # In production, this would generate a signed URL
            return f"/uploads/{key}"
            
        except Exception as e:
            logger.error(f"Error generating URL for key {key}: {str(e)}")
            raise StorageError(f"Failed to generate URL: {str(e)}")
    
    def delete_file(self, key: str) -> bool:
        """
        Delete file from storage
        
        Args:
            key: Storage key
            
        Returns:
            True if deletion was successful
        """
        try:
            full_path = f"uploads/{key}"
            if os.path.exists(full_path):
                os.remove(full_path)
                logger.info(f"File deleted successfully: {key}")
                return True
            else:
                logger.warning(f"File not found for deletion: {key}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting file {key}: {str(e)}")
            raise StorageError(f"Failed to delete file: {str(e)}")
    
    def file_exists(self, key: str) -> bool:
        """
        Check if file exists in storage
        
        Args:
            key: Storage key
            
        Returns:
            True if file exists
        """
        try:
            full_path = f"uploads/{key}"
            return os.path.exists(full_path)
            
        except Exception as e:
            logger.error(f"Error checking file existence {key}: {str(e)}")
            return False
    
    def validate_file(self, file_stream: BinaryIO, filename: str, 
                     max_size_mb: int = 25, allowed_mimes: list = None) -> tuple[bool, str]:
        """
        Validate uploaded file
        
        Args:
            file_stream: File stream to validate
            filename: Original filename
            max_size_mb: Maximum file size in MB
            allowed_mimes: List of allowed MIME types
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if allowed_mimes is None:
            allowed_mimes = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']
        
        # Check file size
        file_stream.seek(0, 2)  # Go to end
        size_bytes = file_stream.tell()
        file_stream.seek(0)  # Reset to beginning
        
        max_size_bytes = max_size_mb * 1024 * 1024
        if size_bytes > max_size_bytes:
            return False, f"File size ({size_bytes / 1024 / 1024:.1f}MB) exceeds maximum allowed ({max_size_mb}MB)"
        
        # Check MIME type
        content_type, _ = mimetypes.guess_type(filename)
        if content_type not in allowed_mimes:
            return False, f"File type '{content_type}' not allowed. Allowed types: {', '.join(allowed_mimes)}"
        
        return True, ""


class StorageError(Exception):
    """Custom exception for storage operations"""
    pass
