
#!/usr/bin/env python3
"""
Script para limpiar estados antiguos de la base de datos y mantener solo estados simplificados
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from datetime import datetime

def migrate_clean_estados():
    """Limpia la base de datos de estados antiguos"""
    print("Iniciando limpieza de estados antiguos...")
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if not DATABASE_URL:
        print("Error: DATABASE_URL no encontrada")
        return
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    try:
        # Mostrar estados actuales
        cursor.execute("SELECT DISTINCT estado FROM proyectos ORDER BY estado")
        estados_actuales = cursor.fetchall()
        print(f"Estados encontrados: {[r['estado'] for r in estados_actuales]}")
        
        # Contar proyectos por estado
        cursor.execute("SELECT estado, COUNT(*) as cantidad FROM proyectos GROUP BY estado")
        conteos = cursor.fetchall()
        print("Conteo de proyectos por estado:")
        for row in conteos:
            print(f"  {row['estado']}: {row['cantidad']}")
        
        # Eliminar restricción existente
        cursor.execute("ALTER TABLE proyectos DROP CONSTRAINT IF EXISTS proyectos_estado_check")
        
        # Estados antiguos que deben ser migrados a 'activo'
        estados_antiguos = [
            'diseño', 'proyecto_simple', 'en_desarrollo', 'aprobado_produccion',
            'seccionado', 'enchapado', 'mecanizado', 'produccion_completa',
            'embalando', 'listo_despacho', 'terminado', 'completado'
        ]
        
        # Migrar estados antiguos a 'activo'
        for estado_antiguo in estados_antiguos:
            cursor.execute("""
                UPDATE proyectos SET estado = 'activo' 
                WHERE estado = %s
            """, (estado_antiguo,))
            if cursor.rowcount > 0:
                print(f"Migrados {cursor.rowcount} proyectos de '{estado_antiguo}' a 'activo'")
        
        # Migrar estados específicos a 'entregado'
        cursor.execute("""
            UPDATE proyectos SET estado = 'entregado' 
            WHERE estado IN ('despachado', 'entregado_cliente', 'finalizado')
        """)
        if cursor.rowcount > 0:
            print(f"Migrados {cursor.rowcount} proyectos a 'entregado'")
        
        # Eliminar registros problemáticos (nulls, vacíos, estados no válidos)
        cursor.execute("""
            SELECT id, codigo, nombre FROM proyectos 
            WHERE estado IS NULL OR estado = '' OR estado NOT IN ('activo', 'entregado', 'cancelado')
        """)
        proyectos_problematicos = cursor.fetchall()
        
        if proyectos_problematicos:
            print(f"Encontrados {len(proyectos_problematicos)} proyectos con estados problemáticos:")
            for p in proyectos_problematicos:
                print(f"  ID {p['id']}: {p['codigo']} - {p['nombre']}")
            
            # Eliminar dependencias primero
            for p in proyectos_problematicos:
                cursor.execute("DELETE FROM proyecto_categorias WHERE proyecto_id = %s", (p['id'],))
                cursor.execute("DELETE FROM ordenes_fabricacion WHERE proyecto_id = %s", (p['id'],))
                cursor.execute("DELETE FROM tareas WHERE proyecto_id = %s", (p['id'],))
                cursor.execute("DELETE FROM despachos WHERE proyecto_id = %s", (p['id'],))
            
            # Eliminar proyectos problemáticos
            cursor.execute("""
                DELETE FROM proyectos 
                WHERE estado IS NULL OR estado = '' OR estado NOT IN ('activo', 'entregado', 'cancelado')
            """)
            print(f"Eliminados {cursor.rowcount} proyectos problemáticos")
        
        # Crear nueva restricción
        cursor.execute("""
            ALTER TABLE proyectos ADD CONSTRAINT proyectos_estado_check 
            CHECK (estado IN ('activo', 'entregado', 'cancelado'))
        """)
        
        # Mostrar resultado final
        cursor.execute("SELECT estado, COUNT(*) as cantidad FROM proyectos GROUP BY estado ORDER BY estado")
        conteos_finales = cursor.fetchall()
        print("\nEstados finales después de la limpieza:")
        for row in conteos_finales:
            print(f"  {row['estado']}: {row['cantidad']}")
        
        conn.commit()
        print("Limpieza de estados completada exitosamente")

    except Exception as e:
        conn.rollback()
        print(f"Error durante la limpieza: {e}")
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_clean_estados()
