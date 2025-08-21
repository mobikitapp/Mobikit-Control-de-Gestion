
#!/usr/bin/env python3
"""
Migración para soportar múltiples categorías por proyecto y pedidos de seguimiento
"""

import sqlite3
from datetime import datetime

def migrate_to_multiple_categories():
    """Migra la base de datos para soportar múltiples categorías"""
    print("Iniciando migración a sistema de múltiples categorías...")
    
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # Crear nuevas tablas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS proyecto_categorias (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                categoria_id INTEGER NOT NULL,
                subcategoria_id INTEGER,
                cantidad INTEGER DEFAULT 1,
                observaciones TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE,
                FOREIGN KEY (categoria_id) REFERENCES categorias_producto (id),
                FOREIGN KEY (subcategoria_id) REFERENCES subcategorias_producto (id),
                UNIQUE(proyecto_id, categoria_id, subcategoria_id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pedidos_seguimiento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                categoria_id INTEGER NOT NULL,
                subcategoria_id INTEGER,
                codigo_pedido TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                estado TEXT DEFAULT 'en_desarrollo' CHECK (estado IN (
                    'en_desarrollo', 'aprobado_produccion', 'seccionado', 'enchapado', 
                    'mecanizado', 'produccion_completa', 'embalando', 'listo_despacho', 'entregado'
                )),
                fecha_inicio DATE,
                fecha_entrega_estimada DATE,
                fecha_entrega_real DATE,
                observaciones TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE,
                FOREIGN KEY (categoria_id) REFERENCES categorias_producto (id),
                FOREIGN KEY (subcategoria_id) REFERENCES subcategorias_producto (id)
            )
        ''')
        
        # Crear índices
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_proyecto_categorias_proyecto ON proyecto_categorias(proyecto_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_proyecto_categorias_categoria ON proyecto_categorias(categoria_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pedidos_seguimiento_proyecto ON pedidos_seguimiento(proyecto_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_pedidos_seguimiento_estado ON pedidos_seguimiento(estado)')
        
        # Migrar datos existentes
        cursor.execute('''
            SELECT id, categoria_id, subcategoria_id, fecha_inicio, fecha_entrega 
            FROM proyectos 
            WHERE categoria_id IS NOT NULL
        ''')
        proyectos_con_categoria = cursor.fetchall()
        
        pedido_numero = 1
        for proyecto_id, categoria_id, subcategoria_id, fecha_inicio, fecha_entrega in proyectos_con_categoria:
            # Crear relación proyecto-categoría
            cursor.execute('''
                INSERT OR IGNORE INTO proyecto_categorias (proyecto_id, categoria_id, subcategoria_id)
                VALUES (?, ?, ?)
            ''', (proyecto_id, categoria_id, subcategoria_id))
            
            # Crear pedido de seguimiento
            codigo_pedido = f"PED-{datetime.now().year}-{pedido_numero:04d}"
            
            # Obtener nombres para el pedido
            cursor.execute('SELECT nombre FROM categorias_producto WHERE id = ?', (categoria_id,))
            categoria_nombre = cursor.fetchone()
            if categoria_nombre:
                nombre_pedido = categoria_nombre[0]
                
                if subcategoria_id:
                    cursor.execute('SELECT nombre FROM subcategorias_producto WHERE id = ?', (subcategoria_id,))
                    subcategoria_nombre = cursor.fetchone()
                    if subcategoria_nombre:
                        nombre_pedido += f" - {subcategoria_nombre[0]}"
                
                cursor.execute('''
                    INSERT OR IGNORE INTO pedidos_seguimiento (
                        proyecto_id, categoria_id, subcategoria_id, codigo_pedido, 
                        nombre, estado, fecha_inicio, fecha_entrega_estimada
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (proyecto_id, categoria_id, subcategoria_id, codigo_pedido,
                      nombre_pedido, 'en_desarrollo', fecha_inicio, fecha_entrega))
                
                pedido_numero += 1
        
        # Remover columnas de categoría del proyecto (simulado con comentario)
        # En SQLite no se pueden eliminar columnas directamente, 
        # pero las dejamos para compatibilidad hacia atrás
        
        conn.commit()
        print("Migración completada exitosamente!")
        print(f"Se migraron {len(proyectos_con_categoria)} proyectos al nuevo sistema")
        
    except Exception as e:
        conn.rollback()
        print(f"Error durante la migración: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_to_multiple_categories()
