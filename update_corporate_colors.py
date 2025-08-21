
#!/usr/bin/env python3
"""
Script para actualizar los colores corporativos oficiales en la base de datos
"""

import sqlite3

def update_corporate_colors():
    """Actualiza los colores a la paleta corporativa oficial"""
    print("Actualizando colores corporativos oficiales...")
    
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # Actualizar color de la categoría Cocinas
        cursor.execute('''
            UPDATE categorias_producto 
            SET color = '#EF1A1F' 
            WHERE nombre = 'Cocinas'
        ''')
        cocinas_updated = cursor.rowcount
        
        # Actualizar color de la categoría Closet
        cursor.execute('''
            UPDATE categorias_producto 
            SET color = '#626363' 
            WHERE nombre = 'Closet'
        ''')
        closet_updated = cursor.rowcount
        
        conn.commit()
        print(f"Colores actualizados exitosamente:")
        print(f"- Cocinas: {cocinas_updated} fila(s)")
        print(f"- Closet: {closet_updated} fila(s)")
        print("Nuevos colores:")
        print("- Rojo intenso: #EF1A1F")
        print("- Gris oscuro: #626363")
        print("- Blanco: #FDFDFD")
            
    except Exception as e:
        conn.rollback()
        print(f"Error al actualizar los colores: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    update_corporate_colors()
