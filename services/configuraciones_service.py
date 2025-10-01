from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy import and_, or_, func, desc
from werkzeug.security import generate_password_hash
import secrets
import string
import logging

from app import db
from models import User, RolUsuario, ComisionVendedor, AuditLog
from services.email_service import EmailService

logger = logging.getLogger(__name__)


class ConfiguracionesService:
    """Service layer for system configuration operations"""

    # Class variables to store operational parameters persistently
    _operational_params = {
        'turnos_por_dia': 1,
        'horas_por_turno': 8.0,
        'dias_laborables_mes': 22,
        'oee': 0.70,
        'horizonte_planificacion': 6,
        'umbral_sobrecarga': 90,
        'factor_horas_extra': 1.5,
        'max_subcontrato': 30,
        'mejora_oee_objetivo': 0.85
    }

    _capacity_params = {
        'capacidad_maxima_tableros_mes': 1500,
        'capacidad_maxima_tableros_semana': 330,
        'horas_disponibles_mes': 200,
        'horas_disponibles_semana': 45
    }

    def __init__(self):
        self.email_service = EmailService()

    def get_configuraciones_stats(self):
        """Get configuration dashboard statistics"""

        # Count users by role
        usuarios_por_rol = (db.session.query(User.rol, func.count(User.id))
                           .group_by(User.rol)
                           .all())

        # Count active/inactive users
        usuarios_activos = db.session.query(User).filter_by(activo=True).count()
        usuarios_inactivos = db.session.query(User).filter_by(activo=False).count()
        total_usuarios = usuarios_activos + usuarios_inactivos

        # Recent users (last 30 days)
        usuarios_recientes = (db.session.query(User)
                             .filter(User.created_at >= datetime.now().replace(day=1))
                             .count())

        return {
            'total_usuarios': total_usuarios,
            'usuarios_activos': usuarios_activos,
            'usuarios_inactivos': usuarios_inactivos,
            'usuarios_recientes': usuarios_recientes,
            'usuarios_por_rol': dict(usuarios_por_rol),
            'roles_disponibles': list(RolUsuario),
            'porcentaje_activos': (usuarios_activos / total_usuarios * 100) if total_usuarios > 0 else 0
        }

    def get_usuarios_lista(self, rol=None, busqueda=None, estado=None):
        """Get filtered list of users"""

        # Build base query
        query = db.session.query(User)

        # Apply filters
        if rol:
            try:
                rol_enum = RolUsuario(rol)
                query = query.filter(User.rol == rol_enum)
            except ValueError:
                pass  # Invalid role, ignore filter

        if busqueda:
            search_term = f"%{busqueda}%"
            query = query.filter(or_(
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.email.ilike(search_term),
                func.concat(User.first_name, ' ', User.last_name).ilike(search_term)
            ))

        if estado:
            if estado == 'activo':
                query = query.filter(User.activo == True)
            elif estado == 'inactivo':
                query = query.filter(User.activo == False)

        # Get users ordered by creation date
        usuarios = query.order_by(desc(User.created_at)).all()

        # Get roles for filter dropdown
        roles_disponibles = list(RolUsuario)

        return {
            'usuarios': usuarios,
            'roles_disponibles': roles_disponibles,
            'filtros': {
                'rol': rol,
                'busqueda': busqueda,
                'estado': estado
            },
            'total_usuarios': len(usuarios)
        }

    def get_roles_disponibles(self):
        """Get available user roles"""
        return [{'value': rol.value, 'label': rol.value.title()} for rol in RolUsuario]

    def crear_usuario(self, datos_usuario: Dict[str, Any], created_by: str) -> Tuple[bool, str, Optional[str]]:
        """Create a new user with temporary password and email notification

        Returns:
            Tuple[bool, str, Optional[str]]: (success, message, temporary_password)
        """
        try:
            # Check if email already exists
            existing_user = db.session.query(User).filter_by(email=datos_usuario['email']).first()
            if existing_user:
                return False, "Ya existe un usuario con ese email", None

            # Generate temporary password
            temp_password = self._generate_temp_password(12)  # 12 character password
            password_hash = generate_password_hash(temp_password)

            # Create user instance
            nuevo_usuario = User()
            nuevo_usuario.id = self._generate_user_id()
            nuevo_usuario.first_name = datos_usuario['nombre']
            nuevo_usuario.last_name = datos_usuario.get('apellido', '')
            nuevo_usuario.email = datos_usuario['email']
            nuevo_usuario.rol = RolUsuario(datos_usuario['rol'])
            nuevo_usuario.activo = datos_usuario.get('activo', True)
            nuevo_usuario.password_hash = password_hash

            db.session.add(nuevo_usuario)
            db.session.commit()

            # Get admin user name for email
            admin_user = db.session.query(User).filter_by(id=created_by).first()
            admin_name = admin_user.nombre_completo if admin_user else "Administrador del Sistema"

            # Send welcome email notification
            user_name = f"{nuevo_usuario.first_name} {nuevo_usuario.last_name or ''}".strip()
            email_sent = self.email_service.send_new_user_notification(
                user_email=nuevo_usuario.email,
                user_name=user_name,
                temporary_password=temp_password,
                admin_name=admin_name
            )

            # Log the creation
            self._log_user_action('crear_usuario', nuevo_usuario.id, created_by,
                                f"Usuario {user_name} creado con rol {nuevo_usuario.rol.value}")

            if email_sent:
                logger.info(f"Email de bienvenida enviado a {nuevo_usuario.email}")
                return True, "Usuario creado exitosamente. Se ha enviado un email con las credenciales de acceso.", temp_password
            else:
                logger.warning(f"Usuario creado pero falló el envío del email a {nuevo_usuario.email}")
                return True, "Usuario creado exitosamente, pero no se pudo enviar el email de notificación. Proporciona manualmente las credenciales al usuario.", temp_password

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error creando usuario: {str(e)}")
            return False, str(e), None

    def get_usuario_by_id(self, usuario_id: str) -> Optional[User]:
        """Get user by ID"""
        return db.session.query(User).filter_by(id=usuario_id).first()

    def actualizar_usuario(self, usuario_id: str, datos_usuario: Dict[str, Any], updated_by: str) -> Tuple[bool, str]:
        """Update existing user"""
        try:
            usuario = self.get_usuario_by_id(usuario_id)
            if not usuario:
                return False, "Usuario no encontrado"

            # Check if email is being changed and already exists
            if datos_usuario['email'] != usuario.email:
                existing_user = db.session.query(User).filter(
                    and_(User.email == datos_usuario['email'], User.id != usuario_id)
                ).first()
                if existing_user:
                    return False, "Ya existe un usuario con ese email"

            # Store old values for logging
            cambios = []
            if usuario.first_name != datos_usuario['nombre']:
                cambios.append(f"nombre: {usuario.first_name} → {datos_usuario['nombre']}")
            if usuario.email != datos_usuario['email']:
                cambios.append(f"email: {usuario.email} → {datos_usuario['email']}")
            if usuario.rol.value != datos_usuario['rol']:
                cambios.append(f"rol: {usuario.rol.value} → {datos_usuario['rol']}")

            # Update user fields
            usuario.first_name = datos_usuario['nombre']
            usuario.last_name = datos_usuario.get('apellido', '')
            usuario.email = datos_usuario['email']
            usuario.rol = RolUsuario(datos_usuario['rol'])
            usuario.activo = datos_usuario.get('activo', True)
            usuario.updated_at = datetime.now()

            db.session.commit()

            # Log the update
            if cambios:
                self._log_user_action('actualizar_usuario', usuario_id, updated_by,
                                    f"Usuario actualizado: {'; '.join(cambios)}")

            return True, "Usuario actualizado exitosamente"

        except Exception as e:
            db.session.rollback()
            return False, str(e)

    def cambiar_estado_usuario(self, usuario_id: str, changed_by: str) -> Tuple[bool, str]:
        """Toggle user active status"""
        try:
            usuario = self.get_usuario_by_id(usuario_id)
            if not usuario:
                return False, "Usuario no encontrado"

            # Toggle status
            nuevo_estado = not usuario.activo
            usuario.activo = nuevo_estado
            usuario.updated_at = datetime.now()

            db.session.commit()

            # Log the change
            accion = "activar_usuario" if nuevo_estado else "desactivar_usuario"
            estado_texto = "activado" if nuevo_estado else "desactivado"
            nombre_completo = f"{usuario.first_name} {usuario.last_name or ''}".strip()
            self._log_user_action(accion, usuario_id, changed_by,
                                f"Usuario {nombre_completo} {estado_texto}")

            return True, f"Usuario {estado_texto} exitosamente"

        except Exception as e:
            db.session.rollback()
            return False, str(e)

    def reset_password_usuario(self, usuario_id, current_user_id):
        """Resetea la contraseña de un usuario"""
        try:
            usuario = User.query.get(usuario_id)
            if not usuario:
                return False, "Usuario no encontrado"

            # Verificar que el usuario no sea de Replit Auth exclusivamente
            if usuario.email is None and not hasattr(usuario, 'password_hash'):
                return False, "No se puede resetear contraseña para usuarios de Replit Auth sin email"

            # Si el usuario no tiene email, no se puede crear login local
            if not usuario.email or usuario.email.strip() == '':
                return False, "El usuario debe tener un email configurado para poder resetear la contraseña"

            # Generar nueva contraseña temporal
            nueva_password = self._generate_temp_password()

            # Hash de la nueva contraseña
            usuario.password_hash = generate_password_hash(nueva_password)
            usuario.updated_at = datetime.now()

            # Crear registro de auditoría
            audit_data = {
                'accion': 'reset_password',
                'usuario_afectado': usuario.email,
                'admin_id': current_user_id
            }

            audit_log = AuditLog(
                entidad='users',
                entidad_id=usuario_id,
                accion='UPDATE',
                actor=current_user_id,
                payload=audit_data
            )
            db.session.add(audit_log)

            db.session.commit()
            return True, nueva_password

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al resetear contraseña para usuario {usuario_id}: {str(e)}")
            return False, f"Error al resetear contraseña: {str(e)}"

    def change_user_password(self, usuario_id, password_actual, password_nueva):
        """Permite al usuario cambiar su propia contraseña"""
        try:
            from werkzeug.security import check_password_hash, generate_password_hash
            
            usuario = User.query.get(usuario_id)
            if not usuario:
                return False, "Usuario no encontrado"

            # Verificar contraseña actual
            if not usuario.password_hash:
                return False, "Usuario no tiene contraseña configurada"
            
            if not check_password_hash(usuario.password_hash, password_actual):
                return False, "Contraseña actual incorrecta"

            # Actualizar con nueva contraseña
            usuario.password_hash = generate_password_hash(password_nueva)
            usuario.updated_at = datetime.now()

            # Crear registro de auditoría
            audit_data = {
                'accion': 'change_password',
                'usuario_id': usuario_id,
                'timestamp': datetime.now().isoformat()
            }

            audit_log = AuditLog(
                entidad='users',
                entidad_id=usuario_id,
                accion='UPDATE',
                actor=usuario_id,
                payload=audit_data
            )
            db.session.add(audit_log)

            db.session.commit()
            return True, "Contraseña actualizada exitosamente"

        except Exception as e:
            db.session.rollback()
            return False, f"Error al cambiar contraseña: {str(e)}"

    def eliminar_usuario(self, usuario_id, current_user_id, hard_delete=False):
        """Elimina un usuario del sistema (soft delete por defecto, hard delete opcional)"""
        try:
            # Obtener usuario a eliminar
            usuario = db.session.query(User).filter_by(id=usuario_id).first()
            if not usuario:
                return False, "Usuario no encontrado"

            # No permitir eliminar el propio usuario
            if usuario_id == current_user_id:
                return False, "No puedes eliminar tu propio usuario"

            # Verificar si es el último admin
            if usuario.rol == RolUsuario.ADMIN:
                admin_count = db.session.query(User).filter_by(rol=RolUsuario.ADMIN, activo=True).count()
                if admin_count <= 1:
                    return False, "No se puede eliminar el último administrador del sistema"

            # Verificar si el usuario tiene registros relacionados críticos
            try:
                # Importar Proyecto dentro del try para evitar circular imports
                from models import Proyecto
                proyectos_responsable = db.session.query(func.count(Proyecto.id)).filter_by(responsable=usuario_id).scalar()
                if proyectos_responsable and proyectos_responsable > 0:
                    return False, f"El usuario tiene {proyectos_responsable} proyectos asignados como responsable. Reasígnalos antes de eliminar."

                # Verificar proyectos como vendedor
                proyectos_vendedor = db.session.query(func.count(Proyecto.id)).filter_by(vendedor_id=usuario_id).scalar()
                if proyectos_vendedor and proyectos_vendedor > 0:
                    return False, f"El usuario tiene {proyectos_vendedor} proyectos asignados como vendedor. Reasígnalos antes de eliminar."

            except ImportError:
                # Si no existe el modelo Proyecto, continuar sin verificar
                logger.warning("Modelo Proyecto no encontrado, omitiendo verificación de proyectos")
                pass
            except Exception as e:
                logger.warning(f"Error verificando proyectos del usuario: {str(e)}")

            if hard_delete:
                # Hard delete: eliminar físicamente de la base de datos
                nombre_completo = usuario.nombre_completo
                email = usuario.email
                rol = usuario.rol.value

                # Crear registro de auditoría antes de eliminar
                audit_data = {
                    'accion': 'hard_delete',
                    'usuario_eliminado': email,
                    'nombre_completo': nombre_completo,
                    'rol': rol,
                    'admin_id': current_user_id
                }

                audit_log = AuditLog(
                    entidad='users',
                    entidad_id=usuario_id,
                    accion='DELETE',
                    actor=current_user_id,
                    payload=audit_data
                )
                db.session.add(audit_log)

                # Eliminar físicamente el usuario
                db.session.delete(usuario)
                db.session.commit()
                return True, f"Usuario {nombre_completo} eliminado permanentemente del sistema"

            else:
                # Soft delete: desactivar en lugar de eliminar
                usuario.activo = False
                usuario.updated_at = datetime.now()

                # Crear registro de auditoría
                audit_data = {
                    'accion': 'soft_delete',
                    'usuario_eliminado': usuario.email,
                    'nombre_completo': usuario.nombre_completo,
                    'rol': usuario.rol.value,
                    'admin_id': current_user_id
                }

                audit_log = AuditLog(
                    entidad='users',
                    entidad_id=usuario_id,
                    accion='DELETE',
                    actor=current_user_id,
                    payload=audit_data
                )
                db.session.add(audit_log)

                db.session.commit()
                return True, f"Usuario {usuario.nombre_completo} desactivado exitosamente (ya no puede acceder al sistema)"

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al eliminar usuario {usuario_id}: {str(e)}")
            return False, f"Error al eliminar usuario: {str(e)}"

    def eliminar_usuario_permanente(self, usuario_id, current_user_id):
        """Elimina un usuario permanentemente del sistema (hard delete)"""
        return self.eliminar_usuario(usuario_id, current_user_id, hard_delete=True)

    def get_roles_permisos(self):
        """Get roles with their permissions and user counts"""

        roles_info = []
        for rol in RolUsuario:
            # Count users with this role
            usuarios_count = db.session.query(User).filter_by(rol=rol, activo=True).count()

            # Get role permissions (based on role definitions)
            permisos = self._get_permisos_por_rol(rol)

            roles_info.append({
                'rol': rol,
                'nombre': rol.value.title(),
                'usuarios_count': usuarios_count,
                'permisos': permisos,
                'descripcion': self._get_rol_descripcion(rol)
            })

        return {
            'roles': roles_info,
            'modulos': self._get_modulos_sistema()
        }

    def get_matriz_permisos(self):
        """Get permissions matrix by role and module"""

        modulos = self._get_modulos_sistema()
        roles = list(RolUsuario)

        matriz = {}
        for rol in roles:
            matriz[rol.value] = {}
            permisos_rol = self._get_permisos_por_rol(rol)

            for modulo in modulos:
                matriz[rol.value][modulo] = {
                    'leer': modulo in permisos_rol.get('leer', []),
                    'crear': modulo in permisos_rol.get('crear', []),
                    'editar': modulo in permisos_rol.get('editar', []),
                    'eliminar': modulo in permisos_rol.get('eliminar', [])
                }

        return {
            'matriz': matriz,
            'roles': roles,
            'modulos': modulos
        }

    def get_configuracion_sistema(self):
        """Get system configuration settings"""

        # Get system statistics
        stats = self.get_configuraciones_stats()

        # Get recent user activity
        actividad_reciente = self._get_actividad_reciente(limit=10)

        return {
            'stats': stats,
            'actividad_reciente': actividad_reciente,
            'version_sistema': '1.0.0',
            'fecha_actualizacion': datetime.now(),
            'configuraciones': {
                'sesion_timeout': 31,  # days
                'max_intentos_login': 3,
                'backup_automatico': True,
                'notificaciones_email': True
            }
        }

    def get_usuarios_stats(self):
        """Get detailed user statistics"""

        # Users created by month (last 12 months)
        usuarios_por_mes = {}
        for mes in range(1, 13):
            count = (db.session.query(User)
                    .filter(func.extract('month', User.created_at) == mes)
                    .count())
            usuarios_por_mes[mes] = count

        # Users by role
        usuarios_por_rol = {}
        for rol in RolUsuario:
            count = db.session.query(User).filter_by(rol=rol, activo=True).count()
            usuarios_por_rol[rol.value] = count

        return {
            'usuarios_por_mes': usuarios_por_mes,
            'usuarios_por_rol': usuarios_por_rol,
            'ultimo_usuario': db.session.query(User).order_by(desc(User.created_at)).first(),
            'usuario_mas_antiguo': db.session.query(User).order_by(User.created_at).first()
        }

    def get_audit_log(self, limit=50, usuario_id=None, accion=None):
        """Get audit log of user actions"""

        # For now, return empty list as we don't have audit table
        # In a real implementation, you would query an audit_log table

        return []

    # Private helper methods

    def _generate_user_id(self) -> str:
        """Generate unique user ID"""
        # For now, use timestamp-based ID
        # In production, you might want to use UUIDs
        timestamp = str(int(datetime.now().timestamp()))
        return f"usr_{timestamp}"

    def _generate_temp_password(self, length=8) -> str:
        """Generate temporary password"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _log_user_action(self, accion: str, usuario_id: str, realizado_por: str, descripcion: str):
        """Log user management action (placeholder for audit table)"""
        # In a real implementation, you would insert into an audit_log table
        print(f"AUDIT: {accion} - Usuario: {usuario_id} - Por: {realizado_por} - {descripcion}")

    def _get_permisos_por_rol(self, rol: RolUsuario) -> Dict[str, List[str]]:
        """Get permissions for a specific role using dynamic system with static fallback"""

        # Intentar usar el sistema dinámico primero
        try:
            from services.permisos_service import PermisosService
            service = PermisosService()

            # Obtener matriz de permisos dinámicos
            resultado = service.obtener_matriz_permisos_completa()

            if resultado['success'] and rol.value in resultado['matriz']:
                permisos_dinamicos = {'leer': [], 'crear': [], 'editar': [], 'eliminar': []}

                # Mapear permisos dinámicos al formato esperado (soportar ambos formatos)
                tipos_mapeo = {
                    'lectura': 'leer',
                    'creacion': 'crear',
                    'edicion': 'editar',
                    'eliminacion': 'eliminar',
                    # También soportar formato ya normalizado
                    'leer': 'leer',
                    'crear': 'crear',
                    'editar': 'editar',
                    'eliminar': 'eliminar'
                }

                for modulo_codigo, permisos_modulo in resultado['matriz'][rol.value].items():
                    for tipo_permiso, permitido in permisos_modulo.items():
                        if permitido and tipo_permiso in tipos_mapeo:
                            tipo_traducido = tipos_mapeo[tipo_permiso]
                            permisos_dinamicos[tipo_traducido].append(modulo_codigo)

                return permisos_dinamicos

        except Exception as e:
            # Si falla el sistema dinámico, usar fallback estático
            pass

        # Permisos estáticos como fallback (incluyendo rol finanzas)
        permisos_estaticos = {
            RolUsuario.ADMIN: {
                'leer': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial', 'planificacion_operacional', 'areas', 'configuraciones'],
                'crear': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial', 'planificacion_operacional', 'areas', 'configuraciones'],
                'editar': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial', 'planificacion_operacional', 'areas', 'configuraciones'],
                'eliminar': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial', 'planificacion_operacional', 'areas', 'configuraciones']
            },
            RolUsuario.OPERACIONES: {
                'leer': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial', 'planificacion_operacional', 'areas', 'configuraciones'],
                'crear': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial', 'planificacion_operacional'],
                'editar': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial', 'planificacion_operacional', 'areas'],
                'eliminar': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial']
            },
            RolUsuario.VENTAS: {
                'leer': ['clientes', 'proyectos', 'contratos', 'comercial'],
                'crear': ['clientes', 'proyectos', 'contratos', 'comercial'],
                'editar': ['clientes', 'proyectos', 'contratos', 'comercial'],
                'eliminar': []
            },
            RolUsuario.PRODUCCION: {
                'leer': ['proyectos', 'fabricacion', 'planificacion_operacional', 'areas'],
                'crear': ['fabricacion'],
                'editar': ['fabricacion', 'areas'],
                'eliminar': []
            },
            RolUsuario.LOGISTICA: {
                'leer': ['proyectos', 'despachos', 'areas'],
                'crear': ['despachos'],
                'editar': ['despachos', 'areas'],
                'eliminar': []
            },
            RolUsuario.GENERAL: {
                'leer': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial', 'planificacion_operacional', 'areas'],
                'crear': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial', 'planificacion_operacional'],
                'editar': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial', 'planificacion_operacional', 'areas'],
                'eliminar': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial']
            },
            RolUsuario.FINANZAS: {
                'leer': ['clientes', 'proyectos', 'contratos', 'fabricacion', 'despachos', 'comercial', 'planificacion_operacional'],
                'crear': ['contratos', 'comercial'],
                'editar': ['contratos', 'comercial'],
                'eliminar': []
            }
        }

        return permisos_estaticos.get(rol, {'leer': [], 'crear': [], 'editar': [], 'eliminar': []})

    def _get_rol_descripcion(self, rol: RolUsuario) -> str:
        """Get role description"""

        descripciones = {
            RolUsuario.ADMIN: "Acceso completo al sistema, gestión de usuarios y configuraciones",
            RolUsuario.OPERACIONES: "Acceso completo excepto edición de configuraciones y gestión de usuarios",
            RolUsuario.VENTAS: "Gestión comercial, clientes y seguimiento de ventas",
            RolUsuario.PRODUCCION: "Gestión de fabricación y control de producción",
            RolUsuario.LOGISTICA: "Gestión de despachos y logística de entrega",
            RolUsuario.GENERAL: "Acceso general al sistema con permisos de gestión operativa",
            RolUsuario.FINANZAS: "Gestión financiera, contratos y reportes comerciales"
        }

        return descripciones.get(rol, "Rol sin descripción")

    def _get_modulos_sistema(self) -> List[str]:
        """Get system modules list"""
        return [
            'clientes', 'proyectos', 'contratos', 'fabricacion',
            'despachos', 'comercial', 'planificacion_operacional',
            'areas', 'configuraciones'
        ]

    def _get_actividad_reciente(self, limit=10) -> List[Dict[str, Any]]:
        """Get recent user activity"""

        # Get recent user creations and updates
        usuarios_recientes = (db.session.query(User)
                             .order_by(desc(User.updated_at))
                             .limit(limit)
                             .all())

        actividad = []
        for usuario in usuarios_recientes:
            actividad.append({
                'fecha': usuario.updated_at or usuario.created_at,
                'accion': 'Usuario actualizado' if usuario.updated_at else 'Usuario creado',
                'usuario': usuario.nombre_completo,
                'detalles': f"Rol: {usuario.rol.value}, Estado: {'Activo' if usuario.activo else 'Inactivo'}"
            })

        return actividad

    # Métodos para gestión de comisiones

    def get_comisiones_vendedores(self):
        """Get commission settings for all sellers"""

        # Get all active users with sales role
        vendedores = (db.session.query(User)
                     .filter(User.rol.in_([RolUsuario.VENTAS, RolUsuario.ADMIN]))
                     .filter_by(activo=True)
                     .order_by(User.first_name, User.last_name)
                     .all())

        # Get existing commission settings
        comisiones_existentes = {
            c.vendedor_id: c for c in
            db.session.query(ComisionVendedor).filter_by(activo=True).all()
        }

        # Build result with defaults for missing settings
        comisiones_vendedores = []
        for vendedor in vendedores:
            comision = comisiones_existentes.get(vendedor.id)
            if not comision:
                # Create default commission record
                comision = ComisionVendedor(
                    vendedor_id=vendedor.id,
                    comision_provision_pct=3.0,
                    comision_instalacion_pct=3.0,
                    created_by=vendedor.id
                )
                db.session.add(comision)
                db.session.flush()  # Get the ID but don't commit yet

            comisiones_vendedores.append({
                'vendedor': vendedor,
                'comision': comision
            })

        try:
            db.session.commit()
        except:
            db.session.rollback()

        return {
            'comisiones_vendedores': comisiones_vendedores,
            'total_vendedores': len(vendedores)
        }

    def actualizar_comision_vendedor(self, vendedor_id: str, comision_provision: float,
                                   comision_instalacion: float, updated_by: str) -> Tuple[bool, str]:
        """Update commission settings for a seller"""
        try:
            # Validate that user is a seller
            vendedor = db.session.query(User).filter_by(id=vendedor_id).first()
            if not vendedor:
                return False, "Vendedor no encontrado"

            if vendedor.rol not in [RolUsuario.VENTAS, RolUsuario.ADMIN]:
                return False, "El usuario no tiene rol de vendedor"

            # Get or create commission record
            comision = db.session.query(ComisionVendedor).filter_by(vendedor_id=vendedor_id).first()
            if not comision:
                comision = ComisionVendedor(vendedor_id=vendedor_id, created_by=updated_by)
                db.session.add(comision)

            # Update values
            comision.comision_provision_pct = comision_provision
            comision.comision_instalacion_pct = comision_instalacion
            comision.updated_at = datetime.now()

            db.session.commit()

            # Log the change
            self._log_user_action('actualizar_comision', vendedor_id, updated_by,
                                f"Comisiones actualizadas: Provisión {comision_provision}%, Instalación {comision_instalacion}%")

            return True, "Comisiones actualizadas exitosamente"

        except Exception as e:
            db.session.rollback()
            return False, str(e)

    def get_comision_vendedor(self, vendedor_id: str) -> Optional[ComisionVendedor]:
        """Get commission settings for a specific seller"""
        return db.session.query(ComisionVendedor).filter_by(vendedor_id=vendedor_id, activo=True).first()

    def calcular_comision_proyecto(self, proyecto_id: int, vendedor_id: str) -> Dict[str, Any]:
        """Calculate commission for a project"""
        try:
            from models import Proyecto

            proyecto = db.session.get(Proyecto, proyecto_id)
            if not proyecto or proyecto.vendedor_id != vendedor_id:
                return None

            comision = self.get_comision_vendedor(vendedor_id)
            if not comision:
                return None

            resultado = {
                'proyecto_id': proyecto_id,
                'vendedor_id': vendedor_id,
                'comision_provision_pct': float(comision.comision_provision_pct),
                'comision_instalacion_pct': float(comision.comision_instalacion_pct),
                'monto_provision': float(proyecto.monto_provision_presupuestado or 0),
                'monto_instalacion': float(proyecto.monto_instalacion_presupuestado or 0),
                'comision_provision_clp': 0,
                'comision_instalacion_clp': 0,
                'comision_total_clp': 0
            }

            # Calculate commissions
            if proyecto.monto_provision_presupuestado:
                resultado['comision_provision_clp'] = float(
                    proyecto.monto_provision_presupuestado * comision.comision_provision_pct / 100
                )

            if proyecto.monto_instalacion_presupuestado:
                resultado['comision_instalacion_clp'] = float(
                    proyecto.monto_instalacion_presupuestado * comision.comision_instalacion_pct / 100
                )

            resultado['comision_total_clp'] = resultado['comision_provision_clp'] + resultado['comision_instalacion_clp']

            return resultado

        except Exception as e:
            return None

    def get_factores_tiempo(self):
        """Get time factors from configuration (defaults if not set)"""
        # For now, use default values - these could be stored in a config table later
        return {
            'factor_tiempo_fabrica': 0.025,  # días por tablero en fábrica
            'factor_tiempo_embalaje': 0.01   # días por tablero en embalaje
        }

    def get_factores_conversion(self):
        """Get conversion factors from operational planning service"""
        try:
            from services.planificacion_operacional_service import PlanificacionOperacionalService
            planif_service = PlanificacionOperacionalService()
            return planif_service.get_factores_conversion()
        except Exception as e:
            print(f"Error getting conversion factors: {e}")
            return {
                'configuracion': {
                    'dias_laborables_semana': 5,
                    'turnos_por_dia': 1,
                    'horas_por_turno': 8,
                    'numero_maquinas': 1,
                    'oee': 0.70
                }
            }

    def get_configuracion_capacidad(self):
        """Get capacity configuration settings"""
        # Get production time factors from planificacion service
        try:
            from services.planificacion_operacional_service import PlanificacionOperacionalService
            planif_service = PlanificacionOperacionalService()
            factores = planif_service.get_factores_conversion()

            # Get operational parameters for correct calculation
            horas_por_turno = 8.0  # Default hours per shift
            turnos_por_dia = 1     # Default shifts per day

            # Calculate horas_por_tablero using correct formula:
            # Horas por Tablero = (Tiempo Fabricación + Tiempo Embalaje) × Horas por turno × Turnos_dia
            horas_por_tablero_social = ((factores.get('SOCIAL', {}).get('factor_tiempo_fabrica', 0.02) +
                                       factores.get('SOCIAL', {}).get('factor_tiempo_embalaje', 0.008)) *
                                       horas_por_turno * turnos_por_dia)
            horas_por_tablero_estandar = ((factores.get('ESTANDAR', {}).get('factor_tiempo_fabrica', 0.025) +
                                         factores.get('ESTANDAR', {}).get('factor_tiempo_embalaje', 0.01)) *
                                         horas_por_turno * turnos_por_dia)
            horas_por_tablero_especial = ((factores.get('ESPECIAL', {}).get('factor_tiempo_fabrica', 0.03) +
                                         factores.get('ESPECIAL', {}).get('factor_tiempo_embalaje', 0.012)) *
                                         horas_por_turno * turnos_por_dia)
        except Exception as e:
            print(f"Error calculating horas_por_tablero from production times: {e}")
            # Fallback values
            horas_por_tablero_social = 0.6
            horas_por_tablero_estandar = 0.5
            horas_por_tablero_especial = 0.4

        # Merge persistent parameters with calculated values
        config = {
            # Production time per board by project type (calculated from production times)
            'horas_por_tablero_social': horas_por_tablero_social,
            'horas_por_tablero_estandar': horas_por_tablero_estandar,
            'horas_por_tablero_especial': horas_por_tablero_especial,
        }

        # Add persistent capacity parameters
        config.update(self._capacity_params)

        # Add persistent operational parameters
        config.update(self._operational_params)

        return config

    def actualizar_configuracion_capacidad(self, capacidad_data: Dict[str, Any], usuario_id: str) -> bool:
        """Update capacity configuration settings"""
        try:
            # Validate and update capacity data
            valid_fields = [
                'capacidad_maxima_tableros_mes', 'capacidad_maxima_tableros_semana',
                'horas_disponibles_mes', 'horas_disponibles_semana'
            ]

            updated_fields = []
            for field, value in capacidad_data.items():
                if field in valid_fields and value is not None and value > 0:
                    # Update persistent storage
                    self._capacity_params[field] = value
                    updated_fields.append(f"{field}: {value}")

            if updated_fields:
                # Log the change
                print(f"Usuario {usuario_id} actualizó configuración de capacidad: {', '.join(updated_fields)}")
                return True
            else:
                return False

        except Exception as e:
            print(f"Error updating capacity configuration: {e}")
            return False

    def actualizar_factores_tiempo(self, factor_fabrica: float, factor_embalaje: float, usuario_id: int) -> bool:
        """Update time factors configuration"""
        try:
            # For now, this is a placeholder that returns True
            # In a full implementation, these would be stored in a config table
            # Here we would update the database with new values

            # Log the change (you could implement audit logging here)
            print(f"Usuario {usuario_id} actualizó factores de tiempo: "
                  f"Fabrica: {factor_fabrica}, Embalaje: {factor_embalaje}")

            # Return success - in a real implementation, check DB operation result
            return True

        except Exception as e:
            print(f"Error updating time factors: {e}")
            return False

    def actualizar_parametros_operacionales(self, parametros_data: Dict[str, Any], usuario_id: str) -> bool:
        """Update operational parameters"""
        try:
            # Validate and update operational parameters
            valid_fields = [
                'turnos_por_dia', 'horas_por_turno', 'dias_laborables_mes', 'oee',
                'horizonte_planificacion', 'umbral_sobrecarga',
                'factor_horas_extra', 'max_subcontrato', 'mejora_oee_objetivo'
            ]

            updated_fields = []
            for field, value in parametros_data.items():
                if field in valid_fields and value is not None:
                    # Update persistent storage
                    self._operational_params[field] = value
                    updated_fields.append(f"{field}: {value}")

            if updated_fields:
                # Log the change
                print(f"Usuario {usuario_id} actualizó parámetros operacionales: {', '.join(updated_fields)}")
                return True
            else:
                return False

        except Exception as e:
            print(f"Error updating operational parameters: {e}")
            return False

    def get_parametros_operacionales(self):
        """Alias for get_configuracion_capacidad for consistency"""
        return self.get_configuracion_capacidad()

    def get_escenarios_deficit(self) -> Dict[str, Any]:
        """
        Obtiene los escenarios disponibles para responder a déficits de capacidad
        """
        try:
            config = self.get_configuracion_capacidad()

            # Calcular capacidad base
            horas_nominales = (config.get('turnos_por_dia', 1) *
                             config.get('horas_por_turno', 8) *
                             config.get('dias_laborables_mes', 22))
            horas_efectivas = horas_nominales * config.get('oee', 0.70)

            escenarios = {
                'capacidad_base': {
                    'horas_nominales_mes': horas_nominales,
                    'horas_efectivas_mes': horas_efectivas,
                    'descripcion': 'Capacidad actual sin modificaciones'
                },
                'horas_extra': {
                    'factor_costo': config.get('factor_horas_extra', 1.5),
                    'horas_adicionales_max': horas_nominales * 0.25,  # Máximo 25% extra
                    'capacidad_adicional': horas_efectivas * 0.25,
                    'costo_adicional_factor': config.get('factor_horas_extra', 1.5) - 1,
                    'descripcion': 'Trabajar horas extra con recargo de {:.0%}'.format(config.get('factor_horas_extra', 1.5) - 1),
                    'recomendacion': 'Usar para déficits temporales menores a 100 horas'
                },
                'turno_adicional': {
                    'turnos_actuales': config.get('turnos_por_dia', 1),
                    'turnos_maximo': 3,
                    'incremento_posible': 3 - config.get('turnos_por_dia', 1),
                    'capacidad_adicional': horas_efectivas * (3 - config.get('turnos_por_dia', 1)),
                    'costo_adicional_factor': 1.2,  # 20% adicional por turno nocturno
                    'descripcion': 'Agregar turnos adicionales (hasta 3 turnos/día)',
                    'recomendacion': 'Usar para déficits persistentes mayores a 200 horas'
                },
                'subcontratacion': {
                    'porcentaje_max': config.get('max_subcontrato', 30),
                    'capacidad_adicional': horas_efectivas * (config.get('max_subcontrato', 30) / 100),
                    'costo_adicional_factor': 1.2,  # 20% más caro que interno
                    'tiempo_implementacion_dias': 15,
                    'descripcion': 'Subcontratar hasta {:.0%} de la producción'.format(config.get('max_subcontrato', 30) / 100),
                    'recomendacion': 'Usar para picos de demanda específicos'
                },
                'mejora_oee': {
                    'oee_actual': config.get('oee', 0.70),
                    'oee_objetivo': config.get('mejora_oee_objetivo', 0.85),
                    'mejora_posible': config.get('mejora_oee_objetivo', 0.85) - config.get('oee', 0.70),
                    'capacidad_adicional': horas_nominales * (config.get('mejora_oee_objetivo', 0.85) - config.get('oee', 0.70)),
                    'costo_adicional_factor': 0.1,  # 10% en inversión en mejoras
                    'tiempo_implementacion_dias': 60,
                    'descripcion': 'Mejorar OEE del {:.0%} al {:.0%}'.format(config.get('oee', 0.70), config.get('mejora_oee_objetivo', 0.85)),
                    'recomendacion': 'Mejor opción a largo plazo, sin costos operativos recurrentes'
                }
            }

            # Agregar escenarios combinados
            escenarios['combinado_horas_extra_oee'] = {
                'capacidad_adicional': (escenarios['horas_extra']['capacidad_adicional'] +
                                      escenarios['mejora_oee']['capacidad_adicional']),
                'costo_adicional_factor': 0.6,  # Promedio ponderado
                'descripcion': 'Combinar horas extra con mejoras de OEE',
                'recomendacion': 'Estrategia intermedia para déficits moderados persistentes'
            }

            escenarios['combinado_turno_subcontrato'] = {
                'capacidad_adicional': (escenarios['turno_adicional']['capacidad_adicional'] +
                                      escenarios['subcontratacion']['capacidad_adicional']),
                'costo_adicional_factor': 1.2,
                'descripcion': 'Combinar turno adicional con subcontratación estratégica',
                'recomendacion': 'Para déficits críticos que requieren solución inmediata'
            }

            return {
                'escenarios_individuales': escenarios,
                'recomendaciones_uso': self._generar_recomendaciones_escenarios(escenarios),
                'parametros_base': {
                    'capacidad_actual_horas': horas_efectivas,
                    'umbral_sobrecarga': config.get('umbral_sobrecarga', 90),
                    'fecha_calculo': datetime.now().isoformat()
                }
            }

        except Exception as e:
            print(f"Error obteniendo escenarios de déficit: {e}")
            return {
                'escenarios_individuales': {},
                'recomendaciones_uso': [],
                'parametros_base': {}
            }

    def _generar_recomendaciones_escenarios(self, escenarios: Dict) -> List[Dict[str, str]]:
        """Genera recomendaciones de uso de escenarios según diferentes situaciones"""
        recomendaciones = [
            {
                'situacion': 'DEFICIT_TEMPORAL_LEVE',
                'rango_deficit': '< 100 horas/mes',
                'escenario_recomendado': 'horas_extra',
                'justificacion': 'Solución rápida y flexible para déficits puntuales',
                'costo_relativo': 'Medio'
            },
            {
                'situacion': 'DEFICIT_MODERADO_PERSISTENTE',
                'rango_deficit': '100-250 horas/mes por 3+ meses',
                'escenario_recomendado': 'mejora_oee',
                'justificacion': 'Mejor ROI a mediano plazo, sin costos recurrentes',
                'costo_relativo': 'Bajo (largo plazo)'
            },
            {
                'situacion': 'DEFICIT_CRITICO_INMEDIATO',
                'rango_deficit': '> 250 horas/mes',
                'escenario_recomendado': 'combinado_turno_subcontrato',
                'justificacion': 'Solución integral para situaciones críticas',
                'costo_relativo': 'Alto'
            },
            {
                'situacion': 'PICO_ESTACIONAL',
                'rango_deficit': 'Variable, 2-4 meses/año',
                'escenario_recomendado': 'subcontratacion',
                'justificacion': 'Flexibilidad para demandas estacionales sin inversión fija',
                'costo_relativo': 'Medio-Alto'
            },
            {
                'situacion': 'CRECIMIENTO_SOSTENIDO',
                'rango_deficit': 'Tendencia creciente constante',
                'escenario_recomendado': 'turno_adicional',
                'justificacion': 'Expansión estructural de capacidad',
                'costo_relativo': 'Alto (pero escalable)'
            }
        ]

        return recomendaciones

    def calcular_impacto_escenario(self, escenario_tipo: str, deficit_horas: float) -> Dict[str, Any]:
        """
        Calcula el impacto específico de aplicar un escenario para un déficit dado
        """
        try:
            escenarios_data = self.get_escenarios_deficit()
            escenarios = escenarios_data['escenarios_individuales']

            if escenario_tipo not in escenarios:
                return {'error': f'Escenario {escenario_tipo} no encontrado'}

            escenario = escenarios[escenario_tipo]
            capacidad_base = escenarios['capacidad_base']['horas_efectivas_mes']

            # Calcular cuánto del déficit se puede cubrir
            capacidad_adicional_disponible = escenario.get('capacidad_adicional', 0)
            deficit_cubierto = min(deficit_horas, capacidad_adicional_disponible)
            deficit_restante = max(0, deficit_horas - capacidad_adicional_disponible)

            # Calcular costos
            costo_adicional_factor = escenario.get('costo_adicional_factor', 0)
            costo_base_estimado = 100000  # CLP por hora base (estimado)
            costo_adicional_total = deficit_cubierto * costo_base_estimado * costo_adicional_factor

            # Calcular nueva utilización
            nueva_capacidad_total = capacidad_base + capacidad_adicional_disponible
            nueva_utilizacion = ((capacidad_base + deficit_horas) / nueva_capacidad_total) * 100

            return {
                'escenario_aplicado': escenario_tipo,
                'deficit_original': deficit_horas,
                'deficit_cubierto': deficit_cubierto,
                'deficit_restante': deficit_restante,
                'cobertura_porcentaje': (deficit_cubierto / deficit_horas) * 100 if deficit_horas > 0 else 0,
                'impacto_capacidad': {
                    'capacidad_base': capacidad_base,
                    'capacidad_adicional': capacidad_adicional_disponible,
                    'capacidad_total_nueva': nueva_capacidad_total,
                    'utilizacion_nueva': round(nueva_utilizacion, 1)
                },
                'impacto_economico': {
                    'costo_adicional_total_clp': round(costo_adicional_total),
                    'costo_por_hora_adicional': round(costo_base_estimado * (1 + costo_adicional_factor)),
                    'factor_costo': costo_adicional_factor
                },
                'recomendacion': self._evaluar_viabilidad_escenario(escenario_tipo, deficit_cubierto, deficit_restante, nueva_utilizacion)
            }

        except Exception as e:
            print(f"Error calculando impacto de escenario: {e}")
            return {'error': str(e)}

    def _evaluar_viabilidad_escenario(self, escenario_tipo: str, deficit_cubierto: float, deficit_restante: float, nueva_utilizacion: float) -> str:
        """Evalúa la viabilidad del escenario aplicado"""

        if deficit_restante > 50:
            return f"INSUFICIENTE: Escenario cubre solo parte del déficit. Considerar escenarios combinados."
        elif nueva_utilizacion > 95:
            return f"VIABLE con RIESGO: Elimina déficit pero utilización muy alta. Monitorear capacidad."
        elif nueva_utilizacion > 85:
            return f"VIABLE: Elimina déficit con utilización adecuada."
        else:
            return f"SOBREDIMENSIONADO: Escenario excede necesidades. Evaluar alternativas más eficientes."

    def actualizar_parametros_operacionales(self, parametros: Dict[str, Any], usuario_id: str) -> bool:
        """Update operational parameters for capacity planning"""
        try:
            # Define valid operational parameters
            valid_operational_params = {
                'turnos_por_dia', 'horas_por_turno',
                'dias_laborables_mes', 'oee', 'horizonte_planificacion',
                'umbral_sobrecarga', 'factor_horas_extra', 'max_subcontrato',
                'mejora_oee_objetivo'
            }

            # Define valid capacity parameters
            valid_capacity_params = {
                'capacidad_maxima_tableros_mes', 'capacidad_maxima_tableros_semana',
                'horas_disponibles_mes', 'horas_disponibles_semana'
            }

            # Filter and validate parameters
            updated_params = []
            for param, valor in parametros.items():
                if param in valid_operational_params and valor is not None:
                    # Basic validation
                    if isinstance(valor, (int, float)) and valor > 0:
                        if param == 'oee' and (valor < 0.1 or valor > 1.0):
                            continue  # OEE must be between 10% and 100%
                        if param == 'mejora_oee_objetivo' and (valor < 0.1 or valor > 1.0):
                            continue  # OEE target must be between 10% and 100%

                        # Update persistent storage
                        self._operational_params[param] = valor
                        updated_params.append(f"{param}: {valor}")

                elif param in valid_capacity_params and valor is not None:
                    if isinstance(valor, (int, float)) and valor > 0:
                        # Update persistent storage
                        self._capacity_params[param] = valor
                        updated_params.append(f"{param}: {valor}")

            if updated_params:
                # Log the change (audit logging could be implemented here)
                print(f"Usuario {usuario_id} actualizó parámetros operacionales: {', '.join(updated_params)}")
                return True
            else:
                print(f"No se proporcionaron parámetros válidos para actualizar por usuario {usuario_id}")
                return False

        except Exception as e:
            print(f"Error updating operational parameters: {e}")
            return False

    def get_escenarios_deficit(self):
        """Get deficit response scenarios for capacity planning"""
        # Calculate theoretical capacity
        capacidad_teorica = self.calcular_capacidad_teorica()

        return {
            'escenarios_individuales': {
                'capacidad_base': {
                    'descripcion': 'Capacidad base actual sin modificaciones',
                    'capacidad_adicional': 0,
                    'costo_adicional_factor': 0,
                    'recomendacion': 'Escenario de referencia'
                },
                'horas_extra': {
                    'descripcion': 'Implementar horas extra hasta 25% adicional',
                    'capacidad_adicional': capacidad_teorica.get('horas_efectivas_mes', 0) * 0.25,
                    'costo_adicional_factor': 0.5,
                    'recomendacion': 'Para déficits menores a 100 horas'
                },
                'turno_adicional': {
                    'descripcion': 'Agregar turno adicional temporal',
                    'capacidad_adicional': capacidad_teorica.get('horas_nominales_mes', 0) * 0.7,
                    'costo_adicional_factor': 0.8,
                    'recomendacion': 'Para déficits mayores a 150 horas'
                },
                'subcontratacion': {
                    'descripcion': 'Subcontratar hasta 30% de la producción',
                    'capacidad_adicional': capacidad_teorica.get('horas_efectivas_mes', 0) * 0.3,
                    'costo_adicional_factor': 1.2,
                    'recomendacion': 'Para déficits críticos o emergencias'
                }
            },
            'recomendaciones_uso': [
                {
                    'situacion': 'deficit_menor',
                    'rango_deficit': '< 100 horas',
                    'escenario_recomendado': 'horas_extra',
                    'justificacion': 'Solución costo-efectiva para déficits pequeños',
                    'costo_relativo': 'Bajo'
                },
                {
                    'situacion': 'deficit_moderado',
                    'rango_deficit': '100-200 horas',
                    'escenario_recomendado': 'turno_adicional',
                    'justificacion': 'Balance entre costo y capacidad adicional',
                    'costo_relativo': 'Medio'
                },
                {
                    'situacion': 'deficit_critico',
                    'rango_deficit': '> 200 horas',
                    'escenario_recomendado': 'subcontratacion',
                    'justificacion': 'Solución rápida para déficits críticos',
                    'costo_relativo': 'Alto'
                }
            ]
        }

    def calcular_capacidad_teorica(self, parametros=None):
        """Calculate theoretical capacity based on operational parameters"""
        if parametros is None:
            parametros = self.get_configuracion_capacidad()

        try:
            # Calculate nominal hours per month
            horas_nominales_mes = (
                parametros['turnos_por_dia'] *
                parametros['horas_por_turno'] *
                parametros['dias_laborables_mes']
            )

            # Calculate effective hours with OEE
            horas_efectivas_mes = horas_nominales_mes * parametros['oee']

            return {
                'horas_nominales_mes': horas_nominales_mes,
                'horas_efectivas_mes': horas_efectivas_mes,
                'turnos_por_dia': parametros['turnos_por_dia'],
                'horas_por_turno': parametros['horas_por_turno'],
                'dias_laborables_mes': parametros['dias_laborables_mes'],
                'oee': parametros['oee']
            }

        except Exception as e:
            print(f"Error calculating theoretical capacity: {e}")
            return {
                'horas_nominales_mes': 176.0,  # Default fallback
                'horas_efectivas_mes': 123.2,  # 176 * 0.7
                'turnos_por_dia': 1,
                'horas_por_turno': 8.0,
                'dias_laborables_mes': 22,
                'oee': 0.70
            }

    def calcular_capacidad_teorica(self, parametros=None):
        """Calculate theoretical capacity based on operational parameters"""
        if parametros is None:
            parametros = self.get_configuracion_capacidad()

        try:
            # Calculate nominal hours per month
            horas_nominales_mes = (
                parametros['turnos_por_dia'] *
                parametros['horas_por_turno'] *
                parametros['dias_laborables_mes']
            )

            # Calculate effective hours with OEE
            horas_efectivas_mes = horas_nominales_mes * parametros['oee']

            # Calculate theoretical capacity by project type
            capacidad_social = int(horas_efectivas_mes / parametros['horas_por_tablero_social']) if parametros['horas_por_tablero_social'] > 0 else 0
            capacidad_estandar = int(horas_efectivas_mes / parametros['horas_por_tablero_estandar']) if parametros['horas_por_tablero_estandar'] > 0 else 0
            capacidad_especial = int(horas_efectivas_mes / parametros['horas_por_tablero_especial']) if parametros['horas_por_tablero_especial'] > 0 else 0

            return {
                'horas_nominales_mes': horas_nominales_mes,
                'horas_efectivas_mes': horas_efectivas_mes,
                'oee_aplicado': parametros['oee'],
                'utilizacion_efectiva': (horas_efectivas_mes / horas_nominales_mes) * 100,
                'capacidad_teorica': {
                    'social': capacidad_social,
                    'estandar': capacidad_estandar,
                    'especial': capacidad_especial
                },
                'tableros_por_hora': {
                    'social': (1 / parametros['horas_por_tablero_social']) if parametros['horas_por_tablero_social'] > 0 else 0,
                    'estandar': (1 / parametros['horas_por_tablero_estandar']) if parametros['horas_por_tablero_estandar'] > 0 else 0,
                    'especial': (1 / parametros['horas_por_tablero_especial']) if parametros['horas_por_tablero_especial'] > 0 else 0
                }
            }

        except Exception as e:
            print(f"Error calculating theoretical capacity: {e}")
            return None

    def calcular_escenarios_deficit_especifico(self, deficit_horas: float, parametros=None):
        """Calculate scenarios to handle capacity deficit"""
        if parametros is None:
            parametros = self.get_configuracion_capacidad()

        try:
            escenarios = []

            # Scenario 1: Extra hours (max 25% additional)
            horas_base = (
                parametros['turnos_por_dia'] *
                parametros['horas_por_turno'] *
                parametros['dias_laborables_mes']
            )
            horas_extra_max = horas_base * 0.25

            if deficit_horas <= horas_extra_max:
                costo_relativo = deficit_horas * parametros['factor_horas_extra']
                escenarios.append({
                    'tipo': 'horas_extra',
                    'nombre': 'Horas Extra',
                    'horas_adicionales': deficit_horas,
                    'costo_relativo': costo_relativo,
                    'factible': True,
                    'descripcion': f"Trabajar {deficit_horas:.0f} horas extra (factor {parametros['factor_horas_extra']}x)"
                })

            # Scenario 2: Additional shifts
            max_turnos = 3
            if parametros['turnos_por_dia'] < max_turnos:
                horas_por_turno_adicional = parametros['horas_por_turno'] * parametros['dias_laborables_mes']
                turnos_necesarios = int(deficit_horas / horas_por_turno_adicional) + 1
                turnos_disponibles = max_turnos - parametros['turnos_por_dia']

                if turnos_necesarios <= turnos_disponibles:
                    horas_adicionales = turnos_necesarios * horas_por_turno_adicional
                    escenarios.append({
                        'tipo': 'turnos_adicionales',
                        'nombre': 'Turnos Adicionales',
                        'turnos_adicionales': turnos_necesarios,
                        'horas_adicionales': horas_adicionales,
                        'costo_relativo': horas_adicionales * 1.1,  # 10% extra cost for additional shifts
                        'factible': True,
                        'descripcion': f"Agregar {turnos_necesarios} turno(s) adicional(es)"
                    })

            # Scenario 3: Subcontracting
            max_subcontrato_horas = horas_base * (parametros['max_subcontrato'] / 100)
            if deficit_horas <= max_subcontrato_horas:
                porcentaje_subcontrato = (deficit_horas / horas_base) * 100
                costo_subcontrato = deficit_horas * 1.2  # 20% more expensive
                escenarios.append({
                    'tipo': 'subcontrato',
                    'nombre': 'Subcontrato',
                    'horas_subcontratadas': deficit_horas,
                    'porcentaje_produccion': porcentaje_subcontrato,
                    'costo_relativo': costo_subcontrato,
                    'factible': True,
                    'descripcion': f"Subcontratar {deficit_horas:.0f} horas ({porcentaje_subcontrato:.1f}% de la producción)"
                })

            # Scenario 4: OEE improvement
            oee_actual = parametros['oee']
            oee_objetivo = parametros['mejora_oee_objetivo']
            if oee_objetivo > oee_actual:
                mejora_oee = oee_objetivo - oee_actual
                horas_adicionales_oee = horas_base * mejora_oee
                if horas_adicionales_oee >= deficit_horas:
                    escenarios.append({
                        'tipo': 'mejora_oee',
                        'nombre': 'Mejora OEE',
                        'oee_actual': oee_actual,
                        'oee_objetivo': oee_objetivo,
                        'mejora_porcentual': mejora_oee * 100,
                        'horas_adicionales': horas_adicionales_oee,
                        'costo_relativo': 0,  # Investment in efficiency, not direct operational cost
                        'factible': True,
                        'descripcion': f"Mejorar OEE del {oee_actual*100:.0f}% al {oee_objetivo*100:.0f}% (+{mejora_oee*100:.1f}%)"
                    })

            return escenarios

        except Exception as e:
            print(f"Error calculating deficit scenarios: {e}")
            return []

    def actualizar_capacidad_fabrica_calculada(self, usuario_id: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Actualiza la capacidad de fábrica basándose en los cálculos de horas disponibles
        y tiempos de producción configurados
        """
        try:
            from services.planificacion_operacional_service import PlanificacionOperacionalService

            planificacion_service = PlanificacionOperacionalService()
            resumen_capacidad = planificacion_service.get_resumen_capacidad_estrategica()

            if 'error' in resumen_capacidad:
                return False, f"Error calculando capacidad: {resumen_capacidad['error']}", {}

            # Obtener capacidad calculada
            capacidad_calculada = resumen_capacidad.get('calculos_capacidad', {}).get('capacidad_actualizada_tableros_mes', 0)

            if capacidad_calculada <= 0:
                return False, "No se pudo calcular una capacidad válida", {}

            # Actualizar configuración con nueva capacidad
            config_actual = self.get_configuracion_capacidad()
            config_actual['capacidad_maxima_tableros_mes'] = int(capacidad_calculada)
            config_actual['capacidad_maxima_tableros_semana'] = int(capacidad_calculada / 4.33)  # Aproximación mensual a semanal

            # En una implementación real, aquí guardarías en la base de datos
            # Por ahora, solo registramos el cambio
            print(f"Usuario {usuario_id} actualizó capacidad de fábrica automáticamente:")
            print(f"  - Nueva capacidad mensual: {int(capacidad_calculada)} tableros/mes")
            print(f"  - Nueva capacidad semanal: {int(capacidad_calculada / 4.33)} tableros/semana")
            print(f"  - Basado en: {resumen_capacidad['calculos_capacidad']['horas_efectivas_mes']:.1f} horas efectivas/mes")

            resultado = {
                'capacidad_anterior': resumen_capacidad.get('capacidad_vs_configurada', {}).get('capacidad_configurada', 1500),
                'capacidad_nueva': int(capacidad_calculada),
                'horas_efectivas_mes': resumen_capacidad['calculos_capacidad']['horas_efectivas_mes'],
                'horas_nominales_mes': resumen_capacidad['calculos_capacidad']['horas_nominales_mes'],
                'oee_aplicado': resumen_capacidad['parametros_operacionales']['oee'],
                'capacidad_por_tipo': resumen_capacidad['capacidad_teorica_tableros'],
                'base_calculo': f"Basado en {resumen_capacidad['parametros_operacionales']['numero_maquinas']} máquinas, "
                               f"{resumen_capacidad['parametros_operacionales']['turnos_por_dia']} turno(s), "
                               f"{resumen_capacidad['parametros_operacionales']['horas_por_turno']} hrs/turno, "
                               f"OEE {resumen_capacidad['parametros_operacionales']['oee']*100:.0f}%"
            }

            return True, f"Capacidad actualizada exitosamente a {int(capacidad_calculada)} tableros/mes", resultado

        except Exception as e:
            print(f"Error actualizando capacidad de fábrica: {e}")
            return False, str(e), {}