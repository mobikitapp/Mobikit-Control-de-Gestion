import json
from datetime import datetime
from flask import request
from flask_login import current_user
from app import db
from models import AuditLog

class AuditService:
    """Service for handling audit logging"""
    
    @staticmethod
    def log_create(table_name: str, record_id, new_data: dict, user_id: str = None):
        """Log create action"""
        AuditService.log_action(table_name, record_id, 'CREATE', datos_nuevos=new_data)

    @staticmethod
    def log_update(table_name: str, record_id, old_data: dict, new_data: dict, user_id: str = None):
        """Log update action"""
        AuditService.log_action(table_name, record_id, 'UPDATE', datos_anteriores=old_data, datos_nuevos=new_data)

    @staticmethod
    def log_delete(table_name: str, record_id, old_data: dict, user_id: str = None):
        """Log delete action"""
        AuditService.log_action(table_name, record_id, 'DELETE', datos_anteriores=old_data)

    @staticmethod
    def log_action(entidad: str, entidad_id, accion: str, 
                  datos_anteriores: dict = None, datos_nuevos: dict = None):
        """
        Log an action in the audit trail
        
        Args:
            entidad: Entity name (table name)
            entidad_id: Entity ID (can be string or integer)
            accion: Action performed (CREATE, UPDATE, DELETE)
            datos_anteriores: Previous data (for UPDATE/DELETE)
            datos_nuevos: New data (for CREATE/UPDATE)
        """
        try:
            # Prepare payload
            payload = {}
            if datos_anteriores:
                payload['antes'] = datos_anteriores
            if datos_nuevos:
                payload['despues'] = datos_nuevos
            
            # Get request information
            ip_address = request.remote_addr if request else None
            user_agent = request.headers.get('User-Agent') if request else None
            
            # Create audit log entry
            audit_entry = AuditLog(
                entidad=entidad,
                entidad_id=entidad_id,
                accion=accion,
                actor=current_user.id if current_user and current_user.is_authenticated else 'system',
                payload=payload,
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            db.session.add(audit_entry)
            db.session.commit()
            
        except Exception as e:
            # Don't let audit failures break the main operation
            db.session.rollback()
            print(f"Audit logging failed: {str(e)}")
    
    @staticmethod
    def get_entity_history(entidad: str, entidad_id, limit: int = 50):
        """
        Get audit history for a specific entity
        
        Args:
            entidad: Entity name
            entidad_id: Entity ID (can be string or integer)
            limit: Maximum number of records to return
            
        Returns:
            List of audit log entries
        """
        return (db.session.query(AuditLog)
                .filter_by(entidad=entidad, entidad_id=str(entidad_id))
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
                .all())
    
    @staticmethod
    def get_recent_activity(limit: int = 100):
        """
        Get recent activity across all entities
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of recent audit log entries
        """
        return (db.session.query(AuditLog)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
                .all())
    
    @staticmethod
    def get_user_activity(user_id: str, limit: int = 50):
        """
        Get activity for a specific user
        
        Args:
            user_id: User ID
            limit: Maximum number of records to return
            
        Returns:
            List of audit log entries for the user
        """
        return (db.session.query(AuditLog)
                .filter_by(actor=user_id)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
                .all())

def serialize_model(model_instance):
    """
    Serialize a SQLAlchemy model instance to a dictionary
    for audit logging purposes
    
    Args:
        model_instance: SQLAlchemy model instance
        
    Returns:
        Dictionary representation of the model
    """
    if not model_instance:
        return None
    
    result = {}
    for column in model_instance.__table__.columns:
        value = getattr(model_instance, column.name)
        
        # Handle different data types
        if isinstance(value, datetime):
            result[column.name] = value.isoformat()
        elif hasattr(value, '__str__'):
            result[column.name] = str(value)
        else:
            result[column.name] = value
    
    return result
