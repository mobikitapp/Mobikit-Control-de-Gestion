
#!/usr/bin/env python3
"""
Migration: Fix audit_log entidad_id column to support string IDs
"""

import psycopg2
import os
from urllib.parse import urlparse

def get_db_connection():
    """Get database connection from environment"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    
    # Parse the database URL
    parsed = urlparse(database_url)
    
    return psycopg2.connect(
        host=parsed.hostname,
        port=parsed.port,
        database=parsed.path[1:],  # Remove leading slash
        user=parsed.username,
        password=parsed.password,
        sslmode='require'
    )

def migrate_audit_log_entidad_id():
    """Migrate audit_log entidad_id column from integer to varchar"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        print("Starting migration: Convert audit_log.entidad_id from integer to varchar(255)")
        
        # First, check if the column is already varchar
        cursor.execute("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name = 'audit_log' 
            AND column_name = 'entidad_id'
        """)
        
        result = cursor.fetchone()
        if result and result[0] in ['character varying', 'varchar', 'text']:
            print("Column entidad_id is already varchar/text type. Migration not needed.")
            return
        
        print("Converting entidad_id column from integer to varchar(255)...")
        
        # Convert the column type
        cursor.execute("""
            ALTER TABLE audit_log 
            ALTER COLUMN entidad_id TYPE VARCHAR(255) 
            USING entidad_id::VARCHAR(255)
        """)
        
        conn.commit()
        print("✅ Migration completed successfully!")
        print("audit_log.entidad_id is now VARCHAR(255)")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    migrate_audit_log_entidad_id()
