
#!/usr/bin/env python3
"""
Migración para agregar tabla de contraseñas temporales
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ.get("DATABASE_URL")

def create_contraseñas_temporales_table():
    """Crear tabla de contraseñas temporales"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Crear tabla de contraseñas temporales
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contraseñas_temporales (
                id SERIAL PRIMARY KEY,
                usuario_id VARCHAR(255) NOT NULL REFERENCES users(id),
                password_temporal VARCHAR(255) NOT NULL,
                tipo_accion VARCHAR(50) NOT NULL CHECK (tipo_accion IN ('creacion', 'reset')),
                generada_por VARCHAR(255) NOT NULL REFERENCES users(id),
                fecha_generacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                fecha_expiracion TIMESTAMP,
                activa BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Crear índices para mejorar rendimiento
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_contraseñas_temporales_usuario_id 
            ON contraseñas_temporales(usuario_id);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_contraseñas_temporales_activa 
            ON contraseñas_temporales(activa);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_contraseñas_temporales_fecha 
            ON contraseñas_temporales(fecha_generacion);
        """)
        
        conn.commit()
        print("✅ Tabla 'contraseñas_temporales' creada exitosamente")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error al crear tabla: {e}")
        if conn:
            conn.rollback()
            conn.close()

if __name__ == "__main__":
    print("🔄 Ejecutando migración para contraseñas temporales...")
    create_contraseñas_temporales_table()
    print("✅ Migración completada")
