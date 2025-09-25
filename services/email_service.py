# Referencia: blueprint:python_sendgrid integration
import os
import sys
import logging
import base64
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content, Attachment
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
    
    def send_email_with_logo(self, to_email: str, from_email: str, subject: str, 
                   html_content: Optional[str] = None, text_content: Optional[str] = None) -> bool:
        """
        Envía un email con el logo de Mobikit embebido usando SendGrid API
        """
        if not self.sendgrid_key:
            logger.error("No se puede enviar email: SENDGRID_API_KEY no configurada")
            return False
            
        if not html_content and not text_content:
            logger.error("Debe proporcionar al menos html_content o text_content")
            return False
        
        try:
            # Usar la implementación oficial de SendGrid
            sg = SendGridAPIClient(self.sendgrid_key)

            message = Mail(
                from_email=Email(from_email),
                to_emails=To(to_email),
                subject=subject
            )

            # Añadir contenido (HTML tiene prioridad)
            if html_content:
                message.content = Content("text/html", html_content)
            elif text_content:
                message.content = Content("text/plain", text_content)

            # Agregar logo como attachment embebido
            try:
                logo_path = "static/images/mobikit-logo-official.png"
                if os.path.exists(logo_path):
                    with open(logo_path, 'rb') as logo_file:
                        logo_data = logo_file.read()
                        logo_base64 = base64.b64encode(logo_data).decode()
                        
                        attachment = Attachment()
                        attachment.file_content = logo_base64
                        attachment.file_type = "image/png"
                        attachment.file_name = "mobikit-logo.png"
                        attachment.disposition = "inline"
                        attachment.content_id = "mobikit_logo"
                        
                        message.attachment = attachment
                else:
                    logger.warning(f"Logo no encontrado en {logo_path}")
            except Exception as logo_error:
                logger.warning(f"Error adjuntando logo: {logo_error}")
                # Continúa enviando sin logo

            # Enviar el email
            response = sg.send(message)
            logger.info(f"Email enviado exitosamente a {to_email}. Status: {response.status_code}")
            return True
            
        except Exception as e:
            logger.error(f"SendGrid error: {e}")
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
        
        # Contenido del email en HTML con colores corporativos Mobikit
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                /* Colores corporativos Mobikit */
                :root {{
                    --mobikit-red: #EF1A1F;
                    --mobikit-red-dark: #C7161A;
                    --mobikit-gray: #626363;
                    --mobikit-white: #FDFDFD;
                    --mobikit-light-bg: #FAFAFA;
                    --mobikit-border: #E5E5E5;
                }}
                
                body {{ 
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                    line-height: 1.6; 
                    color: #626363;
                    background-color: #FAFAFA;
                    margin: 0;
                    padding: 20px;
                }}
                
                .container {{ 
                    max-width: 600px; 
                    margin: 0 auto; 
                    background-color: #FDFDFD;
                    border-radius: 12px;
                    overflow: hidden;
                    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
                }}
                
                .header {{ 
                    background: linear-gradient(135deg, #EF1A1F 0%, #C7161A 100%);
                    color: #FDFDFD; 
                    padding: 30px 20px; 
                    text-align: center;
                    position: relative;
                }}
                
                .logo {{
                    width: 80px;
                    height: 80px;
                    margin: 0 auto 15px;
                    background-color: #FDFDFD;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
                }}
                
                .logo img {{
                    width: 50px;
                    height: 50px;
                    border-radius: 25px;
                }}
                
                .header h1 {{ 
                    margin: 0; 
                    font-size: 28px; 
                    font-weight: 700;
                    text-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
                }}
                
                .header p {{ 
                    margin: 5px 0 0 0; 
                    font-size: 16px; 
                    opacity: 0.95;
                    font-weight: 300;
                }}
                
                .content {{ 
                    padding: 40px 30px; 
                    background-color: #FDFDFD;
                }}
                
                .content h2 {{ 
                    color: #626363; 
                    margin-top: 0; 
                    font-size: 24px;
                    font-weight: 600;
                }}
                
                .welcome-text {{
                    font-size: 16px;
                    color: #626363;
                    margin-bottom: 25px;
                }}
                
                .credentials {{ 
                    background: linear-gradient(135deg, #FAFAFA 0%, #F5F5F5 100%);
                    padding: 25px; 
                    border-left: 5px solid #EF1A1F; 
                    margin: 25px 0; 
                    border-radius: 8px;
                    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
                }}
                
                .credentials h3 {{ 
                    margin-top: 0; 
                    color: #EF1A1F; 
                    font-size: 18px;
                    font-weight: 600;
                }}
                
                .credential-item {{
                    margin: 15px 0;
                    padding: 10px 0;
                    border-bottom: 1px solid #E5E5E5;
                }}
                
                .credential-item:last-child {{
                    border-bottom: none;
                }}
                
                .credential-label {{
                    font-weight: 600;
                    color: #626363;
                    display: inline-block;
                    width: 140px;
                }}
                
                .password {{ 
                    font-family: 'Courier New', 'Monaco', monospace; 
                    font-size: 18px; 
                    font-weight: bold; 
                    color: #EF1A1F;
                    background-color: #FFF5F5;
                    padding: 8px 12px;
                    border-radius: 6px;
                    border: 1px dashed #EF1A1F;
                    display: inline-block;
                    letter-spacing: 1px;
                }}
                
                .important-note {{
                    background-color: #FFF3CD;
                    border: 1px solid #F59E0B;
                    color: #B45309;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                
                .button-container {{
                    text-align: center;
                    margin: 30px 0;
                }}
                
                .cta-button {{
                    display: inline-block;
                    background-color: #FFFFFF !important;
                    color: #EF1A1F !important;
                    text-decoration: none !important;
                    padding: 15px 30px;
                    border-radius: 25px;
                    font-weight: 700;
                    font-size: 16px;
                    box-shadow: 0 4px 15px rgba(239, 26, 31, 0.3);
                    transition: all 0.2s ease;
                    border: 3px solid #EF1A1F !important;
                }}
                
                .cta-button:hover {{
                    transform: translateY(-2px);
                    box-shadow: 0 6px 20px rgba(239, 26, 31, 0.4);
                    color: #C7161A !important;
                    text-decoration: none !important;
                    background-color: #F8F8F8 !important;
                    border-color: #C7161A !important;
                }}
                
                .footer {{ 
                    text-align: center; 
                    padding: 25px; 
                    background-color: #626363;
                    color: #FDFDFD; 
                    font-size: 13px;
                }}
                
                .footer p {{ 
                    margin: 5px 0; 
                    opacity: 0.9;
                }}
                
                .company-info {{
                    margin-top: 15px;
                    padding-top: 15px;
                    border-top: 1px solid rgba(253, 253, 253, 0.2);
                    font-size: 12px;
                    opacity: 0.8;
                }}
                
                @media (max-width: 600px) {{
                    .container {{ margin: 10px; }}
                    .content {{ padding: 25px 20px; }}
                    .header {{ padding: 25px 15px; }}
                    .credentials {{ padding: 20px 15px; }}
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">
                        <img src="cid:mobikit_logo" alt="Mobikit - Muebles" style="max-width: 120px; height: auto;" />
                    </div>
                    <h1>¡Bienvenido a Mobikit!</h1>
                    <p>Sistema de Control de Gestión</p>
                </div>
                
                <div class="content">
                    <h2>Hola {user_name},</h2>
                    
                    <div class="welcome-text">
                        <p>Te damos la bienvenida a <strong>Mobikit App - Control de Gestión</strong>, nuestra plataforma integral para la gestión de manufactura.</p>
                        
                        <p>Tu cuenta ha sido creada exitosamente por el administrador <strong>{admin_name}</strong>.</p>
                    </div>
                    
                    <div class="credentials">
                        <h3>📝 Credenciales de Acceso</h3>
                        <div class="credential-item">
                            <span class="credential-label">📧 Email:</span>
                            <strong>{user_email}</strong>
                        </div>
                        <div class="credential-item">
                            <span class="credential-label">🔑 Contraseña:</span>
                            <span class="password">{temporary_password}</span>
                        </div>
                    </div>
                    
                    <div class="important-note">
                        <strong>⚠️ ¡Importante!</strong> Por tu seguridad, te recomendamos cambiar esta contraseña temporal en tu primer inicio de sesión.
                    </div>
                    
                    <p>Con Mobikit App podrás gestionar proyectos, contratos, órdenes de fabricación y despachos de manera integral.</p>
                    
                    <div class="button-container">
                        <a href="https://mobikitapp.com" class="cta-button" target="_blank">🚀 Acceder a Mobikit App</a>
                    </div>
                    
                    <p>Si tienes alguna pregunta o necesitas ayuda, no dudes en contactar al administrador del sistema.</p>
                    
                    <p><strong>¡Esperamos que disfrutes usando Mobikit App!</strong></p>
                </div>
                
                <div class="footer">
                    <p><strong>Mobikit App - Control de Gestión</strong></p>
                    <p>Sistema integral para manufactura y gestión de proyectos</p>
                    <div class="company-info">
                        <p>Este es un email automático generado por el sistema.</p>
                        <p>Por favor, no respondas a este email.</p>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Contenido alternativo en texto plano con mejores detalles
        text_content = f"""
        ========================================
        ¡BIENVENIDO A MOBIKIT APP!
        Sistema de Control de Gestión
        ========================================
        
        Hola {user_name},
        
        Te damos la bienvenida a Mobikit App - Control de Gestión, nuestra plataforma integral para la gestión de manufactura.
        
        Tu cuenta ha sido creada exitosamente por el administrador {admin_name}.
        
        ========================================
        📝 CREDENCIALES DE ACCESO
        ========================================
        📧 Email: {user_email}
        🔑 Contraseña temporal: {temporary_password}
        
        ⚠️  ¡IMPORTANTE! 
        Por tu seguridad, te recomendamos cambiar esta contraseña temporal en tu primer inicio de sesión.
        
        ========================================
        🚀 FUNCIONALIDADES DISPONIBLES
        ========================================
        Con Mobikit App podrás gestionar:
        • Proyectos y contratos
        • Órdenes de fabricación 
        • Despachos y logística
        • Seguimiento integral de procesos
        
        ========================================
        🌐 ACCESO A LA APLICACIÓN
        ========================================
        Ingresa a Mobikit App desde: https://mobikitapp.com
        
        ========================================
        💬 SOPORTE
        ========================================
        Si tienes alguna pregunta o necesitas ayuda, no dudes en contactar al administrador del sistema.
        
        ¡Esperamos que disfrutes usando Mobikit App!
        
        ========================================
        Mobikit App - Control de Gestión
        Sistema integral para manufactura y gestión de proyectos
        
        Este es un email automático generado por el sistema.
        Por favor, no respondas a este email.
        ========================================
        """
        
        # Email del remitente - debe estar verificado en SendGrid
        from_email = os.environ.get("SENDGRID_FROM_EMAIL")
        if not from_email:
            logger.error("SENDGRID_FROM_EMAIL no está configurado; configure un remitente verificado en SendGrid y exponga SENDGRID_FROM_EMAIL")
            return False
        
        return self.send_email_with_logo(
            to_email=user_email,
            from_email=from_email,
            subject=subject,
            text_content=text_content,
            html_content=html_content
        )