
#!/usr/bin/env python3
"""
Migración: Agregar campo glosa a la tabla despachos
"""

from app import app, db
from models import Despacho
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_add_glosa_field():
    """Agrega el campo glosa a la tabla despachos"""
    
    with app.app_context():
        try:
            # Verificar si la columna ya existe
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='despachos' AND column_name='glosa'
            """))
            
            if result.fetchone():
                logger.info("La columna 'glosa' ya existe en la tabla despachos")
                return
            
            # Agregar la columna glosa
            logger.info("Agregando columna 'glosa' a la tabla despachos...")
            db.session.execute(text("""
                ALTER TABLE despachos 
                ADD COLUMN glosa VARCHAR(500) NOT NULL DEFAULT 'Despacho sin descripción'
            """))
            
            # Actualizar registros existentes con una glosa basada en el número de despacho
            logger.info("Actualizando registros existentes...")
            db.session.execute(text("""
                UPDATE despachos 
                SET glosa = CONCAT('Despacho ', numero_despacho)
                WHERE glosa = 'Despacho sin descripción'
            """))
            
            # Remover el valor por defecto ahora que todos los registros tienen valores
            db.session.execute(text("""
                ALTER TABLE despachos 
                ALTER COLUMN glosa DROP DEFAULT
            """))
            
            db.session.commit()
            logger.info("✓ Migración completada exitosamente")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error en migración: {str(e)}")
            raise

if __name__ == '__main__':
    migrate_add_glosa_field()
    print("Migración de campo glosa para despachos completada")
