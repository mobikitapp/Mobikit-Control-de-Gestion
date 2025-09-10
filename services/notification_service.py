import os
import logging
from typing import List, Dict, Optional
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from models import User
from app import db

logger = logging.getLogger(__name__)

class NotificationService:
    """
    Servicio centralizado para gestión de notificaciones por email
    """
    
    def __init__(self):
        self.sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
        self.default_sender = os.environ.get('MAIL_DEFAULT_SENDER')
        self.sg = SendGridAPIClient(self.sendgrid_api_key) if self.sendgrid_api_key else None
        
        if not self.sendgrid_api_key:
            logger.warning("SENDGRID_API_KEY no configurada - notificaciones por email deshabilitadas")
        if not self.default_sender:
            logger.warning("MAIL_DEFAULT_SENDER no configurado - usando default")
            self.default_sender = "noreply@sistema.com"
    
    def is_enabled(self) -> bool:
        """Verifica si las notificaciones están habilitadas"""
        return bool(self.sendgrid_api_key and self.default_sender)
    
    def get_admin_emails(self, notification_type: str = None) -> List[str]:
        """Obtiene emails de usuarios administradores activos que han habilitado el tipo de notificación"""
        try:
            from models import RolUsuario, NotificationPreferences
            
            # Query base para admins activos
            query = db.session.query(User).filter(
                User.rol == RolUsuario.ADMIN,
                User.activo == True
            )
            
            # Si se especifica tipo de notificación, filtrar por preferencias
            if notification_type:
                query = query.outerjoin(NotificationPreferences).filter(
                    db.or_(
                        # Usuario sin preferencias (por defecto habilitado)
                        NotificationPreferences.id.is_(None),
                        # Usuario con preferencias y email habilitado globalmente
                        db.and_(
                            NotificationPreferences.email_enabled == True,
                            self._get_preference_filter(notification_type)
                        )
                    )
                )
            
            admins = query.all()
            return [admin.email for admin in admins if admin.email]
        except Exception as e:
            logger.error(f"Error obteniendo emails de admins: {str(e)}")
            return []
    
    def _get_preference_filter(self, notification_type: str):
        """Obtiene el filtro de preferencia según el tipo de notificación"""
        from models import NotificationPreferences
        
        type_mapping = {
            'nuevo_proyecto': NotificationPreferences.nuevo_proyecto_email,
            'comentario_bitacora': NotificationPreferences.comentario_bitacora_email,
            'cambio_estado_of': NotificationPreferences.cambio_estado_of_email,
            'vencimiento_contrato': NotificationPreferences.vencimiento_contrato_email,
            'retraso_proyecto': NotificationPreferences.retraso_proyecto_email
        }
        
        return type_mapping.get(notification_type, True)
    
    def get_project_team_emails(self, proyecto_id: int, notification_type: str = None) -> List[str]:
        """Obtiene emails del equipo asociado al proyecto que han habilitado el tipo de notificación"""
        try:
            from models import Proyecto, RolUsuario, NotificationPreferences
            proyecto = db.session.get(Proyecto, proyecto_id)
            if not proyecto:
                return []
            
            emails = []
            
            # Función auxiliar para verificar preferencias
            def user_accepts_notification(user):
                if not notification_type:
                    return True
                
                # Obtener preferencias del usuario
                prefs = db.session.query(NotificationPreferences).filter_by(user_id=user.id).first()
                
                # Si no tiene preferencias, aceptar por defecto
                if not prefs:
                    return True
                
                # Si tiene email deshabilitado globalmente, rechazar
                if not prefs.email_enabled:
                    return False
                
                # Verificar preferencia específica
                return getattr(prefs, f"{notification_type}_email", True)
            
            # Responsable del proyecto
            if (proyecto.responsable_user and 
                proyecto.responsable_user.email and 
                user_accepts_notification(proyecto.responsable_user)):
                emails.append(proyecto.responsable_user.email)
            
            # Cliente contacto si tiene email (sin verificar preferencias ya que es externo)
            if proyecto.cliente and proyecto.cliente.email:
                emails.append(proyecto.cliente.email)
            
            # Usuarios de operaciones y producción
            team_users = db.session.query(User).filter(
                User.rol.in_([RolUsuario.OPERACIONES, RolUsuario.PRODUCCION]),
                User.activo == True
            ).all()
            
            for user in team_users:
                if (user.email and 
                    user.email not in emails and 
                    user_accepts_notification(user)):
                    emails.append(user.email)
            
            return emails
        except Exception as e:
            logger.error(f"Error obteniendo emails del equipo del proyecto {proyecto_id}: {str(e)}")
            return []
    
    def send_email(self, to_emails: List[str], subject: str, content: str, 
                   html_content: Optional[str] = None) -> bool:
        """
        Envía email usando SendGrid
        
        Args:
            to_emails: Lista de emails destinatarios
            subject: Asunto del email
            content: Contenido en texto plano
            html_content: Contenido HTML opcional
            
        Returns:
            bool: True si se envió correctamente
        """
        if not self.is_enabled():
            logger.warning("Notificaciones deshabilitadas - no se enviará email")
            return False
        
        if not to_emails:
            logger.warning("No hay destinatarios para notificación")
            return False
        
        try:
            # Crear mensaje
            message = Mail(
                from_email=Email(self.default_sender),
                to_emails=[To(email) for email in to_emails],
                subject=subject,
                plain_text_content=Content("text/plain", content)
            )
            
            if html_content:
                message.add_content(Content("text/html", html_content))
            
            # Enviar email
            response = self.sg.send(message)
            
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"Email enviado exitosamente a {len(to_emails)} destinatarios")
                return True
            else:
                logger.error(f"Error enviando email: status {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error enviando notificación por email: {str(e)}")
            return False
    
    def notify_new_project(self, proyecto_id: int, created_by_user: User) -> bool:
        """
        Notifica la creación de un nuevo proyecto
        
        Args:
            proyecto_id: ID del proyecto creado
            created_by_user: Usuario que creó el proyecto
            
        Returns:
            bool: True si se envió la notificación
        """
        try:
            from models import Proyecto
            proyecto = db.session.get(Proyecto, proyecto_id)
            if not proyecto:
                logger.error(f"Proyecto {proyecto_id} no encontrado para notificación")
                return False
            
            # Obtener destinatarios (admins + equipo del proyecto)
            admin_emails = self.get_admin_emails('nuevo_proyecto')
            team_emails = self.get_project_team_emails(proyecto_id, 'nuevo_proyecto')
            
            # Combinar y eliminar duplicados
            all_emails = list(set(admin_emails + team_emails))
            
            # Remover email del creador para evitar autonotificación
            if created_by_user.email in all_emails:
                all_emails.remove(created_by_user.email)
            
            if not all_emails:
                logger.info("No hay destinatarios para notificación de nuevo proyecto")
                return True
            
            # Crear contenido del email
            subject = f"🆕 Nuevo Proyecto Creado: {proyecto.nombre}"
            
            content = f"""
Se ha creado un nuevo proyecto en el sistema:

📋 Proyecto: {proyecto.nombre}
👤 Cliente: {proyecto.cliente.nombre if proyecto.cliente else 'N/A'}
👨‍💼 Responsable: {proyecto.responsable_user.nombre_completo if proyecto.responsable_user else 'N/A'}
📅 Fecha de creación: {proyecto.created_at.strftime('%d/%m/%Y %H:%M') if proyecto.created_at else 'N/A'}
✍️ Creado por: {created_by_user.nombre_completo}

Estado comercial: {proyecto.estado_comercial.value.replace('_', ' ').title() if proyecto.estado_comercial else 'N/A'}
            """.strip()
            
            html_content = f"""
<h3>🆕 Nuevo Proyecto Creado</h3>
<div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px;">
    <p><strong>📋 Proyecto:</strong> {proyecto.nombre}</p>
    <p><strong>👤 Cliente:</strong> {proyecto.cliente.nombre if proyecto.cliente else 'N/A'}</p>
    <p><strong>👨‍💼 Responsable:</strong> {proyecto.responsable_user.nombre_completo if proyecto.responsable_user else 'N/A'}</p>
    <p><strong>📅 Fecha de creación:</strong> {proyecto.created_at.strftime('%d/%m/%Y %H:%M') if proyecto.created_at else 'N/A'}</p>
    <p><strong>✍️ Creado por:</strong> {created_by_user.nombre_completo}</p>
    <p><strong>Estado comercial:</strong> 
        <span style="background-color: #007bff; color: white; padding: 2px 8px; border-radius: 3px;">
            {proyecto.estado_comercial.value.replace('_', ' ').title() if proyecto.estado_comercial else 'N/A'}
        </span>
    </p>
</div>
<p><small>Esta notificación se envió automáticamente desde el Sistema de Gestión de Manufactura.</small></p>
            """.strip()
            
            return self.send_email(all_emails, subject, content, html_content)
            
        except Exception as e:
            logger.error(f"Error enviando notificación de nuevo proyecto {proyecto_id}: {str(e)}")
            return False
    
    def notify_bitacora_comment(self, proyecto_id: int, comentario_id: int, 
                               created_by_user: User) -> bool:
        """
        Notifica nuevo comentario en bitácora del proyecto
        
        Args:
            proyecto_id: ID del proyecto
            comentario_id: ID del comentario
            created_by_user: Usuario que agregó el comentario
            
        Returns:
            bool: True si se envió la notificación
        """
        try:
            from models import BitacoraProyecto, Proyecto
            
            comentario = db.session.get(BitacoraProyecto, comentario_id)
            proyecto = db.session.get(Proyecto, proyecto_id)
            
            if not comentario or not proyecto:
                logger.error(f"Comentario {comentario_id} o proyecto {proyecto_id} no encontrado")
                return False
            
            # Obtener destinatarios del equipo del proyecto
            team_emails = self.get_project_team_emails(proyecto_id, 'comentario_bitacora')
            
            # Remover email del creador para evitar autonotificación
            if created_by_user.email in team_emails:
                team_emails.remove(created_by_user.email)
            
            if not team_emails:
                logger.info("No hay destinatarios para notificación de comentario en bitácora")
                return True
            
            # Crear contenido del email
            tipo_emoji = {
                'especificacion': '📋',
                'cambio': '🔄',
                'nota': '📝',
                'general': '💬'
            }.get(comentario.tipo.value, '💬')
            
            subject = f"{tipo_emoji} Nuevo comentario en bitácora - {proyecto.nombre}"
            
            content = f"""
Se ha agregado un nuevo comentario en la bitácora del proyecto:

📋 Proyecto: {proyecto.nombre}
{tipo_emoji} Tipo: {comentario.tipo.value.title()}
👤 Autor: {created_by_user.nombre_completo}
📅 Fecha: {comentario.fecha_comentario.strftime('%d/%m/%Y %H:%M')}

💬 Comentario:
{comentario.comentario}
            """.strip()
            
            html_content = f"""
<h3>{tipo_emoji} Nuevo comentario en bitácora</h3>
<div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px;">
    <p><strong>📋 Proyecto:</strong> {proyecto.nombre}</p>
    <p><strong>{tipo_emoji} Tipo:</strong> 
        <span style="background-color: #17a2b8; color: white; padding: 2px 8px; border-radius: 3px;">
            {comentario.tipo.value.title()}
        </span>
    </p>
    <p><strong>👤 Autor:</strong> {created_by_user.nombre_completo}</p>
    <p><strong>📅 Fecha:</strong> {comentario.fecha_comentario.strftime('%d/%m/%Y %H:%M')}</p>
</div>
<div style="background-color: #e9ecef; padding: 15px; border-radius: 5px; margin-top: 10px;">
    <h4>💬 Comentario:</h4>
    <p>{comentario.comentario}</p>
</div>
<p><small>Esta notificación se envió automáticamente desde el Sistema de Gestión de Manufactura.</small></p>
            """.strip()
            
            return self.send_email(team_emails, subject, content, html_content)
            
        except Exception as e:
            logger.error(f"Error enviando notificación de comentario bitácora: {str(e)}")
            return False
    
    def notify_of_status_change(self, orden_fabricacion_id: int, nuevo_estado_nombre: str,
                               area_nombre: str, changed_by_user: User) -> bool:
        """
        Notifica cambio de estado en orden de fabricación
        
        Args:
            orden_fabricacion_id: ID de la orden de fabricación
            nuevo_estado_nombre: Nombre del nuevo estado
            area_nombre: Nombre del área
            changed_by_user: Usuario que realizó el cambio
            
        Returns:
            bool: True si se envió la notificación
        """
        try:
            from models import OrdenFabricacion
            
            orden = db.session.get(OrdenFabricacion, orden_fabricacion_id)
            if not orden:
                logger.error(f"Orden de fabricación {orden_fabricacion_id} no encontrada")
                return False
            
            # Obtener destinatarios del equipo del proyecto
            team_emails = self.get_project_team_emails(orden.proyecto_id, 'cambio_estado_of')
            
            # Agregar admins para cambios críticos
            admin_emails = self.get_admin_emails('cambio_estado_of')
            all_emails = list(set(team_emails + admin_emails))
            
            # Remover email del usuario que hizo el cambio
            if changed_by_user.email in all_emails:
                all_emails.remove(changed_by_user.email)
            
            if not all_emails:
                logger.info("No hay destinatarios para notificación de cambio de estado")
                return True
            
            # Crear contenido del email
            subject = f"🔄 Cambio de Estado OF - {orden.codigo}"
            
            content = f"""
Se ha actualizado el estado de una orden de fabricación:

🏭 Orden: {orden.codigo}
📋 Proyecto: {orden.proyecto.nombre if orden.proyecto else 'N/A'}
🏢 Área: {area_nombre}
🔄 Nuevo Estado: {nuevo_estado_nombre}
👤 Actualizado por: {changed_by_user.nombre_completo}
📅 Fecha: {orden.updated_at.strftime('%d/%m/%Y %H:%M') if orden.updated_at else 'N/A'}
            """.strip()
            
            html_content = f"""
<h3>🔄 Cambio de Estado - Orden de Fabricación</h3>
<div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px;">
    <p><strong>🏭 Orden:</strong> {orden.codigo}</p>
    <p><strong>📋 Proyecto:</strong> {orden.proyecto.nombre if orden.proyecto else 'N/A'}</p>
    <p><strong>🏢 Área:</strong> {area_nombre}</p>
    <p><strong>🔄 Nuevo Estado:</strong> 
        <span style="background-color: #28a745; color: white; padding: 2px 8px; border-radius: 3px;">
            {nuevo_estado_nombre}
        </span>
    </p>
    <p><strong>👤 Actualizado por:</strong> {changed_by_user.nombre_completo}</p>
    <p><strong>📅 Fecha:</strong> {orden.updated_at.strftime('%d/%m/%Y %H:%M') if orden.updated_at else 'N/A'}</p>
</div>
<p><small>Esta notificación se envió automáticamente desde el Sistema de Gestión de Manufactura.</small></p>
            """.strip()
            
            return self.send_email(all_emails, subject, content, html_content)
            
        except Exception as e:
            logger.error(f"Error enviando notificación de cambio de estado OF: {str(e)}")
            return False

# Instancia global del servicio
notification_service = NotificationService()