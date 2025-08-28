
import os
import subprocess
import json
import uuid
from werkzeug.utils import secure_filename
from datetime import datetime

class ObjectStorageManager:
    def __init__(self, bucket_id="replit-objstore-18a58625-bff7-44cb-bbf9-e8b65ac6622c"):
        self.bucket_id = bucket_id
        
    def upload_file(self, file, folder="general", allowed_extensions=None):
        """Upload a file to Object Storage"""
        if allowed_extensions is None:
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'txt'}
        
        if not file or not file.filename:
            return None, "No file provided"
        
        # Check file extension
        if '.' not in file.filename or \
           file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
            return None, "File type not allowed"
        
        # Generate unique filename
        filename = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_filename = f"{folder}/{timestamp}_{unique_id}_{filename}"
        
        try:
            # Save file temporarily
            temp_path = f"/tmp/{unique_id}_{filename}"
            file.save(temp_path)
            
            # Upload to Object Storage using Node.js script
            result = self._upload_to_storage(temp_path, unique_filename)
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            if result.get('success'):
                return unique_filename, None
            else:
                return None, result.get('error', 'Upload failed')
                
        except Exception as e:
            return None, str(e)
    
    def delete_file(self, filename):
        """Delete a file from Object Storage"""
        try:
            result = self._delete_from_storage(filename)
            return result.get('success', False), result.get('error')
        except Exception as e:
            return False, str(e)
    
    def get_file_url(self, filename):
        """Get a temporary URL for a file"""
        try:
            result = self._get_file_url(filename)
            if result.get('success'):
                return result.get('url'), None
            else:
                return None, result.get('error', 'Failed to get URL')
        except Exception as e:
            return None, str(e)
    
    def _upload_to_storage(self, file_path, storage_path):
        """Upload file using Node.js script"""
        script = f"""
        const {{ Client }} = require('@replit/object-storage');
        const fs = require('fs');
        
        async function upload() {{
            try {{
                const client = new Client();
                const fileContent = fs.readFileSync('{file_path}');
                const {{ ok, error }} = await client.uploadFromBytes('{storage_path}', fileContent);
                
                if (ok) {{
                    console.log(JSON.stringify({{ success: true }}));
                }} else {{
                    console.log(JSON.stringify({{ success: false, error: error?.message || 'Upload failed' }}));
                }}
            }} catch (e) {{
                console.log(JSON.stringify({{ success: false, error: e.message }}));
            }}
        }}
        
        upload();
        """
        
        try:
            result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
            return json.loads(result.stdout) if result.stdout else {'success': False, 'error': 'No response'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _delete_from_storage(self, storage_path):
        """Delete file using Node.js script"""
        script = f"""
        const {{ Client }} = require('@replit/object-storage');
        
        async function deleteFile() {{
            try {{
                const client = new Client();
                const {{ ok, error }} = await client.delete('{storage_path}');
                
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
            return json.loads(result.stdout) if result.stdout else {'success': False, 'error': 'No response'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _get_file_url(self, storage_path):
        """Get file URL using Node.js script"""
        script = f"""
        const {{ Client }} = require('@replit/object-storage');
        
        async function getUrl() {{
            try {{
                const client = new Client();
                const {{ ok, value, error }} = await client.downloadAsBytes('{storage_path}');
                
                if (ok) {{
                    // For now, we'll return a placeholder URL since we can't directly serve from Object Storage
                    console.log(JSON.stringify({{ success: true, url: '/storage/{storage_path}' }}));
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
            return json.loads(result.stdout) if result.stdout else {'success': False, 'error': 'No response'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
