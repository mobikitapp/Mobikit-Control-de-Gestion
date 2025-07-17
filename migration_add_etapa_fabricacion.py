
import sqlite3

def migrate_database():
    """Add etapa_fabricacion column to tareas table"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(tareas)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'etapa_fabricacion' not in columns:
            cursor.execute('''
                ALTER TABLE tareas 
                ADD COLUMN etapa_fabricacion TEXT 
                CHECK (etapa_fabricacion IN ('seccionado', 'enchapado', 'mecanizado', 'fabricacion_completo'))
            ''')
            
            print("Column etapa_fabricacion added successfully")
        else:
            print("Column etapa_fabricacion already exists")
        
        # Create despacho_archivos table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS despacho_archivos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                despacho_id INTEGER NOT NULL,
                tipo TEXT NOT NULL CHECK (tipo IN ('foto', 'guia', 'checklist', 'firma', 'otro')),
                nombre_original TEXT NOT NULL,
                ruta_archivo TEXT NOT NULL,
                tamaño INTEGER,
                descripcion TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (despacho_id) REFERENCES despachos (id)
            )
        ''')
        print("Table despacho_archivos created successfully")
        
        conn.commit()
        print("Migration completed successfully")
        
    except Exception as e:
        print(f"Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_database()
