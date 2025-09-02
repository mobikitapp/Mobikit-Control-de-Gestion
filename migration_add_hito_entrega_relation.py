
#!/usr/bin/env python3
"""
Migration: Add hito_entrega_id column to eventos_entrega table
"""

import sqlite3
import logging
from app import db, app

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    """Add hito_entrega_id column to eventos_entrega table"""
    
    with app.app_context():
        try:
            # Check if column already exists
            cursor = db.session.connection().connection.cursor()
            cursor.execute("PRAGMA table_info(eventos_entrega)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'hito_entrega_id' not in columns:
                logger.info("Adding hito_entrega_id column to eventos_entrega table...")
                
                # Add the new column
                db.session.execute('''
                    ALTER TABLE eventos_entrega 
                    ADD COLUMN hito_entrega_id INTEGER 
                    REFERENCES hitos_entrega(id)
                ''')
                
                db.session.commit()
                logger.info("Column hito_entrega_id added successfully")
                
                # Create index for the new foreign key
                try:
                    db.session.execute('''
                        CREATE INDEX idx_eventos_entrega_hito 
                        ON eventos_entrega(hito_entrega_id)
                    ''')
                    db.session.commit()
                    logger.info("Index idx_eventos_entrega_hito created successfully")
                except Exception as e:
                    logger.warning(f"Index creation failed (may already exist): {str(e)}")
                
            else:
                logger.info("Column hito_entrega_id already exists, skipping migration")
            
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {str(e)}")
            db.session.rollback()
            return False

if __name__ == '__main__':
    logger.info("Starting migration: Add hito_entrega_id to eventos_entrega")
    
    if run_migration():
        logger.info("Migration completed successfully")
    else:
        logger.error("Migration failed")
        exit(1)
