
#!/usr/bin/env python3
"""
Script para otorgar acceso completo de proyectos al rol operaciones
"""

from app import create_app, db
from services.permisos_service import PermisosService
from models import User, RolUsuario
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    app = create_app()
    
    with app.app_context():
        try:
            # Obtener un usuario admin para ejecutar la sincronización
            admin_user = User.query.filter_by(rol=RolUsuario.ADMIN).first()
            if not admin_user:
                logger.error("No se encontró un usuario administrador")
                return
            
            permisos_service = PermisosService()
            
            # Actualizar permisos específicos para operaciones en proyectos
            permisos_a_actualizar = [
                {'rol': 'operaciones', 'modulo': 'proyectos', 'tipo_permiso': 'lectura', 'permitido': True},
                {'rol': 'operaciones', 'modulo': 'proyectos', 'tipo_permiso': 'creacion', 'permitido': True},
                {'rol': 'operaciones', 'modulo': 'proyectos', 'tipo_permiso': 'edicion', 'permitido': True},
            ]
            
            for permiso_data in permisos_a_actualizar:
                success, mensaje = permisos_service.actualizar_permiso(
                    permiso_data['rol'],
                    permiso_data['modulo'], 
                    permiso_data['tipo_permiso'],
                    permiso_data['permitido'],
                    admin_user.id
                )
                
                if success:
                    logger.info(f"✓ Actualizado: {permiso_data['rol']}.{permiso_data['modulo']}.{permiso_data['tipo_permiso']} = {permiso_data['permitido']}")
                else:
                    logger.error(f"✗ Error: {mensaje}")
            
            # Verificar que los permisos se aplicaron correctamente
            resultado_lectura = permisos_service.verificar_permiso_dinamico('operaciones', 'proyectos', 'lectura')
            resultado_creacion = permisos_service.verificar_permiso_dinamico('operaciones', 'proyectos', 'creacion') 
            resultado_edicion = permisos_service.verificar_permiso_dinamico('operaciones', 'proyectos', 'edicion')
            
            print("\n" + "="*60)
            print("VERIFICACIÓN DE PERMISOS PARA ROL OPERACIONES EN PROYECTOS:")
            print("="*60)
            print(f"• Lectura de proyectos: {'✓ SÍ' if resultado_lectura else '✗ NO'}")
            print(f"• Creación de proyectos: {'✓ SÍ' if resultado_creacion else '✗ NO'}")
            print(f"• Edición de proyectos: {'✓ SÍ' if resultado_edicion else '✗ NO'}")
            print("="*60)
            
            if resultado_lectura and resultado_creacion and resultado_edicion:
                print("🎉 ÉXITO: Rol operaciones ahora tiene acceso completo a proyectos")
            else:
                print("⚠️  ADVERTENCIA: Algunos permisos no se aplicaron correctamente")
                
        except Exception as e:
            logger.error(f"Error ejecutando actualización de permisos: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
