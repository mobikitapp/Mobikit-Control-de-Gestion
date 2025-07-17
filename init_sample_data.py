
#!/usr/bin/env python3
"""
Script para inicializar datos de ejemplo en la base de datos de Mobikit
"""

import sqlite3
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import random

def init_sample_data():
    """Inicializa datos de ejemplo para pruebas"""
    print("Inicializando datos de ejemplo...")
    
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    try:
        # 1. Crear áreas
        create_sample_areas(cursor)
        
        # 2. Crear usuarios de ejemplo
        create_sample_users(cursor)
        
        # 3. Crear clientes de ejemplo
        create_sample_clients(cursor)
        
        # 4. Crear proyectos de ejemplo
        create_sample_projects(cursor)
        
        # 5. Crear configuraciones iniciales
        create_initial_config(cursor)
        
        conn.commit()
        print("Datos de ejemplo creados exitosamente!")
        
    except Exception as e:
        conn.rollback()
        print(f"Error al crear datos de ejemplo: {e}")
        raise
    finally:
        conn.close()

def create_sample_areas(cursor):
    """Crea áreas de ejemplo"""
    areas = [
        ('Diseño', 'Área encargada del diseño y planificación de muebles'),
        ('Producción', 'Área de fabricación y manufactura'),
        ('Calidad', 'Control de calidad y supervisión'),
        ('Embalaje', 'Preparación y embalaje de productos'),
        ('Despacho', 'Logística y entrega de productos'),
        ('Administración', 'Gestión administrativa y financiera')
    ]
    
    for nombre, descripcion in areas:
        cursor.execute('''
            INSERT OR IGNORE INTO areas (nombre, descripcion, activo)
            VALUES (?, ?, ?)
        ''', (nombre, descripcion, True))

