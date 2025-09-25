from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, or_, func, extract
from decimal import Decimal
import calendar

from app import db
from models import ObjetivoMensual, Proyecto, EstadoComercial


class RevenueService:
    """Service layer for Revenue Management operations"""
    
    # Break Even Constructoras
    BE_CONSTRUCTORAS = [
        (100_000_000, 60), (110_000_000, 55), (120_000_000, 51), (130_000_000, 48),
        (140_000_000, 45), (150_000_000, 42), (160_000_000, 40), (170_000_000, 38),
        (180_000_000, 36), (190_000_000, 35), (200_000_000, 33), (210_000_000, 32),
        (220_000_000, 31), (230_000_000, 30), (240_000_000, 29), (250_000_000, 28)
    ]
    
    # Break Even General
    BE_GENERAL = [
        (100_000_000, 75), (110_000_000, 68), (120_000_000, 62), (130_000_000, 58),
        (140_000_000, 54), (150_000_000, 51), (160_000_000, 48), (170_000_000, 46),
        (180_000_000, 44), (190_000_000, 43), (200_000_000, 42), (210_000_000, 40),
        (220_000_000, 38), (230_000_000, 37), (240_000_000, 37), (250_000_000, 36)
    ]
    
    def __init__(self):
        pass
    
    def get_break_even_curve(self, curve_type: str = 'general') -> List[Tuple[int, float]]:
        """Get the break even curve points by type"""
        if curve_type == 'constructoras':
            return self.BE_CONSTRUCTORAS
        elif curve_type == 'general':
            return self.BE_GENERAL
        else:
            return self.BE_GENERAL  # Default fallback
    
    def get_available_curves(self) -> Dict[str, str]:
        """Get available curve types with descriptions"""
        return {
            'constructoras': 'Break Even Constructoras',
            'general': 'Break Even General'
        }
    
    def required_margin(self, adjudicado_clp: float, curve_type: str = 'general', buffer_pct: float = 0.0) -> float:
        """Calculate required break even margin for given billing amount with optional buffer"""
        if adjudicado_clp <= 0:
            base_margin = 75.0 if curve_type == 'general' else 60.0
            return base_margin + buffer_pct
            
        # Get the appropriate curve
        curve = self.get_break_even_curve(curve_type)
            
        # Saturate to curve limits
        if adjudicado_clp <= curve[0][0]:
            base_margin = curve[0][1]
        elif adjudicado_clp >= curve[-1][0]:
            base_margin = curve[-1][1]
        else:
            # Linear interpolation between points
            base_margin = curve[0][1]  # Default fallback
            for i in range(len(curve) - 1):
                x1, y1 = curve[i]
                x2, y2 = curve[i + 1]
                
                if x1 <= adjudicado_clp <= x2:
                    # Linear interpolation formula
                    base_margin = y1 + (y2 - y1) * (adjudicado_clp - x1) / (x2 - x1)
                    break
        
        # Apply buffer percentage
        final_margin = base_margin + buffer_pct
        return round(final_margin, 2)
    
    def calculate_objetivo_margin(self, adjudicado_clp: float, buffer_pp: float, 
                                  utilidad_objetivo_clp: float, curve_type: str = 'general',
                                  curve_buffer_pct: float = 0.0) -> float:
        """Calculate target margin percentage with curve selection and buffer"""
        if adjudicado_clp <= 0:
            return 0.0
            
        be_pct = self.required_margin(adjudicado_clp, curve_type, curve_buffer_pct)
        utilidad_pct = (utilidad_objetivo_clp / adjudicado_clp) * 100
        
        return be_pct + buffer_pp + utilidad_pct
    
    def get_revenue_status(self, margen_real_pct: float, margen_objetivo_pct: float) -> str:
        """Determine revenue status color based on margins"""
        if margen_real_pct >= margen_objetivo_pct:
            return "VERDE"
        elif margen_real_pct >= margen_objetivo_pct - 2:
            return "AMARILLO"
        else:
            return "ROJO"
    
    def get_recommendations(self, gap_venta: float, margen_real_pct: float, 
                           margen_objetivo_pct: float) -> str:
        """Get recommendations based on current situation"""
        status = self.get_revenue_status(margen_real_pct, margen_objetivo_pct)
        
        if status == "ROJO":
            if gap_venta > 0:
                return "Subir ventas"
            else:
                return "Mejorar margen"
        elif status == "AMARILLO":
            return "Optimizar mezcla"
        else:  # VERDE
            return "Posible bajar margen para ganar volumen"
    
    def simulate_scenario(self, adjudicado_base: float, adjudicado_extra: float,
                         margen_sim_pct: float, buffer_pp: float, 
                         utilidad_objetivo_clp: float, curve_type: str = 'general',
                         curve_buffer_pct: float = 0.0) -> Dict[str, Any]:
        """Simulate a revenue scenario with curve selection and buffer"""
        total_adjudicado = adjudicado_base + adjudicado_extra
        
        be_pct = self.required_margin(total_adjudicado, curve_type, curve_buffer_pct)
        margen_objetivo_pct = self.calculate_objetivo_margin(
            total_adjudicado, buffer_pp, utilidad_objetivo_clp, curve_type, curve_buffer_pct
        )
        
        status = self.get_revenue_status(margen_sim_pct, margen_objetivo_pct)
        
        # For simulation, gap_venta is the extra amount needed
        gap_venta = adjudicado_extra
        recomendacion = self.get_recommendations(gap_venta, margen_sim_pct, margen_objetivo_pct)
        
        return {
            'adjudicado_total': total_adjudicado,
            'be_pct': be_pct,
            'margen_objetivo_pct': margen_objetivo_pct,
            'margen_simulado_pct': margen_sim_pct,
            'estado': status,
            'recomendacion': recomendacion,
            'utilidad_real_clp': (margen_sim_pct / 100) * total_adjudicado,
            'curve_type': curve_type,
            'curve_buffer_pct': curve_buffer_pct
        }
    
    def get_monthly_data(self, año: int, use_real_data: bool = True) -> List[Dict[str, Any]]:
        """Get monthly revenue data for a given year"""
        return self.get_monthly_data_with_real_projects(año)
    
    def calculate_kpis(self, año: int) -> Dict[str, Any]:
        """Calculate KPIs for the year"""
        monthly_data = self.get_monthly_data(año)
        
        total_presupuesto = sum(mes['presupuesto_facturacion'] for mes in monthly_data)
        total_adjudicado = sum(mes['adjudicado_facturacion'] for mes in monthly_data)
        total_gap = total_presupuesto - total_adjudicado
        
        # Calculate weighted averages
        meses_con_datos = [mes for mes in monthly_data if mes['adjudicado_facturacion'] > 0]
        
        if meses_con_datos:
            avg_be_pct = sum(mes['be_pct'] * mes['adjudicado_facturacion'] 
                           for mes in meses_con_datos) / total_adjudicado if total_adjudicado > 0 else 0
            
            avg_margen_real = sum(mes['margen_real_pct'] * mes['adjudicado_facturacion'] 
                                for mes in meses_con_datos) / total_adjudicado if total_adjudicado > 0 else 0
        else:
            avg_be_pct = 0
            avg_margen_real = 0
        
        # Count months by status
        meses_verde = len([mes for mes in monthly_data if mes['estado'] == 'VERDE'])
        porcentaje_meses_verde = (meses_verde / 12) * 100
        
        return {
            'total_presupuesto': total_presupuesto,
            'total_adjudicado': total_adjudicado,
            'total_gap': total_gap,
            'avg_be_pct': round(avg_be_pct, 1),
            'avg_margen_real_pct': round(avg_margen_real, 1),
            'porcentaje_meses_verde': round(porcentaje_meses_verde, 1),
            'meses_verde': meses_verde,
            'total_meses': 12
        }
    
    def update_monthly_objective(self, año: int, mes: int, data: Dict[str, Any]) -> ObjetivoMensual:
        """Update or create monthly objective"""
        objetivo = (db.session.query(ObjetivoMensual)
                   .filter_by(año=año, mes=mes)
                   .first())
        
        if not objetivo:
            objetivo = ObjetivoMensual()
            objetivo.año = año
            objetivo.mes = mes
            db.session.add(objetivo)
        
        # Update fields
        for field, value in data.items():
            if hasattr(objetivo, field) and value is not None:
                setattr(objetivo, field, Decimal(str(value)) if isinstance(value, (int, float)) else value)
        
        db.session.commit()
        return objetivo
    
    def calculate_real_margins_from_projects(self, año: int, mes: int) -> float:
        """Calculate real margin from adjudicated projects in the given month"""
        # Get projects adjudicated in this month
        proyectos = (db.session.query(Proyecto)
                    .filter(
                        extract('year', Proyecto.fecha_adjudicacion) == año,
                        extract('month', Proyecto.fecha_adjudicacion) == mes,
                        Proyecto.estado_comercial == EstadoComercial.ADJUDICADO,
                        Proyecto.activo == True
                    )
                    .all())
        
        if not proyectos:
            return 0.0
        
        total_facturacion = Decimal('0')
        total_margen_weighted = Decimal('0')
        
        for proyecto in proyectos:
            provision = proyecto.monto_provision_presupuestado or Decimal('0')
            instalacion = proyecto.monto_instalacion_presupuestado or Decimal('0')
            facturacion_proyecto = provision + instalacion
            
            if facturacion_proyecto > 0:
                margen_provision = proyecto.margen_venta_provision or Decimal('0')
                margen_instalacion = proyecto.margen_venta_instalacion or Decimal('0')
                
                # Weighted average margin
                if provision > 0 and instalacion > 0:
                    margen_promedio = (
                        (margen_provision * provision + margen_instalacion * instalacion) / 
                        facturacion_proyecto
                    )
                elif provision > 0:
                    margen_promedio = margen_provision
                elif instalacion > 0:
                    margen_promedio = margen_instalacion
                else:
                    margen_promedio = Decimal('0')
                
                total_facturacion += facturacion_proyecto
                total_margen_weighted += margen_promedio * facturacion_proyecto
        
        if total_facturacion > 0:
            return float(total_margen_weighted / total_facturacion)
        
        return 0.0

    def calculate_real_adjudicado_from_projects(self, año: int, mes: int) -> float:
        """Calculate real adjudicated amount from projects in the given month"""
        proyectos = (db.session.query(Proyecto)
                    .filter(
                        extract('year', Proyecto.fecha_adjudicacion) == año,
                        extract('month', Proyecto.fecha_adjudicacion) == mes,
                        Proyecto.estado_comercial == EstadoComercial.ADJUDICADO,
                        Proyecto.activo == True
                    )
                    .all())
        
        total_adjudicado = Decimal('0')
        for proyecto in proyectos:
            provision = proyecto.monto_provision_presupuestado or Decimal('0')
            instalacion = proyecto.monto_instalacion_presupuestado or Decimal('0')
            total_adjudicado += provision + instalacion
        
        return float(total_adjudicado)

    def calculate_real_presupuesto_from_projects(self, año: int, mes: int) -> float:
        """Calculate real budget amount from projects with presupuesto in the given month"""
        # Projects that were budgeted (have fecha_presupuesto) in this month
        proyectos_presupuestados = (db.session.query(Proyecto)
                                   .filter(
                                       or_(
                                           and_(
                                               extract('year', Proyecto.fecha_presupuesto) == año,
                                               extract('month', Proyecto.fecha_presupuesto) == mes
                                           ),
                                           and_(
                                               extract('year', Proyecto.created_at) == año,
                                               extract('month', Proyecto.created_at) == mes,
                                               Proyecto.estado_comercial.in_([
                                                   EstadoComercial.PRESUPUESTADO,
                                                   EstadoComercial.ADJUDICADO
                                               ])
                                           )
                                       )
                                   )
                                   .filter(Proyecto.activo == True)
                                   .all())
        
        total_presupuesto = Decimal('0')
        for proyecto in proyectos_presupuestados:
            provision = proyecto.monto_provision_presupuestado or Decimal('0')
            instalacion = proyecto.monto_instalacion_presupuestado or Decimal('0')
            total_presupuesto += provision + instalacion
        
        return float(total_presupuesto)

    def get_monthly_data_with_real_projects(self, año: int) -> List[Dict[str, Any]]:
        """Get monthly revenue data combining manual objectives with real project data"""
        # Get all monthly objectives for the year
        objetivos = (db.session.query(ObjetivoMensual)
                    .filter_by(año=año)
                    .order_by(ObjetivoMensual.mes)
                    .all())
        
        monthly_data = []
        
        for mes in range(1, 13):
            # Find objective for this month
            objetivo = next((obj for obj in objetivos if obj.mes == mes), None)
            
            # Always calculate real data from projects first
            real_adjudicado = self.calculate_real_adjudicado_from_projects(año, mes)
            real_presupuesto = self.calculate_real_presupuesto_from_projects(año, mes)
            real_margen = self.calculate_real_margins_from_projects(año, mes)
            
            # Always prioritize real data from projects
            presupuesto = real_presupuesto
            adjudicado = real_adjudicado
            margen_real = real_margen
            
            # Use manual objectives for buffer and utilidad objetivo if available
            if objetivo:
                buffer_pp = float(objetivo.buffer_pp or 2.0)
                utilidad_objetivo = float(objetivo.utilidad_objetivo_clp or 0)
                curve_type = objetivo.curve_type or 'general'
                curve_buffer_pct = float(objetivo.curve_buffer_pct or 0.0)
                
                # Only override with manual data if it's explicitly set and real data is 0
                if real_presupuesto == 0 and objetivo.presupuesto_facturacion:
                    presupuesto = float(objetivo.presupuesto_facturacion)
                if real_adjudicado == 0 and objetivo.adjudicado_facturacion:
                    adjudicado = float(objetivo.adjudicado_facturacion)
                if real_margen == 0 and objetivo.margen_real_pct:
                    margen_real = float(objetivo.margen_real_pct)
            else:
                buffer_pp = 2.0
                utilidad_objetivo = 0
                curve_type = 'general'
                curve_buffer_pct = 0.0
            
            # Calculate derived values
            gap_venta = presupuesto - adjudicado
            be_pct = self.required_margin(adjudicado, curve_type, curve_buffer_pct) if adjudicado > 0 else (75.0 + curve_buffer_pct)
            margen_objetivo_pct = self.calculate_objetivo_margin(
                adjudicado, buffer_pp, utilidad_objetivo, curve_type, curve_buffer_pct
            ) if adjudicado > 0 else (77.0 + curve_buffer_pct)
            
            estado = self.get_revenue_status(margen_real, margen_objetivo_pct)
            recomendacion = self.get_recommendations(gap_venta, margen_real, margen_objetivo_pct)
            
            # Determine if using real data
            usando_datos_reales = (presupuesto == real_presupuesto and 
                                 adjudicado == real_adjudicado and 
                                 margen_real == real_margen)
            
            mes_data = {
                'id': objetivo.id if objetivo else None,
                'periodo': f"{año}-{mes:02d}",
                'mes': mes,
                'mes_nombre': calendar.month_name[mes],
                'presupuesto_facturacion': presupuesto,
                'adjudicado_facturacion': adjudicado,
                'margen_real_pct': margen_real,
                'buffer_pp': buffer_pp,
                'utilidad_objetivo_clp': utilidad_objetivo,
                'be_pct': be_pct,
                'margen_objetivo_pct': margen_objetivo_pct,
                'gap_venta': gap_venta,
                'estado': estado,
                'recomendacion': recomendacion,
                'real_adjudicado': real_adjudicado,
                'real_presupuesto': real_presupuesto,
                'real_margen': real_margen,
                'usando_datos_reales': usando_datos_reales,
                'curve_type': curve_type,
                'curve_buffer_pct': curve_buffer_pct
            }
            
            monthly_data.append(mes_data)
        
        return monthly_data