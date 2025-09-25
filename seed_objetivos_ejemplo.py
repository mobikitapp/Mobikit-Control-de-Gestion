
#!/usr/bin/env python3
"""
Script para crear objetivos mensuales de ejemplo
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import db, create_app
from models import ObjetivoMensual
from decimal import Decimal
from datetime import datetime

def create_sample_objectives():
    """Create sample monthly objectives for current year"""
    app = create_app()
    
    with app.app_context():
        current_year = datetime.now().year
        
        # Sample objectives for each month (in CLP)
        sample_objectives = [
            {'mes': 1, 'provision': 200_000_000, 'instalacion': 50_000_000},
            {'mes': 2, 'provision': 220_000_000, 'instalacion': 55_000_000},
            {'mes': 3, 'provision': 250_000_000, 'instalacion': 60_000_000},
            {'mes': 4, 'provision': 230_000_000, 'instalacion': 58_000_000},
            {'mes': 5, 'provision': 280_000_000, 'instalacion': 65_000_000},
            {'mes': 6, 'provision': 300_000_000, 'instalacion': 70_000_000},
            {'mes': 7, 'provision': 320_000_000, 'instalacion': 75_000_000},
            {'mes': 8, 'provision': 290_000_000, 'instalacion': 68_000_000},
            {'mes': 9, 'provision': 310_000_000, 'instalacion': 72_000_000},
            {'mes': 10, 'provision': 330_000_000, 'instalacion': 78_000_000},
            {'mes': 11, 'provision': 340_000_000, 'instalacion': 80_000_000},
            {'mes': 12, 'provision': 350_000_000, 'instalacion': 85_000_000}
        ]
        
        created_count = 0
        updated_count = 0
        
        for obj_data in sample_objectives:
            # Check if objective already exists
            existing = (db.session.query(ObjetivoMensual)
                       .filter_by(año=current_year, mes=obj_data['mes'])
                       .first())
            
            if existing:
                # Update existing
                existing.objetivo_provision = Decimal(str(obj_data['provision']))
                existing.objetivo_instalacion = Decimal(str(obj_data['instalacion']))
                updated_count += 1
                print(f"Actualizado objetivo para {obj_data['mes']}/{current_year}")
            else:
                # Create new
                objetivo = ObjetivoMensual()
                objetivo.año = current_year
                objetivo.mes = obj_data['mes']
                objetivo.objetivo_provision = Decimal(str(obj_data['provision']))
                objetivo.objetivo_instalacion = Decimal(str(obj_data['instalacion']))
                objetivo.created_by = 'admin'  # Default user
                
                db.session.add(objetivo)
                created_count += 1
                print(f"Creado objetivo para {obj_data['mes']}/{current_year}")
        
        try:
            db.session.commit()
            print(f"\n✅ Objetivos procesados exitosamente:")
            print(f"   - Creados: {created_count}")
            print(f"   - Actualizados: {updated_count}")
            print(f"   - Año: {current_year}")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error al guardar objetivos: {str(e)}")
            raise

if __name__ == '__main__':
    create_sample_objectives()
