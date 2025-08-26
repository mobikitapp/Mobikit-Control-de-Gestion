
#!/usr/bin/env python3
"""
Script para eliminar la tabla pedidos_seguimiento y limpiar el sistema de estados
"""

import sqlite3
from datetime import datetime

def migrate_remove_pedidos_seguimiento():
    """Elimina la tabla pedidos_seguimiento y actualiza estados de órdenes de fabricación"""
    print("Eliminando tabla pedidos_seguimiento y simplificando estados...")
    
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # Verificar si la tabla existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pedidos_seguimiento'")
        if cursor.fetchone():
            print("Tabla pedidos_seguimiento encontrada, eliminando...")
            
            # Eliminar la tabla pedidos_seguimiento
            cursor.execute('DROP TABLE IF EXISTS pedidos_seguimiento')
            print("Tabla pedidos_seguimiento eliminada exitosamente")
        else:
            print("Tabla pedidos_seguimiento no existe")

        # Actualizar estados de órdenes de fabricación para que coincidan con los estados simplificados
        estados_mapping = {
            'pendiente': 'pendiente_fabricacion',
            'aprobado_diseño': 'aprobado_produccion',
            'enviado_produccion': 'aprobado_produccion',
            'enchapando': 'enchapado',
            'listo_embalaje': 'produccion_completa',
            'despachado': 'entregado'
        }

        for estado_viejo, estado_nuevo in estados_mapping.items():
            cursor.execute('''
                UPDATE ordenes_fabricacion 
                SET estado = ? 
                WHERE estado = ?
            ''', (estado_nuevo, estado_viejo))
            
            affected_rows = cursor.rowcount
            if affected_rows > 0:
                print(f"Actualizados {affected_rows} registros de '{estado_viejo}' a '{estado_nuevo}'")

        # Actualizar estados de proyectos para consistencia
        cursor.execute('''
            UPDATE proyectos 
            SET estado = 'en_desarrollo' 
            WHERE estado IN ('diseño', 'pendiente')
        ''')
        
        cursor.execute('''
            UPDATE proyectos 
            SET estado = 'produccion_completa' 
            WHERE estado = 'fabricacion'
        ''')

        # Eliminar índices relacionados con pedidos_seguimiento si existen
        indices_a_eliminar = [
            'idx_pedidos_seguimiento_proyecto',
            'idx_pedidos_seguimiento_estado',
            'idx_pedidos_seguimiento_orden'
        ]
        
        for indice in indices_a_eliminar:
            try:
                cursor.execute(f'DROP INDEX IF EXISTS {indice}')
                print(f"Índice {indice} eliminado")
            except sqlite3.OperationalError:
                pass

        conn.commit()
        print("Migración completada exitosamente!")
        print("Estados simplificados:")
        print("- Proyectos: en_desarrollo, aprobado_produccion, seccionado, enchapado, mecanizado, produccion_completa, embalando, listo_despacho, entregado, cancelado")
        print("- Órdenes de Fabricación: pendiente_fabricacion, aprobado_produccion, seccionado, enchapado, mecanizado, produccion_completa, embalando, listo_despacho, entregado")

    except Exception as e:
        conn.rollback()
        print(f"Error durante la migración: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_remove_pedidos_seguimiento()
