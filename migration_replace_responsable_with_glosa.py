
#!/usr/bin/env python3
"""
Migration script to replace responsable_area field with glosa field in orden_area_progreso table
"""

import sqlite3
import sys
from datetime import datetime

def migrate_responsable_to_glosa():
    """Replace responsable_area column with glosa column"""
    
    try:
        # Connect to database
        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()
        
        print("Starting migration: Replace responsable_area with glosa...")
        
        # Check if the table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='orden_area_progreso'
        """)
        
        if not cursor.fetchone():
            print("Table orden_area_progreso does not exist. Nothing to migrate.")
            return True
        
        # Check current schema
        cursor.execute("PRAGMA table_info(orden_area_progreso)")
        columns = {row[1]: row for row in cursor.fetchall()}
        
        has_responsable = 'responsable_area' in columns
        has_glosa = 'glosa' in columns
        
        print(f"Current schema - Has responsable_area: {has_responsable}, Has glosa: {has_glosa}")
        
        if has_glosa and not has_responsable:
            print("Migration already completed. Glosa column exists and responsable_area doesn't.")
            return True
        
        # Create new table with updated schema
        cursor.execute("""
            CREATE TABLE orden_area_progreso_new (
                id INTEGER PRIMARY KEY,
                orden_fabricacion_id INTEGER NOT NULL,
                area_id INTEGER NOT NULL,
                estado_id INTEGER NOT NULL,
                fecha_ingreso_area DATETIME NOT NULL,
                fecha_cambio_estado DATETIME NOT NULL,
                glosa TEXT,
                tiempo_estimado_horas DECIMAL(10,2),
                notas_area TEXT,
                es_actual BOOLEAN NOT NULL DEFAULT 1,
                archivado BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                FOREIGN KEY (orden_fabricacion_id) REFERENCES ordenes_fabricacion (id),
                FOREIGN KEY (area_id) REFERENCES areas (id),
                FOREIGN KEY (estado_id) REFERENCES area_estados (id),
                FOREIGN KEY (created_by) REFERENCES users (id)
            )
        """)
        
        # Copy data from old table to new table
        if has_responsable:
            # If we have responsable_area, we'll convert it to a glosa description
            cursor.execute("""
                INSERT INTO orden_area_progreso_new (
                    id, orden_fabricacion_id, area_id, estado_id,
                    fecha_ingreso_area, fecha_cambio_estado, glosa,
                    tiempo_estimado_horas, notas_area, es_actual, archivado,
                    created_at, updated_at, created_by
                )
                SELECT 
                    p.id, p.orden_fabricacion_id, p.area_id, p.estado_id,
                    p.fecha_ingreso_area, p.fecha_cambio_estado,
                    CASE 
                        WHEN p.responsable_area IS NOT NULL THEN 
                            'Responsable: ' || COALESCE(u.first_name || ' ' || u.last_name, u.email, p.responsable_area)
                        ELSE NULL
                    END as glosa,
                    p.tiempo_estimado_horas, p.notas_area, p.es_actual, p.archivado,
                    p.created_at, p.updated_at, p.created_by
                FROM orden_area_progreso p
                LEFT JOIN users u ON p.responsable_area = u.id
            """)
        else:
            # Just copy the data as-is
            cursor.execute("""
                INSERT INTO orden_area_progreso_new (
                    id, orden_fabricacion_id, area_id, estado_id,
                    fecha_ingreso_area, fecha_cambio_estado, glosa,
                    tiempo_estimado_horas, notas_area, es_actual, archivado,
                    created_at, updated_at, created_by
                )
                SELECT 
                    id, orden_fabricacion_id, area_id, estado_id,
                    fecha_ingreso_area, fecha_cambio_estado, NULL as glosa,
                    tiempo_estimado_horas, notas_area, es_actual, archivado,
                    created_at, updated_at, created_by
                FROM orden_area_progreso
            """)
        
        # Drop old table and rename new table
        cursor.execute("DROP TABLE orden_area_progreso")
        cursor.execute("ALTER TABLE orden_area_progreso_new RENAME TO orden_area_progreso")
        
        # Recreate indexes
        cursor.execute("CREATE INDEX idx_progreso_orden ON orden_area_progreso(orden_fabricacion_id)")
        cursor.execute("CREATE INDEX idx_progreso_area ON orden_area_progreso(area_id)")
        cursor.execute("CREATE INDEX idx_progreso_estado ON orden_area_progreso(estado_id)")
        cursor.execute("CREATE INDEX idx_progreso_actual ON orden_area_progreso(orden_fabricacion_id, es_actual)")
        cursor.execute("CREATE INDEX idx_progreso_archivado ON orden_area_progreso(archivado)")
        cursor.execute("CREATE INDEX idx_progreso_fechas ON orden_area_progreso(fecha_ingreso_area, fecha_cambio_estado)")
        
        # Commit changes
        conn.commit()
        
        print("✅ Migration completed successfully!")
        print("- Replaced responsable_area column with glosa column")
        print("- Converted existing responsable data to glosa descriptions")
        print("- Recreated all indexes")
        
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
        return False
        
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("=== Mobikit Database Migration ===")
    print("Replacing responsable_area with glosa in orden_area_progreso table")
    print(f"Started at: {datetime.now()}")
    print()
    
    success = migrate_responsable_to_glosa()
    
    print()
    if success:
        print("Migration completed successfully! 🎉")
        sys.exit(0)
    else:
        print("Migration failed! ❌")
        sys.exit(1)
