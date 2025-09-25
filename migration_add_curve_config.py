
<old_str>#!/usr/bin/env python3
"""
Migration to add curve configuration fields to ObjetivoMensual table
"""

import os
import sys
from sqlalchemy import text

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def add_curve_config_fields():
    """Add curve_type and curve_buffer_pct fields to ObjetivoMensual table"""
    
    with app.app_context():
        print("Adding curve configuration fields to ObjetivoMensual table...")
        
        try:
            # Check if columns already exist
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'objetivos_mensuales' 
                AND column_name IN ('curve_type', 'curve_buffer_pct')
            """)).fetchall()
            
            existing_columns = [row[0] for row in result]
            
            # Add curve_type column if it doesn't exist
            if 'curve_type' not in existing_columns:
                db.session.execute(text("""
                    ALTER TABLE objetivos_mensuales 
                    ADD COLUMN curve_type VARCHAR(20) DEFAULT 'general'
                """))
                print("  ✅ Added curve_type column")
            else:
                print("  ⚠️  curve_type column already exists")
            
            # Add curve_buffer_pct column if it doesn't exist
            if 'curve_buffer_pct' not in existing_columns:
                db.session.execute(text("""
                    ALTER TABLE objetivos_mensuales 
                    ADD COLUMN curve_buffer_pct NUMERIC(5,2) DEFAULT 0.0
                """))
                print("  ✅ Added curve_buffer_pct column")
            else:
                print("  ⚠️  curve_buffer_pct column already exists")
            
            # Update existing records to have default values
            db.session.execute(text("""
                UPDATE objetivos_mensuales 
                SET curve_type = 'general' 
                WHERE curve_type IS NULL
            """))
            
            db.session.execute(text("""
                UPDATE objetivos_mensuales 
                SET curve_buffer_pct = 0.0 
                WHERE curve_buffer_pct IS NULL
            """))
            
            db.session.commit()
            print("✅ Migration completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Migration failed: {str(e)}")
            raise

if __name__ == "__main__":
    add_curve_config_fields()</old_str>
<new_str>#!/usr/bin/env python3
"""
Migration to add Revenue Management fields to ObjetivoMensual table
"""

import os
import sys
from sqlalchemy import text

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db

def add_revenue_management_fields():
    """Add all Revenue Management fields to ObjetivoMensual table"""
    
    with app.app_context():
        print("Adding Revenue Management fields to ObjetivoMensual table...")
        
        try:
            # Check if columns already exist
            result = db.session.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'objetivos_mensuales' 
                AND column_name IN ('presupuesto_facturacion', 'adjudicado_facturacion', 'margen_real_pct', 'curve_type', 'curve_buffer_pct')
            """)).fetchall()
            
            existing_columns = [row[0] for row in result]
            
            # Add presupuesto_facturacion column if it doesn't exist
            if 'presupuesto_facturacion' not in existing_columns:
                db.session.execute(text("""
                    ALTER TABLE objetivos_mensuales 
                    ADD COLUMN presupuesto_facturacion NUMERIC(15,2)
                """))
                print("  ✅ Added presupuesto_facturacion column")
            else:
                print("  ⚠️  presupuesto_facturacion column already exists")
            
            # Add adjudicado_facturacion column if it doesn't exist
            if 'adjudicado_facturacion' not in existing_columns:
                db.session.execute(text("""
                    ALTER TABLE objetivos_mensuales 
                    ADD COLUMN adjudicado_facturacion NUMERIC(15,2)
                """))
                print("  ✅ Added adjudicado_facturacion column")
            else:
                print("  ⚠️  adjudicado_facturacion column already exists")
            
            # Add margen_real_pct column if it doesn't exist
            if 'margen_real_pct' not in existing_columns:
                db.session.execute(text("""
                    ALTER TABLE objetivos_mensuales 
                    ADD COLUMN margen_real_pct NUMERIC(5,2)
                """))
                print("  ✅ Added margen_real_pct column")
            else:
                print("  ⚠️  margen_real_pct column already exists")
            
            # Add curve_type column if it doesn't exist
            if 'curve_type' not in existing_columns:
                db.session.execute(text("""
                    ALTER TABLE objetivos_mensuales 
                    ADD COLUMN curve_type VARCHAR(20) DEFAULT 'general'
                """))
                print("  ✅ Added curve_type column")
            else:
                print("  ⚠️  curve_type column already exists")
            
            # Add curve_buffer_pct column if it doesn't exist
            if 'curve_buffer_pct' not in existing_columns:
                db.session.execute(text("""
                    ALTER TABLE objetivos_mensuales 
                    ADD COLUMN curve_buffer_pct NUMERIC(5,2) DEFAULT 0.0
                """))
                print("  ✅ Added curve_buffer_pct column")
            else:
                print("  ⚠️  curve_buffer_pct column already exists")
            
            # Update existing records to have default values
            db.session.execute(text("""
                UPDATE objetivos_mensuales 
                SET curve_type = 'general' 
                WHERE curve_type IS NULL
            """))
            
            db.session.execute(text("""
                UPDATE objetivos_mensuales 
                SET curve_buffer_pct = 0.0 
                WHERE curve_buffer_pct IS NULL
            """))
            
            db.session.commit()
            print("✅ Revenue Management migration completed successfully!")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Migration failed: {str(e)}")
            raise

if __name__ == "__main__":
    add_revenue_management_fields()</new_str>
