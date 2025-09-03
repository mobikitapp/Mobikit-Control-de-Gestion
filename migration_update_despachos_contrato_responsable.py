
#!/usr/bin/env python3

"""
Migration: Update despachos table to add contrato_id and change responsable to responsable_nombre
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import Despacho, User
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    with app.app_context():
        try:
            logger.info("🔄 Starting migration: Update despachos table")
            
            # Add contrato_id column
            logger.info("Adding contrato_id column to despachos table...")
            db.session.execute(text("""
                ALTER TABLE despachos 
                ADD COLUMN IF NOT EXISTS contrato_id INTEGER REFERENCES contratos(id)
            """))
            
            # Add responsable_nombre column
            logger.info("Adding responsable_nombre column to despachos table...")
            db.session.execute(text("""
                ALTER TABLE despachos 
                ADD COLUMN IF NOT EXISTS responsable_nombre VARCHAR(200)
            """))
            
            # Migrate existing responsable data
            logger.info("Migrating existing responsable data...")
            despachos = db.session.query(Despacho).all()
            
            for despacho in despachos:
                if hasattr(despacho, 'responsable') and despacho.responsable:
                    # Get user by ID
                    user = db.session.query(User).filter_by(id=despacho.responsable).first()
                    if user:
                        despacho.responsable_nombre = user.nombre_completo
                        logger.info(f"Updated despacho {despacho.id}: {despacho.responsable} -> {user.nombre_completo}")
            
            # Remove old responsable column (after data migration)
            logger.info("Removing old responsable column...")
            db.session.execute(text("""
                ALTER TABLE despachos 
                DROP COLUMN IF EXISTS responsable
            """))
            
            # Create indexes
            logger.info("Creating indexes...")
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_despacho_contrato 
                ON despachos(contrato_id)
            """))
            db.session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_despacho_responsable_nombre 
                ON despachos(responsable_nombre)
            """))
            
            # Drop old responsable index if it exists
            db.session.execute(text("""
                DROP INDEX IF EXISTS idx_despacho_responsable
            """))
            
            db.session.commit()
            logger.info("✅ Migration completed successfully")
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"❌ Migration failed: {str(e)}")
            raise

if __name__ == "__main__":
    run_migration()
