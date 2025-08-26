
#!/usr/bin/env python3
"""
Script para eliminar tabla pedidos_seguimiento y simplificar estados
"""

import sqlite3
from datetime import datetime

def migrate_remove_pedidos_seguimiento():
    """Elimina tabla pedidos_seguimiento y simplifica estados de fabricación"""
    print("Eliminando tabla pedidos_seguimiento y simplificando estados...")
    
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # Verificar si la tabla pedidos_seguimiento existe
        cursor.execute('''
            SELECT name FROM sqlite_master WHERE type='table' AND name='pedidos_seguimiento'
        ''')
        if cursor.fetchone():
            cursor.execute('DROP TABLE pedidos_seguimiento')
            print("Tabla pedidos_seguimiento eliminada")
        else:
            print("Tabla pedidos_seguimiento no existe")

        # Recrear tabla ordenes_fabricacion con estados correctos
        cursor.execute('DROP TABLE IF EXISTS ordenes_fabricacion')
        print("Tabla ordenes_fabricacion eliminada para recreación")
        
        cursor.execute('''
            CREATE TABLE ordenes_fabricacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_orden TEXT UNIQUE NOT NULL,
                proyecto_id INTEGER NOT NULL,
                tipo_orden TEXT DEFAULT 'parcial' CHECK (tipo_orden IN ('parcial', 'total')),
                fecha_entrega_estimada DATE NOT NULL,
                cantidad_tableros INTEGER NOT NULL,
                estado TEXT DEFAULT 'pendiente_fabricacion' CHECK (estado IN (
                    'pendiente_fabricacion', 'aprobado_diseño', 'enviado_produccion', 
                    'seccionado', 'enchapando', 'mecanizado', 'listo_embalaje', 
                    'embalando', 'listo_despacho', 'despachado'
                )),
                prioridad TEXT DEFAULT 'media' CHECK (prioridad IN ('baja', 'media', 'alta', 'urgente')),
                observaciones TEXT,
                fecha_inicio DATE,
                fecha_entrega_real DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE
            )
        ''')
        print("Tabla ordenes_fabricacion recreada con estados correctos")

        # Recrear tabla orden_fabricacion_categorias
        cursor.execute('DROP TABLE IF EXISTS orden_fabricacion_categorias')
        cursor.execute('''
            CREATE TABLE orden_fabricacion_categorias (
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
        print("Tabla orden_fabricacion_categorias recreada")

        # Actualizar estados de proyectos para que sean consistentes
        estados_mapping = {
            'pendiente': 'en_desarrollo',
            'diseño': 'en_desarrollo',
            'aprobado_produccion': 'aprobado_produccion',
            'fabricacion': 'produccion_completa',
            'control_calidad': 'produccion_completa',
            'embalaje': 'embalando',
            'despacho': 'listo_despacho'
        }

        for estado_viejo, estado_nuevo in estados_mapping.items():
            cursor.execute('''
                UPDATE proyectos 
                SET estado = ? 
                WHERE estado = ?
            ''', (estado_nuevo, estado_viejo))
            
            affected_rows = cursor.rowcount
            if affected_rows > 0:
                print(f"Actualizados {affected_rows} proyectos de '{estado_viejo}' a '{estado_nuevo}'")

        # Crear índices
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ordenes_fabricacion_proyecto ON ordenes_fabricacion(proyecto_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ordenes_fabricacion_estado ON ordenes_fabricacion(estado)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_orden_fabricacion_categorias_orden ON orden_fabricacion_categorias(orden_fabricacion_id)')

        conn.commit()
        print("Migración completada exitosamente")

    except Exception as e:
        conn.rollback()
        print(f"Error durante la migración: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_remove_pedidos_seguimiento()
