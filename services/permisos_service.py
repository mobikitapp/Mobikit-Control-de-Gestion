from app import db
from models import (
    Modulo, PermisoRol, AuditoriaPermisos, RolUsuario, 
    TipoPermiso, User
)
from sqlalchemy import and_, or_, func
from datetime import datetime


class PermisosService:
    """Servicio para gestión dinámica de permisos por rol"""
    
    def __init__(self):
        self.modulos_sistema = {
            'clientes': {
                'nombre': 'Gestión de Clientes',
                'descripcion': 'Administración de clientes y contactos'
            },
            'proyectos': {
                'nombre': 'Gestión de Proyectos',
                'descripcion': 'Administración de proyectos y seguimiento'
            },
            'contratos': {
                'nombre': 'Contratos y Órdenes de Compra',
                'descripcion': 'Gestión de contratos y órdenes de compra'
            },
            'fabricacion': {
                'nombre': 'Módulo de Fabricación',
                'descripcion': 'Control de órdenes de fabricación y procesos'
            },
            'despachos': {
                'nombre': 'Gestión de Despachos',
                'descripcion': 'Control de entregas y logística'
            },
            'comercial': {
                'nombre': 'Dashboard Comercial',
                'descripcion': 'Análisis comercial y estadísticas'
            },
            'mi_dashboard': {
                'nombre': 'Dashboard Personal del Vendedor',
                'descripcion': 'Panel personal para vendedores'
            },
            'planificacion': {
                'nombre': 'Planificación y Calendario',
                'descripcion': 'Gestión de eventos y planificación'
            },
            'configuraciones': {
                'nombre': 'Configuraciones del Sistema',
                'descripcion': 'Administración del sistema y usuarios'
            },
            'finanzas': {
                'nombre': 'Gestión Financiera',
                'descripcion': 'Control financiero, costos, tesorería y análisis'
            }
        }
    
    def inicializar_modulos_sistema(self, user_id):
        """Inicializa los módulos del sistema con permisos por defecto"""
        try:
            for codigo, info in self.modulos_sistema.items():
                # Verificar si el módulo ya existe
                modulo = Modulo.query.filter_by(codigo=codigo).first()
                
                if not modulo:
                    modulo = Modulo(
                        nombre=info['nombre'],
                        descripcion=info['descripcion'],
                        codigo=codigo,
                        activo=True,
                        created_by=user_id
                    )
                    db.session.add(modulo)
                    db.session.flush()  # Para obtener el ID
                    
                    # Crear permisos por defecto para cada rol
                    self._crear_permisos_defecto(modulo, user_id)
            
            db.session.commit()
            
            # Sincronizar permisos por defecto para todos los módulos (nuevos y existentes)
            self.sincronizar_permisos_defecto(user_id, only_missing=False)
            
            return True, "Módulos inicializados correctamente"
            
        except Exception as e:
            db.session.rollback()
            return False, f"Error al inicializar módulos: {str(e)}"
    
    def _crear_permisos_defecto(self, modulo, user_id):
        """Crea permisos por defecto basados en la configuración actual"""
        permisos_defecto = self._obtener_permisos_defecto_por_modulo(modulo.codigo)
        
        for rol in RolUsuario:
            for tipo_permiso in TipoPermiso:
                permitido = self._evaluar_permiso_defecto(rol.value, modulo.codigo, tipo_permiso.value, permisos_defecto)
                
                permiso_rol = PermisoRol(
                    rol=rol,
                    modulo_id=modulo.id,
                    tipo_permiso=tipo_permiso,
                    permitido=permitido,
                    updated_by=user_id
                )
                db.session.add(permiso_rol)
    
    def _obtener_permisos_defecto_por_modulo(self, codigo_modulo):
        """Obtiene permisos por defecto basados en la configuración actual del sistema"""
        # Basado en utils/permissions.py
        permisos_defecto = {
            'clientes': {
                'admin': ['lectura', 'creacion', 'edicion', 'eliminacion'],
                'general': ['lectura', 'creacion', 'edicion'],
                'ventas': ['lectura'],
                'operaciones': [],
                'produccion': [],
                'logistica': [],
                'finanzas': ['lectura']
            },
            'proyectos': {
                'admin': ['lectura', 'creacion', 'edicion', 'eliminacion'],
                'general': ['lectura', 'creacion', 'edicion'],
                'ventas': ['lectura', 'creacion', 'edicion'],
                'operaciones': ['lectura'],
                'produccion': [],
                'logistica': [],
                'finanzas': ['lectura']
            },
            'contratos': {
                'admin': ['lectura', 'creacion', 'edicion', 'eliminacion'],
                'general': ['lectura', 'creacion', 'edicion'],
                'ventas': ['lectura', 'creacion'],
                'operaciones': ['lectura'],
                'produccion': [],
                'logistica': [],
                'finanzas': ['lectura', 'creacion', 'edicion']
            },
            'fabricacion': {
                'admin': ['lectura', 'creacion', 'edicion', 'eliminacion'],
                'general': ['lectura', 'creacion', 'edicion'],
                'ventas': [],
                'operaciones': ['lectura', 'creacion', 'edicion'],
                'produccion': ['lectura', 'creacion', 'edicion'],
                'logistica': [],
                'finanzas': ['lectura']
            },
            'despachos': {
                'admin': ['lectura', 'creacion', 'edicion', 'eliminacion'],
                'general': ['lectura', 'creacion', 'edicion'],
                'ventas': [],
                'operaciones': ['lectura', 'creacion', 'edicion'],
                'produccion': [],
                'logistica': ['lectura', 'creacion', 'edicion'],
                'finanzas': ['lectura']
            },
            'comercial': {
                'admin': ['lectura', 'creacion', 'edicion', 'eliminacion'],
                'general': ['lectura', 'creacion', 'edicion'],
                'ventas': [],
                'operaciones': [],
                'produccion': [],
                'logistica': [],
                'finanzas': ['lectura', 'creacion', 'edicion']
            },
            'mi_dashboard': {
                'admin': [],
                'general': [],
                'ventas': ['lectura', 'creacion', 'edicion'],
                'operaciones': [],
                'produccion': [],
                'logistica': [],
                'finanzas': []
            },
            'planificacion': {
                'admin': ['lectura', 'creacion', 'edicion', 'eliminacion'],
                'general': ['lectura', 'creacion', 'edicion'],
                'ventas': ['lectura'],
                'operaciones': ['lectura'],
                'produccion': [],
                'logistica': [],
                'finanzas': ['lectura']
            },
            'configuraciones': {
                'admin': ['lectura', 'creacion', 'edicion', 'eliminacion'],
                'general': [],
                'ventas': [],
                'operaciones': [],
                'produccion': [],
                'logistica': [],
                'finanzas': []
            },
            'finanzas': {
                'admin': ['lectura', 'creacion', 'edicion', 'eliminacion'],
                'general': ['lectura'],
                'ventas': ['lectura'],
                'operaciones': ['lectura'],
                'produccion': [],
                'logistica': [],
                'finanzas': ['lectura', 'creacion', 'edicion', 'eliminacion']
            }
        }
        
        return permisos_defecto.get(codigo_modulo, {})
    
    def sincronizar_permisos_defecto(self, user_id, only_missing=True):
        """Sincroniza todos los permisos con los valores por defecto"""
        try:
            modulos = Modulo.query.filter_by(activo=True).all()
            cambios_realizados = 0
            
            for modulo in modulos:
                permisos_defecto = self._obtener_permisos_defecto_por_modulo(modulo.codigo)
                
                for rol in RolUsuario:
                    for tipo_permiso in TipoPermiso:
                        permitido_defecto = self._evaluar_permiso_defecto(
                            rol.value, modulo.codigo, tipo_permiso.value, permisos_defecto
                        )
                        
                        # Buscar permiso existente
                        permiso_existente = PermisoRol.query.filter_by(
                            rol=rol,
                            modulo_id=modulo.id,
                            tipo_permiso=tipo_permiso
                        ).first()
                        
                        if permiso_existente:
                            # Actualizar solo si está mal configurado y no es only_missing
                            if not only_missing and permiso_existente.permitido != permitido_defecto:
                                permiso_existente.permitido = permitido_defecto
                                permiso_existente.updated_by = user_id
                                cambios_realizados += 1
                        else:
                            # Crear permiso faltante
                            nuevo_permiso = PermisoRol(
                                rol=rol,
                                modulo_id=modulo.id,
                                tipo_permiso=tipo_permiso,
                                permitido=permitido_defecto,
                                updated_by=user_id
                            )
                            db.session.add(nuevo_permiso)
                            cambios_realizados += 1
            
            db.session.commit()
            return True, f"Sincronización completa. {cambios_realizados} permisos actualizados"
            
        except Exception as e:
            db.session.rollback()
            return False, f"Error en sincronización: {str(e)}"
    
    def _evaluar_permiso_defecto(self, rol, modulo_codigo, tipo_permiso, permisos_defecto):
        """Evalúa si un rol tiene un permiso específico por defecto"""
        permisos_rol = permisos_defecto.get(rol, [])
        return tipo_permiso in permisos_rol
    
    def obtener_matriz_permisos_completa(self):
        """Obtiene la matriz completa de permisos por rol y módulo"""
        try:
            # Asegurar que los módulos están inicializados
            self._verificar_inicializacion()
            
            # Obtener todos los módulos activos
            modulos = Modulo.query.filter_by(activo=True).order_by(Modulo.nombre).all()
            
            # Obtener todos los permisos
            permisos = db.session.query(PermisoRol)\
                .join(Modulo)\
                .filter(Modulo.activo == True)\
                .all()
            
            # Organizar permisos en una estructura de matriz
            matriz = {}
            for rol in RolUsuario:
                matriz[rol.value] = {}
                for modulo in modulos:
                    matriz[rol.value][modulo.codigo] = {}
                    for tipo_permiso in TipoPermiso:
                        matriz[rol.value][modulo.codigo][tipo_permiso.value] = False
            
            # Llenar la matriz con los permisos actuales
            for permiso in permisos:
                if (permiso.rol.value in matriz and 
                    permiso.modulo.codigo in matriz[permiso.rol.value]):
                    matriz[permiso.rol.value][permiso.modulo.codigo][permiso.tipo_permiso.value] = permiso.permitido
            
            return {
                'success': True,
                'modulos': [{'codigo': m.codigo, 'nombre': m.nombre} for m in modulos],
                'roles': [{'codigo': r.value, 'nombre': self._obtener_nombre_rol(r.value)} for r in RolUsuario],
                'tipos_permiso': [{'codigo': t.value, 'nombre': self._obtener_nombre_permiso(t.value)} for t in TipoPermiso],
                'matriz': matriz
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Error al obtener matriz de permisos: {str(e)}"
            }
    
    def actualizar_permiso(self, rol_codigo, modulo_codigo, tipo_permiso_codigo, permitido, user_id):
        """Actualiza un permiso específico"""
        try:
            # Validar entrada
            rol = None
            for r in RolUsuario:
                if r.value == rol_codigo:
                    rol = r
                    break
            
            if not rol:
                return False, f"Rol no válido: {rol_codigo}"
            
            tipo_permiso = None
            for t in TipoPermiso:
                if t.value == tipo_permiso_codigo:
                    tipo_permiso = t
                    break
            
            if not tipo_permiso:
                return False, f"Tipo de permiso no válido: {tipo_permiso_codigo}"
            
            # Obtener módulo
            modulo = Modulo.query.filter_by(codigo=modulo_codigo, activo=True).first()
            if not modulo:
                return False, f"Módulo no encontrado: {modulo_codigo}"
            
            # Buscar permiso existente
            permiso_rol = PermisoRol.query.filter_by(
                rol=rol,
                modulo_id=modulo.id,
                tipo_permiso=tipo_permiso
            ).first()
            
            valor_anterior = None
            accion = 'created'
            
            if permiso_rol:
                valor_anterior = permiso_rol.permitido
                permiso_rol.permitido = permitido
                permiso_rol.updated_by = user_id
                accion = 'updated'
            else:
                permiso_rol = PermisoRol(
                    rol=rol,
                    modulo_id=modulo.id,
                    tipo_permiso=tipo_permiso,
                    permitido=permitido,
                    updated_by=user_id
                )
                db.session.add(permiso_rol)
            
            # Crear auditoría
            auditoria = AuditoriaPermisos(
                rol=rol,
                modulo_codigo=modulo_codigo,
                tipo_permiso=tipo_permiso,
                valor_anterior=valor_anterior,
                valor_nuevo=permitido,
                accion=accion,
                created_by=user_id
            )
            db.session.add(auditoria)
            
            db.session.commit()
            return True, "Permiso actualizado correctamente"
            
        except Exception as e:
            db.session.rollback()
            return False, f"Error al actualizar permiso: {str(e)}"
    
    def actualizar_permisos_masivo(self, updates, user_id):
        """Actualiza múltiples permisos en una sola transacción"""
        try:
            cambios_exitosos = 0
            errores = []
            
            for update in updates:
                rol_codigo = update.get('rol')
                modulo_codigo = update.get('modulo')
                tipo_permiso_codigo = update.get('tipo_permiso')
                permitido = update.get('permitido', False)
                
                success, mensaje = self.actualizar_permiso(
                    rol_codigo, modulo_codigo, tipo_permiso_codigo, permitido, user_id
                )
                
                if success:
                    cambios_exitosos += 1
                else:
                    errores.append(f"{rol_codigo}/{modulo_codigo}/{tipo_permiso_codigo}: {mensaje}")
            
            if cambios_exitosos > 0:
                return True, {
                    'cambios_exitosos': cambios_exitosos,
                    'errores': errores,
                    'mensaje': f"Se actualizaron {cambios_exitosos} permisos"
                }
            else:
                return False, {
                    'cambios_exitosos': 0,
                    'errores': errores,
                    'mensaje': "No se pudo actualizar ningún permiso"
                }
                
        except Exception as e:
            db.session.rollback()
            return False, f"Error en actualización masiva: {str(e)}"
    
    def verificar_permiso_dinamico(self, user_rol, modulo_codigo, tipo_permiso_codigo):
        """Verifica si un rol tiene un permiso específico usando el sistema dinámico"""
        try:
            # Admin siempre tiene todos los permisos
            if user_rol == 'admin':
                return True
            
            # Buscar el permiso en la base de datos
            rol = None
            for r in RolUsuario:
                if r.value == user_rol:
                    rol = r
                    break
            
            if not rol:
                return False
            
            tipo_permiso = None
            for t in TipoPermiso:
                if t.value == tipo_permiso_codigo:
                    tipo_permiso = t
                    break
            
            if not tipo_permiso:
                return False
            
            # Buscar en la base de datos
            permiso = db.session.query(PermisoRol)\
                .join(Modulo)\
                .filter(
                    PermisoRol.rol == rol,
                    Modulo.codigo == modulo_codigo,
                    PermisoRol.tipo_permiso == tipo_permiso,
                    Modulo.activo == True
                ).first()
            
            # Retornar el valor del permiso si existe, None si no existe (para permitir fallback)
            return permiso.permitido if permiso is not None else None
            
        except Exception as e:
            # En caso de error, usar el sistema de permisos original como fallback
            from utils.permissions import has_permission
            return has_permission(user_rol, f"{modulo_codigo}.{tipo_permiso_codigo}")
    
    def obtener_auditoria_permisos(self, limit=50, rol_filtro=None, modulo_filtro=None):
        """Obtiene el historial de cambios en permisos"""
        try:
            query = db.session.query(AuditoriaPermisos)\
                .join(User, AuditoriaPermisos.created_by == User.id)\
                .order_by(AuditoriaPermisos.created_at.desc())
            
            if rol_filtro:
                query = query.filter(AuditoriaPermisos.rol == RolUsuario(rol_filtro))
            
            if modulo_filtro:
                query = query.filter(AuditoriaPermisos.modulo_codigo == modulo_filtro)
            
            if limit:
                query = query.limit(limit)
            
            auditorias = query.all()
            
            return {
                'success': True,
                'auditorias': [
                    {
                        'id': a.id,
                        'rol': a.rol.value,
                        'modulo': a.modulo_codigo,
                        'tipo_permiso': a.tipo_permiso.value,
                        'valor_anterior': a.valor_anterior,
                        'valor_nuevo': a.valor_nuevo,
                        'accion': a.accion,
                        'fecha': a.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'usuario': f"{a.creator.first_name} {a.creator.last_name}" if a.creator else "Sistema"
                    }
                    for a in auditorias
                ]
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f"Error al obtener auditoría: {str(e)}"
            }
    
    def _verificar_inicializacion(self):
        """Verifica si los módulos están inicializados y los inicializa si es necesario"""
        count_modulos = Modulo.query.count()
        if count_modulos == 0:
            # Inicializar con usuario admin (asumiendo que existe)
            admin_user = User.query.filter_by(rol=RolUsuario.ADMIN).first()
            if admin_user:
                self.inicializar_modulos_sistema(admin_user.id)
    
    def _obtener_nombre_rol(self, codigo_rol):
        """Obtiene el nombre legible de un rol"""
        nombres_roles = {
            'admin': 'Administrador',
            'general': 'Gerente General',
            'ventas': 'Vendedor',
            'operaciones': 'Operaciones',
            'produccion': 'Producción',
            'logistica': 'Logística'
        }
        return nombres_roles.get(codigo_rol, codigo_rol.title())
    
    def _obtener_nombre_permiso(self, codigo_permiso):
        """Obtiene el nombre legible de un tipo de permiso"""
        nombres_permisos = {
            'lectura': 'Lectura',
            'creacion': 'Creación',
            'edicion': 'Edición',
            'eliminacion': 'Eliminación'
        }
        return nombres_permisos.get(codigo_permiso, codigo_permiso.title())
    
    def resetear_permisos_rol(self, rol_codigo, user_id):
        """Resetea todos los permisos de un rol a los valores por defecto"""
        try:
            rol = None
            for r in RolUsuario:
                if r.value == rol_codigo:
                    rol = r
                    break
            
            if not rol:
                return False, f"Rol no válido: {rol_codigo}"
            
            # Eliminar permisos actuales del rol
            permisos_actuales = PermisoRol.query.filter_by(rol=rol).all()
            for permiso in permisos_actuales:
                db.session.delete(permiso)
            
            # Recrear permisos por defecto
            modulos = Modulo.query.filter_by(activo=True).all()
            for modulo in modulos:
                self._crear_permisos_defecto_rol(modulo, rol, user_id)
            
            db.session.commit()
            return True, f"Permisos del rol {rol_codigo} reseteados correctamente"
            
        except Exception as e:
            db.session.rollback()
            return False, f"Error al resetear permisos: {str(e)}"
    
    def _crear_permisos_defecto_rol(self, modulo, rol, user_id):
        """Crea permisos por defecto para un rol específico en un módulo"""
        permisos_defecto = self._obtener_permisos_defecto_por_modulo(modulo.codigo)
        
        for tipo_permiso in TipoPermiso:
            permitido = self._evaluar_permiso_defecto(rol.value, modulo.codigo, tipo_permiso.value, permisos_defecto)
            
            permiso_rol = PermisoRol(
                rol=rol,
                modulo_id=modulo.id,
                tipo_permiso=tipo_permiso,
                permitido=permitido,
                updated_by=user_id
            )
            db.session.add(permiso_rol)