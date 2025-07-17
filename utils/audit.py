
import sqlite3
import json
from datetime import datetime
from flask import session, request

def log_audit(tabla_afectada, registro_id, accion, valores_anteriores=None, valores_nuevos=None):
    """
    Registra una acción en la tabla de auditoría
    
    Args:
        tabla_afectada: Nombre de la tabla modificada
        registro_id: ID del registro afectado
        accion: Tipo de acción (INSERT, UPDATE, DELETE)
        valores_anteriores: Diccionario con valores antes del cambio
        valores_nuevos: Diccionario con valores después del cambio
    """
    try:
        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()
        
        usuario_id = session.get('user_id')
        ip_address = request.remote_addr if request else None
        user_agent = request.headers.get('User-Agent') if request else None
        
        cursor.execute('''
            INSERT INTO auditoria (
                tabla_afectada, registro_id, accion, usuario_id,
                valores_anteriores, valores_nuevos, ip_address, user_agent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            tabla_afectada,
            registro_id,
            accion,
            usuario_id,
            json.dumps(valores_anteriores) if valores_anteriores else None,
            json.dumps(valores_nuevos) if valores_nuevos else None,
            ip_address,
            user_agent
        ))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Error al registrar auditoría: {e}")

def get_audit_trail(tabla=None, registro_id=None, usuario_id=None, limit=100):
    """
    Obtiene el historial de auditoría filtrado
    
    Args:
        tabla: Filtrar por tabla específica
        registro_id: Filtrar por ID de registro específico
        usuario_id: Filtrar por usuario específico
        limit: Límite de registros a obtener
    """
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    query = '''
        SELECT a.*, u.nombre as usuario_nombre
        FROM auditoria a
        LEFT JOIN usuarios u ON a.usuario_id = u.id
        WHERE 1=1
    '''
    params = []
    
    if tabla:
        query += ' AND a.tabla_afectada = ?'
        params.append(tabla)
    
    if registro_id:
        query += ' AND a.registro_id = ?'
        params.append(registro_id)
    
    if usuario_id:
        query += ' AND a.usuario_id = ?'
        params.append(usuario_id)
    
    query += ' ORDER BY a.timestamp DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    
    return results

def create_notification(usuario_id, tipo, titulo, mensaje, url_accion=None, metadatos=None):
    """
    Crea una nueva notificación para un usuario
    
    Args:
        usuario_id: ID del usuario destinatario
        tipo: Tipo de notificación (info, warning, error, success)
        titulo: Título de la notificación
        mensaje: Mensaje de la notificación
        url_accion: URL opcional para redirigir al hacer clic
        metadatos: Datos adicionales en formato diccionario
    """
    try:
        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO notificaciones (
                usuario_id, tipo, titulo, mensaje, url_accion, metadatos
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            usuario_id,
            tipo,
            titulo,
            mensaje,
            url_accion,
            json.dumps(metadatos) if metadatos else None
        ))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Error al crear notificación: {e}")

def mark_notification_read(notification_id, usuario_id=None):
    """
    Marca una notificación como leída
    
    Args:
        notification_id: ID de la notificación
        usuario_id: ID del usuario (para verificar permisos)
    """
    try:
        conn = sqlite3.connect('mobikit.db')
        cursor = conn.cursor()
        
        query = 'UPDATE notificaciones SET leida = TRUE WHERE id = ?'
        params = [notification_id]
        
        if usuario_id:
            query += ' AND usuario_id = ?'
            params.append(usuario_id)
        
        cursor.execute(query, params)
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Error al marcar notificación como leída: {e}")

def get_user_notifications(usuario_id, only_unread=False, limit=50):
    """
    Obtiene las notificaciones de un usuario
    
    Args:
        usuario_id: ID del usuario
        only_unread: Si True, solo devuelve notificaciones no leídas
        limit: Límite de notificaciones a obtener
    """
    conn = sqlite3.connect('mobikit.db')
    cursor = conn.cursor()
    
    query = '''
        SELECT * FROM notificaciones
        WHERE usuario_id = ?
    '''
    params = [usuario_id]
    
    if only_unread:
        query += ' AND leida = FALSE'
    
    query += ' ORDER BY created_at DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    
    return results
