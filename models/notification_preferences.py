from enum import Enum
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from app import db
from datetime import datetime

class TipoNotificacion(Enum):
    NUEVO_PROYECTO = 'nuevo_proyecto'
    COMENTARIO_BITACORA = 'comentario_bitacora'
    CAMBIO_ESTADO_OF = 'cambio_estado_of'
    VENCIMIENTO_CONTRATO = 'vencimiento_contrato'
    RETRASO_PROYECTO = 'retraso_proyecto'

class NotificationPreferences(db.Model):
    """Preferencias de notificación por usuario"""
    __tablename__ = 'notification_preferences'
    
    id = Column(String, primary_key=True, default=lambda: str(db.func.gen_random_uuid()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False)
    
    # Preferencias específicas por tipo de notificación
    nuevo_proyecto_email = Column(Boolean, default=True)
    comentario_bitacora_email = Column(Boolean, default=True) 
    cambio_estado_of_email = Column(Boolean, default=True)
    vencimiento_contrato_email = Column(Boolean, default=True)
    retraso_proyecto_email = Column(Boolean, default=True)
    
    # Configuraciones generales
    email_enabled = Column(Boolean, default=True)
    
    # Audit fields
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    def __repr__(self):
        return f"<NotificationPreferences(user_id={self.user_id})>"