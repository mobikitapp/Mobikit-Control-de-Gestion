
#!/usr/bin/env python3
"""
Script para limpiar forzosamente órdenes de compra y órdenes de fabricación
"""

import psycopg2
import os

def limpiar_ordenes_forzado():
    """Limpia forzosamente todas las órdenes de compra y fabricación"""
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("Error: DATABASE_URL no encontrada")
        return
    
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    try:
        print("Iniciando limpieza forzada de órdenes...")
        
        # 1. Eliminar todas las dependencias de órdenes de fabricación
        print("Eliminando categorías de órdenes de fabricación...")
        cursor.execute("DELETE FROM orden_fabricacion_categorias")
        
        # 2. Eliminar todas las órdenes de fabricación
        print("Eliminando órdenes de fabricación...")
        cursor.execute("DELETE FROM ordenes_fabricacion")
        
        # 3. Eliminar todas las órdenes de compra
        print("Eliminando órdenes de compra...")
        cursor.execute("DELETE FROM ordenes_compra")
        
        # 4. Eliminar entregas de contrato
        print("Eliminando entregas de contrato...")
        cursor.execute("DELETE FROM entregas_contrato")
        
        # 5. Eliminar categorías de proyectos (esto hace que no aparezcan como órdenes de compra)
        print("Eliminando categorías de proyectos...")
        cursor.execute("DELETE FROM proyecto_categorias")
        
        # 6. Resetear estados de proyectos a 'activo'
        print("Reseteando estados de proyectos...")
        cursor.execute("""
            UPDATE proyectos 
            SET estado = 'activo', 
                fecha_entrega_real = NULL,
                updated_at = CURRENT_TIMESTAMP
            WHERE estado != 'activo'
        """)
        
        # 7. Eliminar despachos asociados
        print("Eliminando despachos...")
        cursor.execute("DELETE FROM despacho_archivos")
        cursor.execute("DELETE FROM despachos")
        
        # 8. Eliminar recordatorios relacionados
        print("Eliminando recordatorios...")
        cursor.execute("DELETE FROM recordatorios WHERE tipo IN ('despacho', 'proyecto')")
        
        # 9. Limpiar auditoría relacionada
        print("Limpiando auditoría...")
        cursor.execute("""
            DELETE FROM auditoria 
            WHERE tabla_afectada IN ('ordenes_fabricacion', 'ordenes_compra', 'despachos', 'entregas_contrato')
        """)
        
        # 10. Resetear secuencias si existen
        print("Reseteando secuencias...")
        try:
            cursor.execute("ALTER SEQUENCE ordenes_fabricacion_id_seq RESTART WITH 1")
            cursor.execute("ALTER SEQUENCE ordenes_compra_id_seq RESTART WITH 1") 
            cursor.execute("ALTER SEQUENCE despachos_id_seq RESTART WITH 1")
        except Exception as e:
            print(f"Nota: No se pudieron resetear secuencias: {e}")
        
        # Verificar limpieza
        cursor.execute("SELECT COUNT(*) FROM ordenes_fabricacion")
        fab_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM ordenes_compra") 
        oc_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM proyecto_categorias")
        cat_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM despachos")
        desp_count = cursor.fetchone()[0]
        
        print(f"\nResultados de la limpieza:")
        print(f"- Órdenes de fabricación restantes: {fab_count}")
        print(f"- Órdenes de compra restantes: {oc_count}")
        print(f"- Categorías de proyecto restantes: {cat_count}")
        print(f"- Despachos restantes: {desp_count}")
        
        conn.commit()
        print("\n✅ Limpieza forzada completada exitosamente!")
        print("Los proyectos permanecen pero sin categorías asignadas.")
        print("Para que aparezcan como órdenes de compra, debes asignarles categorías nuevamente.")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Error durante la limpieza: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    respuesta = input("⚠️  ADVERTENCIA: Esto eliminará TODAS las órdenes de compra y fabricación. ¿Continuar? (escriba 'SI' para confirmar): ")
    if respuesta == 'SI':
        limpiar_ordenes_forzado()
    else:
        print("Operación cancelada.")
