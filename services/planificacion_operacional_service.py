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


class PlanificacionOperacionalService:
    """Service layer for operational planning operations"""

    # Default conversion factors (Chilean Pesos)
    DEFAULT_FACTORS = {
        'melamina': {
            'factor_m2': 50000,  # $50,000 por m²
            'descripcion': 'Melamina estándar 18mm'
        },
        'mdf': {
            'factor_m2': 35000,  # $35,000 por m²
            'descripcion': 'MDF estándar 18mm'
        },
        'madera': {
            'factor_m2': 80000,  # $80,000 por m²
            'descripcion': 'Madera sólida'
        }
    }
    
    # Standard board dimensions (meters)
    AREA_TABLERO_ESTANDAR = 2.98  # 1.22m x 2.44m = 2.98 m²
    FACTOR_DESPERDICIO = 1.15  # 15% waste factor

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
        
        # Get conversion factor info
        factor_info = self._get_factor_info(tipo_material)
        
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
            'tipos_material': list(self.DEFAULT_FACTORS.keys()),
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
            for material, _ in self.DEFAULT_FACTORS.items():
                resultado = self.calcular_tableros_aproximados(
                    monto_provision=float(proyecto.monto_provision_presupuestado),
                    tipo_material=material
                )
                tableros_por_material[material] = resultado
        
        # Get manufacturing orders
        ordenes_fabricacion = (db.session.query(OrdenFabricacion)
                             .filter_by(proyecto_id=proyecto_id)
                             .order_by(OrdenFabricacion.codigo)
                             .all())
        
        return {
            'proyecto': proyecto,
            'tableros_por_material': tableros_por_material,
            'ordenes_fabricacion': ordenes_fabricacion,
            'factor_info': {material: self._get_factor_info(material) for material in self.DEFAULT_FACTORS}
        }

    def get_analisis_capacidad(self, año, vista='mensual'):
        """Get production capacity analysis"""
        
        # Get projects with commercial state ADJUDICADO
        proyectos_adjudicados = (db.session.query(Proyecto)
                                .filter(Proyecto.estado_comercial == EstadoComercial.ADJUDICADO)
                                .filter(or_(
                                    extract('year', Proyecto.fecha_inicio) == año,
                                    extract('year', Proyecto.fecha_fin_estimada) == año
                                ))
                                .all())
        
        if vista == 'mensual':
            capacidad = self._calcular_capacidad_mensual(proyectos_adjudicados, año)
        else:
            capacidad = self._calcular_capacidad_semanal(proyectos_adjudicados, año)
        
        return {
            'año': año,
            'vista': vista,
            'capacidad': capacidad,
            'proyectos_adjudicados': proyectos_adjudicados,
            'resumen': self._calcular_resumen_capacidad(capacidad)
        }

    def calcular_tableros_aproximados(self, monto_provision, tipo_material='melamina'):
        """Calculate approximate boards needed based on provision amount"""
        
        # Get conversion factor
        factor_data = self.DEFAULT_FACTORS.get(tipo_material, self.DEFAULT_FACTORS['melamina'])
        factor_m2 = factor_data['factor_m2']
        
        # Calculate total area in m²
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
            'tipo_material': tipo_material,
            'detalles': {
                'monto_provision': monto_provision,
                'factor_m2': factor_m2,
                'area_tablero': self.AREA_TABLERO_ESTANDAR,
                'factor_desperdicio': self.FACTOR_DESPERDICIO,
                'descripcion_material': factor_data['descripcion']
            }
        }

    def get_factores_conversion(self):
        """Get current conversion factors"""
        # In the future, these could be stored in database
        # For now, return default factors with current configuration
        factores = {}
        
        for material, data in self.DEFAULT_FACTORS.items():
            factores[material] = {
                'factor_m2': data['factor_m2'],
                'descripcion': data['descripcion']
            }
        
        factores['configuracion'] = {
            'area_tablero_estandar': self.AREA_TABLERO_ESTANDAR,
            'factor_desperdicio': self.FACTOR_DESPERDICIO
        }
        
        return factores

    def actualizar_factores_conversion(self, factores_data, user_id):
        """Update conversion factors (future: store in database)"""
        # For now, this is a placeholder
        # In a real implementation, you would store these in a configuration table
        try:
            # Log the update (could be stored in an audit table)
            print(f"User {user_id} updated conversion factors: {factores_data}")
            return True
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
                    tableros_resultado = self.calcular_tableros_aproximados(
                        monto_provision=float(monto_mes),
                        tipo_material=tipo_material
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

    def _get_factor_info(self, tipo_material):
        """Get factor information for a material type"""
        factor_data = self.DEFAULT_FACTORS.get(tipo_material, self.DEFAULT_FACTORS['melamina'])
        
        return {
            'tipo': tipo_material,
            'factor_m2': factor_data['factor_m2'],
            'descripcion': factor_data['descripcion'],
            'area_tablero': self.AREA_TABLERO_ESTANDAR,
            'factor_desperdicio': self.FACTOR_DESPERDICIO,
            'ejemplo_calculo': f"Ejemplo: $1,000,000 ÷ ${factor_data['factor_m2']:,}/m² = {1000000/factor_data['factor_m2']:.1f}m² ÷ {self.AREA_TABLERO_ESTANDAR}m²/tablero × {self.FACTOR_DESPERDICIO} = {int((1000000/factor_data['factor_m2']) / self.AREA_TABLERO_ESTANDAR * self.FACTOR_DESPERDICIO)} tableros"
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
        
        # Assume capacity limits (could be configurable)
        TABLEROS_MAXIMOS_MES = 500
        HORAS_DISPONIBLES_MES = 160  # 20 days × 8 hours
        HORAS_POR_TABLERO = 0.5  # 30 minutes per board
        
        for proyecto in proyectos:
            meses_proyecto = self._obtener_meses_proyecto(proyecto, año)
            
            for mes in meses_proyecto:
                if mes in capacidad:
                    capacidad[mes]['proyectos_activos'] += 1
                    
                    # Calculate boards for this project in this month
                    if proyecto.monto_provision_presupuestado:
                        tableros_resultado = self.calcular_tableros_aproximados(
                            monto_provision=float(proyecto.monto_provision_presupuestado) / len(meses_proyecto),
                            tipo_material='melamina'  # Default material
                        )
                        
                        capacidad[mes]['tableros_requeridos'] += tableros_resultado['tableros_aproximados']
                        capacidad[mes]['horas_estimadas'] += tableros_resultado['tableros_aproximados'] * HORAS_POR_TABLERO
        
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