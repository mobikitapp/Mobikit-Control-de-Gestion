
import os
import psycopg2

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise Exception('DATABASE_URL environment variable is required')

def add_glosa_column():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        # Verificar si la columna ya existe
        cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'ordenes_fabricacion' AND column_name = 'glosa'
        """)
        
        if not cursor.fetchone():
            # Agregar la columna glosa
            cursor.execute("ALTER TABLE ordenes_fabricacion ADD COLUMN glosa VARCHAR(200)")
            print("Columna 'glosa' agregada exitosamente a la tabla 'ordenes_fabricacion'")
            conn.commit()
        else:
            print("La columna 'glosa' ya existe en la tabla 'ordenes_fabricacion'")
            
    except Exception as e:
        print(f"Error al agregar columna: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    add_glosa_column()
