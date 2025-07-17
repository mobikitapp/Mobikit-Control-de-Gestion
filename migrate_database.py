
#!/usr/bin/env python3
"""
Script de migración para actualizar la base de datos existente de Mobikit
al nuevo esquema completo.
"""

import sqlite3
import json
from datetime import datetime

def migrate_database():
    """Ejecuta la migración de la base de datos"""
    print("Iniciando migración de base de datos...")
    
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # 1. Crear tabla de respaldo de datos existentes
        backup_existing_data(cursor)
        
        # 2. Agregar nuevas columnas a tablas existentes
        add_new_columns(cursor)
        
        # 3. Crear nuevas tablas
        create_new_tables(cursor)
        
        # 4. Migrar datos existentes
        migrate_existing_data(cursor)
        
        # 5. Crear índices y triggers
        create_indexes_and_triggers(cursor)
        
        conn.commit()
        print("Migración completada exitosamente!")
        
    except Exception as e:
        conn.rollback()
        print(f"Error durante la migración: {e}")
        raise
    finally:
        conn.close()

def backup_existing_data(cursor):
    """Crea respaldo de datos existentes"""
    print("Creando respaldo de datos existentes...")
    
    # Backup usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backup_usuarios AS 
        SELECT * FROM usuarios WHERE 1=0
    ''')
    cursor.execute('INSERT INTO backup_usuarios SELECT * FROM usuarios')
    
    # Backup proyectos
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS backup_proyectos AS 
        SELECT * FROM proyectos WHERE 1=0
    ''')
    cursor.execute('INSERT INTO backup_proyectos SELECT * FROM proyectos')

