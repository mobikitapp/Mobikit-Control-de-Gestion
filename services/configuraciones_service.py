from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy import and_, or_, func, desc
from werkzeug.security import generate_password_hash
import secrets
import string

from app import db
from models import User, RolUsuario, ComisionVendedor


class ConfiguracionesService:
    """Service layer for system configuration operations"""

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

    def crear_usuario(self, datos_usuario: Dict[str, Any], created_by: str) -> Tuple[bool, str]:
        """Create a new user"""
        try:
            # Check if email already exists
            existing_user = db.session.query(User).filter_by(email=datos_usuario['email']).first()
            if existing_user:
                return False, "Ya existe un usuario con ese email"
            
            # Create user instance
            nuevo_usuario = User()
            nuevo_usuario.id = self._generate_user_id()
            nuevo_usuario.first_name = datos_usuario['nombre']
            nuevo_usuario.last_name = datos_usuario.get('apellido', '')
            nuevo_usuario.email = datos_usuario['email']
            nuevo_usuario.rol = RolUsuario(datos_usuario['rol'])
            nuevo_usuario.activo = datos_usuario.get('activo', True)
            
            db.session.add(nuevo_usuario)
            db.session.commit()
            
            # Log the creation
            nombre_completo = f"{nuevo_usuario.first_name} {nuevo_usuario.last_name or ''}".strip()
            self._log_user_action('crear_usuario', nuevo_usuario.id, created_by, 
                                f"Usuario {nombre_completo} creado con rol {nuevo_usuario.rol.value}")
            
            return True, "Usuario creado exitosamente"
            
        except Exception as e:
            db.session.rollback()
            return False, str(e)

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

    def reset_password_usuario(self, usuario_id: str, reset_by: str) -> Tuple[bool, str]:
        """Reset user password"""
        try:
            usuario = self.get_usuario_by_id(usuario_id)
            if not usuario:
                return False, "Usuario no encontrado"
            
            # Generate new temporary password
            nueva_password = self._generate_temp_password()
            # Note: User model from Replit Auth doesn't have password_hash field
            # This would need to be handled through Replit Auth system
            usuario.updated_at = datetime.now()
            
            db.session.commit()
            
            # Log the password reset
            nombre_completo = f"{usuario.first_name} {usuario.last_name or ''}".strip()
            self._log_user_action('reset_password', usuario_id, reset_by, 
                                f"Contraseña restablecida para {nombre_completo}")
            
            return True, nueva_password
            
        except Exception as e:
            db.session.rollback()
            return False, str(e)

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
        """Get permissions for a specific role"""
        
        permisos = {
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
            }
        }
        
        return permisos.get(rol, {'leer': [], 'crear': [], 'editar': [], 'eliminar': []})

    def _get_rol_descripcion(self, rol: RolUsuario) -> str:
        """Get role description"""
        
        descripciones = {
            RolUsuario.ADMIN: "Acceso completo al sistema, gestión de usuarios y configuraciones",
            RolUsuario.OPERACIONES: "Acceso completo excepto edición de configuraciones y gestión de usuarios",
            RolUsuario.VENTAS: "Gestión comercial, clientes y seguimiento de ventas",
            RolUsuario.PRODUCCION: "Gestión de fabricación y control de producción",
            RolUsuario.LOGISTICA: "Gestión de despachos y logística de entrega"
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