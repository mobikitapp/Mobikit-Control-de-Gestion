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
            inicio_ano = datetime.now().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

            # Proyectos del año actual
            proyectos_ano = db.session.query(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.created_at >= inicio_ano
            ).count()

            # Contratos confirmados del año
            contratos_ano = db.session.query(Contrato).join(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Contrato.created_at >= inicio_ano
            ).count()

            # Valor total del año
            valor_total = db.session.query(
                func.sum(
                    func.coalesce(Proyecto.monto_provision_presupuestado, 0) + 
                    func.coalesce(Proyecto.monto_instalacion_presupuestado, 0)
                )
            ).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.created_at >= inicio_ano
            ).scalar() or 0

            # Clientes activos (que tienen proyectos activos)
            clientes_activos = db.session.query(Cliente).join(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.estado_comercial.in_([EstadoComercial.PRESUPUESTADO, EstadoComercial.ADJUDICADO])
            ).distinct().count()

            # Proyectos por estado
            proyectos_por_estado = self._get_proyectos_por_estado(vendedor_id)

            return {
                'proyectos_ano': proyectos_ano,
                'contratos_ano': contratos_ano,
                'valor_total_ano': float(valor_total),
                'clientes_activos': clientes_activos,
                'proyectos_por_estado': proyectos_por_estado
            }

        except Exception as e:
            print(f"Error obteniendo métricas del vendedor: {e}")
            return {}

    def _get_proyectos_por_estado(self, vendedor_id: str) -> Dict[str, int]:
        """Obtiene el conteo de proyectos por estado comercial"""
        try:
            proyectos = db.session.query(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.activo == True
            ).all()

            conteo_por_estado = {}
            for estado in EstadoComercial:
                conteo_por_estado[estado.value] = 0

            for proyecto in proyectos:
                if proyecto.estado_comercial:
                    conteo_por_estado[proyecto.estado_comercial.value] += 1

            return conteo_por_estado

        except Exception as e:
            print(f"Error obteniendo proyectos por estado: {e}")
            return {}

    def get_tasa_exito_vendedor(self, vendedor_id: str) -> Dict[str, Any]:
        """Calcula la tasa de éxito del vendedor en el año actual"""
        try:
            inicio_ano = datetime.now().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

            # Proyectos exitosos (adjudicados)
            proyectos_exitosos = db.session.query(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.estado_comercial == EstadoComercial.ADJUDICADO,
                Proyecto.fecha_adjudicacion >= inicio_ano
            ).count()

            # Proyectos perdidos
            proyectos_perdidos = db.session.query(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.estado_comercial == EstadoComercial.PERDIDO,
                Proyecto.created_at >= inicio_ano
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
            proyectos = db.session.query(Proyecto).options(joinedload(Proyecto.cliente)).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.estado_comercial.in_([
                    EstadoComercial.PRESUPUESTADO,
                    EstadoComercial.ADJUDICADO
                ])
            ).order_by(Proyecto.created_at.desc()).limit(5).all()

            resultado = []
            for proyecto in proyectos:
                # Calcular progreso basado en porcentaje de facturación
                try:
                    from services.finanzas_service import FinanzasService
                    finanzas_service = FinanzasService()
                    
                    # Obtener totales dinámicos del proyecto
                    totales = finanzas_service.get_totales_proyecto_dinamicos(proyecto.id)
                    progreso_facturacion = totales.get('avance_facturacion', 0)
                except Exception as e:
                    print(f"Error calculando porcentaje facturación para proyecto {proyecto.id}: {str(e)}")
                    # Si hay error con el cálculo de facturación, usar progreso basado en estado
                    if proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO:
                        progreso_facturacion = 0
                    elif proyecto.estado_comercial == EstadoComercial.ADJUDICADO:
                        progreso_facturacion = 0
                    else:
                        progreso_facturacion = 0

                resultado.append({
                    'nombre': proyecto.nombre,
                    'cliente': proyecto.cliente.nombre if proyecto.cliente else 'Sin cliente',
                    'estado': proyecto.estado_comercial.value,
                    'progreso': round(progreso_facturacion)
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
            ).distinct().order_by(Cliente.created_at.desc()).limit(5).all()

            resultado = []
            for cliente in clientes:
                # Obtener último proyecto de este cliente con este vendedor
                ultimo_proyecto = db.session.query(Proyecto).filter(
                    Proyecto.cliente_id == cliente.id,
                    Proyecto.vendedor_id == vendedor_id
                ).order_by(Proyecto.created_at.desc()).first()

                resultado.append({
                    'nombre': cliente.nombre,
                    'ultimo_contacto': ultimo_proyecto.created_at if ultimo_proyecto else None,
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

            proyectos = query.order_by(Proyecto.created_at.desc()).all()
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