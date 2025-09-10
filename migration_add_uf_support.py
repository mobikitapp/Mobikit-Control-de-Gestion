"""
Migración para agregar soporte de UF (Unidad de Fomento) a contratos y proyectos
Ejecutar con: python migration_add_uf_support.py
"""

import sys
import logging
from app import app, db

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_add_uf_support():
    """Agregar campos UF a contratos y proyectos"""
    
    with app.app_context():
        try:
            logger.info("🔄 Iniciando migración para soporte UF...")
            
            # SQL para agregar campos UF a tabla contratos
            contratos_sql = """
            ALTER TABLE contratos 
            ADD COLUMN IF NOT EXISTS monto_total_uf DECIMAL(15,4),
            ADD COLUMN IF NOT EXISTS valor_uf_conversion DECIMAL(15,2),
            ADD COLUMN IF NOT EXISTS fecha_conversion_uf DATE,
            ADD COLUMN IF NOT EXISTS moneda_original VARCHAR(3);
            """
            
            # SQL para agregar campos UF a tabla proyectos
            proyectos_sql = """
            ALTER TABLE proyectos
            ADD COLUMN IF NOT EXISTS monto_provision_presupuestado_uf DECIMAL(15,4),
            ADD COLUMN IF NOT EXISTS monto_instalacion_presupuestado_uf DECIMAL(15,4),
            ADD COLUMN IF NOT EXISTS valor_uf_presupuesto DECIMAL(15,2),
            ADD COLUMN IF NOT EXISTS fecha_conversion_presupuesto_uf DATE,
            ADD COLUMN IF NOT EXISTS moneda_original_presupuesto VARCHAR(3);
            """
            
            # Ejecutar migraciones
            logger.info("📝 Agregando campos UF a tabla contratos...")
            db.session.execute(db.text(contratos_sql))
            
            logger.info("📝 Agregando campos UF a tabla proyectos...")
            db.session.execute(db.text(proyectos_sql))
            
            # Inicializar campos moneda_original para registros existentes
            logger.info("🔧 Inicializando campos moneda_original para registros existentes...")
            
            # Contratos existentes se asume que fueron ingresados en CLP
            init_contratos_sql = """
            UPDATE contratos 
            SET moneda_original = 'CLP'
            WHERE moneda_original IS NULL;
            """
            db.session.execute(db.text(init_contratos_sql))
            
            # Proyectos existentes se asume que fueron ingresados en CLP
            init_proyectos_sql = """
            UPDATE proyectos
            SET moneda_original_presupuesto = 'CLP'
            WHERE moneda_original_presupuesto IS NULL
            AND (monto_provision_presupuestado IS NOT NULL 
                 OR monto_instalacion_presupuestado IS NOT NULL);
            """
            db.session.execute(db.text(init_proyectos_sql))
            
            # Commit de todos los cambios
            db.session.commit()
            
            logger.info("✅ Migración UF completada exitosamente")
            
            # Verificar las nuevas columnas
            logger.info("🔍 Verificando nuevas columnas...")
            
            # Verificar contratos
            result = db.session.execute(db.text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'contratos' 
                AND column_name LIKE '%uf%' OR column_name = 'moneda_original'
                ORDER BY column_name;
            """))
            
            logger.info("📋 Nuevas columnas en tabla 'contratos':")
            for row in result:
                logger.info(f"   - {row[0]}: {row[1]}")
            
            # Verificar proyectos
            result = db.session.execute(db.text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'proyectos' 
                AND (column_name LIKE '%uf%' OR column_name LIKE '%presupuesto%')
                ORDER BY column_name;
            """))
            
            logger.info("📋 Nuevas columnas en tabla 'proyectos':")
            for row in result:
                logger.info(f"   - {row[0]}: {row[1]}")
                
            return True
            
        except Exception as e:
            logger.error(f"❌ Error durante la migración: {e}")
            db.session.rollback()
            return False

def verify_migration():
    """Verificar que la migración se aplicó correctamente"""
    
    with app.app_context():
        try:
            logger.info("🔍 Verificando migración UF...")
            
            # Contar registros en ambas tablas
            contratos_count = db.session.execute(
                db.text("SELECT COUNT(*) FROM contratos")
            ).scalar()
            
            proyectos_count = db.session.execute(
                db.text("SELECT COUNT(*) FROM proyectos")
            ).scalar()
            
            logger.info(f"📊 Registros existentes:")
            logger.info(f"   - Contratos: {contratos_count}")
            logger.info(f"   - Proyectos: {proyectos_count}")
            
            # Verificar que las columnas existan y funcionen
            test_query = db.session.execute(db.text("""
                SELECT 
                    COUNT(*) as total_contratos,
                    COUNT(moneda_original) as contratos_con_moneda,
                    COUNT(monto_total_uf) as contratos_con_uf
                FROM contratos;
            """))
            
            row = test_query.fetchone()
            logger.info(f"   - Contratos con moneda_original: {row[1]}/{row[0]}")
            logger.info(f"   - Contratos con monto UF: {row[2]}/{row[0]}")
            
            logger.info("✅ Verificación completada")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error durante verificación: {e}")
            return False

if __name__ == "__main__":
    logger.info("🚀 Ejecutando migración UF...")
    
    # Ejecutar migración
    success = migrate_add_uf_support()
    
    if success:
        # Verificar migración
        verify_migration()
        logger.info("🎉 Migración UF completada con éxito")
        sys.exit(0)
    else:
        logger.error("💥 Migración UF falló")
        sys.exit(1)