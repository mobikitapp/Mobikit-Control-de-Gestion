from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date, timedelta
from sqlalchemy import and_, or_, func, extract, case, desc
from sqlalchemy.orm import joinedload
from decimal import Decimal
import logging

from app import db
from models import (
    OrdenFabricacion, Proyecto, Cliente, User, OrdenAreaProgreso, 
    Area, AreaEstado, TipoArea, TipoProyecto, EstadoComercial
)
from services.planificacion_operacional_service import PlanificacionOperacionalService

logger = logging.getLogger(__name__)

class ProductividadService:
    """Servicio para análisis de productividad real basado en tiempos y tableros"""
    
    def __init__(self):
        self.planificacion_service = PlanificacionOperacionalService()
    
    def get_productividad_real(self, filtros: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Obtiene análisis completo de productividad real
        
        Args:
            filtros: Dict con fechas, tipos, áreas, etc.
        
        Returns:
            Dict con métricas de productividad, datos para gráficos y estadísticas
        """
        try:
            # Aplicar filtros por defecto
            if not filtros:
                filtros = {}
            
            fecha_inicio = filtros.get('fecha_inicio', date.today() - timedelta(days=90))
            fecha_fin = filtros.get('fecha_fin', date.today())
            tipo_proyecto = filtros.get('tipo_proyecto')
            area_filtro = filtros.get('area')
            estado_of = filtros.get('estado_of', 'completadas')  # completadas, en_proceso, todas
            
            # Obtener datos base de OFs
            ofs_data = self._get_ofs_con_tiempos_reales(fecha_inicio, fecha_fin, tipo_proyecto, estado_of)
            
            # Calcular métricas por tipo de proyecto
            metricas_por_tipo = self._calcular_metricas_por_tipo_proyecto(ofs_data)
            
            # Calcular métricas por área
            metricas_por_area = self._calcular_metricas_por_area(ofs_data, area_filtro)
            
            # Generar datos para gráficos de dispersión (aplicar filtros)
            datos_scatter = self._generar_datos_scatter(ofs_data, area_filtro, tipo_proyecto)
            
            # Calcular análisis estadístico (aplicar filtros)
            analisis_estadistico = self._calcular_analisis_estadistico(ofs_data, tipo_proyecto)
            
            # Identificar outliers
            outliers = self._identificar_outliers(ofs_data)
            
            return {
                'periodo': {
                    'fecha_inicio': fecha_inicio.isoformat(),
                    'fecha_fin': fecha_fin.isoformat()
                },
                'total_ofs': len(ofs_data),
                'metricas_por_tipo': metricas_por_tipo,
                'metricas_por_area': metricas_por_area,
                'datos_scatter': datos_scatter,
                'analisis_estadistico': analisis_estadistico,
                'outliers': outliers,
                'filtros_aplicados': filtros
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo productividad real: {str(e)}")
            return {'error': str(e)}
    
    def _get_ofs_con_tiempos_reales(self, fecha_inicio: date, fecha_fin: date, 
                                   tipo_proyecto: str = None, estado_of: str = 'completadas') -> List[Dict]:
        """Obtiene OFs con datos de tiempos reales calculados"""
        try:
            # Obtener estadísticas básicas para logging
            total_ofs = db.session.query(OrdenFabricacion).count()
            logger.info(f"Consultando productividad desde {total_ofs} OFs totales")
            
            # Query base para OFs
            query = (db.session.query(OrdenFabricacion, Proyecto)
                    .join(Proyecto, OrdenFabricacion.proyecto_id == Proyecto.id)
                    .options(joinedload(OrdenFabricacion.items)))
            
            # Filtros de fecha  
            if estado_of == 'completadas':
                # TEMPORALMENTE: Incluir también órdenes en proceso para debugging
                logger.info(f"Buscando órdenes completadas Y en proceso para período {fecha_inicio} a {fecha_fin}")
                
                # Incluir órdenes con fecha_inicio (en proceso) temporalmente
                # Incluir OFs completadas Y órdenes en bodega usando sistema de áreas
                from sqlalchemy import or_
                from models import OrdenAreaProgreso, AreaEstado, Area
                
                # TEMPORALMENTE: Incluir todas las órdenes para debugging (sin filtros de fecha estrictos)
                # Subquery para OFs en bodega (listo_para_despacho, programado_para_despacho)
                bodega_subquery = (db.session.query(OrdenAreaProgreso.orden_fabricacion_id)
                    .join(AreaEstado, OrdenAreaProgreso.estado_id == AreaEstado.id)
                    .filter(OrdenAreaProgreso.es_actual == True)
                    .filter(AreaEstado.codigo.in_(['listo_para_despacho', 'programado_para_despacho']))
                    .subquery())
                
                logger.info(f"Buscando OFs en bodega...")
                
                # INCLUIR TODAS LAS ÓRDENES temporalmente para debugging
                query = query.filter(
                    or_(
                        # OFs completadas con fecha_fin
                        OrdenFabricacion.fecha_fin.isnot(None),
                        # OFs en bodega 
                        OrdenFabricacion.id.in_(bodega_subquery),
                        # OFs con fecha_inicio (en proceso)
                        OrdenFabricacion.fecha_inicio.isnot(None)
                    )
                )
                
                # SIN FILTROS DE FECHA temporalmente para debugging
                logger.info("Saltando filtros de fecha para debugging")
            elif estado_of == 'en_proceso':
                query = query.filter(OrdenFabricacion.fecha_inicio.isnot(None))
                query = query.filter(OrdenFabricacion.fecha_fin.is_(None))
                query = query.filter(OrdenFabricacion.fecha_inicio >= fecha_inicio)
            # Para 'todas' no filtrar por estado
            
            # Filtro por tipo de proyecto
            if tipo_proyecto and tipo_proyecto != 'TODAS':
                query = query.filter(Proyecto.tipo_proyecto == tipo_proyecto)
            
            # Solo proyectos activos
            query = query.filter(Proyecto.activo == True)
            
            resultados = query.all()
            logger.info(f"Query devolvió {len(resultados)} resultados para los filtros especificados")
            
            ofs_procesadas = []
            for of, proyecto in resultados:
                # Calcular tiempos reales por área
                tiempos_reales = self._calcular_tiempos_reales_of(of.id)
                
                # Calcular tiempos estimados
                tipo_proyecto_str = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                tiempo_estimado_fabrica = self.planificacion_service.calcular_tiempo_estimado_fabrica(
                    of.cantidad_tableros or 0, tipo_proyecto_str
                )
                tiempo_estimado_embalaje = self.planificacion_service.calcular_tiempo_estimado_embalaje(
                    of.cantidad_tableros or 0, tipo_proyecto_str
                )
                
                # Calcular métricas de productividad
                tableros_por_dia_fabrica = self._calcular_tableros_por_dia(
                    of.cantidad_tableros or 0, tiempos_reales.get('fabrica', {}).get('dias', 0)
                )
                tableros_por_dia_embalaje = self._calcular_tableros_por_dia(
                    of.cantidad_tableros or 0, tiempos_reales.get('embalaje', {}).get('dias', 0)
                )
                
                # Calcular tiempo total
                tiempo_total_dias = tiempos_reales.get('tiempo_total_dias', 0)
                tableros_por_dia_total = self._calcular_tableros_por_dia(
                    of.cantidad_tableros or 0, tiempo_total_dias
                )
                
                of_data = {
                    'id': of.id,
                    'codigo': of.codigo,
                    'proyecto_id': proyecto.id,
                    'proyecto_nombre': proyecto.nombre,
                    'cliente_nombre': proyecto.cliente.nombre if proyecto.cliente else 'Sin cliente',
                    'tipo_proyecto': proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR',
                    'cantidad_tableros': of.cantidad_tableros or 0,
                    'fecha_inicio': of.fecha_inicio.isoformat() if of.fecha_inicio else None,
                    'fecha_fin': of.fecha_fin.isoformat() if of.fecha_fin else None,
                    'tiempos_reales': tiempos_reales,
                    'tiempos_estimados': {
                        'fabrica_dias': tiempo_estimado_fabrica,
                        'embalaje_dias': tiempo_estimado_embalaje,
                        'total_dias': tiempo_estimado_fabrica + tiempo_estimado_embalaje
                    },
                    'productividad': {
                        'tableros_por_dia_fabrica': tableros_por_dia_fabrica,
                        'tableros_por_dia_embalaje': tableros_por_dia_embalaje,
                        'tableros_por_dia_total': tableros_por_dia_total
                    },
                    'eficiencia': {
                        'fabrica_vs_estimado': self._calcular_eficiencia(
                            tiempos_reales.get('fabrica', {}).get('dias', 0), tiempo_estimado_fabrica
                        ),
                        'embalaje_vs_estimado': self._calcular_eficiencia(
                            tiempos_reales.get('embalaje', {}).get('dias', 0), tiempo_estimado_embalaje
                        ),
                        'total_vs_estimado': self._calcular_eficiencia(
                            tiempo_total_dias, tiempo_estimado_fabrica + tiempo_estimado_embalaje
                        )
                    }
                }
                
                ofs_procesadas.append(of_data)
            
            return ofs_procesadas
            
        except Exception as e:
            logger.error(f"Error obteniendo OFs con tiempos reales: {str(e)}")
            logger.error(f"Query parameters: fecha_inicio={fecha_inicio}, fecha_fin={fecha_fin}, tipo_proyecto={tipo_proyecto}")
            return []
    
    def _calcular_tiempos_reales_of(self, of_id: int) -> Dict[str, Any]:
        """Calcula tiempos reales de una OF basado en OrdenAreaProgreso"""
        try:
            # Obtener historial completo de progreso
            historial = (db.session.query(OrdenAreaProgreso)
                        .options(joinedload(OrdenAreaProgreso.area))
                        .filter(OrdenAreaProgreso.orden_fabricacion_id == of_id)
                        .order_by(OrdenAreaProgreso.fecha_ingreso_area.asc())
                        .all())
            
            if not historial:
                return {'fabrica': {'dias': 0}, 'embalaje': {'dias': 0}, 'tiempo_total_dias': 0}
            
            tiempos_por_area = {'fabrica': {'dias': 0}, 'embalaje': {'dias': 0}}
            tiempo_total_segundos = 0
            
            for i, progreso in enumerate(historial):
                # Determinar cuándo salió del área (siguiente progreso o ahora si es actual)
                if progreso.es_actual:
                    # Si es el progreso actual, calcular hasta ahora
                    tiempo_en_area = datetime.now() - progreso.fecha_ingreso_area
                else:
                    # Buscar siguiente progreso para calcular tiempo en área
                    siguiente = None
                    for j in range(i + 1, len(historial)):
                        if historial[j].fecha_ingreso_area > progreso.fecha_ingreso_area:
                            siguiente = historial[j]
                            break
                    
                    if siguiente:
                        tiempo_en_area = siguiente.fecha_ingreso_area - progreso.fecha_ingreso_area
                    else:
                        # Si no hay siguiente, usar tiempo hasta ahora
                        # Asegurar que datetime.now() tenga timezone info si fecha_ingreso_area la tiene
                        ahora = datetime.now()
                        if progreso.fecha_ingreso_area.tzinfo is not None:
                            from datetime import timezone
                            ahora = ahora.replace(tzinfo=timezone.utc)
                        tiempo_en_area = ahora - progreso.fecha_ingreso_area
                
                # Convertir a días
                dias_en_area = tiempo_en_area.total_seconds() / (24 * 3600)
                tiempo_total_segundos += tiempo_en_area.total_seconds()
                
                # Clasificar por tipo de área
                if progreso.area and progreso.area.tipo:
                    if progreso.area.tipo == TipoArea.FABRICA:
                        tiempos_por_area['fabrica']['dias'] += dias_en_area
                    elif progreso.area.tipo == TipoArea.EMBALAJE:
                        tiempos_por_area['embalaje']['dias'] += dias_en_area
            
            return {
                **tiempos_por_area,
                'tiempo_total_dias': tiempo_total_segundos / (24 * 3600)
            }
            
        except Exception as e:
            logger.error(f"Error calculando tiempos reales OF {of_id}: {str(e)}")
            return {'fabrica': {'dias': 0}, 'embalaje': {'dias': 0}, 'tiempo_total_dias': 0}
    
    def _calcular_tableros_por_dia(self, cantidad_tableros: int, dias: float) -> float:
        """Calcula ratio tableros por día"""
        if dias <= 0 or cantidad_tableros <= 0:
            return 0.0
        return round(cantidad_tableros / dias, 2)
    
    def _calcular_eficiencia(self, tiempo_real: float, tiempo_estimado: float) -> float:
        """Calcula eficiencia como porcentaje (tiempo_estimado / tiempo_real * 100)"""
        if tiempo_real <= 0 or tiempo_estimado <= 0:
            return 0.0
        # Proteger contra división por cero
        if tiempo_real == 0:
            return 0.0
        return round((tiempo_estimado / tiempo_real) * 100, 1)
    
    def _calcular_metricas_por_tipo_proyecto(self, ofs_data: List[Dict]) -> Dict[str, Any]:
        """Calcula métricas agregadas por tipo de proyecto"""
        try:
            metricas = {}
            
            # Obtener factores de tiempo estimados de configuración
            factores_tiempo = self._get_factores_tiempo_estimados()
            
            # Agrupar por tipo
            for tipo in ['SOCIAL', 'ESTANDAR', 'ESPECIAL']:
                ofs_tipo = [of for of in ofs_data if of['tipo_proyecto'] == tipo]
                
                if not ofs_tipo:
                    # Calcular tableros/día estimado basado en factores de configuración
                    tableros_dia_estimado = self._calcular_tableros_dia_estimado_tipo(tipo, factores_tiempo)
                    
                    metricas[tipo] = {
                        'total_ofs': 0,
                        'total_tableros': 0,
                        'promedio_tiempo_dias': 0,
                        'promedio_tableros_por_dia_total': 0,
                        'tableros_dia_estimado': tableros_dia_estimado,
                        'diferencia_vs_estimado': 0
                    }
                    continue
                
                total_tableros = sum(of['cantidad_tableros'] for of in ofs_tipo)
                
                # Calcular tiempo promedio total
                tiempos_totales = [of['tiempos_reales']['tiempo_total_dias'] for of in ofs_tipo if of['tiempos_reales']['tiempo_total_dias'] > 0]
                promedio_tiempo_total = round(sum(tiempos_totales) / len(tiempos_totales), 2) if tiempos_totales else 0
                
                # Calcular tableros/día total usando total tableros / promedio tiempo
                promedio_tableros_por_dia_total = round(total_tableros / promedio_tiempo_total, 2) if promedio_tiempo_total > 0 else 0
                
                # Calcular tableros/día estimado basado en factores de configuración
                tableros_dia_estimado = self._calcular_tableros_dia_estimado_tipo(tipo, factores_tiempo)
                
                # Calcular diferencia porcentual
                diferencia_vs_estimado = 0
                if tableros_dia_estimado > 0 and promedio_tableros_por_dia_total > 0:
                    diferencia_vs_estimado = round(((promedio_tableros_por_dia_total - tableros_dia_estimado) / tableros_dia_estimado) * 100, 1)
                
                metricas[tipo] = {
                    'total_ofs': len(ofs_tipo),
                    'total_tableros': total_tableros,
                    'promedio_tiempo_dias': promedio_tiempo_total,
                    'promedio_tableros_por_dia_total': promedio_tableros_por_dia_total,
                    'tableros_dia_estimado': tableros_dia_estimado,
                    'diferencia_vs_estimado': diferencia_vs_estimado
                }
            
            return metricas
            
        except Exception as e:
            logger.error(f"Error calculando métricas por tipo: {str(e)}")
            return {}
    
    def _calcular_metricas_por_area(self, ofs_data: List[Dict], area_filtro: str = None) -> Dict[str, Any]:
        """Calcula métricas agregadas por área"""
        try:
            metricas = {}
            
            # Obtener factores de tiempo estimados de configuración
            factores_tiempo = self._get_factores_tiempo_estimados()
            
            for area in ['fabrica', 'embalaje']:
                if area_filtro and area_filtro.lower() != area:
                    continue
                
                # Filtrar OFs que tienen datos para esta área
                ofs_area = [of for of in ofs_data if of['productividad'][f'tableros_por_dia_{area}'] > 0]
                
                if not ofs_area:
                    # Calcular tableros/día estimado para el área
                    tableros_dia_estimado = self._calcular_tableros_dia_estimado_area(area, factores_tiempo)
                    
                    metricas[area] = {
                        'total_ofs': 0,
                        'total_tableros': 0,
                        'promedio_tableros_por_dia': 0,
                        'tableros_dia_estimado': tableros_dia_estimado,
                        'diferencia_vs_estimado': 0
                    }
                    continue
                
                total_tableros = sum(of['cantidad_tableros'] for of in ofs_area)
                tiempos_dias = [of['tiempos_reales'][area]['dias'] for of in ofs_area if of['tiempos_reales'][area]['dias'] > 0]
                
                # Calcular tableros/día promedio correctamente: total tableros / promedio de días
                promedio_tiempo_dias = round(sum(tiempos_dias) / len(tiempos_dias), 2) if tiempos_dias else 0
                promedio_tableros_por_dia = round(total_tableros / promedio_tiempo_dias, 2) if promedio_tiempo_dias > 0 else 0
                
                # Calcular tableros/día estimado para el área
                tableros_dia_estimado = self._calcular_tableros_dia_estimado_area(area, factores_tiempo)
                
                # Calcular diferencia porcentual
                diferencia_vs_estimado = 0
                if tableros_dia_estimado > 0 and promedio_tableros_por_dia > 0:
                    diferencia_vs_estimado = round(((promedio_tableros_por_dia - tableros_dia_estimado) / tableros_dia_estimado) * 100, 1)
                
                metricas[area] = {
                    'total_ofs': len(ofs_area),
                    'total_tableros': total_tableros,
                    'promedio_tableros_por_dia': promedio_tableros_por_dia,
                    'tableros_dia_estimado': tableros_dia_estimado,
                    'diferencia_vs_estimado': diferencia_vs_estimado
                }
            
            return metricas
            
        except Exception as e:
            logger.error(f"Error calculando métricas por área: {str(e)}")
            return {}
    
    def _generar_datos_scatter(self, ofs_data: List[Dict], area_filtro: str = None, tipo_filtro: str = None) -> Dict[str, Any]:
        """Genera datos para gráficos de dispersión"""
        try:
            datos = {
                'tableros_vs_tiempo_por_tipo': {},
                'tableros_vs_ratio_por_area': {}
            }
            
            # Datos por tipo de proyecto (tableros vs tiempo total)
            tipos_a_procesar = [tipo_filtro] if tipo_filtro and tipo_filtro != 'TODAS' else ['SOCIAL', 'ESTANDAR', 'ESPECIAL']
            for tipo in tipos_a_procesar:
                ofs_tipo = [of for of in ofs_data if of['tipo_proyecto'] == tipo and of['tiempos_reales']['tiempo_total_dias'] > 0]
                datos['tableros_vs_tiempo_por_tipo'][tipo] = [
                    {
                        'x': of['cantidad_tableros'],
                        'y': round(of['tiempos_reales']['tiempo_total_dias'], 2),
                        'of_id': of['id'],
                        'codigo': of['codigo'],
                        'proyecto': of['proyecto_nombre']
                    }
                    for of in ofs_tipo
                ]
            
            # Datos por área (tableros vs ratio tableros/día)
            areas_a_procesar = [area_filtro] if area_filtro and area_filtro != 'todas' else ['fabrica', 'embalaje']
            for area in areas_a_procesar:
                ofs_area = [of for of in ofs_data if of['productividad'][f'tableros_por_dia_{area}'] > 0]
                datos['tableros_vs_ratio_por_area'][area] = [
                    {
                        'x': of['cantidad_tableros'],
                        'y': of['productividad'][f'tableros_por_dia_{area}'],
                        'of_id': of['id'],
                        'codigo': of['codigo'],
                        'proyecto': of['proyecto_nombre']
                    }
                    for of in ofs_area
                ]
            
            return datos
            
        except Exception as e:
            logger.error(f"Error generando datos scatter: {str(e)}")
            return {}
    
    def _calcular_analisis_estadistico(self, ofs_data: List[Dict], tipo_filtro: str = None) -> Dict[str, Any]:
        """Calcula análisis estadístico y regresiones"""
        try:
            import numpy as np
            from scipy import stats
            
            analisis = {}
            
            # Análisis por tipo de proyecto
            tipos_a_analizar = [tipo_filtro] if tipo_filtro and tipo_filtro != 'TODAS' else ['SOCIAL', 'ESTANDAR', 'ESPECIAL']
            for tipo in tipos_a_analizar:
                ofs_tipo = [of for of in ofs_data if of['tipo_proyecto'] == tipo and of['tiempos_reales']['tiempo_total_dias'] > 0]
                
                if len(ofs_tipo) < 3:  # Mínimo para análisis estadístico
                    analisis[tipo] = {'insuficientes_datos': True}
                    continue
                
                tableros = np.array([of['cantidad_tableros'] for of in ofs_tipo])
                tiempos = np.array([of['tiempos_reales']['tiempo_total_dias'] for of in ofs_tipo])
                
                # Regresión lineal
                slope, intercept, r_value, p_value, std_err = stats.linregress(tableros, tiempos)
                
                analisis[tipo] = {
                    'n_muestras': len(ofs_tipo),
                    'correlacion': round(r_value, 3),
                    'r_cuadrado': round(r_value**2, 3),
                    'p_valor': round(p_value, 4),
                    'pendiente': round(slope, 4),
                    'intercepto': round(intercept, 2),
                    'error_estandar': round(std_err, 4),
                    'ecuacion': f'T = {slope:.3f}×Tab + {intercept:.1f}',
                    'significativo': p_value < 0.05
                }
            
            # Análisis por área
            for area in ['fabrica', 'embalaje']:
                ofs_area = [of for of in ofs_data if of['productividad'][f'tableros_por_dia_{area}'] > 0]
                
                if len(ofs_area) < 3:
                    analisis[f'{area}_ratio'] = {'insuficientes_datos': True}
                    continue
                
                tableros = np.array([of['cantidad_tableros'] for of in ofs_area])
                ratios = np.array([of['productividad'][f'tableros_por_dia_{area}'] for of in ofs_area])
                
                slope, intercept, r_value, p_value, std_err = stats.linregress(tableros, ratios)
                
                analisis[f'{area}_ratio'] = {
                    'n_muestras': len(ofs_area),
                    'correlacion': round(r_value, 3),
                    'r_cuadrado': round(r_value**2, 3),
                    'p_valor': round(p_value, 4),
                    'pendiente': round(slope, 4),
                    'intercepto': round(intercept, 2),
                    'ecuacion': f'Ratio = {slope:.3f}×Tab + {intercept:.1f}',
                    'significativo': p_value < 0.05
                }
            
            return analisis
            
        except ImportError:
            logger.warning("scipy no disponible para análisis estadístico")
            return {'error': 'scipy_no_disponible'}
        except Exception as e:
            logger.error(f"Error en análisis estadístico: {str(e)}")
            return {'error': str(e)}
    
    def _get_factores_tiempo_estimados(self) -> Dict[str, float]:
        """Obtiene factores de tiempo estimados desde configuración"""
        try:
            # Obtener factores actualizados directamente desde el servicio de planificación
            factores_conversion = self.planificacion_service.get_factores_conversion()
            
            return {
                'factor_tiempo_fabrica_social': factores_conversion.get('SOCIAL', {}).get('factor_tiempo_fabrica', 0.02),
                'factor_tiempo_embalaje_social': factores_conversion.get('SOCIAL', {}).get('factor_tiempo_embalaje', 0.008),
                'factor_tiempo_fabrica_estandar': factores_conversion.get('ESTANDAR', {}).get('factor_tiempo_fabrica', 0.025),
                'factor_tiempo_embalaje_estandar': factores_conversion.get('ESTANDAR', {}).get('factor_tiempo_embalaje', 0.01),
                'factor_tiempo_fabrica_especial': factores_conversion.get('ESPECIAL', {}).get('factor_tiempo_fabrica', 0.05),
                'factor_tiempo_embalaje_especial': factores_conversion.get('ESPECIAL', {}).get('factor_tiempo_embalaje', 0.012)
            }
        except Exception as e:
            logger.error(f"Error obteniendo factores de tiempo: {str(e)}")
            # Valores por defecto si hay error
            return {
                'factor_tiempo_fabrica_social': 0.02,
                'factor_tiempo_embalaje_social': 0.008,
                'factor_tiempo_fabrica_estandar': 0.025,
                'factor_tiempo_embalaje_estandar': 0.01,
                'factor_tiempo_fabrica_especial': 0.05,
                'factor_tiempo_embalaje_especial': 0.012
            }

    def _calcular_tableros_dia_estimado_tipo(self, tipo_proyecto: str, factores_tiempo: Dict[str, float]) -> float:
        """Calcula tableros/día estimado total para un tipo de proyecto"""
        try:
            tipo_lower = tipo_proyecto.lower()
            
            # Obtener factores de tiempo por tipo (días por tablero)
            tiempo_fabrica_por_tablero = factores_tiempo.get(f'factor_tiempo_fabrica_{tipo_lower}', 0.02)
            tiempo_embalaje_por_tablero = factores_tiempo.get(f'factor_tiempo_embalaje_{tipo_lower}', 0.008)
            
            # Tiempo total por tablero
            tiempo_total_por_tablero = tiempo_fabrica_por_tablero + tiempo_embalaje_por_tablero
            
            # Tableros por día = 1 / (días por tablero)
            if tiempo_total_por_tablero > 0:
                tableros_por_dia = round(1 / tiempo_total_por_tablero, 2)
            else:
                tableros_por_dia = 0
                
            return tableros_por_dia
            
        except Exception as e:
            logger.error(f"Error calculando tableros/día estimado para tipo {tipo_proyecto}: {str(e)}")
            return 0

    def _calcular_tableros_dia_estimado_area(self, area: str, factores_tiempo: Dict[str, float]) -> float:
        """Calcula tableros/día estimado promedio para un área (promedio de todos los tipos)"""
        try:
            tableros_dia_por_tipo = []
            
            for tipo in ['social', 'estandar', 'especial']:
                factor_area = factores_tiempo.get(f'factor_tiempo_{area}_{tipo}', 0.02)
                if factor_area > 0:
                    tableros_dia_tipo = 1 / factor_area
                    tableros_dia_por_tipo.append(tableros_dia_tipo)
            
            # Promedio de tableros/día por área
            if tableros_dia_por_tipo:
                promedio_tableros_dia = round(sum(tableros_dia_por_tipo) / len(tableros_dia_por_tipo), 2)
            else:
                promedio_tableros_dia = 0
                
            return promedio_tableros_dia
            
        except Exception as e:
            logger.error(f"Error calculando tableros/día estimado para área {area}: {str(e)}")
            return 0

    def _identificar_outliers(self, ofs_data: List[Dict]) -> List[Dict]:
        """Identifica OFs con productividad atípica (outliers)"""
        try:
            import numpy as np
            
            outliers = []
            
            # Calcular outliers para tableros/día total
            ratios_totales = [of['productividad']['tableros_por_dia_total'] for of in ofs_data 
                            if of['productividad']['tableros_por_dia_total'] > 0]
            
            if len(ratios_totales) > 4:  # Mínimo para outliers
                ratios_array = np.array(ratios_totales)
                q1, q3 = np.percentile(ratios_array, [25, 75])
                iqr = q3 - q1
                limite_inferior = q1 - 1.5 * iqr
                limite_superior = q3 + 1.5 * iqr
                
                for of in ofs_data:
                    ratio = of['productividad']['tableros_por_dia_total']
                    if ratio > 0 and (ratio < limite_inferior or ratio > limite_superior):
                        outliers.append({
                            'of_id': of['id'],
                            'codigo': of['codigo'],
                            'proyecto': of['proyecto_nombre'],
                            'tipo_outlier': 'productividad_total',
                            'valor': ratio,
                            'limite_inferior': round(limite_inferior, 2),
                            'limite_superior': round(limite_superior, 2),
                            'es_outlier_alto': ratio > limite_superior
                        })
            
            return outliers
            
        except ImportError:
            return []
        except Exception as e:
            logger.error(f"Error identificando outliers: {str(e)}")
            return []