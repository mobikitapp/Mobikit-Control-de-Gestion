
#!/usr/bin/env python3
"""
Script para sincronizar los módulos del sistema de permisos
"""

from app import create_app, db
from services.permisos_service import PermisosService
from models import User, RolUsuario

def sync_modulos():
    app = create_app()
    
    with app.app_context():
        # Buscar un usuario admin para usar como referencia
        admin_user = User.query.filter_by(rol=RolUsuario.ADMIN).first()
        
        if not admin_user:
            print("Error: No se encontró un usuario administrador")
            return
        
        service = PermisosService()
        
        # Inicializar módulos del sistema
        success, message = service.inicializar_modulos_sistema(admin_user.id)
        
        if success:
            print(f"✅ Módulos sincronizados correctamente: {message}")
            
            # Sincronizar permisos faltantes
            success2, message2 = service.sincronizar_permisos_defecto(admin_user.id, only_missing=True)
            
            if success2:
                print(f"✅ Permisos sincronizados: {message2}")
            else:
                print(f"❌ Error sincronizando permisos: {message2}")
        else:
            print(f"❌ Error sincronizando módulos: {message}")

if __name__ == "__main__":
    sync_modulos()
