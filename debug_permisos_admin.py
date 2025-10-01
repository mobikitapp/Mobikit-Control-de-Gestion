
#!/usr/bin/env python3
"""
Script para diagnosticar problemas de permisos de administrador
"""

import os
import sys
sys.path.append('.')

from app import create_app, db
from models import User, RolUsuario
from utils.permissions import has_permission
from services.permisos_service import PermisosService

def debug_admin_permissions():
    """Diagnostica problemas de permisos de admin"""
    app = create_app()
    
    with app.app_context():
        print("=== DIAGNÓSTICO DE PERMISOS DE ADMIN ===\n")
        
        # 1. Buscar usuarios admin
        admins = User.query.filter_by(rol=RolUsuario.ADMIN, activo=True).all()
        print(f"1. Usuarios admin encontrados: {len(admins)}")
        
        for admin in admins:
            print(f"   - ID: {admin.id}")
            print(f"   - Email: {admin.email}")
            print(f"   - Nombre: {admin.first_name} {admin.last_name}")
            print(f"   - Rol: {admin.rol} (tipo: {type(admin.rol)})")
            print(f"   - Activo: {admin.activo}")
            print()
        
        if not admins:
            print("   ❌ NO SE ENCONTRARON USUARIOS ADMIN ACTIVOS")
            
            # Mostrar todos los usuarios para debug
            all_users = User.query.all()
            print(f"\n   Todos los usuarios ({len(all_users)}):")
            for user in all_users:
                print(f"   - {user.email}: {user.rol} (activo: {user.activo})")
            return
        
        # 2. Verificar permisos específicos de configuraciones
        admin_user = admins[0]  # Usar el primer admin para las pruebas
        
        print("2. Verificación de permisos críticos:")
        
        # Permisos de configuración
        config_permissions = [
            'users.view',
            'users.create', 
            'users.edit',
            'users.delete',
            'config.view',
            'config.edit'
        ]
        
        for perm in config_permissions:
            has_perm = has_permission(admin_user.rol.value, perm)
            status = "✅" if has_perm else "❌"
            print(f"   {status} {perm}: {has_perm}")
        
        # 3. Verificar sistema dinámico de permisos
        print("\n3. Sistema dinámico de permisos:")
        try:
            service = PermisosService()
            
            # Verificar permisos dinámicos
            dynamic_perms = [
                ('configuraciones', 'lectura'),
                ('configuraciones', 'creacion'),
                ('configuraciones', 'edicion'),
                ('configuraciones', 'eliminacion')
            ]
            
            for modulo, tipo in dynamic_perms:
                resultado = service.verificar_permiso_dinamico(admin_user.rol.value, modulo, tipo)
                status = "✅" if resultado else "❌" if resultado is False else "⚠️"
                print(f"   {status} {modulo}.{tipo}: {resultado}")
            
        except Exception as e:
            print(f"   ❌ Error en sistema dinámico: {e}")
        
        # 4. Verificar inicialización del sistema de permisos
        print("\n4. Estado del sistema de permisos:")
        try:
            from models import Modulo, PermisoRol
            
            modulos_count = Modulo.query.count()
            permisos_count = PermisoRol.query.count()
            
            print(f"   - Módulos configurados: {modulos_count}")
            print(f"   - Permisos configurados: {permisos_count}")
            
            if modulos_count == 0:
                print("   ⚠️  Sistema de permisos no inicializado")
                print("   💡 Ejecutar: service.inicializar_modulos_sistema(admin_user.id)")
            
        except Exception as e:
            print(f"   ❌ Error verificando estado: {e}")
        
        # 5. Verificar rutas de configuraciones
        print("\n5. Verificación de rutas:")
        with app.test_client() as client:
            try:
                # Simular login como admin
                with client.session_transaction() as sess:
                    sess['user_id'] = str(admin_user.id)
                    sess['user_role'] = admin_user.rol.value
                    sess['user_email'] = admin_user.email
                
                # Probar acceso a configuraciones
                response = client.get('/configuraciones/')
                print(f"   - GET /configuraciones/: {response.status_code}")
                
                response = client.get('/configuraciones/usuarios')
                print(f"   - GET /configuraciones/usuarios: {response.status_code}")
                
            except Exception as e:
                print(f"   ❌ Error probando rutas: {e}")

if __name__ == '__main__':
    debug_admin_permissions()
