
#!/usr/bin/env python3
"""
Script para otorgar permisos de adjuntos a roles general y operaciones
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
            
            # Permisos de adjuntos para diferentes roles
            permisos_adjuntos = [
                # General - acceso completo a adjuntos
                {'rol': 'general', 'modulo': 'proyectos', 'tipo_permiso': 'adjuntos', 'permitido': True},
                {'rol': 'general', 'modulo': 'proyectos', 'tipo_permiso': 'adjuntos_eliminar', 'permitido': True},
                
                # Operaciones - solo lectura de adjuntos
                {'rol': 'operaciones', 'modulo': 'proyectos', 'tipo_permiso': 'adjuntos', 'permitido': True},
                {'rol': 'operaciones', 'modulo': 'proyectos', 'tipo_permiso': 'adjuntos_eliminar', 'permitido': False},
                
                # Ventas - acceso a adjuntos
                {'rol': 'ventas', 'modulo': 'proyectos', 'tipo_permiso': 'adjuntos', 'permitido': True},
                {'rol': 'ventas', 'modulo': 'proyectos', 'tipo_permiso': 'adjuntos_eliminar', 'permitido': False},
            ]
            
            print("Actualizando permisos de adjuntos de proyectos...")
            print("="*60)
            
            for permiso_data in permisos_adjuntos:
                exito, mensaje = permisos_service.actualizar_permiso_dinamico(
                    permiso_data['rol'],
                    permiso_data['modulo'], 
                    permiso_data['tipo_permiso'],
                    permiso_data['permitido']
                )
                
                if exito:
                    logger.info(f"✓ Actualizado: {permiso_data['rol']}.{permiso_data['modulo']}.{permiso_data['tipo_permiso']} = {permiso_data['permitido']}")
                else:
                    logger.error(f"✗ Error: {mensaje}")
            
            # Verificar que los permisos se aplicaron correctamente
            resultado_general = permisos_service.verificar_permiso_dinamico('general', 'proyectos', 'adjuntos')
            resultado_operaciones = permisos_service.verificar_permiso_dinamico('operaciones', 'proyectos', 'adjuntos')
            resultado_ventas = permisos_service.verificar_permiso_dinamico('ventas', 'proyectos', 'adjuntos')
            
            print("\n" + "="*60)
            print("VERIFICACIÓN DE PERMISOS DE ADJUNTOS:")
            print("="*60)
            print(f"• General - Adjuntos: {'✓ SÍ' if resultado_general else '✗ NO'}")
            print(f"• Operaciones - Adjuntos: {'✓ SÍ' if resultado_operaciones else '✗ NO'}")
            print(f"• Ventas - Adjuntos: {'✓ SÍ' if resultado_ventas else '✗ NO'}")
            print("="*60)
            
            if resultado_general and resultado_operaciones and resultado_ventas:
                print("🎉 ÉXITO: Permisos de adjuntos configurados correctamente")
            else:
                print("❌ ERROR: Algunos permisos no se configuraron correctamente")
                
        except Exception as e:
            logger.error(f"Error ejecutando actualización de permisos: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()
