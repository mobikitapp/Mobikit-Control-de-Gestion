
#!/usr/bin/env python3
"""
Migration: Add fecha_entrega_embalaje field to ordenes_fabricacion table
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

def get_database_connection():
    """Get database connection from environment variables"""
    try:
        # Get connection parameters from environment
        db_params = {
            'host': os.getenv('PGHOST', 'localhost'),
            'port': os.getenv('PGPORT', '5432'),
            'database': os.getenv('PGDATABASE', 'manufacturing_db'),
            'user': os.getenv('PGUSER', 'user'),
            'password': os.getenv('PGPASSWORD', 'password')
        }
        
        # Try to connect
        conn = psycopg2.connect(**db_params)
        conn.autocommit = False
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        return None

def run_migration():
    """Run the migration to add fecha_entrega_embalaje field"""
    conn = get_database_connection()
    if not conn:
        print("Failed to connect to database")
        return False

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Check if the column already exists
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'ordenes_fabricacion' 
                AND column_name = 'fecha_entrega_embalaje'
            """)
            
            if cursor.fetchone():
                print("Column 'fecha_entrega_embalaje' already exists in ordenes_fabricacion table")
                return True

            # Add the new column
            print("Adding fecha_entrega_embalaje column to ordenes_fabricacion table...")
            cursor.execute("""
                ALTER TABLE ordenes_fabricacion 
                ADD COLUMN fecha_entrega_embalaje DATE;
            """)

            # Add a comment for documentation
            cursor.execute("""
                COMMENT ON COLUMN ordenes_fabricacion.fecha_entrega_embalaje 
                IS 'Fecha estimada de entrega del área de embalaje';
            """)

            conn.commit()
            print("✅ Successfully added fecha_entrega_embalaje column")
            return True

    except Exception as e:
        conn.rollback()
        print(f"❌ Error running migration: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    print("🔄 Starting migration: Add fecha_entrega_embalaje field")
    success = run_migration()
    if success:
        print("✅ Migration completed successfully")
        sys.exit(0)
    else:
        print("❌ Migration failed")
        sys.exit(1)
