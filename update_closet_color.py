
#!/usr/bin/env python3
"""
Script para actualizar el color de la categoría Closet según el logo
"""

import sqlite3

def update_closet_color():
    """Actualiza el color de la categoría Closet"""
    print("Actualizando color de categoría Closet...")
    
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # Actualizar color de la categoría Closet
        cursor.execute('''
            UPDATE categorias_producto 
            SET color = '#6D6E71' 
            WHERE nombre = 'Closet'
        ''')
        
        affected_rows = cursor.rowcount
        
        if affected_rows > 0:
            conn.commit()
            print(f"Color de categoría Closet actualizado exitosamente ({affected_rows} fila(s) afectada(s))")
        else:
            print("No se encontró la categoría Closet para actualizar")
            
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar el color: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    update_closet_color()
