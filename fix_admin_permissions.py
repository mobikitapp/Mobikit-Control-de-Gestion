
#!/usr/bin/env python3
"""
Script para reparar permisos de administrador
"""

import os
import sys
sys.path.append('.')

from app import create_app, db
from models import User, RolUsuario
from services.permisos_service import PermisosService

def fix_admin_permissions():
    """Repara permisos de administrador"""
    app = create_app()
    
    with app.app_context():
        print("=== REPARACIÓN DE PERMISOS DE ADMIN ===\n")
        
        # 1. Buscar o crear usuario admin
        admin = User.query.filter_by(rol=RolUsuario.ADMIN, activo=True).first()
        
        if not admin:
            print("❌ No se encontró usuario admin activo")
            
            # Buscar usuarios inactivos
            inactive_admin = User.query.filter_by(rol=RolUsuario.ADMIN, activo=False).first()
            if inactive_admin:
                print(f"🔧 Activando usuario admin: {inactive_admin.email}")
                inactive_admin.activo = True
                db.session.commit()
                admin = inactive_admin
            else:
                print("💡 Debe crear un usuario admin manualmente")
                return False
        
        print(f"✅ Usuario admin encontrado: {admin.email}")
        
        # 2. Inicializar sistema de permisos
        print("\n🔧 Inicializando sistema de permisos...")
        try:
            service = PermisosService()
            success, mensaje = service.inicializar_modulos_sistema(admin.id)
            
            if success:
                print(f"✅ {mensaje}")
            else:
                print(f"❌ Error: {mensaje}")
                
        except Exception as e:
            print(f"❌ Error inicializando permisos: {e}")
        
        # 3. Sincronizar permisos
        print("\n🔧 Sincronizando permisos...")
        try:
            service = PermisosService()
            success, mensaje = service.sincronizar_permisos_defecto(admin.id, only_missing=False)
            
            if success:
                print(f"✅ {mensaje}")
            else:
                print(f"❌ Error: {mensaje}")
                
        except Exception as e:
            print(f"❌ Error sincronizando permisos: {e}")
        
        # 4. Verificar permisos críticos
        print("\n🔍 Verificando permisos críticos...")
        from utils.permissions import has_permission
        
        critical_perms = [
            'users.view',
            'users.create',
            'users.edit', 
            'config.view',
            'config.edit'
        ]
        
        all_ok = True
        for perm in critical_perms:
            has_perm = has_permission(admin.rol.value, perm)
            status = "✅" if has_perm else "❌"
            print(f"   {status} {perm}")
            if not has_perm:
                all_ok = False
        
        if all_ok:
            print("\n🎉 Todos los permisos están correctamente configurados")
        else:
            print("\n⚠️  Algunos permisos siguen fallando")
        
        return all_ok

if __name__ == '__main__':
    success = fix_admin_permissions()
    sys.exit(0 if success else 1)
