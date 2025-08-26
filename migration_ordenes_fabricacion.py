
#!/usr/bin/env python3
"""
Migración para agregar soporte de órdenes de fabricación personalizadas
"""

import sqlite3
from datetime import datetime

def migrate_ordenes_fabricacion():
    """Migrar base de datos para soportar órdenes de fabricación"""
    print("Migrando base de datos para órdenes de fabricación...")
    
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # Crear tabla de órdenes de fabricación
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ordenes_fabricacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_orden TEXT UNIQUE NOT NULL,
                proyecto_id INTEGER NOT NULL,
                tipo_orden TEXT DEFAULT 'parcial' CHECK (tipo_orden IN ('parcial', 'total')),
                fecha_entrega_estimada DATE NOT NULL,
                cantidad_tableros INTEGER NOT NULL,
                estado TEXT DEFAULT 'pendiente' CHECK (estado IN (
                    'pendiente', 'aprobado_produccion', 'seccionado', 'enchapado', 
                    'mecanizado', 'produccion_completa', 'embalando', 'listo_despacho', 'entregado'
                )),
                observaciones TEXT,
                fecha_inicio DATE,
                fecha_entrega_real DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE
            )
        ''')

        # Crear tabla de categorías por orden de fabricación
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orden_fabricacion_categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                orden_fabricacion_id INTEGER NOT NULL,
                categoria_id INTEGER NOT NULL,
                subcategoria_id INTEGER,
                cantidad INTEGER DEFAULT 1,
                observaciones TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (orden_fabricacion_id) REFERENCES ordenes_fabricacion (id) ON DELETE CASCADE,
                FOREIGN KEY (categoria_id) REFERENCES categorias_producto (id),
                FOREIGN KEY (subcategoria_id) REFERENCES subcategorias_producto (id)
            )
        ''')

        # Agregar columna orden_fabricacion_id a pedidos_seguimiento si no existe
        cursor.execute("PRAGMA table_info(pedidos_seguimiento)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'orden_fabricacion_id' not in columns:
            cursor.execute('''
                ALTER TABLE pedidos_seguimiento 
                ADD COLUMN orden_fabricacion_id INTEGER 
                REFERENCES ordenes_fabricacion(id) ON DELETE CASCADE
            ''')

        # Crear índices
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ordenes_fabricacion_proyecto ON ordenes_fabricacion(proyecto_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ordenes_fabricacion_estado ON ordenes_fabricacion(estado)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orden_fabricacion_categorias_orden ON orden_fabricacion_categorias(orden_fabricacion_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pedidos_seguimiento_orden ON pedidos_seguimiento(orden_fabricacion_id)')

        conn.commit()
        print("Migración de órdenes de fabricación completada exitosamente!")
        
    except Exception as e:
        conn.rollback()
        print(f"Error en migración: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_ordenes_fabricacion()
