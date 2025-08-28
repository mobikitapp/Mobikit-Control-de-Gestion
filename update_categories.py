
#!/usr/bin/env python3
"""
Script para actualizar las categorías y subcategorías según los requerimientos
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise Exception('DATABASE_URL environment variable is required')

def update_categories():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    try:
        # Limpiar categorías y subcategorías existentes
        cursor.execute('DELETE FROM subcategorias_producto')
        cursor.execute('DELETE FROM categorias_producto')
        
        # Insertar nuevas categorías
        categorias_data = [
            ('Cocinas', 'Muebles de cocina modulares'),
            ('Closets', 'Sistemas de closet y vestidores'),
            ('Baños', 'Mobiliario para baños'),
            ('Cubiertas', 'Cubiertas de cocina y superficies'),
            ('Otro', 'Otros tipos de mobiliario')
        ]
        
        categoria_ids = {}
        for nombre, descripcion in categorias_data:
            cursor.execute('''
                INSERT INTO categorias_producto (nombre, descripcion, activo)
                VALUES (%s, %s, %s) RETURNING id
            ''', (nombre, descripcion, True))
            categoria_ids[nombre] = cursor.fetchone()['id']
        
        # Insertar subcategorías para Cocinas
        subcategorias_cocinas = [
            ('Bases', 'Muebles base de cocina'),
            ('Murales', 'Muebles murales de cocina'),
            ('Kits', 'Kits de instalación y accesorios')
        ]
        
        for nombre, descripcion in subcategorias_cocinas:
            cursor.execute('''
                INSERT INTO subcategorias_producto (categoria_id, nombre, descripcion, activo)
                VALUES (%s, %s, %s, %s)
            ''', (categoria_ids['Cocinas'], nombre, descripcion, True))
        
        # Insertar subcategorías para Closets
        subcategorias_closets = [
            ('Interiores', 'Interiores y organizadores de closet'),
            ('Piernas', 'Piernas y estructuras de soporte'),
            ('Puertas', 'Puertas y frentes de closet')
        ]
        
        for nombre, descripcion in subcategorias_closets:
            cursor.execute('''
                INSERT INTO subcategorias_producto (categoria_id, nombre, descripcion, activo)
                VALUES (%s, %s, %s, %s)
            ''', (categoria_ids['Closets'], nombre, descripcion, True))
        
        # Las categorías Baños, Cubiertas y Otro no tienen subcategorías por ahora
        
        conn.commit()
        print("✓ Categorías actualizadas exitosamente:")
        print("  - Cocinas: Bases, Murales, Kits")
        print("  - Closets: Interiores, Piernas, Puertas")
        print("  - Baños: (sin subcategorías)")
        print("  - Cubiertas: (sin subcategorías)")
        print("  - Otro: (sin subcategorías)")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error actualizando categorías: {e}")
        raise e
    finally:
        conn.close()

if __name__ == '__main__':
    update_categories()
