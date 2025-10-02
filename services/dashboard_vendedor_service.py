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

    def get_metricas_vendedor(self, vendedor_id: str) -> Dict[str, Any]:
        """Obtiene métricas principales del vendedor"""
        try:
            mes_actual = datetime.now().replace(day=1)

            # Proyectos del mes actual
            proyectos_mes = db.session.query(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.fecha_creacion >= mes_actual
            ).count()

            # Contratos confirmados del mes
            contratos_mes = db.session.query(Contrato).join(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Contrato.fecha_confirmacion >= mes_actual
            ).count()

            # Valor total del mes
            valor_total = db.session.query(
                func.sum(Proyecto.monto_provision_presupuestado + Proyecto.monto_instalacion_presupuestado)
            ).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.fecha_creacion >= mes_actual
            ).scalar() or 0

            # Clientes activos (que tienen proyectos activos)
            clientes_activos = db.session.query(Cliente).join(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.estado_comercial.in_([EstadoComercial.PRESUPUESTADO, EstadoComercial.ADJUDICADO])
            ).distinct().count()

            return {
                'proyectos_mes': proyectos_mes,
                'contratos_mes': contratos_mes,
                'valor_total_mes': float(valor_total),
                'clientes_activos': clientes_activos
            }

        except Exception as e:
            print(f"Error obteniendo métricas del vendedor: {e}")
            return {}

    def get_tasa_exito_vendedor(self, vendedor_id: str) -> Dict[str, Any]:
        """Calcula la tasa de éxito del vendedor en los últimos 6 meses"""
        try:
            seis_meses_atras = datetime.now() - timedelta(days=180)

            # Proyectos exitosos (adjudicados)
            proyectos_exitosos = db.session.query(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.estado_comercial == EstadoComercial.ADJUDICADO,
                Proyecto.fecha_adjudicacion >= seis_meses_atras
            ).count()

            # Proyectos perdidos
            proyectos_perdidos = db.session.query(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.estado_comercial == EstadoComercial.PERDIDO,
                Proyecto.fecha_creacion >= seis_meses_atras
            ).count()

            total_oportunidades = proyectos_exitosos + proyectos_perdidos
            tasa_exito = (proyectos_exitosos / total_oportunidades * 100) if total_oportunidades > 0 else 0

            return {
                'proyectos_exitosos': proyectos_exitosos,
                'proyectos_perdidos': proyectos_perdidos,
                'total_oportunidades': total_oportunidades,
                'tasa_exito_porcentaje': tasa_exito
            }

        except Exception as e:
            print(f"Error calculando tasa de éxito: {e}")
            return {}

    def get_proyectos_activos(self, vendedor_id: str) -> List[Dict[str, Any]]:
        """Obtiene los proyectos activos del vendedor"""
        try:
            proyectos = db.session.query(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.estado_comercial.in_([
                    EstadoComercial.PRESUPUESTADO,
                    EstadoComercial.ADJUDICADO
                ])
            ).order_by(Proyecto.fecha_creacion.desc()).limit(5).all()

            resultado = []
            for proyecto in proyectos:
                # Calcular progreso basado en órdenes de fabricación
                total_ofs = db.session.query(OrdenFabricacion).filter(
                    OrdenFabricacion.proyecto_id == proyecto.id
                ).count()

                ofs_completadas = db.session.query(OrdenFabricacion).filter(
                    OrdenFabricacion.proyecto_id == proyecto.id,
                    OrdenFabricacion.estado == EstadoOF.TERMINADO
                ).count()

                progreso = (ofs_completadas / total_ofs * 100) if total_ofs > 0 else 0

                resultado.append({
                    'nombre': proyecto.nombre,
                    'cliente': proyecto.cliente.nombre if proyecto.cliente else 'Sin cliente',
                    'estado': proyecto.estado_comercial.value,
                    'progreso': round(progreso)
                })

            return resultado

        except Exception as e:
            print(f"Error obteniendo proyectos activos: {e}")
            return []

    def get_clientes_recientes(self, vendedor_id: str) -> List[Dict[str, Any]]:
        """Obtiene los clientes recientes del vendedor"""
        try:
            # Obtener clientes que tienen proyectos con este vendedor
            clientes = db.session.query(Cliente).join(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id
            ).distinct().order_by(Cliente.fecha_creacion.desc()).limit(5).all()

            resultado = []
            for cliente in clientes:
                # Obtener último proyecto de este cliente con este vendedor
                ultimo_proyecto = db.session.query(Proyecto).filter(
                    Proyecto.cliente_id == cliente.id,
                    Proyecto.vendedor_id == vendedor_id
                ).order_by(Proyecto.fecha_creacion.desc()).first()

                resultado.append({
                    'nombre': cliente.nombre,
                    'email': cliente.email,
                    'ultimo_contacto': ultimo_proyecto.fecha_creacion if ultimo_proyecto else None,
                    'estado_ultimo_proyecto': ultimo_proyecto.estado_comercial.value if ultimo_proyecto else None
                })

            return resultado

        except Exception as e:
            print(f"Error obteniendo clientes recientes: {e}")
            return []

    def get_tareas_pendientes(self, vendedor_id: str) -> List[Dict[str, Any]]:
        """Obtiene tareas pendientes del vendedor"""
        try:
            # Por ahora retornamos una lista vacía
            # En el futuro se puede integrar con un sistema de tareas
            return []

        except Exception as e:
            print(f"Error obteniendo tareas pendientes: {e}")
            return []

    def get_mis_clientes(self, vendedor_id: str, estado: str = 'todos', busqueda: str = '') -> List[Dict[str, Any]]:
        """Obtiene todos los clientes del vendedor con filtros"""
        try:
            query = db.session.query(Cliente).join(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id
            ).distinct()

            if busqueda:
                query = query.filter(Cliente.nombre.ilike(f'%{busqueda}%'))

            clientes = query.all()
            return clientes

        except Exception as e:
            print(f"Error obteniendo clientes del vendedor: {e}")
            return []

    def get_mis_proyectos(self, vendedor_id: str, estado: str = 'todos', periodo: str = 'actual') -> List[Dict[str, Any]]:
        """Obtiene todos los proyectos del vendedor con filtros"""
        try:
            query = db.session.query(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id
            )

            if estado != 'todos':
                query = query.filter(Proyecto.estado_comercial == EstadoComercial(estado))

            proyectos = query.order_by(Proyecto.fecha_creacion.desc()).all()
            return proyectos

        except Exception as e:
            print(f"Error obteniendo proyectos del vendedor: {e}")
            return []

    def get_estadisticas_detalladas(self, vendedor_id: str, periodo: str = '6meses') -> Dict[str, Any]:
        """Obtiene estadísticas detalladas del vendedor"""
        try:
            # Implementar estadísticas detalladas según el período
            return {}

        except Exception as e:
            print(f"Error obteniendo estadísticas detalladas: {e}")
            return {}

    def get_metricas_mensuales(self, vendedor_id: str, meses: int = 6) -> List[Dict[str, Any]]:
        """Obtiene métricas mensuales para gráficos"""
        try:
            # Implementar métricas mensuales
            return []

        except Exception as e:
            print(f"Error obteniendo métricas mensuales: {e}")
            return []