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
                'horas_disponibles_mes', 'horas_disponibles_semana'
            ]

            # Update operational parameters if provided
            operational_fields = [
                'turnos_por_dia', 'horas_por_turno', 'dias_laborables_mes', 'oee',
                'horizonte_planificacion', 'umbral_sobrecarga',
                'factor_horas_extra', 'max_subcontrato', 'mejora_oee_objetivo'
            ]

            capacity_data = {}
            operational_data = {}

            for field in capacity_fields:
                if factores_data.get(field) is not None:
                    capacity_data[field] = factores_data[field]
                    updated_factors.append(f"{field}: {factores_data[field]}")

            for field in operational_fields:
                if factores_data.get(field) is not None:
                    operational_data[field] = factores_data[field]
                    updated_factors.append(f"{field}: {factores_data[field]}")

            # Update capacity configuration using configuration service
            if capacity_data:
                try:
                    from services.configuraciones_service import ConfiguracionesService
                    config_service = ConfiguracionesService()
                    config_service.actualizar_configuracion_capacidad(capacity_data, user_id)
                except Exception as e:
                    print(f"Error updating capacity configuration: {e}")

            # Update operational parameters using configuration service
            if operational_data:
                try:
                    from services.configuraciones_service import ConfiguracionesService
                    config_service = ConfiguracionesService()
                    config_service.actualizar_parametros_operacionales(operational_data, user_id)
                except Exception as e:
                    print(f"Error updating operational parameters: {e}")

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
        Horas Nominales = Turnos/día × Horas/turno × Días laborables/mes
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
                'escenarios_disponibles': {}  # Simplified to avoid circular imports
            }

        except Exception as e:
            print(f"Error obteniendo resumen de capacidad estratégica: {e}")
            import traceback
            traceback.print_exc()
            return {
                'error': str(e),
                'parametros_operacionales': {
                    'turnos_por_dia': 1,
                    'horas_por_turno': 8,
                    'dias_laborables_mes': 22,
                    'oee': 0.70
                },
                'calculos_capacidad': {
                    'horas_nominales_mes': 176,
                    'horas_efectivas_mes': 123.2,
                    'eficiencia_global': 70,
                    'capacidad_actualizada_tableros_mes': 400
                },
                'capacidad_teorica_tableros': {
                    'social': 200,
                    'estandar': 250,
                    'especial': 300,
                    'promedio': 250
                },
                'tiempos_por_tablero': {
                    'social': 0.6,
                    'estandar': 0.5,
                    'especial': 0.4
                },
                'capacidad_vs_configurada': {
                    'capacidad_configurada': 1500,
                    'capacidad_calculada': 400,
                    'diferencia': -1100,
                    'recomendacion_actualizacion': True
                },
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
            # Asegurar mínimo 12 semanas, máximo según horizonte_meses
            horizonte_semanas = max(12, horizonte_meses * 4)  # Mínimo 12 semanas
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
                proyecto_totales['ofs_count'] += 1
                proyecto_totales['total_tableros'] += tableros_of
                proyecto_totales['total_horas_fabricacion'] += horas_fabricacion
                proyecto_totales['total_horas_embalaje'] += horas_embalaje
                proyecto_totales['total_horas_requeridas'] += horas_totales

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

    def _calcular_rolling_plan_semanal(self, ofs_activas: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Calcula el rolling plan semanal con análisis de backlog acumulado
        """
        try:
            from datetime import timedelta
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal teórica
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:  # Limitar a 52 semanas para evitar bucles infinitos
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana (solo OFs)
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    # Usar fecha_entrega_dinamica si existe, si no, fecha_planificada
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda total de la semana = demanda OFs + backlog heredado
                demanda_total = demanda_semana_ofs + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            backlog_final_total = rolling_plan_por_semana[list(rolling_plan_por_semana.keys())[-1]]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'recomendacion_general': self._generar_recomendacion_rolling_plan(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_mensual(self, ofs_activas: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes (solo OFs)
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda total = demanda original + backlog heredado
                demanda_total = demanda_mes_ofs + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'recomendacion_general': self._generar_recomendacion_rolling_plan(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exception as e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."

    # ==========================================
    # ROLLING PLAN WITH BACKLOG CALCULATIONS
    # ==========================================

    def calcular_rolling_plan_con_backlog(self, año: int, horizonte_meses: int = 6, modo: str = 'mensual', incluir_presupuestados: bool = True) -> Dict[str, Any]:
        """
        Calcula rolling plan con backlog acumulado considerando órdenes de fabricación y proyectos

        Args:
            año: Año base
            horizonte_meses: Horizonte de planificación en meses
            modo: 'mensual' o 'semanal'
            incluir_presupuestados: Si incluir proyectos presupuestados además de adjudicados

        Returns:
            Diccionario con rolling plan por período
        """
        try:
            from datetime import date, timedelta
            from dateutil.relativedelta import relativedelta
            from models import OrdenFabricacion, OrdenAreaProgreso, TipoArea

            fecha_inicio = date(año, 1, 1)
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)

            # Obtener OFs activas en el horizonte de planificación
            ofs_activas = (db.session.query(OrdenFabricacion)
                          .join(OrdenAreaProgreso, and_(
                              OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                              OrdenAreaProgreso.es_actual == True
                          ))
                          .filter(
                              # OFs no archivadas
                              OrdenAreaProgreso.archivado == False,
                              # Con fechas en el horizonte
                              or_(
                                  and_(OrdenFabricacion.fecha_planificada >= fecha_inicio,
                                       OrdenFabricacion.fecha_planificada <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_fabrica >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_fabrica <= fecha_fin),
                                  and_(OrdenFabricacion.fecha_entrega_embalaje >= fecha_inicio,
                                       OrdenFabricacion.fecha_entrega_embalaje <= fecha_fin)
                              )
                          )
                          .all())

            # Obtener proyectos ganados/presupuestados
            proyectos_demand = self._obtener_proyectos_para_rolling_plan(fecha_inicio, fecha_fin, incluir_presupuestados)

            # Procesar según modo
            if modo == 'semanal':
                return self._procesar_rolling_plan_semanal_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)
            else:
                return self._procesar_rolling_plan_mensual_con_proyectos(ofs_activas, proyectos_demand, fecha_inicio, horizonte_meses)

        except Exception as e:
            print(f"Error calculando rolling plan con backlog: {e}")
            import traceback
            traceback.print_exc()
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _obtener_proyectos_para_rolling_plan(self, fecha_inicio: date, fecha_fin: date, incluir_presupuestados: bool) -> List[Dict[str, Any]]:
        """
        Obtiene proyectos ganados y presupuestados para incluir en rolling plan

        Returns:
            Lista de diccionarios con información de proyectos y distribución de tableros
        """
        try:
            # Estados comerciales a incluir
            estados_incluir = [EstadoComercial.ADJUDICADO, EstadoComercial.EN_DESARROLLO, EstadoComercial.TERMINADO]
            if incluir_presupuestados:
                estados_incluir.append(EstadoComercial.PRESUPUESTADO)

            # Obtener proyectos en el horizonte
            proyectos = (db.session.query(Proyecto)
                        .filter(
                            Proyecto.estado_comercial.in_(estados_incluir),
                            # Que tengan monto de provisión para calcular tableros
                            Proyecto.monto_provision_presupuestado.isnot(None),
                            Proyecto.monto_provision_presupuestado > 0,
                            # Con fechas en el horizonte
                            or_(
                                and_(Proyecto.fecha_inicio >= fecha_inicio,
                                     Proyecto.fecha_inicio <= fecha_fin),
                                and_(Proyecto.fecha_fin_estimada >= fecha_inicio,
                                     Proyecto.fecha_fin_estimada <= fecha_fin),
                                # Proyectos que cruzan el horizonte
                                and_(Proyecto.fecha_inicio <= fecha_inicio,
                                     Proyecto.fecha_fin_estimada >= fecha_inicio)
                            )
                        )
                        .all())

            proyectos_demand = []

            for proyecto in proyectos:
                # Calcular tableros aproximados
                tipo_proyecto = proyecto.tipo_proyecto.value if proyecto.tipo_proyecto else 'ESTANDAR'
                resultado_tableros = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_proyecto=tipo_proyecto,
                    margen_venta_provision=float(proyecto.margen_venta_provision) if proyecto.margen_venta_provision else None
                )

                total_tableros = resultado_tableros['tableros_aproximados']

                if total_tableros > 0:
                    # Calcular distribución temporal proporcional
                    distribucion = self._calcular_distribucion_proporcional_proyecto(
                        proyecto, total_tableros, fecha_inicio, fecha_fin
                    )

                    proyectos_demand.append({
                        'proyecto': proyecto,
                        'total_tableros': total_tableros,
                        'tipo_proyecto': tipo_proyecto,
                        'distribucion_temporal': distribucion,
                        'es_presupuestado': proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO
                    })

            return proyectos_demand

        except Exceptionas e:
            print(f"Error obteniendo proyectos para rolling plan: {e}")
            return []

    def _calcular_distribucion_proporcional_proyecto(self, proyecto: Proyecto, total_tableros: int,
                                                   horizonte_inicio: date, horizonte_fin: date) -> Dict[str, Any]:
        """
        Calcula la distribución proporcional de tableros desde inicio a fin del proyecto

        Args:
            proyecto: Instancia del proyecto
            total_tableros: Total de tableros calculados
            horizonte_inicio: Inicio del horizonte de planificación
            horizonte_fin: Fin del horizonte de planificación

        Returns:
            Diccionario con distribución por período
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            # Fechas del proyecto
            fecha_inicio_proyecto = proyecto.fecha_inicio or horizonte_inicio
            fecha_fin_proyecto = proyecto.fecha_fin_estimada or (horizonte_inicio + relativedelta(months=3))  # Default 3 meses

            # Asegurar que estén en el horizonte
            fecha_inicio_efectiva = max(fecha_inicio_proyecto, horizonte_inicio)
            fecha_fin_efectiva = min(fecha_fin_proyecto, horizonte_fin)

            # Calcular duración en días
            duracion_dias = (fecha_fin_efectiva - fecha_inicio_efectiva).days + 1

            if duracion_dias <= 0:
                return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

            # Distribución mensual
            distribucion_mensual = {}
            fecha_actual = fecha_inicio_efectiva

            while fecha_actual <= fecha_fin_efectiva:
                año_mes = fecha_actual.strftime('%Y-%m')

                # Calcular días del proyecto que caen en este mes
                ultimo_dia_mes = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
                fin_mes = date(fecha_actual.year, fecha_actual.month, ultimo_dia_mes)

                inicio_periodo = max(fecha_actual.replace(day=1), fecha_inicio_efectiva)
                fin_periodo = min(fin_mes, fecha_fin_efectiva)

                dias_en_periodo = (fin_periodo - inicio_periodo).days + 1
                proporcion = dias_en_periodo / duracion_dias
                tableros_mes = int(total_tableros * proporcion)

                if tableros_mes > 0:
                    distribucion_mensual[año_mes] = {
                        'tableros': tableros_mes,
                        'proporcion': proporcion,
                        'dias_periodo': dias_en_periodo,
                        'inicio_periodo': inicio_periodo,
                        'fin_periodo': fin_periodo
                    }

                # Siguiente mes
                fecha_actual = fecha_actual.replace(day=1) + relativedelta(months=1)

            # Distribución semanal (simplificada)
            distribucion_semanal = {}
            semanas_en_duracion = max(1, duracion_dias // 7)
            tableros_por_semana = total_tableros // semanas_en_duracion if semanas_en_duracion > 0 else total_tableros

            fecha_semana = fecha_inicio_efectiva
            semana_num = 1

            while fecha_semana <= fecha_fin_efectiva and semana_num <= 52:
                año_semana = f"{fecha_semana.year}-S{semana_num:02d}"
                fin_semana = min(fecha_semana + timedelta(days=6), fecha_fin_efectiva)

                if fecha_semana <= fecha_fin_efectiva:
                    distribucion_semanal[año_semana] = {
                        'tableros': tableros_por_semana,
                        'inicio_semana': fecha_semana,
                        'fin_semana': fin_semana
                    }

                fecha_semana += timedelta(days=7)
                semana_num += 1

            return {
                'distribucion_mensual': distribucion_mensual,
                'distribucion_semanal': distribucion_semanal,
                'duracion_dias': duracion_dias,
                'fecha_inicio_efectiva': fecha_inicio_efectiva,
                'fecha_fin_efectiva': fecha_fin_efectiva
            }

        except Exception as e:
            print(f"Error calculando distribución proporcional: {e}")
            return {'distribucion_mensual': {}, 'distribucion_semanal': {}}

    def _procesar_rolling_plan_mensual_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan mensual con backlog acumulado incluyendo proyectos
        """
        try:
            from dateutil.relativedelta import relativedelta
            import calendar

            rolling_plan_por_mes = {}
            backlog_acumulado = 0

            # Obtener capacidad mensual
            capacidad_mensual = self.calcular_capacidad_teorica_tableros('ESTANDAR')

            for i in range(horizonte_meses):
                fecha_mes = fecha_inicio + relativedelta(months=i)
                año_mes = fecha_mes.strftime('%Y-%m')

                # Demanda original del mes - OFs
                demanda_mes_ofs = 0
                ofs_del_mes = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_of.year == fecha_mes.year and fecha_of.month == fecha_mes.month:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_mes_ofs += tableros_of
                        ofs_del_mes.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original del mes - Proyectos
                demanda_mes_proyectos = 0
                proyectos_del_mes = []

                for proyecto_data in proyectos_demand:
                    distribucion_mensual = proyecto_data['distribucion_temporal']['distribucion_mensual']
                    if año_mes in distribucion_mensual:
                        tableros_proyecto = distribucion_mensual[año_mes]['tableros']
                        demanda_mes_proyectos += tableros_proyecto
                        proyectos_del_mes.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'proporcion': distribucion_mensual[año_mes]['proporcion'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total del mes
                demanda_original_total = demanda_mes_ofs + demanda_mes_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion = self.calcular_utilizacion_capacidad(demanda_total * 0.5)  # Asumiendo 0.5 horas/tablero
                nuevo_backlog = max(0, demanda_total - capacidad_mensual)

                # Estado del mes
                if utilizacion['utilizacion_porcentaje'] <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion['utilizacion_porcentaje'] <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion['utilizacion_porcentaje'] <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_mes[año_mes] = {
                    'mes_info': {
                        'año': fecha_mes.year,
                        'mes': fecha_mes.month,
                        'nombre_mes': calendar.month_name[fecha_mes.month]
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_mes_ofs,
                        'demanda_original_proyectos': demanda_mes_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_del_mes': ofs_del_mes,
                        'proyectos_del_mes': proyectos_del_mes
                    },
                    'capacidad': utilizacion,
                    'backlog_final': nuevo_backlog,
                    'estado_mes': estado
                }

                # Actualizar backlog para siguiente iteración
                backlog_acumulado = nuevo_backlog

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_mes.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_mes.values())
            backlog_final_total = rolling_plan_por_mes[list(rolling_plan_por_mes.keys())[-1]]['backlog_final'] if rolling_plan_por_mes else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'meses_analizados': horizonte_meses,
                'capacidad_mensual_promedio': capacidad_mensual,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_mes)
            }

            return {
                'rolling_plan_por_mes': rolling_plan_por_mes,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan mensual con proyectos: {e}")
            return {'rolling_plan_por_mes': {}, 'resumen_rolling_plan': {}}

    def _procesar_rolling_plan_semanal_con_proyectos(self, ofs_activas: List, proyectos_demand: List, fecha_inicio: date, horizonte_meses: int) -> Dict[str, Any]:
        """
        Procesa rolling plan semanal con backlog acumulado incluyendo proyectos
        """
        try:
            from datetime import timedelta

            rolling_plan_por_semana = {}
            backlog_acumulado = 0

            # Obtener capacidad semanal
            capacidad_semanal = self.calcular_capacidad_teorica_tableros('ESTANDAR') / 4.33  # Aprox semanas por mes

            # Calcular semanas en el horizonte
            fecha_fin = fecha_inicio + relativedelta(months=horizonte_meses)
            fecha_semana = fecha_inicio
            semana_num = 1

            while fecha_semana < fecha_fin and semana_num <= 52:
                fin_semana = fecha_semana + timedelta(days=6)
                año_semana = f"{fecha_semana.year}-W{fecha_semana.isocalendar()[1]:02d}"

                # Demanda original de la semana - OFs
                demanda_semana_ofs = 0
                ofs_de_la_semana = []

                for of in ofs_activas:
                    fecha_of = of.fecha_entrega_dinamica or of.fecha_planificada
                    if fecha_of and fecha_semana <= fecha_of.date() <= fin_semana:
                        tableros_of = of.cantidad_tableros or 0
                        demanda_semana_ofs += tableros_of
                        ofs_de_la_semana.append({
                            'codigo': of.codigo,
                            'tableros': tableros_of,
                            'fecha': fecha_of,
                            'tipo': 'OF'
                        })

                # Demanda original de la semana - Proyectos
                demanda_semana_proyectos = 0
                proyectos_de_la_semana = []

                for proyecto_data in proyectos_demand:
                    distribucion_semanal = proyecto_data['distribucion_temporal']['distribucion_semanal']
                    if año_semana in distribucion_semanal:
                        tableros_proyecto = distribucion_semanal[año_semana]['tableros']
                        demanda_semana_proyectos += tableros_proyecto
                        proyectos_de_la_semana.append({
                            'nombre': proyecto_data['proyecto'].nombre,
                            'cliente': proyecto_data['proyecto'].cliente.nombre if proyecto_data['proyecto'].cliente else 'Sin cliente',
                            'tableros': tableros_proyecto,
                            'tipo_proyecto': proyecto_data['tipo_proyecto'],
                            'es_presupuestado': proyecto_data['es_presupuestado'],
                            'tipo': 'PROYECTO'
                        })

                # Demanda total de la semana
                demanda_original_total = demanda_semana_ofs + demanda_semana_proyectos
                demanda_total = demanda_original_total + backlog_acumulado

                # Calcular utilización y nuevo backlog
                utilizacion_porcentaje = (demanda_total / capacidad_semanal * 100) if capacidad_semanal > 0 else 0
                nuevo_backlog = max(0, demanda_total - capacidad_semanal)

                # Estado de la semana
                if utilizacion_porcentaje <= 70:
                    estado = {'descripcion': 'Capacidad disponible', 'color': 'success'}
                elif utilizacion_porcentaje <= 90:
                    estado = {'descripcion': 'Capacidad normal', 'color': 'warning'}
                elif utilizacion_porcentaje <= 100:
                    estado = {'descripcion': 'Capacidad completa', 'color': 'primary'}
                else:
                    estado = {'descripcion': 'Sobrecarga', 'color': 'danger'}

                rolling_plan_por_semana[año_semana] = {
                    'semana_info': {
                        'año': fecha_semana.year,
                        'semana': semana_num,
                        'fecha_inicio': fecha_semana,
                        'fecha_fin': fin_semana
                    },
                    'demanda': {
                        'demanda_original_ofs': demanda_semana_ofs,
                        'demanda_original_proyectos': demanda_semana_proyectos,
                        'demanda_original_total': demanda_original_total,
                        'backlog_heredado': backlog_acumulado,
                        'demanda_total': demanda_total,
                        'ofs_de_la_semana': ofs_de_la_semana,
                        'proyectos_de_la_semana': proyectos_de_la_semana
                    },
                    'capacidad': {
                        'utilizacion_porcentaje': utilizacion_porcentaje,
                        'capacidad_semanal': capacidad_semanal
                    },
                    'backlog_final': nuevo_backlog,
                    'estado_semana': estado
                }

                # Actualizar para siguiente iteración
                backlog_acumulado = nuevo_backlog
                fecha_semana += timedelta(days=7)
                semana_num += 1

            # Resumen
            total_demanda_ofs = sum(data['demanda']['demanda_original_ofs'] for data in rolling_plan_por_semana.values())
            total_demanda_proyectos = sum(data['demanda']['demanda_original_proyectos'] for data in rolling_plan_por_semana.values())
            backlog_final_total = list(rolling_plan_por_semana.values())[-1]['backlog_final'] if rolling_plan_por_semana else 0

            resumen_rolling_plan = {
                'total_demanda_ofs': total_demanda_ofs,
                'total_demanda_proyectos': total_demanda_proyectos,
                'total_demanda_original': total_demanda_ofs + total_demanda_proyectos,
                'backlog_final': backlog_final_total,
                'semanas_analizadas': len(rolling_plan_por_semana),
                'capacidad_semanal_promedio': capacidad_semanal,
                'proyectos_incluidos': len(proyectos_demand),
                'proyectos_presupuestados': len([p for p in proyectos_demand if p['es_presupuestado']]),
                'recomendacion_general': self._generar_recomendacion_rolling_plan_con_proyectos(rolling_plan_por_semana)
            }

            return {
                'rolling_plan_por_semana': rolling_plan_por_semana,
                'resumen_rolling_plan': resumen_rolling_plan
            }

        except Exception as e:
            print(f"Error procesando rolling plan semanal con proyectos: {e}")
            return {'rolling_plan_por_semana': {}, 'resumen_rolling_plan': {}}

    def _generar_recomendacion_rolling_plan_con_proyectos(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan con proyectos
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar períodos con sobrecarga
            periodos_sobrecarga = 0
            periodos_normales = 0

            for datos in rolling_plan.values():
                utilizacion = datos.get('capacidad', {}).get('utilizacion_porcentaje', 0)
                if utilizacion > 100:
                    periodos_sobrecarga += 1
                elif utilizacion <= 90:
                    periodos_normales += 1

            total_periodos = len(rolling_plan)
            porcentaje_sobrecarga = (periodos_sobrecarga / total_periodos * 100) if total_periodos > 0 else 0

            if porcentaje_sobrecarga == 0:
                return "Capacidad suficiente para toda la demanda proyectada. Considerar aceptar más proyectos presupuestados."
            elif porcentaje_sobrecarga <= 25:
                return "Sobrecarga leve en algunos períodos. Monitorear proyectos presupuestados y considerar ajustes menores en cronogramas."
            elif porcentaje_sobrecarga <= 50:
                return "Sobrecarga moderada detectada. Evaluar subcontratación o extensión de plazos para proyectos presupuestados."
            else:
                return "Sobrecarga significativa proyectada. Acción urgente requerida: reprogramar proyectos, subcontratar o rechazar algunos proyectos presupuestados."

        except Exception as e:
            return "Error generando recomendaciones."

    def _generar_recomendacion_rolling_plan(self, rolling_plan: Dict) -> str:
        """
        Genera recomendación general para rolling plan (solo OFs)
        """
        try:
            if not rolling_plan:
                return "No hay datos suficientes para generar recomendaciones."

            # Contar meses con sobrecarga
            meses_sobrecarga = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] > 100)
            meses_normales = sum(1 for mes in rolling_plan.values() if 70 <= mes['capacidad']['utilizacion_porcentaje'] <= 90)
            meses_baja_utilizacion = sum(1 for mes in rolling_plan.values() if mes['capacidad']['utilizacion_porcentaje'] < 70)

            total_meses = len(rolling_plan)
            porcentaje_sobrecarga = (meses_sobrecarga / total_meses * 100) if total_meses > 0 else 0

            if porcentaje_sobrecarga > 50:
                return "Sobrecarga crítica: Capacidad insuficiente. Evaluar expansión o subcontratación."
            elif porcentaje_sobrecarga > 25:
                return "Sobrecarga moderada: Riesgo de incumplimiento. Considerar ajustes de capacidad o reprogramación."
            elif meses_baja_utilizacion > meses_normales + meses_sobrecarga:
                return "Subutilización de capacidad: Oportunidad para optimizar o aceptar nuevos proyectos."
            else:
                return "Capacidad balanceada: Demanda y oferta en equilibrio."

        except Exception as e:
            return "Error generando recomendaciones."