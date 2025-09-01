
#!/usr/bin/env python3
"""
Script para resetear la base de datos y crear datos ficticios
"""

import os
import sys
from app import app, db

def reset_database():
    """Resetea completamente la base de datos"""
    with app.app_context():
        print("🗄️ Reseteando base de datos...")
        
        # Eliminar todas las tablas
        db.drop_all()
        print("❌ Tablas eliminadas")
        
        # Recrear todas las tablas  
        db.create_all()
        print("✅ Tablas recreadas")
        
        print("🔄 Base de datos reseteada exitosamente!")

if __name__ == '__main__':
    print("🚀 Iniciando reset completo y creación de datos ficticios...")
    
    # Resetear base de datos
    reset_database()
    
    # Importar y ejecutar creación de datos ficticios
    from init_sample_data import init_sample_data
    init_sample_data()
    
    print("🎉 Proceso completado exitosamente!")
