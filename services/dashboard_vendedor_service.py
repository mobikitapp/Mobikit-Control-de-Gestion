"""
Servicio para el Dashboard Personal del Vendedor
Maneja todas las consultas de datos específicas del vendedor logueado
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy import func, and_, or_, desc, extract
from sqlalchemy.orm import joinedload

from app import db
from models import (
    User, Cliente, Proyecto, Contrato, OrdenFabricacion, Despacho,
    EstadoComercial, EstadoContrato, EstadoOF, EstadoDespacho, RolUsuario
)


class DashboardVendedorService:
    """Servicio para datos del dashboard personal del vendedor"""

    def get_metricas_vendedor(self, vendedor_id: int) -> Dict[str, Any]:
        """Obtiene métricas principales del vendedor"""
        try:
            # Fecha actual y rangos
            hoy = datetime.now()
            inicio_mes = hoy.replace(day=1)
            inicio_mes_anterior = (inicio_mes - timedelta(days=1)).replace(day=1)
            
            # Proyectos del vendedor este mes
            proyectos_mes = db.session.query(Proyecto).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Proyecto.fecha_creacion >= inicio_mes
            ).count()
            
            # Proyectos mes anterior
            proyectos_mes_anterior = db.session.query(Proyecto).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Proyecto.fecha_creacion >= inicio_mes_anterior,
                Proyecto.fecha_creacion < inicio_mes
            ).count()
            
            # Contratos confirmados este mes
            contratos_mes = db.session.query(Contrato).join(Proyecto).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Contrato.estado == EstadoContrato.VIGENTE,
                Contrato.fecha_creacion >= inicio_mes
            ).count()
            
            # Valor total de contratos del mes
            valor_total = db.session.query(func.sum(Contrato.valor_total)).join(Proyecto).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Contrato.estado == EstadoContrato.VIGENTE,
                Contrato.fecha_creacion >= inicio_mes
            ).scalar() or 0
            
            # Clientes activos (con proyectos en curso)
            clientes_activos = db.session.query(Cliente).join(Proyecto).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Proyecto.estado_comercial.in_([EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO])
            ).distinct().count()
            
            # Proyectos por estado
            proyectos_estados = db.session.query(
                Proyecto.estado_comercial, func.count(Proyecto.id)
            ).filter(
                Proyecto.responsable_comercial_id == vendedor_id
            ).group_by(Proyecto.estado_comercial).all()
            
            estados_dict = {estado.value: 0 for estado in EstadoComercial}
            for estado, cantidad in proyectos_estados:
                estados_dict[estado.value] = cantidad
            
            # Calcular crecimiento
            crecimiento_proyectos = 0
            if proyectos_mes_anterior > 0:
                crecimiento_proyectos = ((proyectos_mes - proyectos_mes_anterior) / proyectos_mes_anterior) * 100
            
            return {
                'proyectos_mes': proyectos_mes,
                'contratos_mes': contratos_mes,
                'valor_total_mes': valor_total,
                'clientes_activos': clientes_activos,
                'crecimiento_proyectos': round(crecimiento_proyectos, 1),
                'proyectos_por_estado': estados_dict
            }
            
        except Exception as e:
            print(f"Error obteniendo métricas vendedor: {e}")
            return {}

    def get_proyectos_activos(self, vendedor_id: int, limit: int = 5) -> List[Dict]:
        """Obtiene proyectos activos del vendedor"""
        try:
            proyectos = db.session.query(Proyecto).options(
                joinedload(Proyecto.cliente)
            ).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Proyecto.estado_comercial.in_([
                    EstadoComercial.PRESUPUESTADO,
                    EstadoComercial.ADJUDICADO,
                    EstadoComercial.EN_DESARROLLO
                ])
            ).order_by(desc(Proyecto.fecha_actualizacion)).limit(limit).all()
            
            return [
                {
                    'id': proyecto.id,
                    'nombre': proyecto.nombre,
                    'cliente': proyecto.cliente.nombre if proyecto.cliente else 'Sin cliente',
                    'estado': proyecto.estado_comercial.value,
                    'fecha_inicio': proyecto.fecha_inicio,
                    'fecha_entrega_estimada': proyecto.fecha_entrega_estimada,
                    'progreso': self._calcular_progreso_proyecto(proyecto)
                }
                for proyecto in proyectos
            ]
            
        except Exception as e:
            print(f"Error obteniendo proyectos activos: {e}")
            return []

    def get_clientes_recientes(self, vendedor_id: int, limit: int = 5) -> List[Dict]:
        """Obtiene clientes recientes del vendedor"""
        try:
            # Clientes con proyectos del vendedor (últimos contactos)
            clientes = db.session.query(Cliente).join(Proyecto).filter(
                Proyecto.responsable_comercial_id == vendedor_id
            ).order_by(desc(Proyecto.fecha_actualizacion)).limit(limit).all()
            
            resultado = []
            for cliente in clientes:
                # Último proyecto del cliente con este vendedor
                ultimo_proyecto = db.session.query(Proyecto).filter(
                    Proyecto.cliente_id == cliente.id,
                    Proyecto.responsable_comercial_id == vendedor_id
                ).order_by(desc(Proyecto.fecha_actualizacion)).first()
                
                resultado.append({
                    'id': cliente.id,
                    'nombre': cliente.nombre,
                    'email': cliente.email_contacto,
                    'telefono': cliente.telefono_contacto,
                    'ultimo_contacto': ultimo_proyecto.fecha_actualizacion if ultimo_proyecto else None,
                    'estado_ultimo_proyecto': ultimo_proyecto.estado_comercial.value if ultimo_proyecto else None
                })
            
            return resultado
            
        except Exception as e:
            print(f"Error obteniendo clientes recientes: {e}")
            return []

    def get_tareas_pendientes(self, vendedor_id: int) -> List[Dict]:
        """Obtiene tareas pendientes del vendedor"""
        try:
            tareas = []
            
            # Proyectos que necesitan seguimiento (sin actualizar hace más de 7 días)
            hace_semana = datetime.now() - timedelta(days=7)
            proyectos_sin_seguimiento = db.session.query(Proyecto).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Proyecto.estado_comercial.in_([EstadoComercial.PRESUPUESTADO, EstadoComercial.EN_DESARROLLO]),
                Proyecto.fecha_actualizacion < hace_semana
            ).all()
            
            for proyecto in proyectos_sin_seguimiento:
                tareas.append({
                    'tipo': 'seguimiento',
                    'descripcion': f'Dar seguimiento al proyecto "{proyecto.nombre}"',
                    'proyecto_id': proyecto.id,
                    'prioridad': 'media',
                    'dias_pendientes': (datetime.now() - proyecto.fecha_actualizacion).days
                })
            
            # Contratos pendientes de confirmación
            contratos_pendientes = db.session.query(Contrato).join(Proyecto).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Contrato.estado == EstadoContrato.BORRADOR
            ).all()
            
            for contrato in contratos_pendientes:
                tareas.append({
                    'tipo': 'contrato',
                    'descripcion': f'Confirmar contrato del proyecto "{contrato.proyecto.nombre}"',
                    'proyecto_id': contrato.proyecto.id,
                    'contrato_id': contrato.id,
                    'prioridad': 'alta'
                })
            
            # Ordenar por prioridad
            orden_prioridad = {'alta': 1, 'media': 2, 'baja': 3}
            tareas.sort(key=lambda x: orden_prioridad.get(x['prioridad'], 3))
            
            return tareas[:10]  # Máximo 10 tareas
            
        except Exception as e:
            print(f"Error obteniendo tareas pendientes: {e}")
            return []

    def get_mis_clientes(self, vendedor_id: int, estado: str = 'todos', busqueda: str = '') -> List[Dict]:
        """Obtiene todos los clientes del vendedor con filtros"""
        try:
            query = db.session.query(Cliente).join(Proyecto).filter(
                Proyecto.responsable_comercial_id == vendedor_id
            )
            
            if busqueda:
                query = query.filter(
                    or_(
                        Cliente.nombre.ilike(f'%{busqueda}%'),
                        Cliente.email_contacto.ilike(f'%{busqueda}%')
                    )
                )
            
            # TODO: Agregar filtro por estado cuando se implemente en el modelo Cliente
            
            clientes = query.distinct().order_by(Cliente.nombre).all()
            
            resultado = []
            for cliente in clientes:
                # Estadísticas del cliente
                total_proyectos = db.session.query(Proyecto).filter(
                    Proyecto.cliente_id == cliente.id,
                    Proyecto.responsable_comercial_id == vendedor_id
                ).count()
                
                ultimo_proyecto = db.session.query(Proyecto).filter(
                    Proyecto.cliente_id == cliente.id,
                    Proyecto.responsable_comercial_id == vendedor_id
                ).order_by(desc(Proyecto.fecha_creacion)).first()
                
                resultado.append({
                    'id': cliente.id,
                    'nombre': cliente.nombre,
                    'email': cliente.email_contacto,
                    'telefono': cliente.telefono_contacto,
                    'total_proyectos': total_proyectos,
                    'ultimo_proyecto': ultimo_proyecto.nombre if ultimo_proyecto else 'Ninguno',
                    'fecha_ultimo_proyecto': ultimo_proyecto.fecha_creacion if ultimo_proyecto else None
                })
            
            return resultado
            
        except Exception as e:
            print(f"Error obteniendo mis clientes: {e}")
            return []

    def get_mis_proyectos(self, vendedor_id: int, estado: str = 'todos', periodo: str = 'actual') -> List[Dict]:
        """Obtiene proyectos del vendedor con filtros"""
        try:
            query = db.session.query(Proyecto).options(
                joinedload(Proyecto.cliente)
            ).filter(
                Proyecto.responsable_comercial_id == vendedor_id
            )
            
            # Filtro por estado
            if estado != 'todos':
                try:
                    estado_enum = EstadoComercial(estado)
                    query = query.filter(Proyecto.estado_comercial == estado_enum)
                except ValueError:
                    pass  # Estado no válido, ignorar filtro
            
            # Filtro por período
            if periodo == 'actual':
                inicio_mes = datetime.now().replace(day=1)
                query = query.filter(Proyecto.fecha_creacion >= inicio_mes)
            elif periodo == 'trimestre':
                inicio_trimestre = datetime.now() - timedelta(days=90)
                query = query.filter(Proyecto.fecha_creacion >= inicio_trimestre)
            
            proyectos = query.order_by(desc(Proyecto.fecha_creacion)).all()
            
            return [
                {
                    'id': proyecto.id,
                    'nombre': proyecto.nombre,
                    'cliente': proyecto.cliente.nombre if proyecto.cliente else 'Sin cliente',
                    'estado': proyecto.estado_comercial.value,
                    'fecha_creacion': proyecto.fecha_creacion,
                    'fecha_entrega_estimada': proyecto.fecha_entrega_estimada,
                    'progreso': self._calcular_progreso_proyecto(proyecto)
                }
                for proyecto in proyectos
            ]
            
        except Exception as e:
            print(f"Error obteniendo mis proyectos: {e}")
            return []

    def get_estadisticas_detalladas(self, vendedor_id: int, periodo: str = '6meses') -> Dict[str, Any]:
        """Obtiene estadísticas detalladas del vendedor"""
        try:
            # Calcular rango de fechas
            if periodo == '3meses':
                fecha_inicio = datetime.now() - timedelta(days=90)
            elif periodo == '6meses':
                fecha_inicio = datetime.now() - timedelta(days=180)
            elif periodo == '1ano':
                fecha_inicio = datetime.now() - timedelta(days=365)
            else:
                fecha_inicio = datetime.now() - timedelta(days=180)
            
            # Proyectos por mes
            proyectos_mes = db.session.query(
                extract('year', Proyecto.fecha_creacion).label('ano'),
                extract('month', Proyecto.fecha_creacion).label('mes'),
                func.count(Proyecto.id).label('cantidad')
            ).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Proyecto.fecha_creacion >= fecha_inicio
            ).group_by('ano', 'mes').order_by('ano', 'mes').all()
            
            # Contratos por estado
            contratos_estado = db.session.query(
                Contrato.estado, func.count(Contrato.id)
            ).join(Proyecto).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Contrato.fecha_creacion >= fecha_inicio
            ).group_by(Contrato.estado).all()
            
            # Valor total de ventas por mes
            ventas_mes = db.session.query(
                extract('year', Contrato.fecha_creacion).label('ano'),
                extract('month', Contrato.fecha_creacion).label('mes'),
                func.sum(Contrato.valor_total).label('valor')
            ).join(Proyecto).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Contrato.estado == EstadoContrato.VIGENTE,
                Contrato.fecha_creacion >= fecha_inicio
            ).group_by('ano', 'mes').order_by('ano', 'mes').all()
            
            return {
                'proyectos_por_mes': [
                    {
                        'mes': f"{int(item.ano)}-{int(item.mes):02d}",
                        'cantidad': item.cantidad
                    }
                    for item in proyectos_mes
                ],
                'contratos_por_estado': [
                    {
                        'estado': estado.value,
                        'cantidad': cantidad
                    }
                    for estado, cantidad in contratos_estado
                ],
                'ventas_por_mes': [
                    {
                        'mes': f"{int(item.ano)}-{int(item.mes):02d}",
                        'valor': float(item.valor) if item.valor else 0
                    }
                    for item in ventas_mes
                ]
            }
            
        except Exception as e:
            print(f"Error obteniendo estadísticas detalladas: {e}")
            return {}

    def get_metricas_mensuales(self, vendedor_id: int, meses: int = 6) -> Dict[str, Any]:
        """Obtiene métricas mensuales para gráficos"""
        try:
            fecha_inicio = datetime.now() - timedelta(days=30 * meses)
            
            # Proyectos creados por mes
            proyectos = db.session.query(
                extract('year', Proyecto.fecha_creacion).label('ano'),
                extract('month', Proyecto.fecha_creacion).label('mes'),
                func.count(Proyecto.id).label('cantidad')
            ).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Proyecto.fecha_creacion >= fecha_inicio
            ).group_by('ano', 'mes').order_by('ano', 'mes').all()
            
            # Contratos confirmados por mes
            contratos = db.session.query(
                extract('year', Contrato.fecha_creacion).label('ano'),
                extract('month', Contrato.fecha_creacion).label('mes'),
                func.count(Contrato.id).label('cantidad'),
                func.sum(Contrato.valor_total).label('valor')
            ).join(Proyecto).filter(
                Proyecto.responsable_comercial_id == vendedor_id,
                Contrato.estado == EstadoContrato.VIGENTE,
                Contrato.fecha_creacion >= fecha_inicio
            ).group_by('ano', 'mes').order_by('ano', 'mes').all()
            
            return {
                'proyectos': [
                    {
                        'mes': f"{int(p.ano)}-{int(p.mes):02d}",
                        'cantidad': p.cantidad
                    }
                    for p in proyectos
                ],
                'contratos': [
                    {
                        'mes': f"{int(c.ano)}-{int(c.mes):02d}",
                        'cantidad': c.cantidad,
                        'valor': float(c.valor) if c.valor else 0
                    }
                    for c in contratos
                ]
            }
            
        except Exception as e:
            print(f"Error obteniendo métricas mensuales: {e}")
            return {}

    def _calcular_progreso_proyecto(self, proyecto) -> int:
        """Calcula el progreso aproximado de un proyecto basado en su estado"""
        if proyecto.estado_comercial == EstadoComercial.PENDIENTE_PRESUPUESTO:
            return 10
        elif proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO:
            return 30
        elif proyecto.estado_comercial == EstadoComercial.ADJUDICADO:
            return 50
        elif proyecto.estado_comercial == EstadoComercial.EN_DESARROLLO:
            return 80
        elif proyecto.estado_comercial == EstadoComercial.TERMINADO:
            return 100
        else:
            return 0