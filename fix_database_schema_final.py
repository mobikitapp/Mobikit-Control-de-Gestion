
#!/usr/bin/env python3
import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("❌ DATABASE_URL no está configurado")
    exit(1)

def fix_database_schema():
    """Fix database schema issues"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("🔄 Verificando y corrigiendo esquema de base de datos...")
        
        # First, check if comisiones_vendedores table exists
        cur.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'comisiones_vendedores';
        """)
        
        table_exists = cur.fetchone()
        
        if table_exists:
            print("✅ Tabla comisiones_vendedores existe")
            
            # Drop the table to recreate it properly
            print("🔧 Eliminando tabla para recrearla correctamente...")
            cur.execute("DROP TABLE IF EXISTS comisiones_vendedores CASCADE;")
            print("✅ Tabla eliminada")
        
        # Create the table with proper constraints
        print("🔧 Creando tabla comisiones_vendedores...")
        cur.execute("""
            CREATE TABLE comisiones_vendedores (
                id SERIAL PRIMARY KEY,
                vendedor_id VARCHAR(255) NOT NULL,
                comision_provision_pct NUMERIC(5, 2) NOT NULL DEFAULT 3.0,
                comision_instalacion_pct NUMERIC(5, 2) NOT NULL DEFAULT 3.0,
                activo BOOLEAN NOT NULL DEFAULT TRUE,
                created_by VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_comision_vendedor UNIQUE (vendedor_id),
                FOREIGN KEY(vendedor_id) REFERENCES users (id)
            );
        """)
        
        # Create indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_comision_vendedor 
            ON comisiones_vendedores(vendedor_id);
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_comision_activo 
            ON comisiones_vendedores(activo);
        """)
        
        print("✅ Tabla comisiones_vendedores creada correctamente")
        
        # Also check and fix contraseñas_temporales table if it has issues
        cur.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'contraseñas_temporales';
        """)
        
        temp_pass_table = cur.fetchone()
        
        if not temp_pass_table:
            print("🔧 Creando tabla contraseñas_temporales...")
            cur.execute("""
                CREATE TABLE contraseñas_temporales (
                    id SERIAL PRIMARY KEY,
                    usuario_id VARCHAR(255) NOT NULL,
                    contraseña_temporal VARCHAR(255) NOT NULL,
                    fecha_creacion TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    usado BOOLEAN NOT NULL DEFAULT FALSE,
                    created_by VARCHAR(255) NOT NULL,
                    FOREIGN KEY(usuario_id) REFERENCES users (id)
                );
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_contraseñas_usuario 
                ON contraseñas_temporales(usuario_id);
            """)
            
            print("✅ Tabla contraseñas_temporales creada")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print("✅ Esquema de base de datos corregido exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error corrigiendo esquema: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

if __name__ == "__main__":
    print("🔄 Ejecutando corrección final del esquema de base de datos...")
    success = fix_database_schema()
    
    if success:
        print("✅ Corrección completada. La aplicación debería poder iniciarse ahora.")
    else:
        print("❌ Error en la corrección. Revisa los logs para más detalles.")
