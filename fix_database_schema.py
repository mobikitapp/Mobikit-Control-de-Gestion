
#!/usr/bin/env python3
"""
Migration script to fix missing database columns
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

def migrate_missing_columns():
    """Add missing columns to match the SQLAlchemy models"""
    if not DATABASE_URL:
        print("DATABASE_URL environment variable not set")
        return
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    try:
        print("Adding missing columns to database...")
        
        # Add missing columns to clientes table
        missing_columns = [
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS condiciones_comerciales TEXT",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS contacto_principal VARCHAR(200)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS email_contacto VARCHAR(200)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS telefono_contacto VARCHAR(50)",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS direccion TEXT",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS activo BOOLEAN DEFAULT TRUE",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE clientes ADD COLUMN IF NOT EXISTS created_by VARCHAR(255)"
        ]
        
        for sql in missing_columns:
            cursor.execute(sql)
            print(f"✓ Executed: {sql[:50]}...")
        
        # Add missing columns to proyectos table
        proyecto_columns = [
            "ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS descripcion TEXT",
            "ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS estado VARCHAR(50) DEFAULT 'planificacion'",
            "ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS fecha_inicio DATE",
            "ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS fecha_fin_estimada DATE", 
            "ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS fecha_fin_real DATE",
            "ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS responsable VARCHAR(255)",
            "ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS notas TEXT",
            "ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE proyectos ADD COLUMN IF NOT EXISTS created_by VARCHAR(255)"
        ]
        
        for sql in proyecto_columns:
            cursor.execute(sql)
            print(f"✓ Executed: {sql[:50]}...")
        
        # Check if contratos table exists, if not create basic structure
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contratos (
                id SERIAL PRIMARY KEY,
                proyecto_id INTEGER REFERENCES proyectos(id),
                numero_oc VARCHAR(50) UNIQUE,
                monto_total DECIMAL(15,2),
                moneda VARCHAR(3) DEFAULT 'CLP',
                estado VARCHAR(50) DEFAULT 'borrador',
                fecha_emision DATE,
                fecha_vencimiento DATE,
                condiciones_pago TEXT,
                notas TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(255)
            )
        """)
        
        # Check if ordenes_fabricacion table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ordenes_fabricacion (
                id SERIAL PRIMARY KEY,
                proyecto_id INTEGER REFERENCES proyectos(id),
                contrato_id INTEGER REFERENCES contratos(id),
                codigo VARCHAR(50) UNIQUE,
                descripcion TEXT,
                estado VARCHAR(50) DEFAULT 'planificada',
                fecha_planificada DATE,
                fecha_inicio TIMESTAMP,
                fecha_qc TIMESTAMP,
                fecha_fin TIMESTAMP,
                responsable VARCHAR(255),
                notas TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(255)
            )
        """)
        
        # Check if despachos table exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS despachos (
                id SERIAL PRIMARY KEY,
                proyecto_id INTEGER REFERENCES proyectos(id),
                of_id INTEGER REFERENCES ordenes_fabricacion(id),
                numero_despacho VARCHAR(50) UNIQUE,
                estado VARCHAR(50) DEFAULT 'programado',
                fecha_programada DATE,
                fecha_envio TIMESTAMP,
                fecha_entrega TIMESTAMP,
                destino TEXT,
                contacto_destino VARCHAR(200),
                telefono_contacto VARCHAR(50),
                observaciones TEXT,
                responsable VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(255)
            )
        """)
        
        conn.commit()
        print("✓ Migration completed successfully!")
        
    except Exception as e:
        print(f"✗ Error during migration: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_missing_columns()
