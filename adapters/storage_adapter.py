
import os
import uuid
import json
import subprocess
from typing import BinaryIO, Optional
from datetime import datetime, timedelta
import mimetypes
import logging

logger = logging.getLogger(__name__)

class StorageAdapter:
    """
    Adapter for Replit Storage service
    Provides file upload, download and deletion capabilities using Replit Object Storage
    """
    
    def __init__(self):
        self.base_url = os.environ.get("STORAGE_BASE_URL", "")
        self.bucket = os.environ.get("STORAGE_BUCKET", "manufacturing-app")
        
    def generate_storage_path(self, entity_type: str, entity_id: int, 
                            sub_entity: str = None, filename: str = None,
                            cliente_id: int = None, proyecto_id: int = None) -> str:
        """
        Generate standardized storage path following Cliente/Proyecto structure
        
        Args:
            entity_type: Type of entity (contratos, despachos, etc.)
            entity_id: ID of the entity
            sub_entity: Sub-entity type (docs, evidencias)
            filename: Original filename
            cliente_id: ID of the client (required for new structure)
            proyecto_id: ID of the project (required for new structure)
            
        Returns:
            Storage path following the Cliente/Proyecto structure
        """
        # For the new Cliente/Proyecto structure
        if cliente_id and proyecto_id and entity_type in ['contratos', 'despachos']:
            parts = [
                f"Cliente-{cliente_id}",
                f"Proyecto-{proyecto_id}",
                entity_type.title(),  # Contratos or Despachos
                str(entity_id)
            ]
            
            if sub_entity:
                parts.append(sub_entity)
                
            if filename:
                # Generate unique filename to avoid conflicts
                file_ext = os.path.splitext(filename)[1]
                unique_filename = f"{uuid.uuid4().hex}{file_ext}"
                parts.append(unique_filename)
                
            return "/".join(parts)
        
        # Fallback to legacy structure for backward compatibility
        else:
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
        Upload file to Replit Object Storage
        
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
            
            storage_key = f"{self.bucket}/{path}"
            
            # Save file temporarily for upload to Replit Object Storage
            temp_path = f"/tmp/{uuid.uuid4().hex}"
            with open(temp_path, 'wb') as temp_file:
                temp_file.write(file_stream.read())
            
            # Upload to Replit Object Storage using Node.js script
            result = self._upload_to_replit_storage(temp_path, storage_key)
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            if result.get('success'):
                logger.info(f"File uploaded successfully to Replit Object Storage: {storage_key}")
                return storage_key
            else:
                raise StorageError(f"Failed to upload to Replit Object Storage: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Error uploading file: {str(e)}")
            raise StorageError(f"Failed to upload file: {str(e)}")
    
    def get_url(self, key: str, expires_s: int = 3600) -> str:
        """
        Get signed URL for file access from Replit Object Storage
        
        Args:
            key: Storage key
            expires_s: URL expiration time in seconds
            
        Returns:
            Signed URL for file access
        """
        try:
            # Generate download URL using Replit Object Storage
            result = self._get_download_url(key)
            
            if result.get('success'):
                return result.get('url', f"/storage/download/{key}")
            else:
                # Fallback URL
                return f"/storage/download/{key}"
                
        except Exception as e:
            logger.error(f"Error generating URL for key {key}: {str(e)}")
            return f"/storage/download/{key}"
    
    def delete_file(self, key: str) -> bool:
        """
        Delete file from Replit Object Storage
        
        Args:
            key: Storage key
            
        Returns:
            True if deletion was successful
        """
        try:
            result = self._delete_from_replit_storage(key)
            
            if result.get('success'):
                logger.info(f"File deleted successfully from Replit Object Storage: {key}")
                return True
            else:
                logger.warning(f"Failed to delete file from Replit Object Storage: {key}")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting file {key}: {str(e)}")
            return False
    
    def file_exists(self, key: str) -> bool:
        """
        Check if file exists in Replit Object Storage
        
        Args:
            key: Storage key
            
        Returns:
            True if file exists
        """
        try:
            result = self._check_file_exists(key)
            return result.get('exists', False)
            
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
        try:
            if allowed_mimes is None:
                allowed_mimes = ['application/pdf', 'image/jpeg', 'image/png', 'image/jpg']
            
            # Check if filename is valid
            if not filename or not filename.strip():
                return False, "Filename is required"
            
            # Check file size
            try:
                file_stream.seek(0, 2)  # Go to end
                size_bytes = file_stream.tell()
                file_stream.seek(0)  # Reset to beginning
            except Exception as e:
                return False, f"Error reading file stream: {str(e)}"
            
            if size_bytes == 0:
                return False, "File is empty"
            
            max_size_bytes = max_size_mb * 1024 * 1024
            if size_bytes > max_size_bytes:
                return False, f"File size ({size_bytes / 1024 / 1024:.1f}MB) exceeds maximum allowed ({max_size_mb}MB)"
            
            # Check MIME type
            content_type, _ = mimetypes.guess_type(filename)
            if content_type is None:
                # Try to detect from file extension
                ext = os.path.splitext(filename.lower())[1]
                if ext == '.pdf':
                    content_type = 'application/pdf'
                elif ext in ['.jpg', '.jpeg']:
                    content_type = 'image/jpeg'
                elif ext == '.png':
                    content_type = 'image/png'
                else:
                    return False, f"Unable to determine file type for '{filename}'"
            
            if content_type not in allowed_mimes:
                return False, f"File type '{content_type}' not allowed. Allowed types: {', '.join(allowed_mimes)}"
            
            logger.info(f"File validation successful: {filename}, size: {size_bytes} bytes, type: {content_type}")
            return True, ""
            
        except Exception as e:
            logger.error(f"Error during file validation: {str(e)}")
            return False, f"Validation error: {str(e)}"

    def _upload_to_replit_storage(self, file_path: str, storage_key: str) -> dict:
        """Upload file to Replit Object Storage using Node.js client"""
        script = f"""
        const {{ Client }} = require('@replit/object-storage');
        const fs = require('fs');
        
        async function upload() {{
            try {{
                if (!fs.existsSync('{file_path}')) {{
                    console.log(JSON.stringify({{ success: false, error: 'File does not exist' }}));
                    return;
                }}
                
                const client = new Client();
                const fileContent = fs.readFileSync('{file_path}');
                
                console.error(`Uploading file of size: ${{fileContent.length}} bytes to ${{'{storage_key}'}}`);
                
                const result = await client.uploadFromBytes('{storage_key}', fileContent);
                
                if (result && result.ok) {{
                    console.log(JSON.stringify({{ success: true }}));
                }} else {{
                    const errorMsg = result?.error?.message || 'Upload failed - no error details';
                    console.log(JSON.stringify({{ success: false, error: errorMsg }}));
                }}
            }} catch (e) {{
                console.log(JSON.stringify({{ success: false, error: `Exception: ${{e.message}}` }}));
            }}
        }}
        
        upload().catch(e => {{
            console.log(JSON.stringify({{ success: false, error: `Promise rejection: ${{e.message}}` }}));
        }});
        """
        
        try:
            result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=30)
            
            logger.info(f"Node.js script stdout: {result.stdout}")
            if result.stderr:
                logger.warning(f"Node.js script stderr: {result.stderr}")
            
            if result.stdout:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}, stdout: {result.stdout}")
                    return {'success': False, 'error': f'Invalid JSON response: {result.stdout}'}
            else:
                return {
                    'success': False, 
                    'error': f'No stdout from Node.js script. Return code: {result.returncode}, stderr: {result.stderr}'
                }
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Upload timeout after 30 seconds'}
        except Exception as e:
            logger.error(f"Script execution failed: {str(e)}")
            return {'success': False, 'error': f'Script execution failed: {str(e)}'}

    def _delete_from_replit_storage(self, storage_key: str) -> dict:
        """Delete file from Replit Object Storage using Node.js client"""
        script = f"""
        const {{ Client }} = require('@replit/object-storage');
        
        async function deleteFile() {{
            try {{
                const client = new Client();
                const {{ ok, error }} = await client.delete('{storage_key}');
                
                if (ok) {{
                    console.log(JSON.stringify({{ success: true }}));
                }} else {{
                    console.log(JSON.stringify({{ success: false, error: error?.message || 'Delete failed' }}));
                }}
            }} catch (e) {{
                console.log(JSON.stringify({{ success: false, error: e.message }}));
            }}
        }}
        
        deleteFile();
        """
        
        try:
            result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
            if result.stdout:
                return json.loads(result.stdout)
            else:
                return {'success': False, 'error': 'No response from Node.js script'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _get_download_url(self, storage_key: str) -> dict:
        """Get download URL for file in Replit Object Storage"""
        script = f"""
        const {{ Client }} = require('@replit/object-storage');
        
        async function getUrl() {{
            try {{
                const client = new Client();
                // Check if file exists first
                const {{ ok, value, error }} = await client.downloadAsBytes('{storage_key}');
                
                if (ok) {{
                    // File exists, return a download URL
                    console.log(JSON.stringify({{ success: true, url: '/storage/download/{storage_key}' }}));
                }} else {{
                    console.log(JSON.stringify({{ success: false, error: error?.message || 'File not found' }}));
                }}
            }} catch (e) {{
                console.log(JSON.stringify({{ success: false, error: e.message }}));
            }}
        }}
        
        getUrl();
        """
        
        try:
            result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
            if result.stdout:
                return json.loads(result.stdout)
            else:
                return {'success': False, 'error': 'No response from Node.js script'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _check_file_exists(self, storage_key: str) -> dict:
        """Check if file exists in Replit Object Storage"""
        script = f"""
        const {{ Client }} = require('@replit/object-storage');
        
        async function checkExists() {{
            try {{
                const client = new Client();
                const {{ ok, value, error }} = await client.downloadAsBytes('{storage_key}');
                
                console.log(JSON.stringify({{ exists: ok }}));
            }} catch (e) {{
                console.log(JSON.stringify({{ exists: false }}));
            }}
        }}
        
        checkExists();
        """
        
        try:
            result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
            if result.stdout:
                return json.loads(result.stdout)
            else:
                return {'exists': False}
        except Exception as e:
            return {'exists': False}


class StorageError(Exception):
    """Custom exception for storage operations"""
    pass
