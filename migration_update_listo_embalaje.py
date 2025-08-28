
import psycopg2
from psycopg2.extras import RealDictCursor
import os

DATABASE_URL = os.getenv('DATABASE_URL')

def migrate():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    try:
        print("Iniciando migración para cambiar 'listo_embalaje' por 'pendiente_embalaje'...")
        
        # 1. Actualizar registros existentes
        cursor.execute("""
            UPDATE ordenes_fabricacion 
            SET estado = 'pendiente_embalaje' 
            WHERE estado = 'listo_embalaje'
        """)
        updated_rows = cursor.rowcount
        print(f"Se actualizaron {updated_rows} registros con el nuevo estado")
        
        # 2. Eliminar la restricción existente
        cursor.execute("""
            ALTER TABLE ordenes_fabricacion 
            DROP CONSTRAINT IF EXISTS ordenes_fabricacion_estado_check
        """)
        print("Restricción anterior eliminada")
        
        # 3. Crear nueva restricción con los estados actualizados
        cursor.execute("""
            ALTER TABLE ordenes_fabricacion 
            ADD CONSTRAINT ordenes_fabricacion_estado_check 
            CHECK (estado IN ('pendiente_aprobacion_diseño', 'aprobado_diseño', 'enviado_produccion', 
                            'seccionado', 'enchapando', 'mecanizado', 'pendiente_embalaje', 
                            'embalando', 'embalaje_listo', 'listo_despacho', 'despachado', 'entregado'))
        """)
        print("Nueva restricción creada con estados actualizados")
        
        conn.commit()
        print("Migración completada exitosamente")
        
    except Exception as e:
        print(f"Error durante la migración: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
