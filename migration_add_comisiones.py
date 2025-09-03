
#!/usr/bin/env python3
"""
Migration script to add commission configuration table
"""

import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from models import ComisionVendedor, User, RolUsuario

def create_comisiones_table():
    """Create the commission table and default records"""
    
    app = create_app()
    
    with app.app_context():
        try:
            # Create the table
            db.create_all()
            print("✓ Tabla comisiones_vendedor creada")
            
            # Create default commission records for existing sellers
            vendedores = (db.session.query(User)
                         .filter(User.rol.in_([RolUsuario.VENTAS, RolUsuario.ADMIN]))
                         .filter_by(activo=True)
                         .all())
            
            comisiones_creadas = 0
            for vendedor in vendedores:
                # Check if commission record already exists
                existing = db.session.query(ComisionVendedor).filter_by(vendedor_id=vendedor.id).first()
                if not existing:
                    comision = ComisionVendedor(
                        vendedor_id=vendedor.id,
                        comision_provision_pct=3.0,  # 3% default
                        comision_instalacion_pct=3.0,  # 3% default
                        created_by=vendedor.id
                    )
                    db.session.add(comision)
                    comisiones_creadas += 1
                    print(f"✓ Comisión por defecto creada para: {vendedor.nombre_completo}")
            
            if comisiones_creadas > 0:
                db.session.commit()
                print(f"✓ Se crearon {comisiones_creadas} registros de comisión por defecto")
            else:
                print("✓ No se necesitaron crear registros de comisión (ya existen)")
            
            print("\n🎉 Migración de comisiones completada exitosamente")
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error en la migración: {str(e)}")
            return False
            
    return True

if __name__ == '__main__':
    success = create_comisiones_table()
    sys.exit(0 if success else 1)
