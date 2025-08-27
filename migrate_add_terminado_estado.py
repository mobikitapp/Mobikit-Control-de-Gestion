
#!/usr/bin/env python3
"""
Script para agregar el estado 'terminado' a la tabla proyectos
"""

import psycopg2
import os
from datetime import datetime

def migrate_add_terminado_estado():
    """Migra la base de datos para agregar el estado 'terminado' a proyectos"""
    print("Agregando estado 'terminado' a proyectos...")
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("Error: DATABASE_URL no encontrada")
        return
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        # Primero eliminar la restricción existente
        cursor.execute("ALTER TABLE proyectos DROP CONSTRAINT IF EXISTS proyectos_estado_check")
        
        # Agregar nueva restricción que incluye 'terminado'
        cursor.execute("""
            ALTER TABLE proyectos ADD CONSTRAINT proyectos_estado_check 
            CHECK (estado IN ('diseño', 'proyecto_simple', 'en_desarrollo', 'aprobado_produccion', 
                             'seccionado', 'enchapado', 'mecanizado', 'produccion_completa', 
                             'embalando', 'listo_despacho', 'entregado', 'terminado', 'completado', 'cancelado'))
        """)
        
        conn.commit()
        print("Estado 'terminado' agregado exitosamente a la tabla proyectos")

    except Exception as e:
        conn.rollback()
        print(f"Error durante la migración: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_add_terminado_estado()
