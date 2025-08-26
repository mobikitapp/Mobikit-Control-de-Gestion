
#!/usr/bin/env python3
"""
Migración para actualizar estados de fabricación y agregar prioridad
"""

import sqlite3
from datetime import datetime

def migrate_estados_fabricacion():
    """Migrar estados de fabricación y agregar campo prioridad"""
    print("Migrando estados de fabricación...")
    
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # Agregar columna prioridad a ordenes_fabricacion si no existe
        cursor.execute("PRAGMA table_info(ordenes_fabricacion)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'prioridad' not in columns:
            cursor.execute('''
                ALTER TABLE ordenes_fabricacion 
                ADD COLUMN prioridad TEXT DEFAULT 'media' 
                CHECK (prioridad IN ('baja', 'media', 'alta', 'urgente'))
            ''')
            print("Columna prioridad agregada a ordenes_fabricacion")

        # Mapear estados antiguos a nuevos
        mapeo_estados = {
            'pendiente': 'pendiente_fabricacion',
            'aprobado_produccion': 'aprobado_diseño',
            'enchapado': 'enchapando',
            'produccion_completa': 'listo_embalaje',
            'embalando': 'embalando',
            'listo_despacho': 'listo_despacho',
            'entregado': 'despachado'
        }

        # Actualizar estados en ordenes_fabricacion
        for estado_viejo, estado_nuevo in mapeo_estados.items():
            cursor.execute('''
                UPDATE ordenes_fabricacion 
                SET estado = ? 
                WHERE estado = ?
            ''', (estado_nuevo, estado_viejo))

        # Actualizar estados en pedidos_seguimiento
        for estado_viejo, estado_nuevo in mapeo_estados.items():
            cursor.execute('''
                UPDATE pedidos_seguimiento 
                SET estado = ? 
                WHERE estado = ?
            ''', (estado_nuevo, estado_viejo))

        # Mapear estados adicionales específicos
        cursor.execute('''
            UPDATE pedidos_seguimiento 
            SET estado = 'enviado_produccion' 
            WHERE estado = 'aprobado_produccion'
        ''')

        cursor.execute('''
            UPDATE ordenes_fabricacion 
            SET estado = 'enviado_produccion' 
            WHERE estado = 'aprobado_produccion'
        ''')

        conn.commit()
        print("Migración de estados de fabricación completada exitosamente!")
        
    except Exception as e:
        conn.rollback()
        print(f"Error en migración: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_estados_fabricacion()