def add_new_columns(cursor):
    """Agrega nuevas columnas a tablas existentes"""
    print("Agregando nuevas columnas...")
    
    # Nuevas columnas para usuarios
    new_user_columns = [
        ('apellido', 'TEXT'),
        ('telefono', 'TEXT'),
        ('area_id', 'INTEGER'),
        ('activo', 'BOOLEAN DEFAULT TRUE'),
        ('ultimo_acceso', 'TIMESTAMP'),
        ('updated_at', 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
    ]
    
    for column_name, column_type in new_user_columns:
        try:
            cursor.execute(f'ALTER TABLE usuarios ADD COLUMN {column_name} {column_type}')
        except sqlite3.OperationalError:
            pass  # La columna ya existe
    
    # Nuevas columnas para proyectos
    new_project_columns = [
        ('codigo', 'TEXT'),
        ('cliente_id', 'INTEGER'),
        ('prioridad', 'TEXT DEFAULT "media"'),
        ('fecha_entrega_real', 'DATE'),
        ('supervisor_id', 'INTEGER'),
        ('presupuesto', 'DECIMAL(12,2)'),
        ('costo_real', 'DECIMAL(12,2)'),
        ('observaciones', 'TEXT')
    ]
    
    for column_name, column_type in new_project_columns:
        try:
            cursor.execute(f'ALTER TABLE proyectos ADD COLUMN {column_name} {column_type}')
        except sqlite3.OperationalError:
            pass

def create_new_tables(cursor):
    """Crea las nuevas tablas"""
    print("Creando nuevas tablas...")
    
    # Ejecutar el schema SQL completo
    try:
        with open('database_schema.sql', 'r', encoding='utf-8') as f:
            schema_sql = f.read()
            cursor.executescript(schema_sql)
    except FileNotFoundError:
        print("Archivo database_schema.sql no encontrado. Creando tablas manualmente...")
        create_tables_manually(cursor)

def create_tables_manually(cursor):
    """Crear tablas nuevas manualmente si no existe el archivo SQL"""
    
    # Crear tabla de clientes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            rut TEXT UNIQUE,
            email TEXT,
            telefono TEXT,
            direccion TEXT,
            ciudad TEXT,
            region TEXT,
            contacto_principal TEXT,
            observaciones TEXT,
            activo BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Otras tablas nuevas...
    tables_sql = [
        '''CREATE TABLE IF NOT EXISTS areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL UNIQUE,
            descripcion TEXT,
            responsable_id INTEGER,
            activo BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        
        '''CREATE TABLE IF NOT EXISTS incidencias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto_id INTEGER,
            tarea_id INTEGER,
            usuario_reporta_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            severidad TEXT DEFAULT 'media',
            titulo TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            estado TEXT DEFAULT 'abierta',
            usuario_asignado_id INTEGER,
            fecha_resolucion TIMESTAMP,
            solucion TEXT,
            costo_incidencia DECIMAL(10,2),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        
        '''CREATE TABLE IF NOT EXISTS notificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            titulo TEXT NOT NULL,
            mensaje TEXT NOT NULL,
            leida BOOLEAN DEFAULT FALSE,
            url_accion TEXT,
            metadatos TEXT,
            expira_en TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        
        '''CREATE TABLE IF NOT EXISTS auditoria (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tabla_afectada TEXT NOT NULL,
            registro_id INTEGER NOT NULL,
            accion TEXT NOT NULL,
            usuario_id INTEGER,
            valores_anteriores TEXT,
            valores_nuevos TEXT,
            ip_address TEXT,
            user_agent TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )'''
    ]
    
    for table_sql in tables_sql:
        cursor.execute(table_sql)

def migrate_existing_data(cursor):
    """Migra datos existentes al nuevo formato"""
    print("Migrando datos existentes...")
    
    # Generar códigos únicos para proyectos existentes
    cursor.execute('SELECT id, nombre FROM proyectos WHERE codigo IS NULL')
    proyectos_sin_codigo = cursor.fetchall()
    
    for proyecto_id, nombre in proyectos_sin_codigo:
        codigo = f"MOB-{proyecto_id:04d}"
        cursor.execute('UPDATE proyectos SET codigo = ? WHERE id = ?', (codigo, proyecto_id))
    
    # Crear clientes a partir de los nombres de cliente en proyectos
    cursor.execute('SELECT DISTINCT cliente FROM proyectos WHERE cliente IS NOT NULL')
    clientes_existentes = cursor.fetchall()
    
    for (cliente_nombre,) in clientes_existentes:
        # Verificar si ya existe el cliente
        cursor.execute('SELECT id FROM clientes WHERE nombre = ?', (cliente_nombre,))
        if not cursor.fetchone():
            cursor.execute('''
                INSERT INTO clientes (nombre, activo)
                VALUES (?, ?)
            ''', (cliente_nombre, True))
            
            cliente_id = cursor.lastrowid
            
            # Actualizar proyectos para usar el ID del cliente
            cursor.execute('''
                UPDATE proyectos SET cliente_id = ? WHERE cliente = ?
            ''', (cliente_id, cliente_nombre))

def create_indexes_and_triggers(cursor):
    """Crea índices y triggers para optimización y auditoría"""
    print("Creando índices y triggers...")
    
    # Índices principales
    indexes = [
        'CREATE INDEX IF NOT EXISTS idx_proyectos_cliente ON proyectos(cliente_id)',
        'CREATE INDEX IF NOT EXISTS idx_proyectos_estado ON proyectos(estado)',
        'CREATE INDEX IF NOT EXISTS idx_tareas_proyecto ON tareas(proyecto_id)',
        'CREATE INDEX IF NOT EXISTS idx_tareas_usuario ON tareas(usuario_asignado_id)',
        'CREATE INDEX IF NOT EXISTS idx_notificaciones_usuario ON notificaciones(usuario_id)',
        'CREATE INDEX IF NOT EXISTS idx_auditoria_tabla_registro ON auditoria(tabla_afectada, registro_id)'
    ]
    
    for index_sql in indexes:
        cursor.execute(index_sql)

if __name__ == '__main__':
    migrate_database()
