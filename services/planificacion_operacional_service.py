from typing import List, Dict, Any, Optional
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, or_, func, extract, case
from decimal import Decimal
import calendar
import json

from app import db
from models import (
    Proyecto, Cliente, User, OrdenFabricacion,
    EstadoComercial, RolUsuario
)
from services.configuraciones_service import ConfiguracionesService


class PlanificacionOperacionalService:
    """Service layer for operational planning operations"""

    # Default conversion factors by project type (Chilean Pesos)
    DEFAULT_FACTORS_BY_TYPE = {
        'SOCIAL': {
            'factor_m2': 5246,  # Calculated from 24000 / 4.575
            'factor_clp_tablero': 24000,  # $24,000 por tablero for social projects
            'factor_tiempo_fabrica': 0.02,  # 0.02 días por tablero
            'factor_tiempo_embalaje': 0.008  # 0.008 días por tablero
        },
        'ESTANDAR': {
            'factor_m2': 6557,  # Calculated from 30000 / 4.575
            'factor_clp_tablero': 30000,  # $30,000 por tablero for standard projects
            'factor_tiempo_fabrica': 0.025,  # 0.025 días por tablero
            'factor_tiempo_embalaje': 0.01  # 0.01 días por tablero
        },
        'ESPECIAL': {
            'factor_m2': 9836,  # Calculated from 45000 / 4.575
            'factor_clp_tablero': 45000,  # $45,000 por tablero for special projects
            'factor_tiempo_fabrica': 0.03,  # 0.03 días por tablero
            'factor_tiempo_embalaje': 0.012  # 0.012 días por tablero
        }
    }
    
    # Standard board dimensions (meters)
    AREA_TABLERO_ESTANDAR = 4.575  # Standard board area in m²
    FACTOR_DESPERDICIO = 1.1  # Waste factor
    
    # Time factors - now loaded from configuration
    def _get_factores_tiempo(self):
        """Get time factors from configuration service"""
        try:
            config_service = ConfiguracionesService()
            return config_service.get_factores_tiempo()
        except Exception as e:
            # Fallback to default values if configuration service fails
            return {
                'factor_tiempo_fabrica': 0.025,  # 0.025 días por tablero en fábrica
                'factor_tiempo_embalaje': 0.01   # 0.01 días por tablero en embalaje
            }

    def calcular_tiempo_estimado_fabrica(self, cantidad_tableros: int, tipo_proyecto: str = 'ESTANDAR') -> float:
        """Calcula tiempo estimado en fábrica basado en cantidad de tableros y tipo de proyecto"""
        if not cantidad_tableros or cantidad_tableros <= 0:
            return 0.0
        factor_data = self.DEFAULT_FACTORS_BY_TYPE.get(tipo_proyecto, self.DEFAULT_FACTORS_BY_TYPE['ESTANDAR'])
        return cantidad_tableros * factor_data['factor_tiempo_fabrica']
    
    def calcular_tiempo_estimado_embalaje(self, cantidad_tableros: int, tipo_proyecto: str = 'ESTANDAR') -> float:
        """Calcula tiempo estimado en embalaje basado en cantidad de tableros y tipo de proyecto"""
        if not cantidad_tableros or cantidad_tableros <= 0:
            return 0.0
        factor_data = self.DEFAULT_FACTORS_BY_TYPE.get(tipo_proyecto, self.DEFAULT_FACTORS_BY_TYPE['ESTANDAR'])
        return cantidad_tableros * factor_data['factor_tiempo_embalaje']

    def get_matriz_operacional(self, año, mes_inicio=1, mes_fin=12, cliente_id=None, tipo_material='melamina'):
        """Get operational planning matrix with board calculations"""
        
        # Get projects in the specified period
        proyectos = self._get_proyectos_periodo(año, mes_inicio, mes_fin, cliente_id)
        
        # Build monthly matrix with board calculations
        matriz = self._construir_matriz_operacional(proyectos, año, mes_inicio, mes_fin, tipo_material)
        
        # Calculate monthly totals
        totales_mes = self._calcular_totales_operacionales(matriz)
        
        # Get clients for filtering
        clientes = db.session.query(Cliente).filter_by(activo=True).order_by(Cliente.nombre).all()
        
        # Get conversion factor info (now using ESTANDAR as default)
        factor_info = self._get_factor_info('ESTANDAR')
        
        return {
            'año': año,
            'mes_inicio': mes_inicio,
            'mes_fin': mes_fin,
            'tipo_material': tipo_material,
            'matriz': matriz,
            'totales_mes': totales_mes,
            'proyectos': proyectos,
            'clientes': clientes,
            'factor_info': factor_info,
            'tipos_proyecto': list(self.DEFAULT_FACTORS_BY_TYPE.keys()),
            'filtros': {
                'cliente_id': cliente_id,
                'tipo_material': tipo_material
            }
        }

    def get_detalle_proyecto_operacional(self, proyecto_id):
        """Get operational details for a specific project"""
        proyecto = (db.session.query(Proyecto)
                   .join(Cliente)
                   .filter(Proyecto.id == proyecto_id)
                   .first())
        
        if not proyecto:
            return None
        
        # Calculate boards for different materials
        tableros_por_material = {}
        
        if proyecto.monto_provision_presupuestado:
            # Get project type, default to ESTANDAR
            tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
            
            resultado = self.calcular_tableros_aproximados(
                monto_provision=float(proyecto.monto_provision_presupuestado),
                tipo_proyecto=tipo_proyecto,
                margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
            )
            tableros_por_material['melamina'] = resultado
        
        # Get manufacturing orders
        ordenes_fabricacion = (db.session.query(OrdenFabricacion)
                             .filter_by(proyecto_id=proyecto_id)
                             .order_by(OrdenFabricacion.codigo)
                             .all())
        
        # Get project type for factor info
        tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
        
        return {
            'proyecto': proyecto,
            'tableros_por_material': tableros_por_material,
            'ordenes_fabricacion': ordenes_fabricacion,
            'factor_info': {'melamina': self._get_factor_info(tipo_proyecto)},
            'tipo_proyecto': tipo_proyecto
        }

    def get_analisis_capacidad(self, año=2025, vista='mensual'):
        """Get production capacity analysis including productivity data"""
        
        # Get projects with commercial states: ADJUDICADO, EN_DESARROLLO, TERMINADO
        proyectos_activos = (db.session.query(Proyecto)
                            .filter(Proyecto.estado_comercial.in_([
                                EstadoComercial.ADJUDICADO,
                                EstadoComercial.EN_DESARROLLO, 
                                EstadoComercial.TERMINADO
                            ]))
                            .filter(or_(
                                extract('year', Proyecto.fecha_inicio) == año,
                                extract('year', Proyecto.fecha_fin_estimada) == año
                            ))
                            .all())
        
        if vista == 'mensual':
            capacidad = self._calcular_capacidad_mensual(proyectos_activos, año)
        else:
            capacidad = self._calcular_capacidad_semanal(proyectos_activos, año)
        
        # Get productivity data (only for monthly view)
        analisis_mensual = {}
        total_fabricados = 0
        total_embalados = 0
        rendimiento_promedio_fabrica = 0
        rendimiento_promedio_embalaje = 0
        
        if vista == 'mensual':
            # Get productivity data
            productividad_fabrica = self.get_productividad_fabrica(año, 'mensual')
            productividad_embalaje = self.get_productividad_embalaje(año, 'mensual')
            
            # Calculate productivity totals
            total_fabricados = sum(data['tableros_completados'] for data in productividad_fabrica.values())
            total_embalados = sum(data['tableros_completados'] for data in productividad_embalaje.values())
            
            # Merge capacity and productivity data by month
            for mes in range(1, 13):
                analisis_mensual[mes] = {
                    'mes': mes,
                    'mes_nombre': calendar.month_name[mes],
                    # Capacity data
                    'tableros_estimados': capacidad.get(mes, {}).get('tableros_requeridos', 0),
                    'horas_estimadas': capacidad.get(mes, {}).get('horas_estimadas', 0),
                    'capacidad_porcentaje': capacidad.get(mes, {}).get('capacidad_porcentaje', 0),
                    # Productivity data
                    'tableros_fabricados': productividad_fabrica.get(mes, {}).get('tableros_completados', 0),
                    'tableros_embalados': productividad_embalaje.get(mes, {}).get('tableros_completados', 0),
                    # Performance indicators
                    'rendimiento_fabrica': 0,  # Will calculate below
                    'rendimiento_embalaje': 0,  # Will calculate below
                }
                
                # Calculate performance ratios
                estimados = analisis_mensual[mes]['tableros_estimados']
                if estimados > 0:
                    analisis_mensual[mes]['rendimiento_fabrica'] = round(
                        (analisis_mensual[mes]['tableros_fabricados'] / estimados) * 100, 1
                    )
                    analisis_mensual[mes]['rendimiento_embalaje'] = round(
                        (analisis_mensual[mes]['tableros_embalados'] / estimados) * 100, 1
                    )
            
            # Calculate average performance
            rendimiento_promedio_fabrica = round(sum(data['rendimiento_fabrica'] for data in analisis_mensual.values()) / 12, 1)
            rendimiento_promedio_embalaje = round(sum(data['rendimiento_embalaje'] for data in analisis_mensual.values()) / 12, 1)
        
        # Calculate summary statistics
        total_tableros = sum(data['tableros_requeridos'] for data in capacidad.values())
        total_horas = sum(data['horas_estimadas'] for data in capacidad.values())
        promedio_capacidad = sum(data['capacidad_porcentaje'] for data in capacidad.values()) / len(capacidad) if capacidad else 0
        
        return {
            # Original capacity analysis data
            'año': año,
            'vista': vista,
            'capacidad': capacidad,
            'proyectos_activos': proyectos_activos,
            'resumen': self._calcular_resumen_capacidad(capacidad),
            # Enhanced summary with productivity
            'total_tableros_año': total_tableros,
            'total_horas_año': total_horas,
            'promedio_capacidad_porcentaje': promedio_capacidad,
            'meses_sobrecargados': len([data for data in capacidad.values() if data['capacidad_porcentaje'] > 100]),
            # New productivity metrics
            'total_fabricados_año': total_fabricados,
            'total_embalados_año': total_embalados,
            'rendimiento_promedio_fabrica': rendimiento_promedio_fabrica,
            'rendimiento_promedio_embalaje': rendimiento_promedio_embalaje,
            'analisis_mensual': analisis_mensual
        }

    def calcular_tableros_aproximados(self, monto_provision, tipo_proyecto='ESTANDAR', margen_venta_provision=None):
        """Calculate approximate boards needed based on provision amount using new formula:
        Monto_provision * (1-margen_vta_provision) / factor_(CLP/tablero)
        Only uses Melamina, with factors based on project type.
        """
        
        # Get conversion factor based on project type
        factor_data = self.DEFAULT_FACTORS_BY_TYPE.get(tipo_proyecto, self.DEFAULT_FACTORS_BY_TYPE['ESTANDAR'])
        factor_m2 = factor_data['factor_m2']
        factor_clp_por_tablero = factor_data['factor_clp_tablero']
        
        # Apply new formula if margin is provided
        if margen_venta_provision is not None:
            # New formula: Monto_provision * (1-margen_vta_provision) / factor_(CLP/tablero)
            margen_decimal = Decimal(str(margen_venta_provision)) / 100  # Convert percentage to decimal
            monto_neto = Decimal(str(monto_provision)) * (1 - margen_decimal)
            
            # Calculate boards directly using CLP per board
            tableros_sin_desperdicio = monto_neto / Decimal(str(factor_clp_por_tablero))
            
            # Apply waste factor
            tableros_aproximados = tableros_sin_desperdicio * Decimal(str(self.FACTOR_DESPERDICIO))
            
            # Calculate derived values for compatibility
            area_total_m2 = tableros_sin_desperdicio * Decimal(str(self.AREA_TABLERO_ESTANDAR))
            area_con_desperdicio = area_total_m2 * Decimal(str(self.FACTOR_DESPERDICIO))
        else:
            # Legacy formula: monto_provision / factor_m2 
            area_total_m2 = Decimal(str(monto_provision)) / Decimal(str(factor_m2))
            
            # Apply waste factor
            area_con_desperdicio = area_total_m2 * Decimal(str(self.FACTOR_DESPERDICIO))
            
            # Calculate boards needed
            tableros_aproximados = area_con_desperdicio / Decimal(str(self.AREA_TABLERO_ESTANDAR))
        
        # Round up to whole boards
        tableros_enteros = int(tableros_aproximados.to_integral_value())
        if tableros_aproximados > tableros_enteros:
            tableros_enteros += 1
        
        return {
            'tableros_aproximados': tableros_enteros,
            'tableros_exactos': float(tableros_aproximados),
            'area_total_m2': float(area_total_m2),
            'area_con_desperdicio': float(area_con_desperdicio),
            'factor_usado': factor_m2,
            'factor_clp_por_tablero': factor_clp_por_tablero,
            'tipo_proyecto': tipo_proyecto,
            'formula_usada': 'nueva' if margen_venta_provision is not None else 'legacy',
            'detalles': {
                'monto_provision': monto_provision,
                'margen_venta_provision': margen_venta_provision,
                'tipo_proyecto': tipo_proyecto,
                'factor_m2': factor_m2,
                'factor_clp_por_tablero': factor_clp_por_tablero,
                'area_tablero': self.AREA_TABLERO_ESTANDAR,
                'factor_desperdicio': self.FACTOR_DESPERDICIO
            }
        }

    def get_factores_conversion(self):
        """Get current conversion factors including time and capacity settings"""
        # In the future, these could be stored in database
        # For now, return default factors with current configuration
        factores = {}
        
        for tipo_proyecto, data in self.DEFAULT_FACTORS_BY_TYPE.items():
            factores[tipo_proyecto] = {
                'factor_m2': data['factor_m2'],
                'factor_clp_tablero': data['factor_clp_tablero'],
                'factor_tiempo_fabrica': data['factor_tiempo_fabrica'],
                'factor_tiempo_embalaje': data['factor_tiempo_embalaje'],
                'descripcion': self._get_descripcion_tipo_proyecto(tipo_proyecto)
            }
        
        # Get capacity configuration
        try:
            from services.configuraciones_service import ConfiguracionesService
            config_service = ConfiguracionesService()
            capacidad_config = config_service.get_configuracion_capacidad()
        except:
            capacidad_config = {
                'capacidad_maxima_tableros_mes': 500,
                'capacidad_maxima_tableros_semana': 125,
                'horas_disponibles_mes': 160,
                'horas_disponibles_semana': 40,
                'horas_por_tablero_social': 0.6,
                'horas_por_tablero_estandar': 0.5,
                'horas_por_tablero_especial': 0.4,
            }
        
        # Add configuration section
        factores['configuracion'] = {
            'area_tablero_estandar': self.AREA_TABLERO_ESTANDAR,
            'factor_desperdicio': self.FACTOR_DESPERDICIO,
            **capacidad_config
        }
        
        return factores
    
    def _get_descripcion_tipo_proyecto(self, tipo_proyecto):
        """Get description for project type"""
        descripciones = {
            'SOCIAL': 'Proyectos de vivienda social con especificaciones básicas',
            'ESTANDAR': 'Proyectos comerciales estándar con especificaciones medias',
            'ESPECIAL': 'Proyectos premium con especificaciones altas y acabados especiales'
        }
        return descripciones.get(tipo_proyecto, 'Descripción no disponible')
        
        factores['configuracion'] = {
            'area_tablero_estandar': self.AREA_TABLERO_ESTANDAR,
            'factor_desperdicio': self.FACTOR_DESPERDICIO,
            'factor_tiempo_fabrica': factores_tiempo['factor_tiempo_fabrica'],
            'factor_tiempo_embalaje': factores_tiempo['factor_tiempo_embalaje'],
            # Add capacity configuration
            **capacidad_config
        }
        
        return factores

    def actualizar_factores_conversion(self, factores_data, user_id):
        """Update conversion factors including time and capacity settings"""
        try:
            updated_factors = []
            
            # Update tablero factors by project type
            if factores_data.get('factor_social_tablero') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['SOCIAL']['factor_clp_tablero'] = factores_data['factor_social_tablero']
                updated_factors.append(f"Social CLP/tablero: {factores_data['factor_social_tablero']:,}")
                
            if factores_data.get('factor_estandar_tablero') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['ESTANDAR']['factor_clp_tablero'] = factores_data['factor_estandar_tablero']
                updated_factors.append(f"Estándar CLP/tablero: {factores_data['factor_estandar_tablero']:,}")
                
            if factores_data.get('factor_especial_tablero') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['ESPECIAL']['factor_clp_tablero'] = factores_data['factor_especial_tablero']
                updated_factors.append(f"Especial CLP/tablero: {factores_data['factor_especial_tablero']:,}")
            
            # Update time factors by project type
            if factores_data.get('factor_tiempo_fabrica_social') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['SOCIAL']['factor_tiempo_fabrica'] = factores_data['factor_tiempo_fabrica_social']
                updated_factors.append(f"Social tiempo fábrica: {factores_data['factor_tiempo_fabrica_social']}")
                
            if factores_data.get('factor_tiempo_embalaje_social') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['SOCIAL']['factor_tiempo_embalaje'] = factores_data['factor_tiempo_embalaje_social']
                updated_factors.append(f"Social tiempo embalaje: {factores_data['factor_tiempo_embalaje_social']}")
                
            if factores_data.get('factor_tiempo_fabrica_estandar') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['ESTANDAR']['factor_tiempo_fabrica'] = factores_data['factor_tiempo_fabrica_estandar']
                updated_factors.append(f"Estándar tiempo fábrica: {factores_data['factor_tiempo_fabrica_estandar']}")
                
            if factores_data.get('factor_tiempo_embalaje_estandar') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['ESTANDAR']['factor_tiempo_embalaje'] = factores_data['factor_tiempo_embalaje_estandar']
                updated_factors.append(f"Estándar tiempo embalaje: {factores_data['factor_tiempo_embalaje_estandar']}")
                
            if factores_data.get('factor_tiempo_fabrica_especial') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['ESPECIAL']['factor_tiempo_fabrica'] = factores_data['factor_tiempo_fabrica_especial']
                updated_factors.append(f"Especial tiempo fábrica: {factores_data['factor_tiempo_fabrica_especial']}")
                
            if factores_data.get('factor_tiempo_embalaje_especial') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['ESPECIAL']['factor_tiempo_embalaje'] = factores_data['factor_tiempo_embalaje_especial']
                updated_factors.append(f"Especial tiempo embalaje: {factores_data['factor_tiempo_embalaje_especial']}")
            
            # Update general configuration constants if provided
            if factores_data.get('area_tablero_estandar') is not None:
                self.AREA_TABLERO_ESTANDAR = factores_data['area_tablero_estandar']
                updated_factors.append(f"Área tablero estándar: {factores_data['area_tablero_estandar']}")
                
            if factores_data.get('factor_desperdicio') is not None:
                self.FACTOR_DESPERDICIO = factores_data['factor_desperdicio']
                updated_factors.append(f"Factor desperdicio: {factores_data['factor_desperdicio']}")
            
            # Update capacity configuration if provided
            capacity_fields = [
                'capacidad_maxima_tableros_mes', 'capacidad_maxima_tableros_semana',
                'horas_disponibles_mes', 'horas_disponibles_semana',
                'horas_por_tablero_social', 'horas_por_tablero_estandar', 'horas_por_tablero_especial'
            ]
            
            capacity_data = {}
            for field in capacity_fields:
                if factores_data.get(field) is not None:
                    capacity_data[field] = factores_data[field]
                    updated_factors.append(f"{field}: {factores_data[field]}")
            
            # Update capacity configuration using configuration service
            if capacity_data:
                try:
                    from services.configuraciones_service import ConfiguracionesService
                    config_service = ConfiguracionesService()
                    config_service.actualizar_configuracion_capacidad(capacity_data, user_id)
                except Exception as e:
                    print(f"Error updating capacity configuration: {e}")
            
            # Log all updates
            if updated_factors:
                print(f"Usuario {user_id} actualizó factores: {', '.join(updated_factors)}")
                return True
            else:
                print(f"Usuario {user_id} no proporcionó factores válidos para actualizar")
                return False
                
        except Exception as e:
            print(f"Error updating conversion factors: {e}")
            return Falsefactor_tiempo_fabrica_social']
                updated_factors.append(f"Social tiempo fábrica: {factores_data['factor_tiempo_fabrica_social']}")
                
            if factores_data.get('factor_tiempo_embalaje_social') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['SOCIAL']['factor_tiempo_embalaje'] = factores_data['factor_tiempo_embalaje_social']
                updated_factors.append(f"Social tiempo embalaje: {factores_data['factor_tiempo_embalaje_social']}")
                
            if factores_data.get('factor_tiempo_fabrica_estandar') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['ESTANDAR']['factor_tiempo_fabrica'] = factores_data['factor_tiempo_fabrica_estandar']
                updated_factors.append(f"Estándar tiempo fábrica: {factores_data['factor_tiempo_fabrica_estandar']}")
                
            if factores_data.get('factor_tiempo_embalaje_estandar') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['ESTANDAR']['factor_tiempo_embalaje'] = factores_data['factor_tiempo_embalaje_estandar']
                updated_factors.append(f"Estándar tiempo embalaje: {factores_data['factor_tiempo_embalaje_estandar']}")
                
            if factores_data.get('factor_tiempo_fabrica_especial') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['ESPECIAL']['factor_tiempo_fabrica'] = factores_data['factor_tiempo_fabrica_especial']
                updated_factors.append(f"Especial tiempo fábrica: {factores_data['factor_tiempo_fabrica_especial']}")
                
            if factores_data.get('factor_tiempo_embalaje_especial') is not None:
                self.DEFAULT_FACTORS_BY_TYPE['ESPECIAL']['factor_tiempo_embalaje'] = factores_data['factor_tiempo_embalaje_especial']
                updated_factors.append(f"Especial tiempo embalaje: {factores_data['factor_tiempo_embalaje_especial']}")
            
            # Update general configuration constants if provided
            if factores_data.get('area_tablero_estandar') is not None:
                self.AREA_TABLERO_ESTANDAR = factores_data['area_tablero_estandar']
                updated_factors.append(f"Área tablero estándar: {factores_data['area_tablero_estandar']}")
                
            if factores_data.get('factor_desperdicio') is not None:
                self.FACTOR_DESPERDICIO = factores_data['factor_desperdicio']
                updated_factors.append(f"Factor desperdicio: {factores_data['factor_desperdicio']}")
            
            # Update capacity configuration if provided
            capacity_fields = [
                'capacidad_maxima_tableros_mes', 'capacidad_maxima_tableros_semana',
                'horas_disponibles_mes', 'horas_disponibles_semana',
                'horas_por_tablero_social', 'horas_por_tablero_estandar', 'horas_por_tablero_especial'
            ]
            
            capacity_data = {}
            for field in capacity_fields:
                if factores_data.get(field) is not None:
                    capacity_data[field] = factores_data[field]
                    updated_factors.append(f"{field}: {factores_data[field]}")
            
            # Update capacity configuration using configuration service
            if capacity_data:
                try:
                    from services.configuraciones_service import ConfiguracionesService
                    config_service = ConfiguracionesService()
                    config_service.actualizar_configuracion_capacidad(capacity_data, user_id)
                except Exception as e:
                    print(f"Error updating capacity configuration: {e}")
            
            # Log all updates
            if updated_factors:
                print(f"Usuario {user_id} actualizó factores: {', '.join(updated_factors)}")
                return True
            else:
                print(f"Usuario {user_id} no proporcionó factores válidos para actualizar")
                return False
                
        except Exception as e:
            print(f"Error updating factors: {e}")
            return False

    # Private helper methods
    
    def _get_proyectos_periodo(self, año, mes_inicio, mes_fin, cliente_id=None):
        """Get projects for the specified period"""
        fecha_inicio = date(año, mes_inicio, 1)
        ultimo_dia = calendar.monthrange(año, mes_fin)[1]
        fecha_fin = date(año, mes_fin, ultimo_dia)
        
        query = db.session.query(Proyecto).join(Cliente)
        
        # Filter by date range
        query = query.filter(
            or_(
                and_(Proyecto.fecha_inicio.isnot(None), 
                     Proyecto.fecha_inicio <= fecha_fin,
                     or_(Proyecto.fecha_fin_estimada.is_(None),
                         Proyecto.fecha_fin_estimada >= fecha_inicio)),
                and_(Proyecto.fecha_fin_estimada.isnot(None), 
                     Proyecto.fecha_fin_estimada >= fecha_inicio,
                     Proyecto.fecha_fin_estimada <= fecha_fin)
            )
        )
        
        # Filter by commercial states that have provision amounts
        query = query.filter(Proyecto.estado_comercial.in_([
            EstadoComercial.PRESUPUESTADO,
            EstadoComercial.ADJUDICADO,
            EstadoComercial.TERMINADO
        ]))
        
        # Filter by provision amount (must have one)
        query = query.filter(Proyecto.monto_provision_presupuestado.isnot(None))
        
        # Apply client filter
        if cliente_id:
            query = query.filter(Proyecto.cliente_id == cliente_id)
        
        return query.all()

    def _construir_matriz_operacional(self, proyectos, año, mes_inicio, mes_fin, tipo_material):
        """Build operational matrix with board calculations"""
        matriz = {}
        
        for mes in range(mes_inicio, mes_fin + 1):
            matriz[mes] = {
                'mes': mes,
                'mes_nombre': calendar.month_name[mes],
                'proyectos': [],
                'total_monto': Decimal('0'),
                'total_tableros': 0,
                'total_area_m2': Decimal('0')
            }
        
        for proyecto in proyectos:
            # Determine which months this project affects
            meses_proyecto = self._obtener_meses_proyecto(proyecto, año, mes_inicio, mes_fin)
            
            for mes in meses_proyecto:
                if mes in matriz:
                    # Calculate prorated values
                    meses_duracion = len(meses_proyecto)
                    
                    monto_mes = Decimal('0')
                    if proyecto.monto_provision_presupuestado:
                        monto_mes = proyecto.monto_provision_presupuestado / meses_duracion
                    
                    # Calculate boards for this month
                    # Get project type, default to ESTANDAR
                    tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                    
                    tableros_resultado = self.calcular_tableros_aproximados(
                        monto_provision=float(monto_mes),
                        tipo_proyecto=tipo_proyecto,
                        margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                    )
                    
                    proyecto_mes = {
                        'proyecto': proyecto,
                        'monto_mes': monto_mes,
                        'tableros_mes': tableros_resultado['tableros_aproximados'],
                        'area_m2_mes': Decimal(str(tableros_resultado['area_total_m2'])),
                        'meses_duracion': meses_duracion,
                        'detalles_calculo': tableros_resultado['detalles']
                    }
                    
                    matriz[mes]['proyectos'].append(proyecto_mes)
                    matriz[mes]['total_monto'] += monto_mes
                    matriz[mes]['total_tableros'] += tableros_resultado['tableros_aproximados']
                    matriz[mes]['total_area_m2'] += Decimal(str(tableros_resultado['area_total_m2']))
        
        return matriz

    def _obtener_meses_proyecto(self, proyecto, año, mes_inicio=1, mes_fin=12):
        """Get months affected by a project in the given year and range"""
        if not proyecto.fecha_inicio or not proyecto.fecha_fin_estimada:
            # If no dates, assume current month within range
            mes_actual = datetime.now().month
            if mes_inicio <= mes_actual <= mes_fin and datetime.now().year == año:
                return [mes_actual]
            else:
                return [mes_inicio]  # Default to first month of range
        
        inicio = max(proyecto.fecha_inicio, date(año, mes_inicio, 1))
        ultimo_dia = calendar.monthrange(año, mes_fin)[1]
        fin = min(proyecto.fecha_fin_estimada, date(año, mes_fin, ultimo_dia))
        
        if inicio > date(año, mes_fin, ultimo_dia) or fin < date(año, mes_inicio, 1):
            return []
        
        meses = []
        fecha_actual = date(inicio.year, inicio.month, 1)
        fecha_limite = date(fin.year, fin.month, 1)
        
        while fecha_actual <= fecha_limite:
            if fecha_actual.year == año and mes_inicio <= fecha_actual.month <= mes_fin:
                meses.append(fecha_actual.month)
            fecha_actual += relativedelta(months=1)
        
        return meses

    def _calcular_totales_operacionales(self, matriz):
        """Calculate operational totals from matrix"""
        totales = {}
        
        for mes, data in matriz.items():
            totales[mes] = {
                'total_monto': data['total_monto'],
                'total_tableros': data['total_tableros'],
                'total_area_m2': data['total_area_m2'],
                'proyectos_count': len(data['proyectos']),
                'promedio_tableros_por_proyecto': data['total_tableros'] / len(data['proyectos']) if data['proyectos'] else 0
            }
        
        return totales

    def _get_factor_info(self, tipo_proyecto):
        """Get factor information for a project type"""
        factor_data = self.DEFAULT_FACTORS_BY_TYPE.get(tipo_proyecto, self.DEFAULT_FACTORS_BY_TYPE['ESTANDAR'])
        
        return {
            'tipo_proyecto': tipo_proyecto,
            'factor_m2': factor_data['factor_m2'],
            'factor_clp_tablero': factor_data['factor_clp_tablero'],
            'area_tablero': self.AREA_TABLERO_ESTANDAR,
            'factor_desperdicio': self.FACTOR_DESPERDICIO,
            'factor_tiempo_fabrica': factor_data['factor_tiempo_fabrica'],
            'factor_tiempo_embalaje': factor_data['factor_tiempo_embalaje'],
            'ejemplo_calculo': f"Ejemplo: $1,000,000 ÷ ${factor_data['factor_clp_tablero']:,}/tablero = {1000000/factor_data['factor_clp_tablero']:.1f} tableros × {self.FACTOR_DESPERDICIO} = {int((1000000/factor_data['factor_clp_tablero']) * self.FACTOR_DESPERDICIO)} tableros"
        }

    def _calcular_capacidad_mensual(self, proyectos, año):
        """Calculate monthly capacity analysis"""
        capacidad = {}
        
        for mes in range(1, 13):
            capacidad[mes] = {
                'mes': mes,
                'mes_nombre': calendar.month_name[mes],
                'proyectos_activos': 0,
                'tableros_requeridos': 0,
                'horas_estimadas': 0,
                'capacidad_porcentaje': 0
            }
        
        # Get capacity limits from configuration
        try:
            from services.configuraciones_service import ConfiguracionesService
            config_service = ConfiguracionesService()
            capacidad_config = config_service.get_configuracion_capacidad()
            
            TABLEROS_MAXIMOS_MES = capacidad_config['capacidad_maxima_tableros_mes']
            HORAS_DISPONIBLES_MES = capacidad_config['horas_disponibles_mes']
            HORAS_POR_TABLERO_SOCIAL = capacidad_config['horas_por_tablero_social']
            HORAS_POR_TABLERO_ESTANDAR = capacidad_config['horas_por_tablero_estandar']
            HORAS_POR_TABLERO_ESPECIAL = capacidad_config['horas_por_tablero_especial']
        except:
            # Fallback to default values
            TABLEROS_MAXIMOS_MES = 500
            HORAS_DISPONIBLES_MES = 160
            HORAS_POR_TABLERO_SOCIAL = 0.6
            HORAS_POR_TABLERO_ESTANDAR = 0.5
            HORAS_POR_TABLERO_ESPECIAL = 0.4
        
        for proyecto in proyectos:
            meses_proyecto = self._obtener_meses_proyecto(proyecto, año)
            
            for mes in meses_proyecto:
                if mes in capacidad:
                    capacidad[mes]['proyectos_activos'] += 1
                    
                    # Calculate boards for this project in this month using new formula
                    if proyecto.monto_provision_presupuestado:
                        # Get project type, default to ESTANDAR
                        tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                        
                        tableros_resultado = self.calcular_tableros_aproximados(
                            monto_provision=float(proyecto.monto_provision_presupuestado) / len(meses_proyecto),
                            tipo_proyecto=tipo_proyecto,
                            margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                        )
                        
                        tableros_mes = tableros_resultado['tableros_aproximados']
                        capacidad[mes]['tableros_requeridos'] += tableros_mes
                        
                        # Use project-specific hours per board
                        if tipo_proyecto == 'SOCIAL':
                            horas_tablero = HORAS_POR_TABLERO_SOCIAL
                        elif tipo_proyecto == 'ESPECIAL':
                            horas_tablero = HORAS_POR_TABLERO_ESPECIAL
                        else:  # ESTANDAR or default
                            horas_tablero = HORAS_POR_TABLERO_ESTANDAR
                        
                        capacidad[mes]['horas_estimadas'] += tableros_mes * horas_tablero
        
        # Calculate capacity percentage
        for mes in capacidad:
            capacidad[mes]['capacidad_porcentaje'] = min(
                (capacidad[mes]['tableros_requeridos'] / TABLEROS_MAXIMOS_MES) * 100,
                100
            )
        
        return capacidad

    def _calcular_capacidad_semanal(self, proyectos, año):
        """Calculate weekly capacity analysis (simplified)"""
        # For now, return monthly capacity divided by weeks
        capacidad_mensual = self._calcular_capacidad_mensual(proyectos, año)
        
        capacidad_semanal = {}
        for mes, data in capacidad_mensual.items():
            semanas_mes = 4  # Simplified
            for semana in range(1, semanas_mes + 1):
                clave_semana = f"{mes}_{semana}"
                capacidad_semanal[clave_semana] = {
                    'mes': mes,
                    'semana': semana,
                    'tableros_requeridos': data['tableros_requeridos'] // semanas_mes,
                    'horas_estimadas': data['horas_estimadas'] // semanas_mes,
                    'capacidad_porcentaje': data['capacidad_porcentaje']
                }
        
        return capacidad_semanal

    def _calcular_resumen_capacidad(self, capacidad):
        """Calculate capacity summary"""
        if not capacidad:
            return {}
        
        total_tableros = sum(data['tableros_requeridos'] for data in capacidad.values())
        total_horas = sum(data['horas_estimadas'] for data in capacidad.values())
        promedio_capacidad = sum(data['capacidad_porcentaje'] for data in capacidad.values()) / len(capacidad)
        
        return {
            'total_tableros_año': total_tableros,
            'total_horas_año': total_horas,
            'promedio_capacidad_porcentaje': promedio_capacidad,
            'meses_sobrecargados': len([data for data in capacidad.values() if data['capacidad_porcentaje'] > 100])
        }


    # New productivity methods
    def get_productividad_fabrica(self, año, vista='mensual'):
        """Get factory productivity data - boards completed to FABRICACION_COMPLETA"""
        from sqlalchemy import func, extract
        from models import OrdenFabricacion, Proyecto, OrdenAreaProgreso, AreaEstado
        
        # Query to get actual completed boards using area progress system
        if vista == 'mensual':
            query = (db.session.query(
                extract('month', OrdenAreaProgreso.fecha_cambio_estado).label('periodo'),
                func.sum(OrdenFabricacion.cantidad_tableros).label('tableros_completados')
            )
            .join(OrdenFabricacion, OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id)
            .join(AreaEstado, OrdenAreaProgreso.estado_id == AreaEstado.id)
            .join(Proyecto, OrdenFabricacion.proyecto_id == Proyecto.id)
            .filter(
                extract('year', OrdenAreaProgreso.fecha_cambio_estado) == año,
                AreaEstado.codigo == 'fabricacion_completa',
                OrdenFabricacion.cantidad_tableros.isnot(None)
            )
            .group_by(extract('month', OrdenAreaProgreso.fecha_cambio_estado))
            .order_by(extract('month', OrdenAreaProgreso.fecha_cambio_estado))
            )
        else:  # semanal
            query = (db.session.query(
                extract('week', OrdenAreaProgreso.fecha_cambio_estado).label('periodo'),
                extract('month', OrdenAreaProgreso.fecha_cambio_estado).label('mes'),
                func.sum(OrdenFabricacion.cantidad_tableros).label('tableros_completados')
            )
            .join(OrdenFabricacion, OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id)
            .join(AreaEstado, OrdenAreaProgreso.estado_id == AreaEstado.id)
            .join(Proyecto, OrdenFabricacion.proyecto_id == Proyecto.id)
            .filter(
                extract('year', OrdenAreaProgreso.fecha_cambio_estado) == año,
                AreaEstado.codigo == 'fabricacion_completa',
                OrdenFabricacion.cantidad_tableros.isnot(None)
            )
            .group_by(extract('week', OrdenAreaProgreso.fecha_cambio_estado), extract('month', OrdenAreaProgreso.fecha_cambio_estado))
            .order_by(extract('month', OrdenAreaProgreso.fecha_cambio_estado), extract('week', OrdenAreaProgreso.fecha_cambio_estado))
            )

        try:
            resultados = query.all()
        except Exception as e:
            print(f"Error querying factory productivity: {e}")
            resultados = []

        # Process results
        productividad = {}
        if vista == 'mensual':
            for mes in range(1, 13):
                productividad[mes] = {
                    'periodo': mes,
                    'periodo_nombre': calendar.month_name[mes],
                    'tableros_completados': 0
                }
            
            for resultado in resultados:
                mes = int(resultado.periodo)
                if mes in productividad:
                    productividad[mes]['tableros_completados'] = int(resultado.tableros_completados or 0)
        else:
            # Para vista semanal, agrupar por mes y semana
            for resultado in resultados:
                semana = int(resultado.periodo)
                mes = int(resultado.mes) if hasattr(resultado, 'mes') else 1
                clave = f"{mes}_{semana}"
                productividad[clave] = {
                    'periodo': semana,
                    'mes': mes,
                    'periodo_nombre': f"Sem {semana} - {calendar.month_name[mes][:3]}",
                    'tableros_completados': int(resultado.tableros_completados or 0)
                }

        return productividad

    def get_productividad_embalaje(self, año, vista='mensual'):
        """Get packaging productivity data - boards completed to EMBALAJE_LISTO"""
        from sqlalchemy import func, extract
        from models import OrdenFabricacion, Proyecto, OrdenAreaProgreso, AreaEstado
        
        # Query to get actual packaged boards using area progress system
        if vista == 'mensual':
            query = (db.session.query(
                extract('month', OrdenAreaProgreso.fecha_cambio_estado).label('periodo'),
                func.sum(OrdenFabricacion.cantidad_tableros).label('tableros_completados')
            )
            .join(OrdenFabricacion, OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id)
            .join(AreaEstado, OrdenAreaProgreso.estado_id == AreaEstado.id)
            .join(Proyecto, OrdenFabricacion.proyecto_id == Proyecto.id)
            .filter(
                extract('year', OrdenAreaProgreso.fecha_cambio_estado) == año,
                AreaEstado.codigo == 'embalaje_listo',
                OrdenFabricacion.cantidad_tableros.isnot(None)
            )
            .group_by(extract('month', OrdenAreaProgreso.fecha_cambio_estado))
            .order_by(extract('month', OrdenAreaProgreso.fecha_cambio_estado))
            )
        else:  # semanal
            query = (db.session.query(
                extract('week', OrdenAreaProgreso.fecha_cambio_estado).label('periodo'),
                extract('month', OrdenAreaProgreso.fecha_cambio_estado).label('mes'),
                func.sum(OrdenFabricacion.cantidad_tableros).label('tableros_completados')
            )
            .join(OrdenFabricacion, OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id)
            .join(AreaEstado, OrdenAreaProgreso.estado_id == AreaEstado.id)
            .join(Proyecto, OrdenFabricacion.proyecto_id == Proyecto.id)
            .filter(
                extract('year', OrdenAreaProgreso.fecha_cambio_estado) == año,
                AreaEstado.codigo == 'embalaje_listo',
                OrdenFabricacion.cantidad_tableros.isnot(None)
            )
            .group_by(extract('week', OrdenAreaProgreso.fecha_cambio_estado), extract('month', OrdenAreaProgreso.fecha_cambio_estado))
            .order_by(extract('month', OrdenAreaProgreso.fecha_cambio_estado), extract('week', OrdenAreaProgreso.fecha_cambio_estado))
            )

        try:
            resultados = query.all()
        except Exception as e:
            print(f"Error querying packaging productivity: {e}")
            resultados = []

        # Process results
        productividad = {}
        if vista == 'mensual':
            for mes in range(1, 13):
                productividad[mes] = {
                    'periodo': mes,
                    'periodo_nombre': calendar.month_name[mes],
                    'tableros_completados': 0
                }
            
            for resultado in resultados:
                mes = int(resultado.periodo)
                if mes in productividad:
                    productividad[mes]['tableros_completados'] = int(resultado.tableros_completados or 0)
        else:
            # Para vista semanal, agrupar por mes y semana
            for resultado in resultados:
                semana = int(resultado.periodo)
                mes = int(resultado.mes) if hasattr(resultado, 'mes') else 1
                clave = f"{mes}_{semana}"
                productividad[clave] = {
                    'periodo': semana,
                    'mes': mes,
                    'periodo_nombre': f"Sem {semana} - {calendar.month_name[mes][:3]}",
                    'tableros_completados': int(resultado.tableros_completados or 0)
                }

        return productividad