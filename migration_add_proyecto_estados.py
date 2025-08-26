
#!/usr/bin/env python3
"""
Script para agregar nuevos campos de estado de proyecto
"""

import sqlite3
from datetime import datetime

def migrate_proyecto_estados():
    """Migra la base de datos para agregar nuevos campos de estado de proyecto"""
    print("Migrando base de datos para estados de proyecto...")
    
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # Agregar nuevas columnas a la tabla proyectos
        try:
            cursor.execute('ALTER TABLE proyectos ADD COLUMN estado_proyecto TEXT DEFAULT "pendiente_presupuesto"')
            print("Campo estado_proyecto agregado exitosamente")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("Campo estado_proyecto ya existe")
            else:
                raise

        try:
            cursor.execute('ALTER TABLE proyectos ADD COLUMN monto_neto_provision DECIMAL(12,2)')
            print("Campo monto_neto_provision agregado exitosamente")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("Campo monto_neto_provision ya existe")
            else:
                raise

        try:
            cursor.execute('ALTER TABLE proyectos ADD COLUMN monto_neto_instalacion DECIMAL(12,2)')
            print("Campo monto_neto_instalacion agregado exitosamente")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("Campo monto_neto_instalacion ya existe")
            else:
                raise

        try:
            cursor.execute('ALTER TABLE proyectos ADD COLUMN fecha_estimada_inicio DATE')
            print("Campo fecha_estimada_inicio agregado exitosamente")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("Campo fecha_estimada_inicio ya existe")
            else:
                raise

        # Actualizar proyectos existentes con valores por defecto
        cursor.execute('''
            UPDATE proyectos 
            SET estado_proyecto = 'pendiente_presupuesto'
            WHERE estado_proyecto IS NULL
        ''')

        conn.commit()
        print("Migración de estados de proyecto completada exitosamente")

    except Exception as e:
        conn.rollback()
        print(f"Error durante la migración: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_proyecto_estados()
