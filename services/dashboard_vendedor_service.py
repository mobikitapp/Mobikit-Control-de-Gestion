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

    def get_comisiones_potenciales(self, vendedor_id: str) -> Dict[str, Any]:
        """Obtiene comisiones potenciales del vendedor"""
        try:
            # Proyectos presupuestados (potencial de comisión)
            proyectos_presupuestados = db.session.query(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
            ).all()

            comision_provision_potencial = 0
            comision_instalacion_potencial = 0
            
            for proyecto in proyectos_presupuestados:
                if proyecto.monto_provision_presupuestado:
                    # Asumir 3% de comisión por defecto
                    comision_provision_potencial += proyecto.monto_provision_presupuestado * 0.03
                if proyecto.monto_instalacion_presupuestado:
                    # Asumir 3% de comisión por defecto
                    comision_instalacion_potencial += proyecto.monto_instalacion_presupuestado * 0.03

            return {
                'comision_provision_potencial': comision_provision_potencial,
                'comision_instalacion_potencial': comision_instalacion_potencial,
                'comision_total_potencial': comision_provision_potencial + comision_instalacion_potencial,
                'proyectos_presupuestados': len(proyectos_presupuestados)
            }

        except Exception as e:
            print(f"Error obteniendo comisiones potenciales: {e}")
            return {
                'comision_provision_potencial': 0,
                'comision_instalacion_potencial': 0,
                'comision_total_potencial': 0,
                'proyectos_presupuestados': 0
            }

    def get_comisiones_adjudicadas(self, vendedor_id: str) -> Dict[str, Any]:
        """Obtiene comisiones adjudicadas del vendedor en el año actual"""
        try:
            inicio_ano = datetime.now().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            
            # Proyectos adjudicados en el año actual
            proyectos_adjudicados = db.session.query(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.estado_comercial == EstadoComercial.ADJUDICADO,
                Proyecto.fecha_adjudicacion >= inicio_ano
            ).all()

            comision_provision_adjudicada = 0
            comision_instalacion_adjudicada = 0
            
            for proyecto in proyectos_adjudicados:
                if proyecto.monto_provision_presupuestado:
                    # Asumir 3% de comisión por defecto
                    comision_provision_adjudicada += proyecto.monto_provision_presupuestado * 0.03
                if proyecto.monto_instalacion_presupuestado:
                    # Asumir 3% de comisión por defecto
                    comision_instalacion_adjudicada += proyecto.monto_instalacion_presupuestado * 0.03

            return {
                'comision_provision_adjudicada': comision_provision_adjudicada,
                'comision_instalacion_adjudicada': comision_instalacion_adjudicada,
                'comision_total_adjudicada': comision_provision_adjudicada + comision_instalacion_adjudicada,
                'proyectos_adjudicados': len(proyectos_adjudicados)
            }

        except Exception as e:
            print(f"Error obteniendo comisiones adjudicadas: {e}")
            return {
                'comision_provision_adjudicada': 0,
                'comision_instalacion_adjudicada': 0,
                'comision_total_adjudicada': 0,
                'proyectos_adjudicados': 0
            }

    def get_margenes_promedio(self, vendedor_id: str) -> Dict[str, Any]:
        """Obtiene márgenes promedio del vendedor"""
        try:
            # Proyectos adjudicados del vendedor
            proyectos = db.session.query(Proyecto).filter(
                Proyecto.vendedor_id == vendedor_id,
                Proyecto.estado_comercial == EstadoComercial.ADJUDICADO
            ).all()

            if not proyectos:
                return {
                    'margen_promedio_provision': 0,
                    'margen_promedio_instalacion': 0,
                    'proyectos_evaluados': 0
                }

            margenes_provision = []
            margenes_instalacion = []

            for proyecto in proyectos:
                # Calcular margen de provisión usando costos disponibles
                if (proyecto.monto_provision_presupuestado and 
                    proyecto.monto_provision_presupuestado > 0):
                    
                    # Usar costo_provision si existe, sino usar una estimación del 70% como margen típico
                    costo_provision = getattr(proyecto, 'costo_provision', None)
                    if costo_provision and costo_provision > 0:
                        margen_provision = ((proyecto.monto_provision_presupuestado - costo_provision) / 
                                          proyecto.monto_provision_presupuestado * 100)
                        margenes_provision.append(margen_provision)
                    else:
                        # Si no hay costo registrado, asumir margen del 30% (típico en la industria)
                        margenes_provision.append(30.0)

                # Calcular margen de instalación
                if (proyecto.monto_instalacion_presupuestado and 
                    proyecto.monto_instalacion_presupuestado > 0):
                    
                    # Usar costo_instalacion si existe, sino usar una estimación del 70% como margen típico
                    costo_instalacion = getattr(proyecto, 'costo_instalacion', None)
                    if costo_instalacion and costo_instalacion > 0:
                        margen_instalacion = ((proyecto.monto_instalacion_presupuestado - costo_instalacion) / 
                                            proyecto.monto_instalacion_presupuestado * 100)
                        margenes_instalacion.append(margen_instalacion)
                    else:
                        # Si no hay costo registrado, asumir margen del 25% (típico en instalaciones)
                        margenes_instalacion.append(25.0)

            margen_promedio_provision = sum(margenes_provision) / len(margenes_provision) if margenes_provision else 0
            margen_promedio_instalacion = sum(margenes_instalacion) / len(margenes_instalacion) if margenes_instalacion else 0

            return {
                'margen_promedio_provision': margen_promedio_provision,
                'margen_promedio_instalacion': margen_promedio_instalacion,
                'proyectos_evaluados': len(proyectos)
            }

        except Exception as e:
            print(f"Error obteniendo márgenes promedio: {e}")
            return {
                'margen_promedio_provision': 0,
                'margen_promedio_instalacion': 0,
                'proyectos_evaluados': 0
            }