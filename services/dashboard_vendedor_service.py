"""
Servicio para el Dashboard Personal del Vendedor
Maneja todas las consultas de datos específicas del vendedor logueado
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy import func, and_, or_, desc, extract
from sqlalchemy.orm import joinedload
from decimal import Decimal

# Importación de logger (asumiendo que está configurado en app)
try:
    from app import db, logger
except ImportError:
    # Definiciones de mock para que el código sea ejecutable sin la app completa
    class MockDB:
        def __init__(self):
            self.session = None
    db = MockDB()
    class MockLogger:
        def error(self, message):
            print(f"ERROR: {message}")
    logger = MockLogger()

from models import (
    User, Cliente, Proyecto, Contrato, OrdenFabricacion, Despacho,
    EstadoComercial, EstadoContrato, EstadoOF, EstadoDespacho, RolUsuario
)

# Asumiendo que existe un repositorio para Proyectos
# Si no, estas llamadas fallarán. Se asume que ProyectosRepository está definido en otro lugar.
class ProyectosRepository:
    @staticmethod
    def count_by_vendedor_and_year(vendedor_id: str, year: int) -> int:
        return 0
    @staticmethod
    def count_by_vendedor_estado_year(vendedor_id: str, estado: EstadoComercial, year: int) -> int:
        return 0
    @staticmethod
    def get_total_value_by_vendedor_year(vendedor_id: str, year: int, estados: List[EstadoComercial]) -> Decimal:
        return Decimal('0')
    @staticmethod
    def count_active_clients_by_vendedor(vendedor_id: str) -> int:
        return 0
    @staticmethod
    def get_count_by_estado_vendedor(vendedor_id: str) -> Dict[str, int]:
        return {}
    @staticmethod
    def get_by_vendedor_and_period(vendedor_id: str, fecha_inicio: datetime.date, fecha_fin: datetime.date) -> List[Any]:
        return []

class DashboardVendedorService:
    """Servicio para datos del dashboard personal del vendedor"""

    def get_metricas_vendedor(self, vendedor_id: str) -> Dict[str, Any]:
        """Obtiene métricas específicas del vendedor"""
        try:
            # Métricas del año actual
            año_actual = datetime.now().year

            # Proyectos del año
            proyectos_ano = ProyectosRepository.count_by_vendedor_and_year(vendedor_id, año_actual)

            # Contratos confirmados (adjudicados)
            contratos_ano = ProyectosRepository.count_by_vendedor_estado_year(
                vendedor_id,
                EstadoComercial.ADJUDICADO,
                año_actual
            )

            # Valor total de proyectos adjudicados
            valor_total_ano = ProyectosRepository.get_total_value_by_vendedor_year(
                vendedor_id,
                año_actual,
                estados=[EstadoComercial.ADJUDICADO]
            )

            # Clientes activos (con proyectos en curso)
            clientes_activos = ProyectosRepository.count_active_clients_by_vendedor(vendedor_id)

            # Estados de proyectos
            proyectos_por_estado = ProyectosRepository.get_count_by_estado_vendedor(vendedor_id)

            # Calcular comisiones y rendimiento financiero
            comisiones_data = self._calcular_comisiones_vendedor(vendedor_id, año_actual)
            rendimiento_financiero = self._calcular_rendimiento_financiero(vendedor_id, año_actual)

            return {
                'proyectos_ano': proyectos_ano,
                'contratos_ano': contratos_ano,
                'valor_total_ano': valor_total_ano or Decimal('0'),
                'clientes_activos': clientes_activos,
                'proyectos_por_estado': proyectos_por_estado,
                'comisiones_potenciales': comisiones_data['potenciales'],
                'comisiones_adjudicadas': comisiones_data['adjudicadas'],
                'rendimiento_financiero': rendimiento_financiero
            }

        except Exception as e:
            logger.error(f"Error obteniendo métricas del vendedor {vendedor_id}: {str(e)}")
            return {
                'proyectos_ano': 0,
                'contratos_ano': 0,
                'valor_total_ano': Decimal('0'),
                'clientes_activos': 0,
                'proyectos_por_estado': {},
                'comisiones_potenciales': Decimal('0'),
                'comisiones_adjudicadas': Decimal('0'),
                'rendimiento_financiero': 0.0
            }

    def _calcular_comisiones_vendedor(self, vendedor_id: str, año: int) -> Dict[str, Decimal]:
        """Calcula comisiones potenciales y adjudicadas del vendedor"""
        try:
            from app import db

            # Obtener proyectos presupuestados (comisiones potenciales)
            proyectos_presupuestados = db.session.query(Proyecto)\
                .filter_by(vendedor_id=vendedor_id, activo=True)\
                .filter(extract('year', Proyecto.created_at) == año)\
                .filter(Proyecto.estado_comercial.in_([
                    EstadoComercial.PRESUPUESTADO,
                    EstadoComercial.ADJUDICADO
                ]))\
                .all()

            # Obtener proyectos adjudicados (comisiones adjudicadas)
            proyectos_adjudicados = [p for p in proyectos_presupuestados
                                   if p.estado_comercial == EstadoComercial.ADJUDICADO]

            # Tasa de comisión por defecto (se puede hacer configurable)
            tasa_comision = Decimal('0.02')  # 2%

            comisiones_potenciales = Decimal('0')
            for proyecto in proyectos_presupuestados:
                valor_proyecto = (proyecto.monto_provision_presupuestado or Decimal('0')) + \
                               (proyecto.monto_instalacion_presupuestado or Decimal('0'))
                comisiones_potenciales += valor_proyecto * tasa_comision

            comisiones_adjudicadas = Decimal('0')
            for proyecto in proyectos_adjudicados:
                valor_proyecto = (proyecto.monto_provision_presupuestado or Decimal('0')) + \
                               (proyecto.monto_instalacion_presupuestado or Decimal('0'))
                comisiones_adjudicadas += valor_proyecto * tasa_comision

            return {
                'potenciales': comisiones_potenciales,
                'adjudicadas': comisiones_adjudicadas
            }

        except Exception as e:
            logger.error(f"Error calculando comisiones: {str(e)}")
            return {
                'potenciales': Decimal('0'),
                'adjudicadas': Decimal('0')
            }

    def _calcular_rendimiento_financiero(self, vendedor_id: str, año: int) -> float:
        """Calcula el rendimiento financiero del vendedor basado en márgenes"""
        try:
            from app import db

            proyectos_adjudicados = db.session.query(Proyecto)\
                .filter_by(vendedor_id=vendedor_id, activo=True)\
                .filter(extract('year', Proyecto.created_at) == año)\
                .filter_by(estado_comercial=EstadoComercial.ADJUDICADO)\
                .all()

            if not proyectos_adjudicados:
                return 0.0

            # Calcular margen promedio ponderado
            total_facturacion = Decimal('0')
            margen_total_ponderado = Decimal('0')

            for proyecto in proyectos_adjudicados:
                provision = proyecto.monto_provision_presupuestado or Decimal('0')
                instalacion = proyecto.monto_instalacion_presupuestado or Decimal('0')
                facturacion_proyecto = provision + instalacion

                if facturacion_proyecto > 0:
                    # Obtener márgenes del proyecto
                    margen_provision = proyecto.margen_venta_provision or Decimal('0')
                    margen_instalacion = proyecto.margen_venta_instalacion or Decimal('0')

                    # Calcular margen promedio ponderado del proyecto
                    if provision > 0 and instalacion > 0:
                        margen_proyecto = (margen_provision * provision + margen_instalacion * instalacion) / facturacion_proyecto
                    elif provision > 0:
                        margen_proyecto = margen_provision
                    elif instalacion > 0:
                        margen_proyecto = margen_instalacion
                    else:
                        margen_proyecto = Decimal('0')

                    total_facturacion += facturacion_proyecto
                    margen_total_ponderado += margen_proyecto * facturacion_proyecto

            if total_facturacion > 0:
                rendimiento = float(margen_total_ponderado / total_facturacion)
                return round(rendimiento, 1)

            return 0.0

        except Exception as e:
            logger.error(f"Error calculando rendimiento financiero: {str(e)}")
            return 0.0

    def get_estadisticas_detalladas(self, vendedor_id: str, periodo: str = '6meses') -> Dict[str, Any]:
        """Obtiene estadísticas detalladas del vendedor para un período específico"""
        try:
            # Calcular fechas del período
            fecha_fin = datetime.now().date()

            if periodo == '3meses':
                fecha_inicio = fecha_fin - timedelta(days=90)
            elif periodo == '6meses':
                fecha_inicio = fecha_fin - timedelta(days=180)
            elif periodo == '1ano':
                fecha_inicio = fecha_fin - timedelta(days=365)
            else:
                fecha_inicio = fecha_fin - timedelta(days=180)  # Default 6 meses

            # Obtener proyectos del período
            proyectos = ProyectosRepository.get_by_vendedor_and_period(
                vendedor_id, fecha_inicio, fecha_fin
            )

            # Calcular estadísticas
            total_proyectos = len(proyectos)
            proyectos_adjudicados = len([p for p in proyectos if p.estado_comercial == EstadoComercial.ADJUDICADO])

            tasa_exito = (proyectos_adjudicados / total_proyectos * 100) if total_proyectos > 0 else 0

            valor_total = sum([
                (p.monto_provision_presupuestado or Decimal('0')) +
                (p.monto_instalacion_presupuestado or Decimal('0'))
                for p in proyectos if p.estado_comercial == EstadoComercial.ADJUDICADO
            ])

            # Distribución por estado
            distribucion_estados = {}
            for proyecto in proyectos:
                estado = proyecto.estado_comercial.value if proyecto.estado_comercial else 'SIN_ESTADO'
                distribucion_estados[estado] = distribucion_estados.get(estado, 0) + 1

            # Clientes únicos
            clientes_unicos = len(set([p.cliente_id for p in proyectos if p.cliente_id]))

            return {
                'periodo': periodo,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'total_proyectos': total_proyectos,
                'proyectos_adjudicados': proyectos_adjudicados,
                'tasa_exito': round(tasa_exito, 1),
                'valor_total': valor_total,
                'distribucion_estados': distribucion_estados,
                'clientes_unicos': clientes_unicos,
                'valor_promedio_proyecto': valor_total / proyectos_adjudicados if proyectos_adjudicados > 0 else Decimal('0')
            }

        except Exception as e:
            logger.error(f"Error obteniendo estadísticas detalladas: {str(e)}")
            return {
                'periodo': periodo,
                'total_proyectos': 0,
                'tasa_exito': 0,
                'valor_total': Decimal('0')
            }

    def get_metricas_vendedor_original(self, vendedor_id: str) -> Dict[str, Any]:
        """Obtiene métricas principales del vendedor (versión original de referencia)"""
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
                # Calcular progreso basado en órdenes de fabricación si existen
                try:
                    total_ofs = db.session.query(OrdenFabricacion).filter(
                        OrdenFabricacion.proyecto_id == proyecto.id
                    ).count()

                    ofs_completadas = db.session.query(OrdenFabricacion).filter(
                        OrdenFabricacion.proyecto_id == proyecto.id,
                        OrdenFabricacion.estado_fabricacion == 'TERMINADO'
                    ).count()

                    progreso = (ofs_completadas / total_ofs * 100) if total_ofs > 0 else 0
                except:
                    # Si hay error con las órdenes de fabricación, usar progreso basado en estado
                    if proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO:
                        progreso = 25
                    elif proyecto.estado_comercial == EstadoComercial.ADJUDICADO:
                        progreso = 50
                    else:
                        progreso = 0

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
        """Obtiene estadísticas detalladas del vendedor para un período específico"""
        try:
            # Calcular fechas del período
            fecha_fin = datetime.now().date()

            if periodo == '3meses':
                fecha_inicio = fecha_fin - timedelta(days=90)
            elif periodo == '6meses':
                fecha_inicio = fecha_fin - timedelta(days=180)
            elif periodo == '1ano':
                fecha_inicio = fecha_fin - timedelta(days=365)
            else:
                fecha_inicio = fecha_fin - timedelta(days=180)  # Default 6 meses

            # Obtener proyectos del período
            proyectos = ProyectosRepository.get_by_vendedor_and_period(
                vendedor_id, fecha_inicio, fecha_fin
            )

            # Calcular estadísticas
            total_proyectos = len(proyectos)
            proyectos_adjudicados = len([p for p in proyectos if p.estado_comercial == EstadoComercial.ADJUDICADO])

            tasa_exito = (proyectos_adjudicados / total_proyectos * 100) if total_proyectos > 0 else 0

            valor_total = sum([
                (p.monto_provision_presupuestado or Decimal('0')) +
                (p.monto_instalacion_presupuestado or Decimal('0'))
                for p in proyectos if p.estado_comercial == EstadoComercial.ADJUDICADO
            ])

            # Distribución por estado
            distribucion_estados = {}
            for proyecto in proyectos:
                estado = proyecto.estado_comercial.value if proyecto.estado_comercial else 'SIN_ESTADO'
                distribucion_estados[estado] = distribucion_estados.get(estado, 0) + 1

            # Clientes únicos
            clientes_unicos = len(set([p.cliente_id for p in proyectos if p.cliente_id]))

            return {
                'periodo': periodo,
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'total_proyectos': total_proyectos,
                'proyectos_adjudicados': proyectos_adjudicados,
                'tasa_exito': round(tasa_exito, 1),
                'valor_total': valor_total,
                'distribucion_estados': distribucion_estados,
                'clientes_unicos': clientes_unicos,
                'valor_promedio_proyecto': valor_total / proyectos_adjudicados if proyectos_adjudicados > 0 else Decimal('0')
            }

        except Exception as e:
            logger.error(f"Error obteniendo estadísticas detalladas: {str(e)}")
            return {
                'periodo': periodo,
                'total_proyectos': 0,
                'tasa_exito': 0,
                'valor_total': Decimal('0')
            }

    def get_metricas_mensuales(self, vendedor_id: str, meses: int = 6) -> List[Dict[str, Any]]:
        """Obtiene métricas mensuales para gráficos"""
        try:
            # Implementar métricas mensuales
            return []

        except Exception as e:
            print(f"Error obteniendo métricas mensuales: {e}")
            return []