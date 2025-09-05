
#!/usr/bin/env python3

"""
Migration: Add EstadoPago table for advanced payment tracking
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import EstadoPago, TipoEstadoPago, EstadoPagoContrato

def run_migration():
    """Run the migration to add EstadoPago table"""
    try:
        with app.app_context():
            print("Creating EstadoPago table...")
            
            # Create the table
            db.create_all()
            
            print("✅ EstadoPago table created successfully")
            print("✅ Migration completed successfully!")
            
            # Show table info
            inspector = db.inspect(db.engine)
            if 'estados_pago' in inspector.get_table_names():
                columns = inspector.get_columns('estados_pago')
                print(f"\nTable 'estados_pago' created with {len(columns)} columns:")
                for col in columns:
                    print(f"  - {col['name']}: {col['type']}")
            
    except Exception as e:
        print(f"❌ Error during migration: {str(e)}")
        raise

if __name__ == "__main__":
    print("🔄 Starting EstadoPago migration...")
    run_migration()
