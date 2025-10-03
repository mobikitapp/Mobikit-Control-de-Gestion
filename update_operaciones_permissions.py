
#!/usr/bin/env python3
"""
Script para actualizar los permisos del rol de operaciones
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
            
            # Sincronizar permisos por defecto (esto aplicará los cambios nuevos)
            success, message = permisos_service.sincronizar_permisos_defecto(
                admin_user.id, 
                only_missing=False  # Forzar actualización de todos los permisos
            )
            
            if success:
                logger.info(f"Permisos actualizados correctamente: {message}")
                
                # Verificar que los permisos se aplicaron correctamente
                resultado = permisos_service.verificar_permiso_dinamico(
                    'operaciones', 'contratos', 'creacion'
                )
                
                if resultado:
                    logger.info("✓ Rol operaciones ahora tiene permiso de creación en contratos")
                else:
                    logger.warning("⚠ El permiso de creación en contratos no se aplicó correctamente")
                    
                # Verificar acceso a proyectos
                resultado_proyectos = permisos_service.verificar_permiso_dinamico(
                    'operaciones', 'proyectos', 'lectura'
                )
                
                if resultado_proyectos:
                    logger.info("✓ Rol operaciones mantiene permiso de lectura en proyectos")
                else:
                    logger.warning("⚠ El permiso de lectura en proyectos no está configurado")
                    
                print("\n" + "="*60)
                print("PERMISOS ACTUALIZADOS PARA ROL OPERACIONES:")
                print("="*60)
                print("• Proyectos: Lectura (detalle de proyectos)")
                print("• Contratos: Lectura + Creación (detalle y crear contratos/OC)")
                print("• Fabricación: Lectura, Creación, Edición")
                print("• Despachos: Lectura, Creación, Edición")
                print("• Áreas: Lectura, Creación, Edición")
                print("="*60)
                
            else:
                logger.error(f"Error actualizando permisos: {message}")
                
        except Exception as e:
            logger.error(f"Error ejecutando actualización de permisos: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
