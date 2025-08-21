
#!/usr/bin/env python3
"""
Migración para agregar sistema de categorías y subcategorías de productos
"""

import sqlite3
from datetime import datetime

def migrate_add_categories():
    """Agregar tablas de categorías y subcategorías"""
    print("Iniciando migración: Agregar sistema de categorías...")
    
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # Crear tabla de categorías
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS categorias_producto (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT UNIQUE NOT NULL,
                descripcion TEXT,
                color TEXT DEFAULT '#E31E24',
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Crear tabla de subcategorías
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subcategorias_producto (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria_id INTEGER NOT NULL,
                nombre TEXT NOT NULL,
                descripcion TEXT,
                activo BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (categoria_id) REFERENCES categorias_producto (id),
                UNIQUE(categoria_id, nombre)
            )
        ''')
        
        # Agregar columnas a la tabla proyectos si no existen
        try:
            cursor.execute('ALTER TABLE proyectos ADD COLUMN categoria_id INTEGER')
            print("✓ Columna categoria_id agregada a proyectos")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("✓ Columna categoria_id ya existe en proyectos")
            else:
                raise e
        
        try:
            cursor.execute('ALTER TABLE proyectos ADD COLUMN subcategoria_id INTEGER')
            print("✓ Columna subcategoria_id agregada a proyectos")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("✓ Columna subcategoria_id ya existe en proyectos")
            else:
                raise e
        
        # Insertar datos iniciales de categorías
        categorias_data = [
            ('Cocinas', 'Muebles de cocina y accesorios', '#E31E24'),
            ('Closet', 'Closets y vestidores', '#8B4513')
        ]
        
        for nombre, descripcion, color in categorias_data:
            cursor.execute('''
                INSERT OR IGNORE INTO categorias_producto (nombre, descripcion, color)
                VALUES (?, ?, ?)
            ''', (nombre, descripcion, color))
        
        # Obtener IDs de categorías
        cursor.execute('SELECT id FROM categorias_producto WHERE nombre = "Cocinas"')
        cocinas_id = cursor.fetchone()[0]
        
        cursor.execute('SELECT id FROM categorias_producto WHERE nombre = "Closet"')
        closet_id = cursor.fetchone()[0]
        
        # Insertar subcategorías para Cocinas
        subcategorias_cocinas = [
            (cocinas_id, 'Bases', 'Muebles base de cocina'),
            (cocinas_id, 'Murales', 'Muebles murales de cocina'),
            (cocinas_id, 'Kits de Instalación', 'Kits y accesorios para instalación')
        ]
        
        for categoria_id, nombre, descripcion in subcategorias_cocinas:
            cursor.execute('''
                INSERT OR IGNORE INTO subcategorias_producto (categoria_id, nombre, descripcion)
                VALUES (?, ?, ?)
            ''', (categoria_id, nombre, descripcion))
        
        # Insertar subcategorías para Closet
        subcategorias_closet = [
            (closet_id, 'Interiores', 'Interiores y organizadores de closet'),
            (closet_id, 'Piernas', 'Piernas y estructura de soporte'),
            (closet_id, 'Puertas', 'Puertas y frentes de closet')
        ]
        
        for categoria_id, nombre, descripcion in subcategorias_closet:
            cursor.execute('''
                INSERT OR IGNORE INTO subcategorias_producto (categoria_id, nombre, descripcion)
                VALUES (?, ?, ?)
            ''', (categoria_id, nombre, descripcion))
        
        conn.commit()
        print("✓ Migración completada exitosamente!")
        print(f"✓ Se crearon {len(categorias_data)} categorías")
        print(f"✓ Se crearon {len(subcategorias_cocinas) + len(subcategorias_closet)} subcategorías")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error en la migración: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_add_categories()
