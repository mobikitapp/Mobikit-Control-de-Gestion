from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, or_, func, extract, case
from decimal import Decimal
import calendar
import json

from app import db
from models import (
    Proyecto, Cliente, User, OrdenFabricacion,
    EstadoComercial, RolUsuario, OrdenAreaProgreso, AreaEstado
)
from services.configuraciones_service import ConfiguracionesService
from sqlalchemy.orm import selectinload


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
                'capacidad_maxima_tableros_mes': 1500,
                'capacidad_maxima_tableros_semana': 330,
                'horas_disponibles_mes': 200,
                'horas_disponibles_semana': 45,
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
            return False

    # ==========================================
    # STRATEGIC CAPACITY PLANNING CALCULATIONS
    # ==========================================

    def calcular_horas_nominales_mensuales(self) -> float:
        """
        Calcula las horas nominales mensuales usando la fórmula:
        Horas Nominales = Máquinas × Turnos/día × Horas/turno × Días laborables/mes
        """
        try:
            config_service = ConfiguracionesService()
            config = config_service.get_configuracion_capacidad()

            turnos_por_dia = config.get('turnos_por_dia', 1)
            horas_por_turno = config.get('horas_por_turno', 8)
            dias_laborables_mes = config.get('dias_laborables_mes', 22)

            horas_nominales = turnos_por_dia * horas_por_turno * dias_laborables_mes
            return float(horas_nominales)

        except Exception as e:
            print(f"Error calculando horas nominales: {e}")
            # Valores por defecto si hay error
            return 1 * 8 * 22  # 176 horas

    def calcular_horas_efectivas_mensuales(self) -> float:
        """
        Calcula las horas efectivas mensuales usando la fórmula:
        Horas Efectivas = Horas Nominales × OEE
        """
        try:
            config_service = ConfiguracionesService()
            config = config_service.get_configuracion_capacidad()

            horas_nominales = self.calcular_horas_nominales_mensuales()
            oee = config.get('oee', 0.70)

            horas_efectivas = horas_nominales * oee
            return float(horas_efectivas)

        except Exception as e:
            print(f"Error calculando horas efectivas: {e}")
            return 352 * 0.70  # 246.4 horas

    def calcular_capacidad_teorica_tableros(self, tipo_proyecto: str = 'ESTANDAR') -> float:
        """
        Calcula la capacidad teórica en tableros usando la fórmula:
        Capacidad = Horas Efectivas / Tiempo por tablero
        """
        try:
            config_service = ConfiguracionesService()
            config = config_service.get_configuracion_capacidad()

            horas_efectivas = self.calcular_horas_efectivas_mensuales()

            # Obtener tiempo por tablero según tipo de proyecto
            tiempo_por_tablero_map = {
                'SOCIAL': config.get('horas_por_tablero_social', 0.6),
                'ESTANDAR': config.get('horas_por_tablero_estandar', 0.5),
                'ESPECIAL': config.get('horas_por_tablero_especial', 0.4)
            }

            tiempo_por_tablero = tiempo_por_tablero_map.get(tipo_proyecto, 0.5)

            if tiempo_por_tablero <= 0:
                return 0.0

            capacidad_tableros = horas_efectivas / tiempo_por_tablero
            return float(capacidad_tableros)

        except Exception as e:
            print(f"Error calculando capacidad teórica: {e}")
            # Fallback calculation using default values
            return 246.4 / 0.5  # 492.8 tableros

    def calcular_utilizacion_capacidad(self, horas_requeridas: float) -> Dict[str, float]:
        """
        Calcula la utilización de capacidad y brecha
        """
        try:
            horas_efectivas = self.calcular_horas_efectivas_mensuales()

            utilizacion = (horas_requeridas / horas_efectivas) * 100 if horas_efectivas > 0 else 0
            brecha_horas = horas_efectivas - horas_requeridas
            brecha_porcentaje = (brecha_horas / horas_efectivas) * 100 if horas_efectivas > 0 else 0

            return {
                'horas_efectivas': horas_efectivas,
                'horas_requeridas': horas_requeridas,
                'utilizacion_porcentaje': utilizacion,
                'brecha_horas': brecha_horas,
                'brecha_porcentaje': brecha_porcentaje,
                'sobrecarga': utilizacion > 100
            }

        except Exception as e:
            print(f"Error calculando utilización: {e}")
            return {
                'horas_efectivas': 0.0,
                'horas_requeridas': horas_requeridas,
                'utilizacion_porcentaje': 0.0,
                'brecha_horas': 0.0,
                'brecha_porcentaje': 0.0,
                'sobrecarga': False
            }

    def get_resumen_capacidad_estrategica(self) -> Dict[str, Any]:
        """
        Obtiene resumen completo de capacidad estratégica con todos los cálculos clave
        """
        try:
            config_service = ConfiguracionesService()
            config = config_service.get_configuracion_capacidad()

            # Cálculos básicos
            horas_nominales = self.calcular_horas_nominales_mensuales()
            horas_efectivas = self.calcular_horas_efectivas_mensuales()

            # Capacidad por tipo de proyecto
            capacidad_social = self.calcular_capacidad_teorica_tableros('SOCIAL')
            capacidad_estandar = self.calcular_capacidad_teorica_tableros('ESTANDAR')
            capacidad_especial = self.calcular_capacidad_teorica_tableros('ESPECIAL')

            # Actualizar capacidad máxima basada en cálculos reales
            capacidad_promedio = (capacidad_social + capacidad_estandar + capacidad_especial) / 3

            return {
                'parametros_operacionales': {
                    'numero_maquinas': config.get('numero_maquinas', 2),
                    'turnos_por_dia': config.get('turnos_por_dia', 1),
                    'horas_por_turno': config.get('horas_por_turno', 8),
                    'dias_laborables_mes': config.get('dias_laborables_mes', 22),
                    'oee': config.get('oee', 0.70)
                },
                'calculos_capacidad': {
                    'horas_nominales_mes': horas_nominales,
                    'horas_efectivas_mes': horas_efectivas,
                    'eficiencia_global': config.get('oee', 0.70) * 100,
                    'capacidad_actualizada_tableros_mes': round(capacidad_promedio, 0)
                },
                'capacidad_teorica_tableros': {
                    'social': round(capacidad_social, 1),
                    'estandar': round(capacidad_estandar, 1),
                    'especial': round(capacidad_especial, 1),
                    'promedio': round(capacidad_promedio, 1)
                },
                'tiempos_por_tablero': {
                    'social': config.get('horas_por_tablero_social', 0.6),
                    'estandar': config.get('horas_por_tablero_estandar', 0.5),
                    'especial': config.get('horas_por_tablero_especial', 0.4)
                },
                'capacidad_vs_configurada': {
                    'capacidad_configurada': config.get('capacidad_maxima_tableros_mes', 1500),
                    'capacidad_calculada': round(capacidad_promedio, 0),
                    'diferencia': round(capacidad_promedio - config.get('capacidad_maxima_tableros_mes', 1500), 0),
                    'recomendacion_actualizacion': capacidad_promedio != config.get('capacidad_maxima_tableros_mes', 1500)
                },
                'escenarios_disponibles': config_service.get_escenarios_deficit() if hasattr(config_service, 'get_escenarios_deficit') else {}
            }

        except Exception as e:
            print(f"Error obteniendo resumen de capacidad estratégica: {e}")
            return {
                'error': str(e),
                'parametros_operacionales': {},
                'calculos_capacidad': {},
                'capacidad_teorica_tableros': {},
                'tiempos_por_tablero': {},
                'capacidad_vs_configurada': {},
                'escenarios_disponibles': {}
            }

    # ==========================================
    # HIERARCHICAL DEMAND STRUCTURE
    # ==========================================

    def calcular_demanda_mensual_jerarquica(self, año: int, horizonte_meses: int = 6) -> Dict[str, Any]:
        """
        Calcula la demanda mensual estructurada jerárquicamente: mes → proyecto → cliente
        Incluye tanto proyectos activos como órdenes de fabricación planificadas
        """
        try:
            from datetime import datetime
            from dateutil.relativedelta import relativedelta

            # Calcular rango de fechas para el horizonte - siempre 12 meses desde el mes actual
            from datetime import date
            hoy = date.today()
            fecha_inicio = date(hoy.year, hoy.month, 1)  # Primer día del mes actual
            horizonte_meses = 12  # Siempre 12 meses como requerido
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Estructura de demanda jerárquica
            demanda_jerarquica = {}

            # Nombres de meses en español
            nombres_meses_es = {
                1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
                5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
                9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
            }

            # Inicializar estructura para cada mes en el horizonte
            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                mes_key = f"{fecha_mes.year}-{fecha_mes.month:02d}"
                demanda_jerarquica[mes_key] = {
                    'mes': fecha_mes.month,
                    'año': fecha_mes.year,
                    'nombre_mes': f"{nombres_meses_es[fecha_mes.month]} {fecha_mes.year}",
                    'proyectos': {},
                    'totales_mes': {
                        'total_tableros': 0,
                        'total_horas_requeridas': 0,
                        'proyectos_count': 0,
                        'clientes_count': 0
                    }
                }

            # Obtener órdenes de fabricación planificadas en el horizonte con joins explícitos
            ofs_query = (db.session.query(OrdenFabricacion, Proyecto, Cliente)
                .join(Proyecto, OrdenFabricacion.proyecto_id == Proyecto.id)
                .join(Cliente, Proyecto.cliente_id == Cliente.id)
                .filter(
                    and_(
                        OrdenFabricacion.fecha_planificada >= fecha_inicio,
                        OrdenFabricacion.fecha_planificada < fecha_fin,
                        OrdenFabricacion.fecha_planificada.isnot(None)
                    )
                )
            ).all()

            # Procesar cada OF
            for of, proyecto, cliente in ofs_query:
                fecha_of = of.fecha_planificada
                mes_key = f"{fecha_of.year}-{fecha_of.month:02d}"

                if mes_key not in demanda_jerarquica:
                    continue

                # Clave única por proyecto
                proyecto_key = f"proyecto_{proyecto.id}"

                # Inicializar proyecto si no existe
                if proyecto_key not in demanda_jerarquica[mes_key]['proyectos']:
                    demanda_jerarquica[mes_key]['proyectos'][proyecto_key] = {
                        'id': proyecto.id,
                        'codigo': getattr(proyecto, 'codigo_interno', None) or f"PROY-{proyecto.id}",
                        'nombre': proyecto.nombre,
                        'tipo_proyecto': proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR',
                        'cliente': {
                            'id': cliente.id,
                            'nombre': cliente.nombre,
                            'tipo': 'Empresa'  # Simplificado ya que no hay tipo_cliente en el modelo actual
                        },
                        'ordenes_fabricacion': [],
                        'totales_proyecto': {
                            'total_tableros': 0,
                            'total_horas_fabricacion': 0,
                            'total_horas_embalaje': 0,
                            'total_horas_requeridas': 0,
                            'ofs_count': 0
                        }
                    }

                # Calcular tableros y horas para esta OF
                tableros_of = of.cantidad_tableros or 0
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'

                # Obtener tiempos por tablero según tipo de proyecto
                config_service = ConfiguracionesService()
                config = config_service.get_configuracion_capacidad()

                tiempo_por_tablero_map = {
                    'SOCIAL': config.get('horas_por_tablero_social', 0.6),
                    'ESTANDAR': config.get('horas_por_tablero_estandar', 0.5),
                    'ESPECIAL': config.get('horas_por_tablero_especial', 0.4)
                }

                tiempo_por_tablero = tiempo_por_tablero_map.get(tipo_proyecto, 0.5)
                # Calcular solo horas de fabricación (tiempo total por tablero incluye fabricación completa)
                horas_totales = tableros_of * tiempo_por_tablero
                horas_fabricacion = horas_totales
                horas_embalaje = 0  # Ya está incluido en el tiempo total por tablero

                # Agregar OF al proyecto
                of_data = {
                    'id': of.id,
                    'codigo': of.codigo,
                    'fecha_planificada': fecha_of.isoformat(),
                    'cantidad_tableros': tableros_of,
                    'tipo_proyecto': tipo_proyecto,
                    'tiempo_por_tablero': tiempo_por_tablero,
                    'horas_fabricacion': round(horas_fabricacion, 2),
                    'horas_embalaje': round(horas_embalaje, 2),
                    'horas_totales': round(horas_totales, 2),
                    'estado': (getattr(of.estado_actual, 'nombre', None) or getattr(of.estado_actual, 'value', None) or 'planificada')
                }

                demanda_jerarquica[mes_key]['proyectos'][proyecto_key]['ordenes_fabricacion'].append(of_data)

                # Actualizar totales del proyecto
                proyecto_totales = demanda_jerarquica[mes_key]['proyectos'][proyecto_key]['totales_proyecto']
                proyecto_totales['total_tableros'] += tableros_of
                proyecto_totales['total_horas_fabricacion'] += horas_fabricacion
                proyecto_totales['total_horas_embalaje'] += horas_embalaje
                proyecto_totales['total_horas_requeridas'] += horas_totales
                proyecto_totales['ofs_count'] += 1

                # Actualizar totales del mes
                mes_totales = demanda_jerarquica[mes_key]['totales_mes']
                mes_totales['total_tableros'] += tableros_of
                mes_totales['total_horas_requeridas'] += horas_totales

            # Calcular totales finales por mes (proyectos únicos y clientes únicos)
            for mes_key in demanda_jerarquica:
                mes_data = demanda_jerarquica[mes_key]
                mes_data['totales_mes']['proyectos_count'] = len(mes_data['proyectos'])

                # Contar clientes únicos en el mes
                clientes_unicos = set()
                for proyecto in mes_data['proyectos'].values():
                    clientes_unicos.add(proyecto['cliente']['id'])
                mes_data['totales_mes']['clientes_count'] = len(clientes_unicos)

            return {
                'periodo': {
                    'año': año,
                    'horizonte_meses': horizonte_meses,
                    'fecha_inicio': fecha_inicio.isoformat(),
                    'fecha_fin': fecha_fin.isoformat()
                },
                'demanda_por_mes': demanda_jerarquica,
                'resumen_general': self._calcular_resumen_demanda_general(demanda_jerarquica)
            }

        except Exception as e:
            print(f"Error calculando demanda mensual jerárquica: {e}")
            return {
                'error': str(e),
                'periodo': {},
                'demanda_por_mes': {},
                'resumen_general': {}
            }

    def _calcular_resumen_demanda_general(self, demanda_jerarquica: Dict) -> Dict[str, Any]:
        """Calcula resumen general de la demanda para todos los meses"""
        try:
            resumen = {
                'total_tableros_horizonte': 0,
                'total_horas_requeridas_horizonte': 0,
                'total_proyectos_unicos': 0,
                'total_clientes_unicos': 0,
                'total_ofs': 0,
                'pico_demanda_mes': '',
                'valle_demanda_mes': '',
                'promedio_mensual': {
                    'tableros': 0,
                    'horas': 0
                }
            }

            if not demanda_jerarquica:
                return resumen

            # Calcular totales
            proyectos_unicos = set()
            clientes_unicos = set()
            max_horas_mes = 0
            min_horas_mes = float('inf')
            pico_mes = ''
            valle_mes = ''

            for mes_key, mes_data in demanda_jerarquica.items():
                totales_mes = mes_data['totales_mes']

                # Acumular totales
                resumen['total_tableros_horizonte'] += totales_mes['total_tableros']
                resumen['total_horas_requeridas_horizonte'] += totales_mes['total_horas_requeridas']
                resumen['total_ofs'] += sum(p['totales_proyecto']['ofs_count'] for p in mes_data['proyectos'].values())

                # Rastrear picos y valles
                horas_mes = totales_mes['total_horas_requeridas']
                if horas_mes > max_horas_mes:
                    max_horas_mes = horas_mes
                    pico_mes = mes_data['nombre_mes']

                if horas_mes < min_horas_mes:
                    min_horas_mes = horas_mes
                    valle_mes = mes_data['nombre_mes']

                # Recopilar proyectos y clientes únicos
                for proyecto in mes_data['proyectos'].values():
                    proyectos_unicos.add(proyecto['id'])
                    clientes_unicos.add(proyecto['cliente']['id'])

            # Finalizar resumen
            resumen['total_proyectos_unicos'] = len(proyectos_unicos)
            resumen['total_clientes_unicos'] = len(clientes_unicos)
            resumen['pico_demanda_mes'] = pico_mes
            resumen['valle_demanda_mes'] = valle_mes


            # Calcular promedios
            num_meses = len(demanda_jerarquica)
            if num_meses > 0:
                resumen['promedio_mensual']['tableros'] = round(resumen['total_tableros_horizonte'] / num_meses, 1)
                resumen['promedio_mensual']['horas'] = round(resumen['total_horas_requeridas_horizonte'] / num_meses, 1)

            return resumen

        except Exception as e:
            print(f"Error calculando resumen general de demanda: {e}")
            return {
                'total_tableros_horizonte': 0,
                'total_horas_requeridas_horizonte': 0,
                'total_proyectos_unicos': 0,
                'total_clientes_unicos': 0,
                'total_ofs': 0,
                'pico_demanda_mes': '',
                'valle_demanda_mes': '',
                'promedio_mensual': {'tableros': 0, 'horas': 0}
            }

    def calcular_demanda_semanal_jerarquica(self, año: int, horizonte_meses: int = 6) -> Dict[str, Any]:
        """
        Calcula la demanda semanal estructurada jerárquicamente: semana → proyecto → cliente
        Similar a la demanda mensual pero agrupada por semanas
        """
        try:
            from datetime import datetime, timedelta
            from dateutil.relativedelta import relativedelta
            import calendar

            # Calcular rango de fechas para el horizonte
            from datetime import date
            hoy = date.today()
            fecha_inicio = hoy - timedelta(days=hoy.weekday())  # Inicio de semana actual (lunes)
            horizonte_semanas = horizonte_meses * 4  # Aproximadamente 4 semanas por mes
            fecha_fin = fecha_inicio + timedelta(weeks=horizonte_semanas)

            # Estructura de demanda jerárquica semanal
            demanda_jerarquica = {}

            # Inicializar estructura para cada semana en el horizonte
            for i in range(horizonte_semanas):
                fecha_semana = fecha_inicio + timedelta(weeks=i)
                semana_key = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"
                
                demanda_jerarquica[semana_key] = {
                    'numero_semana': fecha_semana.isocalendar()[1],
                    'año': fecha_semana.year,
                    'mes': fecha_semana.month,
                    'nombre_periodo': f"Semana {fecha_semana.isocalendar()[1]} ({calendar.month_name[fecha_semana.month][:3]} {fecha_semana.year})",
                    'fecha_inicio': fecha_semana.isoformat(),
                    'fecha_fin': (fecha_semana + timedelta(days=6)).isoformat(),
                    'proyectos': {},
                    'totales_semana': {
                        'total_tableros': 0,
                        'total_horas_requeridas': 0,
                        'proyectos_count': 0,
                        'clientes_count': 0
                    }
                }

            # Obtener órdenes de fabricación planificadas en el horizonte con joins explícitos
            ofs_query = (db.session.query(OrdenFabricacion, Proyecto, Cliente)
                .join(Proyecto, OrdenFabricacion.proyecto_id == Proyecto.id)
                .join(Cliente, Proyecto.cliente_id == Cliente.id)
                .filter(
                    and_(
                        OrdenFabricacion.fecha_planificada >= fecha_inicio,
                        OrdenFabricacion.fecha_planificada < fecha_fin,
                        OrdenFabricacion.fecha_planificada.isnot(None)
                    )
                )
            ).all()

            # Procesar cada OF
            for of, proyecto, cliente in ofs_query:
                fecha_of = of.fecha_planificada
                # Encontrar la semana correspondiente
                inicio_semana = fecha_of - timedelta(days=fecha_of.weekday())
                semana_key = f"{inicio_semana.year}-W{inicio_semana.isocalendar()[1]:02d}"

                if semana_key not in demanda_jerarquica:
                    continue

                # Clave única por proyecto
                proyecto_key = f"proyecto_{proyecto.id}"

                # Inicializar proyecto si no existe
                if proyecto_key not in demanda_jerarquica[semana_key]['proyectos']:
                    demanda_jerarquica[semana_key]['proyectos'][proyecto_key] = {
                        'id': proyecto.id,
                        'codigo': getattr(proyecto, 'codigo_interno', None) or f"PROY-{proyecto.id}",
                        'nombre': proyecto.nombre,
                        'tipo_proyecto': proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR',
                        'cliente': {
                            'id': cliente.id,
                            'nombre': cliente.nombre,
                            'tipo': 'Empresa'
                        },
                        'ordenes_fabricacion': [],
                        'totales_proyecto': {
                            'total_tableros': 0,
                            'total_horas_fabricacion': 0,
                            'total_horas_embalaje': 0,
                            'total_horas_requeridas': 0,
                            'ofs_count': 0
                        }
                    }

                # Calcular tableros y horas para esta OF
                tableros_of = of.cantidad_tableros or 0
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'

                # Obtener tiempos por tablero según tipo de proyecto
                config_service = ConfiguracionesService()
                config = config_service.get_configuracion_capacidad()

                tiempo_por_tablero_map = {
                    'SOCIAL': config.get('horas_por_tablero_social', 0.6),
                    'ESTANDAR': config.get('horas_por_tablero_estandar', 0.5),
                    'ESPECIAL': config.get('horas_por_tablero_especial', 0.4)
                }

                tiempo_por_tablero = tiempo_por_tablero_map.get(tipo_proyecto, 0.5)
                horas_totales = tableros_of * tiempo_por_tablero
                horas_fabricacion = horas_totales
                horas_embalaje = 0

                # Agregar OF al proyecto
                of_data = {
                    'id': of.id,
                    'codigo': of.codigo,
                    'fecha_planificada': fecha_of.isoformat(),
                    'cantidad_tableros': tableros_of,
                    'tipo_proyecto': tipo_proyecto,
                    'tiempo_por_tablero': tiempo_por_tablero,
                    'horas_fabricacion': round(horas_fabricacion, 2),
                    'horas_embalaje': round(horas_embalaje, 2),
                    'horas_totales': round(horas_totales, 2),
                    'estado': (getattr(of.estado_actual, 'nombre', None) or getattr(of.estado_actual, 'value', None) or 'planificada')
                }

                demanda_jerarquica[semana_key]['proyectos'][proyecto_key]['ordenes_fabricacion'].append(of_data)

                # Actualizar totales del proyecto
                proyecto_totales = demanda_jerarquica[semana_key]['proyectos'][proyecto_key]['totales_proyecto']
                proyecto_totales['total_tableros'] += tableros_of
                proyecto_totales['total_horas_fabricacion'] += horas_fabricacion
                proyecto_totales['total_horas_embalaje'] += horas_embalaje
                proyecto_totales['total_horas_requeridas'] += horas_totales
                proyecto_totales['ofs_count'] += 1

                # Actualizar totales de la semana
                semana_totales = demanda_jerarquica[semana_key]['totales_semana']
                semana_totales['total_tableros'] += tableros_of
                semana_totales['total_horas_requeridas'] += horas_totales

            # Calcular totales finales por semana (proyectos únicos y clientes únicos)
            for semana_key in demanda_jerarquica:
                semana_data = demanda_jerarquica[semana_key]
                semana_data['totales_semana']['proyectos_count'] = len(semana_data['proyectos'])

                # Contar clientes únicos en la semana
                clientes_unicos = set()
                for proyecto in semana_data['proyectos'].values():
                    clientes_unicos.add(proyecto['cliente']['id'])
                semana_data['totales_semana']['clientes_count'] = len(clientes_unicos)

            return {
                'periodo': {
                    'año': año,
                    'horizonte_meses': horizonte_meses,
                    'horizonte_semanas': horizonte_semanas,
                    'fecha_inicio': fecha_inicio.isoformat(),
                    'fecha_fin': fecha_fin.isoformat()
                },
                'demanda_por_semana': demanda_jerarquica,
                'resumen_general': self._calcular_resumen_demanda_general_semanal(demanda_jerarquica)
            }

        except Exception as e:
            print(f"Error calculando demanda semanal jerárquica: {e}")
            import traceback
            traceback.print_exc()
            return {
                'error': str(e),
                'periodo': {},
                'demanda_por_semana': {},
                'resumen_general': {}
            }

    def _calcular_resumen_demanda_general_semanal(self, demanda_jerarquica: Dict) -> Dict[str, Any]:
        """Calcula resumen general de la demanda semanal"""
        try:
            resumen = {
                'total_tableros_horizonte': 0,
                'total_horas_requeridas_horizonte': 0,
                'total_proyectos_unicos': 0,
                'total_clientes_unicos': 0,
                'total_ofs': 0,
                'pico_demanda_semana': '',
                'valle_demanda_semana': '',
                'promedio_semanal': {
                    'tableros': 0,
                    'horas': 0
                }
            }

            if not demanda_jerarquica:
                return resumen

            # Calcular totales
            proyectos_unicos = set()
            clientes_unicos = set()
            max_horas_semana = 0
            min_horas_semana = float('inf')
            pico_semana = ''
            valle_semana = ''

            for semana_key, semana_data in demanda_jerarquica.items():
                totales_semana = semana_data['totales_semana']

                # Acumular totales
                resumen['total_tableros_horizonte'] += totales_semana['total_tableros']
                resumen['total_horas_requeridas_horizonte'] += totales_semana['total_horas_requeridas']
                resumen['total_ofs'] += sum(p['totales_proyecto']['ofs_count'] for p in semana_data['proyectos'].values())

                # Rastrear picos y valles
                horas_semana = totales_semana['total_horas_requeridas']
                if horas_semana > max_horas_semana:
                    max_horas_semana = horas_semana
                    pico_semana = semana_data['nombre_periodo']

                if horas_semana < min_horas_semana:
                    min_horas_semana = horas_semana
                    valle_semana = semana_data['nombre_periodo']

                # Recopilar proyectos y clientes únicos
                for proyecto in semana_data['proyectos'].values():
                    proyectos_unicos.add(proyecto['id'])
                    clientes_unicos.add(proyecto['cliente']['id'])

            # Finalizar resumen
            resumen['total_proyectos_unicos'] = len(proyectos_unicos)
            resumen['total_clientes_unicos'] = len(clientes_unicos)
            resumen['pico_demanda_semana'] = pico_semana
            resumen['valle_demanda_semana'] = valle_semana

            # Calcular promedios
            num_semanas = len(demanda_jerarquica)
            if num_semanas > 0:
                resumen['promedio_semanal']['tableros'] = round(resumen['total_tableros_horizonte'] / num_semanas, 1)
                resumen['promedio_semanal']['horas'] = round(resumen['total_horas_requeridas_horizonte'] / num_semanas, 1)

            return resumen

        except Exception as e:
            print(f"Error calculando resumen general de demanda semanal: {e}")
            return {
                'total_tableros_horizonte': 0,
                'total_horas_requeridas_horizonte': 0,
                'total_proyectos_unicos': 0,
                'total_clientes_unicos': 0,
                'total_ofs': 0,
                'pico_demanda_semana': '',
                'valle_demanda_semana': '',
                'promedio_semanal': {'tableros': 0, 'horas': 0}
            }

    def _calcular_rolling_plan_semanal(self, año: int, horizonte_meses: int = 6) -> Dict[str, Any]:
        """
        Calcula el rolling plan semanal con análisis de backlog acumulado
        """
        try:
            # Obtener demanda semanal jerárquica
            demanda_data = self.calcular_demanda_semanal_jerarquica(año, horizonte_meses)
            demanda_por_semana = demanda_data['demanda_por_semana']

            # Obtener capacidad efectiva semanal (horas efectivas disponibles)
            horas_efectivas_semana = self.calcular_horas_efectivas_semanales()

            # Estructura del rolling plan
            rolling_plan = {}
            backlog_acumulado = 0  # Horas acumuladas que no se pueden satisfacer

            # Procesar cada semana en orden cronológico
            semanas_ordenadas = sorted(demanda_por_semana.keys())

            for i, semana_key in enumerate(semanas_ordenadas):
                semana_data = demanda_por_semana[semana_key]
                # Calcular horas de demanda basándose en OFs
                horas_demanda_semana = self._calcular_horas_demanda_semana_correctas(semana_data)

                # Agregar backlog de la semana anterior
                horas_demanda_total = horas_demanda_semana + backlog_acumulado

                # Calcular capacidad vs demanda (calcular directamente el porcentaje)
                utilizacion_porcentaje = (horas_demanda_total / horas_efectivas_semana * 100) if horas_efectivas_semana > 0 else 0

                # Determinar qué se puede producir esta semana
                horas_a_producir = min(horas_demanda_total, horas_efectivas_semana)
                horas_restantes = max(0, horas_demanda_total - horas_efectivas_semana)

                # Actualizar backlog para la próxima semana
                backlog_acumulado = horas_restantes

                # Calcular métricas de la semana
                exceso_capacidad = max(0, horas_efectivas_semana - horas_demanda_total)
                deficit_capacidad = max(0, horas_demanda_total - horas_efectivas_semana)

                # Debug: Log calculation details
                print(f"Rolling Plan Semana {semana_data['numero_semana']} ({semana_data['nombre_periodo']}): "
                      f"OFs={sum(len(p.get('ordenes_fabricacion', [])) for p in semana_data.get('proyectos', {}).values())}, "
                      f"Tableros={semana_data['totales_semana']['total_tableros']}, "
                      f"Horas Demanda Original={horas_demanda_semana:.1f}, "
                      f"Horas Efectivas Disponibles={horas_efectivas_semana:.1f}")

                rolling_plan[semana_key] = {
                    'semana_info': {
                        'numero_semana': semana_data['numero_semana'],
                        'año': semana_data['año'],
                        'mes': semana_data['mes'],
                        'nombre_periodo': semana_data['nombre_periodo'],
                        'fecha_inicio': semana_data['fecha_inicio'],
                        'fecha_fin': semana_data['fecha_fin'],
                        'orden_secuencial': i + 1
                    },
                    'demanda': {
                        'tableros_demandados': semana_data['totales_semana']['total_tableros'],
                        'horas_demanda_original': round(horas_demanda_semana, 1),
                        'backlog_heredado': round(backlog_acumulado - horas_restantes, 1),
                        'horas_demanda_total': round(horas_demanda_total, 1),
                        'proyectos_activos': semana_data['totales_semana']['proyectos_count']
                    },
                    'capacidad': {
                        'horas_efectivas_disponibles': round(horas_efectivas_semana, 1),
                        'utilizacion_porcentaje': round(utilizacion_porcentaje, 1),
                        'horas_a_producir': round(horas_a_producir, 1),
                        'exceso_capacidad': round(exceso_capacidad, 1),
                        'deficit_capacidad': round(deficit_capacidad, 1)
                    },
                    'backlog': {
                        'backlog_inicio_semana': round(backlog_acumulado - horas_restantes, 1),
                        'backlog_fin_semana': round(horas_restantes, 1),
                        'variacion_backlog': round(horas_restantes - (backlog_acumulado - horas_restantes), 1)
                    },
                    'estado_semana': self._evaluar_estado_periodo(
                        utilizacion_porcentaje,
                        deficit_capacidad,
                        exceso_capacidad
                    )
                }

            # Calcular resumen del rolling plan semanal
            resumen_rolling_plan = self._calcular_resumen_rolling_plan_semanal(rolling_plan)

            return {
                'rolling_plan_por_semana': rolling_plan,
                'resumen_rolling_plan': resumen_rolling_plan,
                'parametros_plan': {
                    'año': año,
                    'horizonte_meses': horizonte_meses,
                    'capacidad_semanal_horas': horas_efectivas_semana,
                    'fecha_generacion': datetime.now().isoformat(),
                    'modo': 'semanal'
                },
                'recomendaciones_estrategicas': self._generar_recomendaciones_estrategicas_semanal(rolling_plan)
            }

        except Exception as e:
            print(f"Error calculando rolling plan semanal: {e}")
            return {
                'error': str(e),
                'rolling_plan_por_semana': {},
                'resumen_rolling_plan': {}
            }

    def calcular_demanda_semanal_jerarquica(self, año: int, horizonte_meses: int = 6) -> Dict[str, Any]:
        """
        Calcula demanda jerárquica a nivel semanal para el rolling plan
        """
        try:
            from datetime import date
            
            # Calcular rango de fechas para el horizonte - desde hoy hacia adelante
            hoy = date.today()
            fecha_inicio = hoy - timedelta(days=hoy.weekday())  # Inicio de semana actual (lunes)
            horizonte_semanas = horizonte_meses * 4  # Aproximadamente 4 semanas por mes
            fecha_fin = fecha_inicio + timedelta(weeks=horizonte_semanas)

            # Obtener todas las OFs en el período usando fecha_planificada
            ordenes_fabricacion = (
                db.session.query(OrdenFabricacion)
                .join(Proyecto)
                .join(Cliente, Proyecto.cliente_id == Cliente.id)
                .filter(Proyecto.estado_comercial.in_([
                    EstadoComercial.ADJUDICADO,
                    EstadoComercial.EN_DESARROLLO,
                    EstadoComercial.TERMINADO
                ]))
                .filter(
                    and_(
                        OrdenFabricacion.fecha_planificada >= fecha_inicio,
                        OrdenFabricacion.fecha_planificada <= fecha_fin,
                        OrdenFabricacion.fecha_planificada.isnot(None)
                    )
                )
                .options(
                    selectinload(OrdenFabricacion.proyecto)
                    .selectinload(Proyecto.cliente)
                )
                .all()
            )

            # Agrupar por semanas
            demanda_por_semana = {}

            for of in ordenes_fabricacion:
                fecha_fabricacion = of.fecha_planificada

                # Calcular fecha inicio de semana (lunes)
                fecha_inicio_semana = fecha_fabricacion - timedelta(days=fecha_fabricacion.weekday())
                fecha_fin_semana = fecha_inicio_semana + timedelta(days=6)
                
                # Usar un formato de clave más simple
                semana_key = f"{fecha_inicio_semana.year}-W{fecha_inicio_semana.isocalendar()[1]:02d}"

                if semana_key not in demanda_por_semana:
                    demanda_por_semana[semana_key] = {
                        'numero_semana': fecha_inicio_semana.isocalendar()[1],
                        'año': fecha_inicio_semana.year,
                        'mes': fecha_fabricacion.month,
                        'nombre_periodo': f"Semana {fecha_inicio_semana.isocalendar()[1]} ({fecha_inicio_semana.strftime('%d/%m')} - {fecha_fin_semana.strftime('%d/%m')})",
                        'fecha_inicio': fecha_inicio_semana.isoformat(),
                        'fecha_fin': fecha_fin_semana.isoformat(),
                        'proyectos': {},
                        'totales_semana': {
                            'proyectos_count': 0,
                            'total_tableros': 0,
                            'total_horas_requeridas': 0.0,
                            'ofs_count': 0
                        }
                    }

                # Usar clave de proyecto compatible con el template
                proyecto_key = f"proyecto_{of.proyecto.id}"

                if proyecto_key not in demanda_por_semana[semana_key]['proyectos']:
                    demanda_por_semana[semana_key]['proyectos'][proyecto_key] = {
                        'id': of.proyecto.id,
                        'codigo': getattr(of.proyecto, 'codigo_interno', None) or f"PROY-{of.proyecto.id}",
                        'nombre': of.proyecto.nombre,
                        'cliente': {
                            'id': of.proyecto.cliente.id,
                            'nombre': of.proyecto.cliente.nombre,
                            'tipo': 'Empresa'
                        },
                        'tipo_proyecto': of.proyecto.tipo_proyecto.value if of.proyecto.tipo_proyecto else 'ESTANDAR',
                        'ordenes_fabricacion': [],
                        'totales_proyecto': {
                            'ofs_count': 0,
                            'total_tableros': 0,
                            'total_horas_fabricacion': 0.0,
                            'total_horas_embalaje': 0.0,
                            'total_horas_requeridas': 0.0
                        }
                    }

                # Calcular horas correctamente
                cantidad_tableros = of.cantidad_tableros or 0
                tipo_proyecto = of.proyecto.tipo_proyecto.value if of.proyecto.tipo_proyecto else 'ESTANDAR'
                
                config_service = ConfiguracionesService()
                config = config_service.get_configuracion_capacidad()
                
                tiempo_por_tablero_map = {
                    'SOCIAL': config.get('horas_por_tablero_social', 0.6),
                    'ESTANDAR': config.get('horas_por_tablero_estandar', 0.5),
                    'ESPECIAL': config.get('horas_por_tablero_especial', 0.4)
                }
                
                tiempo_por_tablero = tiempo_por_tablero_map.get(tipo_proyecto, 0.5)
                horas_totales = cantidad_tableros * tiempo_por_tablero
                
                # Agregar OF al proyecto
                demanda_por_semana[semana_key]['proyectos'][proyecto_key]['ordenes_fabricacion'].append({
                    'id': of.id,
                    'codigo': of.codigo,
                    'cantidad_tableros': cantidad_tableros,
                    'fecha_planificada': of.fecha_planificada.isoformat(),
                    'tipo_proyecto': tipo_proyecto,
                    'tiempo_por_tablero': tiempo_por_tablero,
                    'horas_fabricacion': round(horas_totales, 2),
                    'horas_embalaje': 0,  # Ya incluido en tiempo total
                    'horas_totales': round(horas_totales, 2),
                    'estado': getattr(of.estado_actual, 'nombre', None) or getattr(of.estado_actual, 'value', None) or 'planificada'
                })

                # Actualizar totales del proyecto
                proyecto_totales = demanda_por_semana[semana_key]['proyectos'][proyecto_key]['totales_proyecto']
                proyecto_totales['ofs_count'] += 1
                proyecto_totales['total_tableros'] += cantidad_tableros
                proyecto_totales['total_horas_fabricacion'] += horas_totales
                proyecto_totales['total_horas_requeridas'] += horas_totales

            # Calcular totales por semana
            for semana_key, semana_data in demanda_por_semana.items():
                semana_data['totales_semana']['proyectos_count'] = len(semana_data['proyectos'])
                semana_data['totales_semana']['total_tableros'] = sum(
                    p['totales_proyecto']['total_tableros'] for p in semana_data['proyectos'].values()
                )
                semana_data['totales_semana']['total_horas_requeridas'] = sum(
                    p['totales_proyecto']['total_horas_requeridas'] for p in semana_data['proyectos'].values()
                )
                semana_data['totales_semana']['ofs_count'] = sum(
                    p['totales_proyecto']['ofs_count'] for p in semana_data['proyectos'].values()
                )
                
                # Contar clientes únicos
                clientes_unicos = set()
                for proyecto in semana_data['proyectos'].values():
                    clientes_unicos.add(proyecto['cliente']['id'])
                semana_data['totales_semana']['clientes_count'] = len(clientes_unicos)

            print(f"Debug: Calculando demanda semanal, encontradas {len(ordenes_fabricacion)} OFs en {len(demanda_por_semana)} semanas")

            return {
                'demanda_por_semana': demanda_por_semana,
                'resumen_general': self._calcular_resumen_general_semanal(demanda_por_semana),
                'periodo': {
                    'año': año,
                    'horizonte_meses': horizonte_meses,
                    'horizonte_semanas': horizonte_semanas,
                    'fecha_inicio': fecha_inicio.isoformat(),
                    'fecha_fin': fecha_fin.isoformat()
                }
            }

        except Exception as e:
            print(f"Error calculando demanda semanal jerárquica: {e}")
            return {'demanda_por_semana': {}, 'resumen_general': {}}

    def calcular_horas_efectivas_semanales(self) -> float:
        """
        Calcula horas efectivas disponibles por semana
        """
        # Obtener configuración actual o valores por defecto
        try:
            config_service = ConfiguracionesService()
            config = config_service.get_configuracion_capacidad()

            # Parámetros semanales
            dias_laborables_semana = 5  # Default working days per week
            turnos_por_dia = config.get('turnos_por_dia', 1)
            horas_por_turno = config.get('horas_por_turno', 8)
            numero_maquinas = config.get('numero_maquinas', 1)  # Default 1 machine

            # OEE (Overall Equipment Effectiveness)
            oee = config.get('oee', 0.70)

            # Cálculo de horas efectivas semanales
            horas_nominales_semana = dias_laborables_semana * turnos_por_dia * horas_por_turno * numero_maquinas
            horas_efectivas_semana = horas_nominales_semana * oee

            return round(horas_efectivas_semana, 2)

        except Exception as e:
            print(f"Error calculando horas efectivas semanales: {e}")
            # Valor por defecto: 5 días * 1 turno * 8 horas * 1 máquina * 0.70 OEE = 28 horas/semana
            return 28.0

    def _calcular_horas_demanda_semana_correctas(self, semana_data: Dict) -> float:
        """
        Calcula las horas de demanda correctas para una semana basándose en las OFs
        """
        try:
            total_horas = 0.0

            for proyecto in semana_data.get('proyectos', {}).values():
                for of in proyecto.get('ordenes_fabricacion', []):
                    total_horas += of.get('horas_estimadas', 0.0)

            return total_horas

        except Exception as e:
            print(f"Error calculando horas demanda semana: {e}")
            return semana_data.get('totales_semana', {}).get('total_horas_requeridas', 0.0)

    def _calcular_resumen_rolling_plan_semanal(self, rolling_plan: Dict) -> Dict[str, Any]:
        """Calcula resumen ejecutivo del rolling plan semanal"""
        try:
            if not rolling_plan:
                return {}

            total_horas_demanda = sum(semana['demanda']['horas_demanda_total'] for semana in rolling_plan.values())
            total_horas_capacidad = sum(semana['capacidad']['horas_efectivas_disponibles'] for semana in rolling_plan.values())
            total_deficit = sum(semana['capacidad']['deficit_capacidad'] for semana in rolling_plan.values())
            total_exceso = sum(semana['capacidad']['exceso_capacidad'] for semana in rolling_plan.values())

            # Backlog máximo en el horizonte
            backlog_maximo = max(semana['backlog']['backlog_fin_semana'] for semana in rolling_plan.values())

            # Semanas con problemas
            semanas_con_sobrecarga = len([semana for semana in rolling_plan.values() 
                                        if semana['capacidad']['utilizacion_porcentaje'] > 100])

            semanas_con_baja_utilizacion = len([semana for semana in rolling_plan.values() 
                                              if semana['capacidad']['utilizacion_porcentaje'] < 70])

            return {
                'totales_horizonte': {
                    'total_horas_demanda': round(total_horas_demanda, 1),
                    'total_horas_capacidad': round(total_horas_capacidad, 1),
                    'utilizacion_promedio': round((total_horas_demanda / total_horas_capacidad) * 100, 1) if total_horas_capacidad > 0 else 0,
                    'total_deficit_horas': round(total_deficit, 1),
                    'total_exceso_horas': round(total_exceso, 1)
                },
                'analisis_backlog': {
                    'backlog_maximo_horas': round(backlog_maximo, 1),
                    'backlog_maximo_tableros': self._convertir_horas_a_tableros(backlog_maximo),
                    'backlog_final_horizonte': round(list(rolling_plan.values())[-1]['backlog']['backlog_fin_semana'], 1)
                },
                'distribucion_utilizacion': {
                    'semanas_sobrecarga': semanas_con_sobrecarga,
                    'semanas_baja_utilizacion': semanas_con_baja_utilizacion,
                    'semanas_optimas': len(rolling_plan) - semanas_con_sobrecarga - semanas_con_baja_utilizacion
                },
                'recomendacion_general': self._generar_recomendacion_general(
                    (total_horas_demanda / total_horas_capacidad) * 100 if total_horas_capacidad > 0 else 0,
                    semanas_con_sobrecarga,
                    backlog_maximo
                )
            }

        except Exception as e:
            print(f"Error calculando resumen rolling plan semanal: {e}")
            return {}

    def _calcular_resumen_general_semanal(self, demanda_semanal: Dict) -> Dict[str, Any]:
        """
        Calcula resumen general de la demanda semanal
        """
        try:
            resumen = {
                'total_semanas_horizonte': len(demanda_semanal),
                'total_tableros_horizonte': 0,
                'total_horas_requeridas_horizonte': 0.0,
                'total_proyectos_unicos': 0,
                'total_clientes_unicos': 0,
                'pico_demanda_semana': '',
                'valle_demanda_semana': '',
                'promedio_semanal': {
                    'tableros': 0.0,
                    'horas': 0.0
                }
            }

            # Rastrear proyectos y clientes únicos
            proyectos_unicos = set()
            clientes_unicos = set()

            # Rastrear picos y valles
            max_horas_semana = 0
            min_horas_semana = float('inf')
            pico_semana = ''
            valle_semana = ''

            for semana_key, semana_data in demanda_semanal.items():
                # Acumular totales
                resumen['total_tableros_horizonte'] += semana_data['totales_semana']['total_tableros']
                resumen['total_horas_requeridas_horizonte'] += semana_data['totales_semana']['total_horas_requeridas']

                # Recopilar proyectos únicos
                for proyecto in semana_data['proyectos'].values():
                    proyectos_unicos.add(proyecto['id'])
                    clientes_unicos.add(proyecto['cliente']['id'])

                # Rastrear picos y valles
                horas_semana = semana_data['totales_semana']['total_horas_requeridas']
                if horas_semana > max_horas_semana:
                    max_horas_semana = horas_semana
                    pico_semana = semana_data['nombre_periodo']

                if horas_semana < min_horas_semana:
                    min_horas_semana = horas_semana
                    valle_semana = semana_data['nombre_periodo']

            # Finalizar resumen
            resumen['total_proyectos_unicos'] = len(proyectos_unicos)
            resumen['total_clientes_unicos'] = len(clientes_unicos)
            resumen['pico_demanda_semana'] = pico_semana
            resumen['valle_demanda_semana'] = valle_semana

            # Calcular promedios
            num_semanas = len(demanda_semanal)
            if num_semanas > 0:
                resumen['promedio_semanal']['tableros'] = round(resumen['total_tableros_horizonte'] / num_semanas, 1)
                resumen['promedio_semanal']['horas'] = round(resumen['total_horas_requeridas_horizonte'] / num_semanas, 1)

            return resumen

        except Exception as e:
            print(f"Error calculando resumen general semanal: {e}")
            return {}

    def _generar_recomendaciones_estrategicas_semanal(self, rolling_plan: Dict) -> List[Dict[str, str]]:
        """Genera recomendaciones estratégicas basadas en el rolling plan semanal"""
        recomendaciones = []

        try:
            if not rolling_plan:
                return recomendaciones

            # Analizar patrones en el plan
            semanas_data = list(rolling_plan.values())

            # Recomendación sobre backlog
            backlog_final = semanas_data[-1]['backlog']['backlog_fin_semana']
            if backlog_final > 25:  # Ajustado para escala semanal
                recomendaciones.append({
                    'prioridad': 'ALTA',
                    'categoria': 'CAPACIDAD',
                    'titulo': 'Déficit de Capacidad Crítico Semanal',
                    'descripcion': f'Backlog acumulado de {round(backlog_final, 1)} horas al final del horizonte semanal',
                    'accion_recomendada': 'Evaluar horas extra o redistribución de carga semanal'
                })

            # Recomendación sobre utilización desbalanceada
            utilizaciones = [semana['capacidad']['utilizacion_porcentaje'] for semana in semanas_data]
            if max(utilizaciones) - min(utilizaciones) > 60:
                recomendaciones.append({
                    'prioridad': 'MEDIA',
                    'categoria': 'NIVELACION',
                    'titulo': 'Carga de Trabajo Desbalanceada',
                    'descripcion': f'Variación de {round(max(utilizaciones) - min(utilizaciones), 1)}% entre semanas',
                    'accion_recomendada': 'Considerar nivelación de producción entre semanas'
                })

            # Recomendación sobre semanas críticas
            semanas_criticas = [s for s in semanas_data if s['capacidad']['utilizacion_porcentaje'] > 120]
            if semanas_criticas:
                recomendaciones.append({
                    'prioridad': 'ALTA',
                    'categoria': 'SOBRECARGA',
                    'titulo': 'Semanas con Sobrecarga Crítica',
                    'descripcion': f'{len(semanas_criticas)} semanas con utilización > 120%',
                    'accion_recomendada': 'Planificar recursos adicionales o reprogramar producción'
                })

            return recomendaciones

        except Exception as e:
            print(f"Error generando recomendaciones estratégicas semanales: {e}")
            return recomendaciones


    def _calcular_horas_demanda_mes_correctas(self, mes_data: Dict) -> float:
        """
        Calcula correctamente las horas de demanda de un mes basándose en:
        cantidad_tableros * horas_por_tablero (según tipo de proyecto) de cada OF
        """
        try:
            config_service = ConfiguracionesService()
            config = config_service.get_configuracion_capacidad()

            tiempo_por_tablero_map = {
                'SOCIAL': config.get('horas_por_tablero_social', 0.6),
                'ESTANDAR': config.get('horas_por_tablero_estandar', 0.5),
                'ESPECIAL': config.get('horas_por_tablero_especial', 0.4)
            }

            total_horas = 0.0

            # Iterar sobre todos los proyectos del mes
            for proyecto in mes_data.get('proyectos', {}).values():
                # Iterar sobre todas las OFs del proyecto
                for of_data in proyecto.get('ordenes_fabricacion', []):
                    tableros = of_data.get('cantidad_tableros', 0)
                    tipo_proyecto = proyecto.get('tipo_proyecto', 'ESTANDAR')

                    tiempo_por_tablero = tiempo_por_tablero_map.get(tipo_proyecto, 0.5)
                    horas_of = tableros * tiempo_por_tablero
                    total_horas += horas_of

            return round(total_horas, 2)

        except Exception as e:
            print(f"Error calculando horas de demanda del mes: {e}")
            # Fallback al valor existente
            return mes_data.get('totales_mes', {}).get('total_horas_requeridas', 0.0)

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual') -> Dict[str, Any]:
        """
        Calcula el rolling plan con análisis de backlog acumulado y redistribución de carga
        Soporta modo mensual y semanal
        """
        try:
            if modo == 'semanal':
                return self._calcular_rolling_plan_semanal(año, horizonte_meses)

            # Obtener demanda mensual jerárquica
            demanda_data = self.calcular_demanda_mensual_jerarquica(año, horizonte_meses)
            demanda_por_mes = demanda_data['demanda_por_mes']

            # Obtener capacidad efectiva mensual (horas efectivas disponibles)
            horas_efectivas_mes = self.calcular_horas_efectivas_mensuales()

            # Estructura del rolling plan
            rolling_plan = {}
            backlog_acumulado = 0  # Horas acumuladas que no se pueden satisfacer

            # Procesar cada mes en orden cronológico
            meses_ordenados = sorted(demanda_por_mes.keys())

            for i, mes_key in enumerate(meses_ordenados):
                mes_data = demanda_por_mes[mes_key]
                # Calcular correctamente las horas de demanda basándose en OFs
                horas_demanda_mes = self._calcular_horas_demanda_mes_correctas(mes_data)

                # Agregar backlog del mes anterior
                horas_demanda_total = horas_demanda_mes + backlog_acumulado

                # Calcular capacidad vs demanda
                utilizacion_capacidad = self.calcular_utilizacion_capacidad(horas_demanda_total)

                # Determinar qué se puede producir este mes
                horas_a_producir = min(horas_demanda_total, horas_efectivas_mes)
                horas_restantes = max(0, horas_demanda_total - horas_efectivas_mes)

                # Actualizar backlog para el próximo mes
                backlog_acumulado = horas_restantes

                # Calcular métricas del mes
                exceso_capacidad = max(0, horas_efectivas_mes - horas_demanda_total)
                deficit_capacidad = max(0, horas_demanda_total - horas_efectivas_mes)

                # Debug: Log calculation details
                print(f"Rolling Plan {mes_data['nombre_mes']}: "
                      f"OFs={sum(len(p.get('ordenes_fabricacion', [])) for p in mes_data.get('proyectos', {}).values())}, "
                      f"Tableros={mes_data['totales_mes']['total_tableros']}, "
                      f"Horas Demanda Original={horas_demanda_mes:.1f}, "
                      f"Horas Efectivas Disponibles={horas_efectivas_mes:.1f}")

                rolling_plan[mes_key] = {
                    'mes_info': {
                        'mes': mes_data['mes'],
                        'año': mes_data['año'],
                        'nombre_mes': mes_data['nombre_mes'],
                        'orden_secuencial': i + 1
                    },
                    'demanda': {
                        'horas_demanda_original': horas_demanda_mes,
                        'backlog_heredado': horas_demanda_total - horas_demanda_mes,
                        'horas_demanda_total': horas_demanda_total,
                        'proyectos_count': mes_data['totales_mes']['proyectos_count'],
                        'tableros_demandados': mes_data['totales_mes']['total_tableros']
                    },
                    'capacidad': {
                        'horas_efectivas_disponibles': horas_efectivas_mes,
                        'horas_a_producir': horas_a_producir,
                        'utilizacion_porcentaje': (horas_a_producir / horas_efectivas_mes) * 100,
                        'exceso_capacidad': exceso_capacidad,
                        'deficit_capacidad': deficit_capacidad
                    },
                    'backlog': {
                        'backlog_fin_mes': backlog_acumulado,
                        'backlog_en_tableros': self._convertir_horas_a_tableros(backlog_acumulado),
                        'variacion_backlog': backlog_acumulado - (horas_demanda_total - horas_demanda_mes)
                    },
                    'estado_mes': self._determinar_estado_mes(utilizacion_capacidad['utilizacion_porcentaje']),
                    'oportunidades_optimizacion': self._identificar_oportunidades_optimizacion(
                        utilizacion_capacidad['utilizacion_porcentaje'], 
                        deficit_capacidad, 
                        exceso_capacidad
                    )
                }

            # Calcular resumen del rolling plan
            resumen_rolling_plan = self._calcular_resumen_rolling_plan(rolling_plan)

            return {
                'rolling_plan_por_mes': rolling_plan,
                'resumen_rolling_plan': resumen_rolling_plan,
                'parametros_plan': {
                    'año': año,
                    'horizonte_meses': horizonte_meses,
                    'capacidad_mensual_horas': horas_efectivas_mes,
                    'fecha_generacion': datetime.now().isoformat()
                },
                'recomendaciones_estrategicas': self._generar_recomendaciones_estrategicas(rolling_plan)
            }

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            return {
                'error': str(e),
                'rolling_plan_por_mes': {},
                'resumen_rolling_plan': {},
                'parametros_plan': {},
                'recomendaciones_estrategicas': []
            }

    def _convertir_horas_a_tableros(self, horas: float, tipo_proyecto: str = 'ESTANDAR') -> float:
        """Convierte horas a tableros aproximados según tipo de proyecto"""
        try:
            config_service = ConfiguracionesService()
            config = config_service.get_configuracion_capacidad()

            tiempo_por_tablero_map = {
                'SOCIAL': config.get('horas_por_tablero_social', 0.6),
                'ESTANDAR': config.get('horas_por_tablero_estandar', 0.5),
                'ESPECIAL': config.get('horas_por_tablero_especial', 0.4)
            }

            tiempo_por_tablero = tiempo_por_tablero_map.get(tipo_proyecto, 0.5)

            if tiempo_por_tablero <= 0:
                return 0.0

            return round(horas / tiempo_por_tablero, 1)

        except Exception as e:
            print(f"Error convirtiendo horas a tableros: {e}")
            return 0.0

    def _determinar_estado_mes(self, utilizacion_porcentaje: float) -> Dict[str, str]:
        """Determina el estado del mes basado en utilización"""
        if utilizacion_porcentaje <= 70:
            return {
                'codigo': 'BAJA_UTILIZACION',
                'descripcion': 'Utilización baja - Capacidad excedente',
                'color': 'success'
            }
        elif utilizacion_porcentaje <= 90:
            return {
                'codigo': 'UTILIZACION_OPTIMA',
                'descripcion': 'Utilización óptima',
                'color': 'primary'
            }
        elif utilizacion_porcentaje <= 110:
            return {
                'codigo': 'SOBRECARGA_MODERADA',
                'descripcion': 'Sobrecarga moderada - Requiere atención',
                'color': 'warning'
            }
        else:
            return {
                'codigo': 'SOBRECARGA_CRITICA',
                'descripcion': 'Sobrecarga crítica - Requiere intervención',
                'color': 'danger'
            }

    def _identificar_oportunidades_optimizacion(self, utilizacion: float, deficit: float, exceso: float) -> List[Dict[str, str]]:
        """Identifica oportunidades de optimización para el mes"""
        oportunidades = []

        if exceso > 50:  # Más de 50 horas de exceso
            oportunidades.append({
                'tipo': 'ADELANTAR_PRODUCCION',
                'descripcion': f'Oportunidad para adelantar {self._convertir_horas_a_tableros(exceso)} tableros del mes siguiente',
                'impacto': 'Reducir backlog futuro'
            })

        if deficit > 50:  # Más de 50 horas de déficit
            config_service = ConfiguracionesService()
            escenarios = config_service.get_escenarios_deficit() if hasattr(config_service, 'get_escenarios_deficit') else {}

            if deficit <= 100:
                oportunidades.append({
                    'tipo': 'HORAS_EXTRA',
                    'descripcion': f'Considerar {round(deficit/8, 1)} días de horas extra',
                    'impacto': 'Eliminar déficit con costo adicional'
                })
            else:
                oportunidades.append({
                    'tipo': 'TURNO_ADICIONAL',
                    'descripcion': 'Evaluar turno adicional temporal',
                    'impacto': 'Aumentar capacidad significativamente'
                })

        if 80 <= utilizacion <= 95:
            oportunidades.append({
                'tipo': 'MEJORAR_OEE',
                'descripcion': 'Optimizar OEE para aumentar capacidad efectiva',
                'impacto': 'Mejora continua sin costos adicionales'
            })

        return oportunidades

    def _calcular_resumen_rolling_plan(self, rolling_plan: Dict) -> Dict[str, Any]:
        """Calcula resumen ejecutivo del rolling plan"""
        try:
            if not rolling_plan:
                return {}

            total_horas_demanda = sum(mes['demanda']['horas_demanda_total'] for mes in rolling_plan.values())
            total_horas_capacidad = sum(mes['capacidad']['horas_efectivas_disponibles'] for mes in rolling_plan.values())
            total_deficit = sum(mes['capacidad']['deficit_capacidad'] for mes in rolling_plan.values())
            total_exceso = sum(mes['capacidad']['exceso_capacidad'] for mes in rolling_plan.values())

            # Backlog máximo en el horizonte
            backlog_maximo = max(mes['backlog']['backlog_fin_mes'] for mes in rolling_plan.values())

            # Meses con problemas
            meses_con_sobrecarga = len([mes for mes in rolling_plan.values() 
                                      if mes['capacidad']['utilizacion_porcentaje'] > 100])

            meses_con_baja_utilizacion = len([mes for mes in rolling_plan.values() 
                                            if mes['capacidad']['utilizacion_porcentaje'] < 70])

            return {
                'totales_horizonte': {
                    'total_horas_demanda': round(total_horas_demanda, 1),
                    'total_horas_capacidad': round(total_horas_capacidad, 1),
                    'utilizacion_promedio': round((total_horas_demanda / total_horas_capacidad) * 100, 1),
                    'total_deficit_horas': round(total_deficit, 1),
                    'total_exceso_horas': round(total_exceso, 1)
                },
                'analisis_backlog': {
                    'backlog_maximo_horas': round(backlog_maximo, 1),
                    'backlog_maximo_tableros': self._convertir_horas_a_tableros(backlog_maximo),
                    'backlog_final_horizonte': round(list(rolling_plan.values())[-1]['backlog']['backlog_fin_mes'], 1)
                },
                'distribucion_utilizacion': {
                    'meses_sobrecarga': meses_con_sobrecarga,
                    'meses_baja_utilizacion': meses_con_baja_utilizacion,
                    'meses_optimos': len(rolling_plan) - meses_con_sobrecarga - meses_con_baja_utilizacion
                },
                'recomendacion_general': self._generar_recomendacion_general(
                    (total_horas_demanda / total_horas_capacidad) * 100,
                    meses_con_sobrecarga,
                    backlog_maximo
                )
            }

        except Exception as e:
            print(f"Error calculando resumen rolling plan: {e}")
            return {}

    def _generar_recomendaciones_estrategicas(self, rolling_plan: Dict) -> List[Dict[str, str]]:
        """Genera recomendaciones estratégicas basadas en el rolling plan"""
        recomendaciones = []

        try:
            if not rolling_plan:
                return recomendaciones

            # Analizar patrones en el plan
            meses_data = list(rolling_plan.values())

            # Recomendación sobre backlog
            backlog_final = meses_data[-1]['backlog']['backlog_fin_mes']
            if backlog_final > 100:
                recomendaciones.append({
                    'prioridad': 'ALTA',
                    'categoria': 'CAPACIDAD',
                    'titulo': 'Déficit de Capacidad Crítico',
                    'descripcion': f'Backlog acumulado de {round(backlog_final, 1)} horas al final del horizonte',
                    'accion_recomendada': 'Evaluar expansión de capacidad o subcontratación estratégica'
                })

            # Recomendación sobre utilización desbalanceada
            utilizaciones = [mes['capacidad']['utilizacion_porcentaje'] for mes in meses_data]
            if max(utilizaciones) - min(utilizaciones) > 50:
                recomendaciones.append({
                    'prioridad': 'MEDIA',
                    'categoria': 'NIVELACION',
                    'titulo': 'Desbalance en Utilización',
                    'descripcion': 'Gran variación en utilización mensual de capacidad',
                    'accion_recomendada': 'Implementar estrategia de nivelación de producción'
                })

            # Recomendación sobre oportunidades de mejora
            excesos_significativos = [mes for mes in meses_data if mes['capacidad']['exceso_capacidad'] > 80]
            if len(excesos_significativos) >= 2:
                recomendaciones.append({
                    'prioridad': 'BAJA',
                    'categoria': 'OPTIMIZACION',
                    'titulo': 'Oportunidades de Adelanto',
                    'descripcion': f'{len(excesos_significativos)} meses con capacidad excedente significativa',
                    'accion_recomendada': 'Considerar adelantar producción para reducir backlog futuro'
                })

            return recomendaciones

        except Exception as e:
            print(f"Error generando recomendaciones estratégicas: {e}")
            return []

    def _generar_recomendacion_general(self, utilizacion_promedio: float, meses_sobrecarga: int, backlog_maximo: float) -> str:
        """Genera recomendación general del rolling plan"""
        if utilizacion_promedio > 110 and meses_sobrecarga >= 3:
            return "CRÍTICO: Capacidad insuficiente. Requiere expansión inmediata o subcontratación."
        elif utilizacion_promedio > 95 and backlog_maximo > 200:
            return "ALERTA: Riesgo de incumplimiento. Evaluar medidas de incremento de capacidad."
        elif utilizacion_promedio < 70:
            return "OPORTUNIDAD: Capacidad subutilizada. Evaluar nuevos proyectos o reducción de costos."
        else:
            return "BALANCEADO: Capacidad y demanda en equilibrio general."

    def _calcular_horas_of(self, of) -> float:
        """Calcula las horas estimadas para una Orden de Fabricación"""
        try:
            tableros = of.cantidad_tableros or 0
            if tableros <= 0:
                return 0.0
            
            # Obtener tipo de proyecto
            tipo_proyecto = of.proyecto.tipo_proyecto.value if of.proyecto.tipo_proyecto else 'ESTANDAR'
            
            # Obtener configuración de tiempo por tablero
            config_service = ConfiguracionesService()
            config = config_service.get_configuracion_capacidad()
            
            tiempo_por_tablero_map = {
                'SOCIAL': config.get('horas_por_tablero_social', 0.6),
                'ESTANDAR': config.get('horas_por_tablero_estandar', 0.5),
                'ESPECIAL': config.get('horas_por_tablero_especial', 0.4)
            }
            
            tiempo_por_tablero = tiempo_por_tablero_map.get(tipo_proyecto, 0.5)
            return round(tableros * tiempo_por_tablero, 2)
            
        except Exception as e:
            print(f"Error calculando horas de OF {getattr(of, 'id', 'N/A')}: {e}")
            return 0.0

    def _evaluar_estado_periodo(self, utilizacion_porcentaje: float, deficit_capacidad: float, exceso_capacidad: float) -> Dict[str, str]:
        """Evalúa el estado de un período (semana/mes) basado en métricas de capacidad"""
        if utilizacion_porcentaje > 120:
            return {
                'codigo': 'SOBRECARGA_CRITICA',
                'descripcion': 'Sobrecarga crítica - Requiere intervención inmediata',
                'color': 'danger'
            }
        elif utilizacion_porcentaje > 100:
            return {
                'codigo': 'SOBRECARGA_MODERADA', 
                'descripcion': 'Sobrecarga moderada - Requiere atención',
                'color': 'warning'
            }
        elif utilizacion_porcentaje > 90:
            return {
                'codigo': 'UTILIZACION_ALTA',
                'descripcion': 'Utilización alta - Monitorear',
                'color': 'info'
            }
        elif utilizacion_porcentaje > 70:
            return {
                'codigo': 'UTILIZACION_OPTIMA',
                'descripcion': 'Utilización óptima',
                'color': 'success'
            }
        else:
            return {
                'codigo': 'BAJA_UTILIZACION',
                'descripcion': 'Utilización baja - Capacidad excedente',
                'color': 'secondary'
            }

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
            TABLEROS_MAXIMOS_MES = 1500
            HORAS_DISPONIBLES_MES = 200
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