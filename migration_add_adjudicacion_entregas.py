
#!/usr/bin/env python3
"""
Migración para agregar campos de adjudicación y sistema de entregas
"""

import sqlite3

def migrate_adjudicacion_entregas():
    """Agregar campos de adjudicación y tabla de entregas"""
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()

    try:
        # Verificar si ya existe el campo adjudicacion_tipo
        cursor.execute("PRAGMA table_info(proyectos)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'adjudicacion_tipo' not in columns:
            # Agregar campo adjudicacion_tipo
            cursor.execute('ALTER TABLE proyectos ADD COLUMN adjudicacion_tipo TEXT DEFAULT "orden_compra" CHECK (adjudicacion_tipo IN ("contrato", "orden_compra"))')
            print("Campo adjudicacion_tipo agregado exitosamente")

        if 'monto_neto' not in columns:
            # Renombrar presupuesto a monto_neto (SQLite no permite RENAME COLUMN directamente)
            cursor.execute('ALTER TABLE proyectos ADD COLUMN monto_neto DECIMAL(12,2)')
            # Copiar datos de presupuesto a monto_neto
            cursor.execute('UPDATE proyectos SET monto_neto = presupuesto WHERE presupuesto IS NOT NULL')
            print("Campo monto_neto agregado exitosamente")

        # Eliminar campo prioridad si existe
        if 'prioridad' in columns:
            print("Nota: El campo prioridad seguirá existiendo por limitaciones de SQLite, pero no se usará en la nueva interfaz")

        # Crear tabla de entregas de contrato si no existe
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS entregas_contrato (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                detalle TEXT NOT NULL,
                fecha_entrega DATE NOT NULL,
                estado TEXT DEFAULT 'programada' CHECK (estado IN ('programada', 'en_proceso', 'completada', 'retrasada')),
                observaciones TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (proyecto_id) REFERENCES proyectos (id) ON DELETE CASCADE
            )
        ''')
        print("Tabla entregas_contrato creada exitosamente")

        # Crear índice para mejorar rendimiento
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entregas_contrato_proyecto ON entregas_contrato(proyecto_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_entregas_contrato_fecha ON entregas_contrato(fecha_entrega)')

        conn.commit()
        print("Migración completada exitosamente")

    except Exception as e:
        conn.rollback()
        print(f"Error en la migración: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_adjudicacion_entregas()
