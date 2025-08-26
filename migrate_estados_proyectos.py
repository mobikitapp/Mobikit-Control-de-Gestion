
#!/usr/bin/env python3
"""
Script para migrar estados de proyectos a los nuevos valores
"""

import sqlite3

def migrate_estados():
    """Migra los estados de proyectos al nuevo sistema"""
    print("Migrando estados de proyectos...")
    
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # Mapeo de estados antiguos a nuevos
        mapeo_estados = {
            'diseño': 'en_desarrollo',
            'aprobado': 'aprobado_produccion',
            'pendiente_fabricacion': 'aprobado_produccion',
            'producción': 'seccionado',
            'embalaje': 'embalando',
            'despacho': 'listo_despacho'
        }
        
        # Desactivar temporalmente la restricción CHECK
        cursor.execute('PRAGMA foreign_keys = OFF')
        cursor.execute('BEGIN TRANSACTION')
        
        # Crear tabla temporal con la nueva estructura
        cursor.execute('''
            CREATE TABLE proyectos_new AS SELECT * FROM proyectos
        ''')
        
        # Actualizar estados en la tabla temporal
        for estado_viejo, estado_nuevo in mapeo_estados.items():
            cursor.execute('''
                UPDATE proyectos_new SET estado = ? WHERE estado = ?
            ''', (estado_nuevo, estado_viejo))
        
        # Eliminar tabla original
        cursor.execute('DROP TABLE proyectos')
        
        # Recrear la tabla con la nueva restricción CHECK
        cursor.execute('''
            CREATE TABLE proyectos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo TEXT UNIQUE NOT NULL,
                nombre TEXT NOT NULL,
                cliente_id INTEGER NOT NULL,
                descripcion TEXT,
                estado TEXT DEFAULT 'en_desarrollo' CHECK (estado IN ('en_desarrollo', 'aprobado_produccion', 'seccionado', 'enchapado', 'mecanizado', 'produccion_completa', 'embalando', 'listo_despacho', 'entregado', 'cancelado')),
                prioridad TEXT DEFAULT 'media' CHECK (prioridad IN ('baja', 'media', 'alta', 'urgente')),
                fecha_inicio DATE,
                fecha_entrega DATE,
                fecha_entrega_real DATE,
                diseñador_id INTEGER,
                supervisor_id INTEGER,
                presupuesto DECIMAL(12,2),
                costo_real DECIMAL(12,2),
                observaciones TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (cliente_id) REFERENCES clientes (id),
                FOREIGN KEY (diseñador_id) REFERENCES usuarios (id),
                FOREIGN KEY (supervisor_id) REFERENCES usuarios (id)
            )
        ''')
        
        # Insertar datos migrados
        cursor.execute('''
            INSERT INTO proyectos SELECT * FROM proyectos_new
        ''')
        
        # Limpiar tabla temporal
        cursor.execute('DROP TABLE proyectos_new')
        
        # Recrear índices
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_proyectos_cliente ON proyectos(cliente_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_proyectos_estado ON proyectos(estado)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_proyectos_fecha_entrega ON proyectos(fecha_entrega)')
        
        # Recrear triggers
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS update_proyectos_timestamp 
                AFTER UPDATE ON proyectos
                BEGIN
                    UPDATE proyectos SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END
        ''')
        
        cursor.execute('''
            CREATE TRIGGER IF NOT EXISTS audit_proyectos_insert
                AFTER INSERT ON proyectos
                BEGIN
                    INSERT INTO auditoria (tabla_afectada, registro_id, accion, valores_nuevos)
                    VALUES ('proyectos', NEW.id, 'INSERT', 
                            json_object('codigo', NEW.codigo, 'nombre', NEW.nombre, 'estado', NEW.estado));
                END
        ''')
        
        cursor.execute('COMMIT')
        cursor.execute('PRAGMA foreign_keys = ON')
        
        print("Migración de estados completada exitosamente!")
        
    except Exception as e:
        cursor.execute('ROLLBACK')
        print(f"Error durante la migración: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_estados()
