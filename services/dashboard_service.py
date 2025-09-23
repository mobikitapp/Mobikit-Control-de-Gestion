from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import logging

from models import RolUsuario, User
from repositories.clientes_repo import ClientesRepository
from repositories.proyectos_repo import ProyectosRepository
from repositories.contratos_repo import ContratosRepository
from repositories.fabricacion_repo import FabricacionRepository
from repositories.despachos_repo import DespachosRepository
from services.areas_service import AreasService
from services.finanzas_service import FinanzasService

logger = logging.getLogger(__name__)

class DashboardService:
    """Servicio para generar dashboards dinámicos según el rol del usuario"""
    
    def __init__(self):
        self.areas_service = AreasService()
        self.finanzas_service = FinanzasService()
    
    def get_dashboard_data(self, user: User) -> Dict[str, Any]:
        """
        Obtiene datos completos del dashboard personalizado según el rol del usuario
        """
        try:
            # Datos base que siempre se incluyen
            base_data = {
                'user': user,
                'current_date': datetime.now(),
                'rol': user.rol.value,
                'nombre_usuario': f"{user.first_name} {user.last_name}".strip() or user.id
            }
            
            # Obtener métricas específicas del rol
            metrics = self._get_role_specific_metrics(user.rol)
            
            # Obtener accesos rápidos específicos del rol
            quick_actions = self._get_role_quick_actions(user.rol)
            
            # Obtener contenido de actividad específico del rol
            activity_content = self._get_role_activity_content(user.rol, user.id)
            
            # Obtener configuración visual del rol
            visual_config = self._get_role_visual_config(user.rol)
            
            return {
                **base_data,
                'metrics': metrics,
                'quick_actions': quick_actions,
                'activity': activity_content,
                'visual': visual_config
            }
            
        except Exception as e:
            logger.error(f"Error generando dashboard data: {str(e)}")
            return self._get_fallback_dashboard(user)
    
    def _get_role_specific_metrics(self, rol: RolUsuario) -> Dict[str, Any]:
        """Obtiene métricas específicas según el rol del usuario"""
        try:
            if rol == RolUsuario.ADMIN:
                return self._get_admin_metrics()
            elif rol == RolUsuario.GENERAL:
                return self._get_general_metrics()
            elif rol == RolUsuario.VENTAS:
                return self._get_ventas_metrics()
            elif rol == RolUsuario.OPERACIONES:
                return self._get_operaciones_metrics()
            elif rol == RolUsuario.PRODUCCION:
                return self._get_produccion_metrics()
            else:
                return self._get_basic_metrics()
        except Exception as e:
            logger.error(f"Error obteniendo métricas para rol {rol}: {str(e)}")
            return self._get_basic_metrics()
    
    def _get_admin_metrics(self) -> Dict[str, Any]:
        """Métricas completas para administradores"""
        return {
            # Métricas generales del sistema
            'total_usuarios': self._count_active_users(),
            'total_clientes': ClientesRepository.count_active(),
            'proyectos_activos': ProyectosRepository.count_by_status(['PENDIENTE_PRESUPUESTO', 'PRESUPUESTADO', 'ADJUDICADO', 'EN_DESARROLLO']),
            'contratos_vigentes': ContratosRepository.count_by_status('VIGENTE'),
            
            # Métricas de producción
            'of_en_produccion': FabricacionRepository.count_by_status(['enviado_a_fabricacion', 'seccionando', 'enchapando', 'mecanizando']),
            'of_pendientes': FabricacionRepository.count_by_status(['planificada']),
            'despachos_pendientes': DespachosRepository.count_by_status(['PROGRAMADO', 'EN_TRANSPORTE']),
            
            # Métricas financieras
            'contratos_por_facturar': self._get_contratos_pendientes_facturacion(),
            'ingresos_mes_actual': self._get_ingresos_mes_actual(),
            
            # Métricas de áreas
            'areas_con_retrasos': self._get_areas_con_retrasos(),
            'eficiencia_general': self._get_eficiencia_general()
        }
    
    def _get_general_metrics(self) -> Dict[str, Any]:
        """Métricas para usuarios generales con acceso amplio"""
        return {
            'total_clientes': ClientesRepository.count_active(),
            'proyectos_activos': ProyectosRepository.count_by_status(['PENDIENTE_PRESUPUESTO', 'PRESUPUESTADO', 'ADJUDICADO', 'EN_DESARROLLO']),
            'contratos_vigentes': ContratosRepository.count_by_status('VIGENTE'),
            'of_en_produccion': FabricacionRepository.count_by_status(['enviado_a_fabricacion', 'seccionando', 'enchapando', 'mecanizando']),
            'despachos_pendientes': DespachosRepository.count_by_status(['PROGRAMADO', 'EN_TRANSPORTE']),
            'contratos_por_facturar': self._get_contratos_pendientes_facturacion(),
            'areas_con_retrasos': self._get_areas_con_retrasos()
        }
    
    def _get_ventas_metrics(self) -> Dict[str, Any]:
        """Métricas enfocadas en ventas y comercial"""
        return {
            'clientes_activos': ClientesRepository.count_active(),
            'proyectos_pendientes_presupuesto': ProyectosRepository.count_by_status(['PENDIENTE_PRESUPUESTO']),
            'proyectos_presupuestados': ProyectosRepository.count_by_status(['PRESUPUESTADO']),
            'proyectos_adjudicados': ProyectosRepository.count_by_status(['ADJUDICADO']),
            'contratos_vigentes': ContratosRepository.count_by_status('VIGENTE'),
            'ingresos_mes_actual': self._get_ingresos_mes_actual(),
            'clientes_nuevos_mes': self._get_clientes_nuevos_mes(),
            'tasa_conversion': self._get_tasa_conversion_proyectos()
        }
    
    def _get_operaciones_metrics(self) -> Dict[str, Any]:
        """Métricas para operaciones y logística"""
        return {
            'of_en_produccion': FabricacionRepository.count_by_status(['enviado_a_fabricacion', 'seccionando', 'enchapando', 'mecanizando']),
            'of_terminadas_pendiente_despacho': FabricacionRepository.count_by_status(['terminada']),
            'despachos_programados': DespachosRepository.count_by_status(['PROGRAMADO']),
            'despachos_en_transito': DespachosRepository.count_by_status(['EN_TRANSPORTE']),
            'despachos_entregados_mes': self._get_despachos_entregados_mes(),
            'areas_con_retrasos': self._get_areas_con_retrasos(),
            'eficiencia_despachos': self._get_eficiencia_despachos(),
            'tiempo_promedio_produccion': self._get_tiempo_promedio_produccion()
        }
    
    def _get_produccion_metrics(self) -> Dict[str, Any]:
        """Métricas específicas para producción"""
        return {
            'of_asignadas_a_mi': 0,  # Placeholder - se actualiza con user_id real
            'of_en_mi_area': 0,  # Placeholder - se actualiza con user_id real
            'of_vencidas': self._get_ofs_vencidas(),
            'of_completadas_hoy': self._get_ofs_completadas_hoy(),
            'tiempo_promedio_mi_area': self._get_tiempo_promedio_area_usuario(None),
            'eficiencia_personal': self._get_eficiencia_personal(None),
            'alertas_calidad': self._get_alertas_calidad(),
            'maquinas_disponibles': self._get_maquinas_disponibles()
        }
    
    def _get_basic_metrics(self) -> Dict[str, Any]:
        """Métricas básicas para roles no especificados"""
        return {
            'proyectos_activos': ProyectosRepository.count_by_status(['EN_DESARROLLO']),
            'of_en_produccion': FabricacionRepository.count_by_status(['enviado_a_fabricacion', 'seccionando', 'enchapando', 'mecanizando']),
            'despachos_pendientes': DespachosRepository.count_by_status(['PROGRAMADO']),
            'tareas_pendientes': 0
        }
    
    def _get_role_quick_actions(self, rol: RolUsuario) -> List[Dict[str, Any]]:
        """Obtiene accesos rápidos específicos según el rol"""
        base_actions = []
        
        if rol == RolUsuario.ADMIN:
            base_actions = [
                {'title': 'Gestión de Usuarios', 'url': '/configuraciones/usuarios', 'icon': 'users', 'color': 'primary'},
                {'title': 'Ver Finanzas', 'url': '/finanzas/dashboard', 'icon': 'dollar-sign', 'color': 'success'},
                {'title': 'Dashboard Áreas', 'url': '/areas/dashboard', 'icon': 'layers', 'color': 'info'},
                {'title': 'Configuraciones', 'url': '/configuraciones', 'icon': 'settings', 'color': 'secondary'},
                {'title': 'Calendario General', 'url': '/calendario', 'icon': 'calendar', 'color': 'warning'},
                {'title': 'Reportes', 'url': '/comercial/reportes', 'icon': 'bar-chart-2', 'color': 'dark'}
            ]
        elif rol == RolUsuario.GENERAL:
            base_actions = [
                {'title': 'Nuevo Proyecto', 'url': '/proyectos/nuevo', 'icon': 'plus-circle', 'color': 'primary'},
                {'title': 'Ver Finanzas', 'url': '/finanzas/dashboard', 'icon': 'dollar-sign', 'color': 'success'},
                {'title': 'Calendario', 'url': '/calendario', 'icon': 'calendar', 'color': 'info'},
                {'title': 'Dashboard Áreas', 'url': '/areas/dashboard', 'icon': 'layers', 'color': 'warning'},
                {'title': 'Planificación', 'url': '/planificacion-operacional', 'icon': 'trending-up', 'color': 'secondary'}
            ]
        elif rol == RolUsuario.VENTAS:
            base_actions = [
                {'title': 'Nuevo Cliente', 'url': '/clientes/nuevo', 'icon': 'user-plus', 'color': 'primary'},
                {'title': 'Nuevo Proyecto', 'url': '/proyectos/nuevo', 'icon': 'folder-plus', 'color': 'success'},
                {'title': 'Mi Dashboard', 'url': '/mi-dashboard', 'icon': 'pie-chart', 'color': 'info'},
                {'title': 'Ver Contratos', 'url': '/contratos', 'icon': 'file-text', 'color': 'warning'},
                {'title': 'Estados de Pago', 'url': '/proyectos/estados-pago', 'icon': 'credit-card', 'color': 'secondary'}
            ]
        elif rol == RolUsuario.OPERACIONES:
            base_actions = [
                {'title': 'Ver Despachos', 'url': '/despachos', 'icon': 'truck', 'color': 'primary'},
                {'title': 'Dashboard Áreas', 'url': '/areas/dashboard', 'icon': 'layers', 'color': 'success'},
                {'title': 'Calendario', 'url': '/calendario', 'icon': 'calendar', 'color': 'info'},
                {'title': 'Planificación', 'url': '/planificacion-operacional', 'icon': 'trending-up', 'color': 'warning'},
                {'title': 'Ver Fabricación', 'url': '/fabricacion', 'icon': 'tool', 'color': 'secondary'}
            ]
        elif rol == RolUsuario.PRODUCCION:
            base_actions = [
                {'title': 'Mis Tareas', 'url': '/fabricacion?assigned_to=me', 'icon': 'check-square', 'color': 'primary'},
                {'title': 'Dashboard Áreas', 'url': '/areas/dashboard', 'icon': 'layers', 'color': 'success'},
                {'title': 'Ver Fabricación', 'url': '/fabricacion', 'icon': 'tool', 'color': 'info'},
                {'title': 'Calendario', 'url': '/calendario', 'icon': 'calendar', 'color': 'warning'}
            ]
        
        return base_actions[:6]  # Máximo 6 acciones rápidas
    
    def _get_role_activity_content(self, rol: RolUsuario, user_id: str) -> Dict[str, Any]:
        """Obtiene contenido de actividad específico del rol"""
        try:
            base_content = {
                'recent_projects': [],
                'pending_tasks': [],
                'notifications': []
            }
            
            if rol in [RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.VENTAS]:
                base_content['recent_projects'] = ProyectosRepository.get_recent(limit=5)
            
            if rol in [RolUsuario.ADMIN, RolUsuario.GENERAL, RolUsuario.OPERACIONES, RolUsuario.PRODUCCION]:
                base_content['pending_tasks'] = FabricacionRepository.get_pending_by_user(user_id, limit=5)
            
            if rol == RolUsuario.VENTAS:
                base_content['recent_clients'] = ClientesRepository.get_recent(limit=5)
                # Usar método existente para obtener proyectos recientes
                base_content['pending_quotes'] = []  # Placeholder por ahora
            
            if rol in [RolUsuario.OPERACIONES, RolUsuario.PRODUCCION]:
                # Usar método existente para obtener despachos pendientes
                base_content['recent_dispatches'] = []  # Placeholder por ahora
            
            return base_content
            
        except Exception as e:
            logger.error(f"Error obteniendo contenido de actividad: {str(e)}")
            return {'recent_projects': [], 'pending_tasks': [], 'notifications': []}
    
    def _get_role_visual_config(self, rol: RolUsuario) -> Dict[str, Any]:
        """Obtiene configuración visual específica del rol"""
        configs = {
            RolUsuario.ADMIN: {
                'primary_color': 'red',
                'accent_color': 'dark',
                'icon_theme': 'admin',
                'dashboard_title': 'Panel de Administración'
            },
            RolUsuario.GENERAL: {
                'primary_color': 'primary',
                'accent_color': 'info',
                'icon_theme': 'general',
                'dashboard_title': 'Dashboard General'
            },
            RolUsuario.VENTAS: {
                'primary_color': 'success',
                'accent_color': 'warning',
                'icon_theme': 'sales',
                'dashboard_title': 'Dashboard de Ventas'
            },
            RolUsuario.OPERACIONES: {
                'primary_color': 'info',
                'accent_color': 'secondary',
                'icon_theme': 'operations',
                'dashboard_title': 'Dashboard de Operaciones'
            },
            RolUsuario.PRODUCCION: {
                'primary_color': 'warning',
                'accent_color': 'success',
                'icon_theme': 'production',
                'dashboard_title': 'Dashboard de Producción'
            }
        }
        
        return configs.get(rol, configs[RolUsuario.GENERAL])
    
    # Métodos auxiliares para cálculos específicos
    def _count_active_users(self) -> int:
        """Cuenta usuarios activos"""
        try:
            from app import db
            return db.session.query(User).filter_by(activo=True).count()
        except Exception as e:
            logger.error(f"Error contando usuarios activos: {str(e)}")
            return 0
    
    def _get_contratos_pendientes_facturacion(self) -> int:
        """Obtiene contratos pendientes de facturación"""
        try:
            # Implementar lógica específica según la estructura de datos
            return 0
        except Exception as e:
            logger.error(f"Error obteniendo contratos pendientes facturación: {str(e)}")
            return 0
    
    def _get_ingresos_mes_actual(self) -> float:
        """Obtiene ingresos del mes actual"""
        try:
            # Implementar lógica con el servicio de finanzas
            return 0.0
        except Exception as e:
            logger.error(f"Error obteniendo ingresos mes actual: {str(e)}")
            return 0.0
    
    def _get_areas_con_retrasos(self) -> int:
        """Obtiene áreas con retrasos"""
        try:
            areas_data = self.areas_service.get_areas_dashboard_data()
            return areas_data.get('stats', {}).get('overdue_count', 0)
        except Exception as e:
            logger.error(f"Error obteniendo áreas con retrasos: {str(e)}")
            return 0
    
    def _get_eficiencia_general(self) -> float:
        """Obtiene eficiencia general del sistema"""
        try:
            # Implementar cálculo de eficiencia general
            return 85.0  # Valor por defecto
        except Exception as e:
            logger.error(f"Error obteniendo eficiencia general: {str(e)}")
            return 0.0
    
    def _get_clientes_nuevos_mes(self) -> int:
        """Obtiene clientes nuevos del mes"""
        try:
            # Usar método existente - implementar lógica básica
            return 0  # Placeholder hasta implementar lógica específica
        except Exception as e:
            logger.error(f"Error obteniendo clientes nuevos mes: {str(e)}")
            return 0
    
    def _get_tasa_conversion_proyectos(self) -> float:
        """Obtiene tasa de conversión de proyectos"""
        try:
            # Implementar cálculo de tasa de conversión
            return 75.0  # Valor por defecto
        except Exception as e:
            logger.error(f"Error obteniendo tasa conversión: {str(e)}")
            return 0.0
    
    def _get_despachos_entregados_mes(self) -> int:
        """Obtiene despachos entregados en el mes"""
        try:
            # Usar método existente - implementar lógica básica
            return 0  # Placeholder hasta implementar lógica específica
        except Exception as e:
            logger.error(f"Error obteniendo despachos entregados mes: {str(e)}")
            return 0
    
    def _get_eficiencia_despachos(self) -> float:
        """Obtiene eficiencia de despachos"""
        try:
            # Implementar cálculo de eficiencia de despachos
            return 90.0  # Valor por defecto
        except Exception as e:
            logger.error(f"Error obteniendo eficiencia despachos: {str(e)}")
            return 0.0
    
    def _get_tiempo_promedio_produccion(self) -> float:
        """Obtiene tiempo promedio de producción"""
        try:
            # Implementar cálculo de tiempo promedio
            return 7.5  # Días por defecto
        except Exception as e:
            logger.error(f"Error obteniendo tiempo promedio producción: {str(e)}")
            return 0.0
    
    # Métodos específicos para producción
    def _get_ofs_en_area_usuario(self, user_id: str) -> int:
        """Obtiene OFs en el área del usuario"""
        try:
            # Implementar lógica específica por área
            return 0
        except Exception as e:
            logger.error(f"Error obteniendo OFs en área usuario: {str(e)}")
            return 0
    
    def _get_ofs_vencidas(self) -> int:
        """Obtiene OFs vencidas"""
        try:
            # Implementar lógica de OFs vencidas
            return 0
        except Exception as e:
            logger.error(f"Error obteniendo OFs vencidas: {str(e)}")
            return 0
    
    def _get_ofs_completadas_hoy(self) -> int:
        """Obtiene OFs completadas hoy"""
        try:
            # Usar método existente - implementar lógica básica
            return 0  # Placeholder hasta implementar lógica específica
        except Exception as e:
            logger.error(f"Error obteniendo OFs completadas hoy: {str(e)}")
            return 0
    
    def _get_tiempo_promedio_area_usuario(self, user_id: str) -> float:
        """Obtiene tiempo promedio del área del usuario"""
        try:
            # Implementar cálculo específico por área
            return 0.0
        except Exception as e:
            logger.error(f"Error obteniendo tiempo promedio área usuario: {str(e)}")
            return 0.0
    
    def _get_eficiencia_personal(self, user_id: str) -> float:
        """Obtiene eficiencia personal del usuario"""
        try:
            # Implementar cálculo de eficiencia personal
            return 85.0  # Valor por defecto
        except Exception as e:
            logger.error(f"Error obteniendo eficiencia personal: {str(e)}")
            return 0.0
    
    def _get_alertas_calidad(self) -> int:
        """Obtiene alertas de calidad"""
        try:
            # Implementar lógica de alertas de calidad
            return 0
        except Exception as e:
            logger.error(f"Error obteniendo alertas calidad: {str(e)}")
            return 0
    
    def _get_maquinas_disponibles(self) -> int:
        """Obtiene máquinas disponibles"""
        try:
            # Implementar lógica de máquinas disponibles
            return 8  # Valor por defecto
        except Exception as e:
            logger.error(f"Error obteniendo máquinas disponibles: {str(e)}")
            return 0
    
    def _get_fallback_dashboard(self, user: User) -> Dict[str, Any]:
        """Dashboard de respaldo en caso de error"""
        return {
            'user': user,
            'current_date': datetime.now(),
            'rol': user.rol.value,
            'nombre_usuario': user.id,
            'metrics': self._get_basic_metrics(),
            'quick_actions': [],
            'activity': {'recent_projects': [], 'pending_tasks': [], 'notifications': []},
            'visual': self._get_role_visual_config(RolUsuario.GENERAL)
        }