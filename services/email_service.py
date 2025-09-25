# Referencia: blueprint:python_sendgrid integration
import os
import sys
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from typing import Optional

logger = logging.getLogger(__name__)

class EmailService:
    """Servicio para envío de emails usando SendGrid"""
    
    def __init__(self):
        self.sendgrid_key = os.environ.get('SENDGRID_API_KEY')
        if not self.sendgrid_key:
            logger.error('SENDGRID_API_KEY environment variable not set')
            self.sendgrid_key = None
    
    def send_email(
        self,
        to_email: str,
        from_email: str,
        subject: str,
        text_content: Optional[str] = None,
        html_content: Optional[str] = None
    ) -> bool:
        """
        Envía un email usando SendGrid
        
        Args:
            to_email: Email del destinatario
            from_email: Email del remitente
            subject: Asunto del email
            text_content: Contenido en texto plano (opcional)
            html_content: Contenido en HTML (opcional)
        
        Returns:
            bool: True si el email se envió correctamente, False en caso contrario
        """
        if not self.sendgrid_key:
            logger.error('SendGrid API key no está configurada')
            return False
            
        if not (text_content or html_content):
            logger.error('Se debe proporcionar contenido en texto o HTML')
            return False
        
        try:
            sg = SendGridAPIClient(self.sendgrid_key)

            message = Mail(
                from_email=from_email,
                to_emails=to_email,
                subject=subject,
                html_content=html_content,
                plain_text_content=text_content
            )

            response = sg.send(message)
            logger.info(f'Email enviado exitosamente a {to_email}. Status: {response.status_code}')
            return True
            
        except Exception as e:
            logger.error(f"Error enviando email con SendGrid: {e}")
            return False
    
    def send_new_user_notification(
        self,
        user_email: str,
        user_name: str,
        temporary_password: str,
        admin_name: str
    ) -> bool:
        """
        Envía notificación de nueva cuenta creada a un usuario
        
        Args:
            user_email: Email del nuevo usuario
            user_name: Nombre del nuevo usuario  
            temporary_password: Contraseña temporal generada
            admin_name: Nombre del administrador que creó la cuenta
        
        Returns:
            bool: True si se envió correctamente, False en caso contrario
        """
        subject = "Bienvenido a Mobikit App - Control de Gestión"
        
        # Contenido del email en HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background-color: #f9f9f9; }}
                .credentials {{ background-color: #e9ecef; padding: 15px; border-left: 4px solid #007bff; margin: 20px 0; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
                .password {{ font-family: 'Courier New', monospace; font-size: 16px; font-weight: bold; color: #dc3545; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>¡Bienvenido a Mobikit App!</h1>
                    <p>Control de Gestión</p>
                </div>
                
                <div class="content">
                    <h2>Hola {user_name},</h2>
                    
                    <p>Te damos la bienvenida a <strong>Mobikit App - Control de Gestión</strong>.</p>
                    
                    <p>Tu cuenta ha sido creada exitosamente por el administrador <strong>{admin_name}</strong>.</p>
                    
                    <div class="credentials">
                        <h3>Credenciales de Acceso:</h3>
                        <p><strong>Email:</strong> {user_email}</p>
                        <p><strong>Contraseña temporal:</strong> <span class="password">{temporary_password}</span></p>
                    </div>
                    
                    <p><strong>¡Importante!</strong> Por seguridad, te recomendamos cambiar tu contraseña temporal en el primer inicio de sesión.</p>
                    
                    <p>Puedes acceder a la aplicación usando las credenciales proporcionadas arriba.</p>
                    
                    <p>Si tienes alguna pregunta o necesitas ayuda, no dudes en contactar al administrador del sistema.</p>
                    
                    <p>¡Esperamos que disfrutes usando Mobikit App!</p>
                </div>
                
                <div class="footer">
                    <p>Este es un email automático generado por Mobikit App - Control de Gestión.</p>
                    <p>Por favor, no respondas a este email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Contenido alternativo en texto plano
        text_content = f"""
        ¡Bienvenido a Mobikit App - Control de Gestión!
        
        Hola {user_name},
        
        Te damos la bienvenida a Mobikit App - Control de Gestión.
        
        Tu cuenta ha sido creada exitosamente por el administrador {admin_name}.
        
        CREDENCIALES DE ACCESO:
        Email: {user_email}
        Contraseña temporal: {temporary_password}
        
        ¡IMPORTANTE! Por seguridad, te recomendamos cambiar tu contraseña temporal en el primer inicio de sesión.
        
        Puedes acceder a la aplicación usando las credenciales proporcionadas arriba.
        
        Si tienes alguna pregunta o necesitas ayuda, no dudes en contactar al administrador del sistema.
        
        ¡Esperamos que disfrutes usando Mobikit App!
        
        ---
        Este es un email automático generado por Mobikit App - Control de Gestión.
        Por favor, no respondas a este email.
        """
        
        # Email del remitente - usar email que funciona con SendGrid
        from_email = "test@example.com"  # Email de prueba que funciona con SendGrid
        
        return self.send_email(
            to_email=user_email,
            from_email=from_email,
            subject=subject,
            text_content=text_content,
            html_content=html_content
        )