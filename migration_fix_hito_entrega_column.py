
#!/usr/bin/env python3

"""
Migration: Add hito_entrega_id column to eventos_entrega table (PostgreSQL compatible)
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    with app.app_context():
        try:
            logger.info("🔄 Starting migration: Add hito_entrega_id column to eventos_entrega")
            
            # Check if column exists
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'eventos_entrega' 
                AND column_name = 'hito_entrega_id'
            """))
            
            if result.fetchone() is None:
                logger.info("Adding hito_entrega_id column to eventos_entrega table...")
                
                # Add the column
                db.session.execute(text("""
                    ALTER TABLE eventos_entrega 
                    ADD COLUMN hito_entrega_id INTEGER REFERENCES hitos_entrega(id)
                """))
                
                # Create index
                db.session.execute(text("""
                    CREATE INDEX IF NOT EXISTS idx_eventos_entrega_hito 
                    ON eventos_entrega(hito_entrega_id)
                """))
                
                db.session.commit()
                logger.info("✅ Column hito_entrega_id added successfully")
            else:
                logger.info("Column hito_entrega_id already exists, skipping migration")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Migration failed: {str(e)}")
            db.session.rollback()
            return False

if __name__ == "__main__":
    run_migration()
