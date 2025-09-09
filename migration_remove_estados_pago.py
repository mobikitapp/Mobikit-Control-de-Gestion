
#!/usr/bin/env python3
"""
Migration: Remove EstadoPago table and related functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def run_migration():
    """Run the migration to remove EstadoPago table"""
    try:
        with app.app_context():
            print("Removing EstadoPago table...")
            
            # Drop the table if it exists
            inspector = db.inspect(db.engine)
            if 'estados_pago' in inspector.get_table_names():
                db.engine.execute('DROP TABLE IF EXISTS estados_pago CASCADE')
                print("✅ EstadoPago table removed successfully")
            else:
                print("⚠️  EstadoPago table doesn't exist")
            
            print("✅ Migration completed successfully!")
            
    except Exception as e:
        print(f"❌ Error during migration: {str(e)}")
        raise

if __name__ == "__main__":
    print("🔄 Starting EstadoPago removal migration...")
    run_migration()
