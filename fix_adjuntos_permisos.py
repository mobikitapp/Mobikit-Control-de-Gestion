
#!/usr/bin/env python3
"""
Script para otorgar permisos de adjuntos de proyectos a roles General, Operaciones y Ventas
"""

from app import create_app, db
from services.permisos_service import PermisosService
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    app = create_app()
    
    with app.app_context():
        try:
            permisos_service = PermisosService()
            
            # Permisos de adjuntos para diferentes roles usando tipos válidos del sistema dinámico
            permisos_adjuntos = [
                # General - acceso completo a proyectos incluyendo adjuntos
                {'rol': 'general', 'modulo': 'proyectos', 'tipo_permiso': 'lectura', 'permitido': True},
                {'rol': 'general', 'modulo': 'proyectos', 'tipo_permiso': 'creacion', 'permitido': True},
                {'rol': 'general', 'modulo': 'proyectos', 'tipo_permiso': 'edicion', 'permitido': True},
                {'rol': 'general', 'modulo': 'proyectos', 'tipo_permiso': 'eliminacion', 'permitido': True},
                
                # Operaciones - acceso completo a proyectos incluyendo adjuntos
                {'rol': 'operaciones', 'modulo': 'proyectos', 'tipo_permiso': 'lectura', 'permitido': True},
                {'rol': 'operaciones', 'modulo': 'proyectos', 'tipo_permiso': 'creacion', 'permitido': True},
                {'rol': 'operaciones', 'modulo': 'proyectos', 'tipo_permiso': 'edicion', 'permitido': True},
                {'rol': 'operaciones', 'modulo': 'proyectos', 'tipo_permiso': 'eliminacion', 'permitido': False},
                
                # Ventas - acceso a lectura, creación y edición de proyectos incluyendo adjuntos
                {'rol': 'ventas', 'modulo': 'proyectos', 'tipo_permiso': 'lectura', 'permitido': True},
                {'rol': 'ventas', 'modulo': 'proyectos', 'tipo_permiso': 'creacion', 'permitido': True},
                {'rol': 'ventas', 'modulo': 'proyectos', 'tipo_permiso': 'edicion', 'permitido': True},
                {'rol': 'ventas', 'modulo': 'proyectos', 'tipo_permiso': 'eliminacion', 'permitido': False},
            ]
            
            print("Actualizando permisos de adjuntos de proyectos...")
            print("="*60)
            
            for permiso_data in permisos_adjuntos:
                exito, mensaje = permisos_service.actualizar_permiso(
                    permiso_data['rol'],
                    permiso_data['modulo'], 
                    permiso_data['tipo_permiso'],
                    permiso_data['permitido'],
                    1  # user_id - using 1 as admin user
                )
                
                if exito:
                    logger.info(f"✓ Actualizado: {permiso_data['rol']}.{permiso_data['modulo']}.{permiso_data['tipo_permiso']} = {permiso_data['permitido']}")
                else:
                    logger.error(f"✗ Error: {mensaje}")
            
            # Verificar que los permisos se aplicaron correctamente
            resultado_general_lectura = permisos_service.verificar_permiso_dinamico('general', 'proyectos', 'lectura')
            resultado_operaciones_lectura = permisos_service.verificar_permiso_dinamico('operaciones', 'proyectos', 'lectura')
            resultado_ventas_lectura = permisos_service.verificar_permiso_dinamico('ventas', 'proyectos', 'lectura')
            resultado_ventas_creacion = permisos_service.verificar_permiso_dinamico('ventas', 'proyectos', 'creacion')
            resultado_operaciones_creacion = permisos_service.verificar_permiso_dinamico('operaciones', 'proyectos', 'creacion')
            
            print("\n" + "="*60)
            print("VERIFICACIÓN DE PERMISOS DE ADJUNTOS DE PROYECTOS:")
            print("="*60)
            print(f"• General - Lectura Proyectos: {'✓ SÍ' if resultado_general_lectura else '✗ NO'}")
            print(f"• Operaciones - Lectura Proyectos: {'✓ SÍ' if resultado_operaciones_lectura else '✗ NO'}")
            print(f"• Operaciones - Creación Proyectos: {'✓ SÍ' if resultado_operaciones_creacion else '✗ NO'}")
            print(f"• Ventas - Lectura Proyectos: {'✓ SÍ' if resultado_ventas_lectura else '✗ NO'}")
            print(f"• Ventas - Creación Proyectos: {'✓ SÍ' if resultado_ventas_creacion else '✗ NO'}")
            print("="*60)
            
            if (resultado_general_lectura and resultado_operaciones_lectura and 
                resultado_ventas_lectura and resultado_operaciones_creacion and resultado_ventas_creacion):
                print("🎉 ÉXITO: Permisos configurados correctamente para acceso a adjuntos")
                print("📋 Los roles General, Operaciones y Ventas pueden ver y gestionar adjuntos de proyectos")
            else:
                print("❌ ERROR: Algunos permisos no se configuraron correctamente")
                
        except Exception as e:
            logger.error(f"Error ejecutando actualización de permisos: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
