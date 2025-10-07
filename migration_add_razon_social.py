
#!/usr/bin/env python3
"""
Migración para agregar el campo razon_social a la tabla clientes
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv('DATABASE_URL')

def add_razon_social_column():
    """Agregar columna razon_social a la tabla clientes"""
    if not DATABASE_URL:
        logger.error("DATABASE_URL environment variable not set")
        return False
    
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    cursor = conn.cursor()
    
    try:
        logger.info("🔄 Agregando columna razon_social a tabla clientes...")
        
        # Verificar si la columna ya existe
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'clientes' AND column_name = 'razon_social';
        """)
        
        if cursor.fetchone():
            logger.info("✅ La columna razon_social ya existe en la tabla clientes")
            return True
        
        # Agregar la columna razon_social
        cursor.execute("""
            ALTER TABLE clientes 
            ADD COLUMN razon_social VARCHAR(250);
        """)
        
        # Confirmar los cambios
        conn.commit()
        logger.info("✅ Columna razon_social agregada exitosamente a la tabla clientes")
        
        # Verificar que se agregó correctamente
        cursor.execute("""
            SELECT column_name, data_type, character_maximum_length 
            FROM information_schema.columns 
            WHERE table_name = 'clientes' AND column_name = 'razon_social';
        """)
        
        result = cursor.fetchone()
        if result:
            logger.info(f"📋 Nueva columna: {result[0]} ({result[1]}({result[2]}))")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error durante la migración: {e}")
        conn.rollback()
        return False
        
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    success = add_razon_social_column()
    sys.exit(0 if success else 1)