def create_sample_users(cursor):
    """Crea usuarios de ejemplo"""
    usuarios = [
        ('diseñador1', 'Carlos Mendoza', 'diseñador', 'carlos.mendoza@mobikit.com', '9-1234-5678'),
        ('operario1', 'Ana García', 'operación', 'ana.garcia@mobikit.com', '9-2345-6789'),
        ('supervisor1', 'Luis Rodriguez', 'general', 'luis.rodriguez@mobikit.com', '9-3456-7890'),
        ('embalador1', 'María López', 'embalaje', 'maria.lopez@mobikit.com', '9-4567-8901'),
        ('despachador1', 'José Silva', 'despacho', 'jose.silva@mobikit.com', '9-5678-9012')
    ]
    
    for username, nombre, rol, email, telefono in usuarios:
        password_hash = generate_password_hash('123456')
        cursor.execute('''
            INSERT OR IGNORE INTO usuarios (
                username, password_hash, nombre, rol, email, telefono, activo
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (username, password_hash, nombre, rol, email, telefono, True))

def create_sample_clients(cursor):
    """Crea clientes de ejemplo"""
    clientes = [
        ('Muebles Moderna Ltda.', '76.123.456-7', 'compras@mueblesmoderna.cl', '2-2234-5678', 
         'Av. Principal 1234', 'Santiago', 'Metropolitana', 'Pedro Sánchez'),
        ('Decoraciones Elite S.A.', '96.789.012-3', 'contacto@decoracioneselite.cl', '2-3345-6789',
         'Los Leones 567', 'Las Condes', 'Metropolitana', 'Carmen Ruiz'),
        ('Hogar & Estilo', '77.456.789-0', 'ventas@hogaryestilo.cl', '2-4456-7890',
         'Mall Plaza Norte Local 45', 'Huechuraba', 'Metropolitana', 'Ricardo Torres'),
        ('Oficinas Ejecutivas', '85.234.567-1', 'admin@oficinasejecutivas.cl', '2-5567-8901',
         'Providencia 890', 'Providencia', 'Metropolitana', 'Sofía Morales')
    ]
    
    for nombre, rut, email, telefono, direccion, ciudad, region, contacto in clientes:
        cursor.execute('''
            INSERT OR IGNORE INTO clientes (
                nombre, rut, email, telefono, direccion, ciudad, region, contacto_principal, activo
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (nombre, rut, email, telefono, direccion, ciudad, region, contacto, True))

def create_sample_projects(cursor):
    """Crea proyectos de ejemplo"""
    # Obtener IDs de clientes y usuarios
    cursor.execute('SELECT id FROM clientes LIMIT 4')
    cliente_ids = [row[0] for row in cursor.fetchall()]
    
    cursor.execute('SELECT id FROM usuarios WHERE rol = "diseñador" LIMIT 1')
    diseñador_id = cursor.fetchone()[0] if cursor.rowcount > 0 else 1
    
    proyectos = [
        ('MOB-2024-001', 'Escritorio Ejecutivo Premium', cliente_ids[0] if cliente_ids else 1, 
         'Escritorio ejecutivo con cajones laterales y acabado en nogal', 'diseño', 'alta',
         datetime.now().date(), (datetime.now() + timedelta(days=30)).date(), 1500000),
        
        ('MOB-2024-002', 'Juego de Comedor 6 Personas', cliente_ids[1] if len(cliente_ids) > 1 else 1,
         'Mesa de comedor redonda con 6 sillas tapizadas', 'producción', 'media',
         (datetime.now() - timedelta(days=5)).date(), (datetime.now() + timedelta(days=25)).date(), 800000),
        
        ('MOB-2024-003', 'Estantería Modular Oficina', cliente_ids[2] if len(cliente_ids) > 2 else 1,
         'Sistema de estanterías modulares para oficina', 'embalaje', 'baja',
         (datetime.now() - timedelta(days=20)).date(), (datetime.now() + timedelta(days=10)).date(), 650000),
        
        ('MOB-2024-004', 'Mueble TV Living', cliente_ids[3] if len(cliente_ids) > 3 else 1,
         'Mueble para TV con compartimentos para equipos', 'completado', 'media',
         (datetime.now() - timedelta(days=45)).date(), (datetime.now() - timedelta(days=5)).date(), 450000)
    ]
    
    for codigo, nombre, cliente_id, descripcion, estado, prioridad, fecha_inicio, fecha_entrega, presupuesto in proyectos:
        cursor.execute('''
            INSERT OR IGNORE INTO proyectos (
                codigo, nombre, cliente_id, descripcion, estado, prioridad,
                fecha_inicio, fecha_entrega, diseñador_id, presupuesto
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (codigo, nombre, cliente_id, descripcion, estado, prioridad, 
              fecha_inicio, fecha_entrega, diseñador_id, presupuesto))

def create_initial_config(cursor):
    """Crea configuraciones iniciales"""
    configuraciones = [
        ('empresa_nombre', 'Mobikit', 'Nombre de la empresa', 'string'),
        ('empresa_rut', '12.345.678-9', 'RUT de la empresa', 'string'),
        ('empresa_direccion', 'Av. Industrial 1234, Santiago', 'Dirección de la empresa', 'string'),
        ('empresa_telefono', '2-2345-6789', 'Teléfono principal', 'string'),
        ('empresa_email', 'contacto@mobikit.com', 'Email de contacto', 'string'),
        ('notificaciones_email', 'true', 'Activar notificaciones por email', 'boolean'),
        ('tiempo_sesion_minutos', '480', 'Duración de sesión en minutos', 'integer'),
        ('backup_automatico', 'true', 'Realizar backup automático diario', 'boolean'),
        ('moneda_principal', 'CLP', 'Moneda principal para presupuestos', 'string'),
        ('timezone', 'America/Santiago', 'Zona horaria del sistema', 'string')
    ]
    
    for clave, valor, descripcion, tipo in configuraciones:
        cursor.execute('''
            INSERT OR IGNORE INTO configuraciones (clave, valor, descripcion, tipo)
            VALUES (?, ?, ?, ?)
        ''', (clave, valor, descripcion, tipo))

if __name__ == '__main__':
    init_sample_data()
