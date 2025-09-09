
#!/usr/bin/env python3
"""
Migration to remove the redundant usuarios table and update foreign key references
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

def migrate_remove_usuarios_table():
    """Remove usuarios table and update foreign key references"""
    
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("DATABASE_URL environment variable not set")
        return
    
    conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    try:
        print("Starting migration to remove usuarios table...")
        
        # First, check if usuarios table exists
        cursor.execute("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables 
                WHERE table_name = 'usuarios'
            )
        """)
        
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            print("Found usuarios table, proceeding with removal...")
            
            # Drop foreign key constraints first
            constraints_to_drop = [
                "ALTER TABLE proyectos DROP CONSTRAINT IF EXISTS proyectos_diseñador_id_fkey",
                "ALTER TABLE proyectos DROP CONSTRAINT IF EXISTS proyectos_supervisor_id_fkey", 
                "ALTER TABLE tareas DROP CONSTRAINT IF EXISTS tareas_usuario_asignado_id_fkey",
                "ALTER TABLE auditoria DROP CONSTRAINT IF EXISTS auditoria_usuario_id_fkey",
                "ALTER TABLE recordatorios DROP CONSTRAINT IF EXISTS recordatorios_usuario_id_fkey",
                "ALTER TABLE documentos_proyecto DROP CONSTRAINT IF EXISTS documentos_proyecto_usuario_subida_id_fkey"
            ]
            
            for constraint_sql in constraints_to_drop:
                try:
                    cursor.execute(constraint_sql)
                    print(f"✓ Dropped constraint: {constraint_sql.split()[-1]}")
                except Exception as e:
                    print(f"Warning: Could not drop constraint: {e}")
            
            # Now drop the usuarios table
            cursor.execute("DROP TABLE IF EXISTS usuarios CASCADE")
            print("✓ Dropped usuarios table")
            
            # Update foreign key columns to VARCHAR(255) to match users.id
            column_updates = [
                "ALTER TABLE proyectos ALTER COLUMN diseñador_id TYPE VARCHAR(255)",
                "ALTER TABLE proyectos ALTER COLUMN supervisor_id TYPE VARCHAR(255)",
                "ALTER TABLE tareas ALTER COLUMN usuario_asignado_id TYPE VARCHAR(255)",
                "ALTER TABLE auditoria ALTER COLUMN usuario_id TYPE VARCHAR(255)",
                "ALTER TABLE recordatorios ALTER COLUMN usuario_id TYPE VARCHAR(255)",
                "ALTER TABLE documentos_proyecto ALTER COLUMN usuario_subida_id TYPE VARCHAR(255)"
            ]
            
            for update_sql in column_updates:
                try:
                    cursor.execute(update_sql)
                    print(f"✓ Updated column type: {update_sql}")
                except Exception as e:
                    print(f"Warning: Could not update column: {e}")
            
            # Add foreign key constraints back to users table
            new_constraints = [
                "ALTER TABLE proyectos ADD CONSTRAINT proyectos_diseñador_id_fkey FOREIGN KEY (diseñador_id) REFERENCES users(id)",
                "ALTER TABLE proyectos ADD CONSTRAINT proyectos_supervisor_id_fkey FOREIGN KEY (supervisor_id) REFERENCES users(id)",
                "ALTER TABLE tareas ADD CONSTRAINT tareas_usuario_asignado_id_fkey FOREIGN KEY (usuario_asignado_id) REFERENCES users(id)",
                "ALTER TABLE auditoria ADD CONSTRAINT auditoria_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES users(id)",
                "ALTER TABLE recordatorios ADD CONSTRAINT recordatorios_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES users(id)",
                "ALTER TABLE documentos_proyecto ADD CONSTRAINT documentos_proyecto_usuario_subida_id_fkey FOREIGN KEY (usuario_subida_id) REFERENCES users(id)"
            ]
            
            for constraint_sql in new_constraints:
                try:
                    cursor.execute(constraint_sql)
                    print(f"✓ Added constraint: {constraint_sql.split()[-3]}")
                except Exception as e:
                    print(f"Warning: Could not add constraint: {e}")
            
            conn.commit()
            print("✅ Migration completed successfully!")
            
        else:
            print("usuarios table not found, nothing to migrate")
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    migrate_remove_usuarios_table()
