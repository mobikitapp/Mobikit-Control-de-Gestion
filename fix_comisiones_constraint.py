
#!/usr/bin/env python3
import os
import psycopg2
from psycopg2.extras import RealDictCursor

# Database configuration
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    print("❌ DATABASE_URL no está configurado")
    exit(1)

def fix_comisiones_constraint():
    """Fix duplicate constraint issue for comisiones_vendedores table"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("🔄 Verificando estado de la tabla comisiones_vendedores...")
        
        # Check if table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'comisiones_vendedores'
            );
        """)
        
        table_exists = cur.fetchone()[0]
        
        if table_exists:
            print("✅ Tabla comisiones_vendedores ya existe")
            
            # Check if constraint exists
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.table_constraints 
                    WHERE constraint_name = 'uq_comision_vendedor'
                    AND table_name = 'comisiones_vendedores'
                );
            """)
            
            constraint_exists = cur.fetchone()[0]
            
            if constraint_exists:
                print("✅ Constraint uq_comision_vendedor ya existe correctamente")
            else:
                print("🔧 Agregando constraint faltante...")
                cur.execute("""
                    ALTER TABLE comisiones_vendedores 
                    ADD CONSTRAINT uq_comision_vendedor UNIQUE (vendedor_id);
                """)
                print("✅ Constraint agregado exitosamente")
        else:
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
            
            # Create index
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_comision_vendedor 
                ON comisiones_vendedores(vendedor_id);
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_comision_activo 
                ON comisiones_vendedores(activo);
            """)
            
            print("✅ Tabla comisiones_vendedores creada exitosamente")
        
        conn.commit()
        cur.close()
        conn.close()
        
        print("✅ Migración completada exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error en migración: {str(e)}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

if __name__ == "__main__":
    print("🔄 Ejecutando corrección de constraint para comisiones...")
    success = fix_comisiones_constraint()
    
    if success:
        print("✅ Corrección completada. La aplicación debería poder iniciarse ahora.")
    else:
        print("❌ Error en la corrección. Revisa los logs para más detalles.")
