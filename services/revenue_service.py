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
    
    # Curva Break Even para constructoras
    BREAK_EVEN_CURVE = [
        (100000000, 60), (110000000, 55), (120000000, 51), (130000000, 48),
        (140000000, 45), (150000000, 42), (160000000, 40), (170000000, 38),
        (180000000, 36), (190000000, 35), (200000000, 33), (210000000, 32),
        (220000000, 31), (230000000, 30), (240000000, 29), (250000000, 28)
    ]
    
    def __init__(self):
        pass
    
    def get_break_even_curve(self) -> List[Tuple[int, float]]:
        """Get the break even curve points"""
        return self.BREAK_EVEN_CURVE
    
    def required_margin(self, adjudicado_clp: float) -> float:
        """Calculate required break even margin for given billing amount"""
        if adjudicado_clp <= 0:
            return 60.0  # Default to highest margin
            
        # Saturate to curve limits
        if adjudicado_clp <= self.BREAK_EVEN_CURVE[0][0]:
            return self.BREAK_EVEN_CURVE[0][1]
        
        if adjudicado_clp >= self.BREAK_EVEN_CURVE[-1][0]:
            return self.BREAK_EVEN_CURVE[-1][1]
        
        # Linear interpolation between points
        for i in range(len(self.BREAK_EVEN_CURVE) - 1):
            x1, y1 = self.BREAK_EVEN_CURVE[i]
            x2, y2 = self.BREAK_EVEN_CURVE[i + 1]
            
            if x1 <= adjudicado_clp <= x2:
                # Linear interpolation formula
                margin = y1 + (y2 - y1) * (adjudicado_clp - x1) / (x2 - x1)
                return round(margin, 2)
        
        return 60.0  # Fallback
    
    def calculate_objetivo_margin(self, adjudicado_clp: float, buffer_pp: float, 
                                  utilidad_objetivo_clp: float) -> float:
        """Calculate target margin percentage"""
        if adjudicado_clp <= 0:
            return 0.0
            
        be_pct = self.required_margin(adjudicado_clp)
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
                         utilidad_objetivo_clp: float) -> Dict[str, Any]:
        """Simulate a revenue scenario"""
        total_adjudicado = adjudicado_base + adjudicado_extra
        
        be_pct = self.required_margin(total_adjudicado)
        margen_objetivo_pct = self.calculate_objetivo_margin(
            total_adjudicado, buffer_pp, utilidad_objetivo_clp
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
            'utilidad_real_clp': (margen_sim_pct / 100) * total_adjudicado
        }
    
    def get_monthly_data(self, año: int) -> List[Dict[str, Any]]:
        """Get monthly revenue data for a given year"""
        # Get all monthly objectives for the year
        objetivos = (db.session.query(ObjetivoMensual)
                    .filter_by(año=año)
                    .order_by(ObjetivoMensual.mes)
                    .all())
        
        monthly_data = []
        
        for mes in range(1, 13):
            # Find objective for this month
            objetivo = next((obj for obj in objetivos if obj.mes == mes), None)
            
            if not objetivo:
                # Create empty month structure
                mes_data = {
                    'periodo': f"{año}-{mes:02d}",
                    'mes': mes,
                    'mes_nombre': calendar.month_name[mes],
                    'presupuesto_facturacion': 0,
                    'adjudicado_facturacion': 0,
                    'margen_real_pct': 0,
                    'buffer_pp': 2.0,
                    'utilidad_objetivo_clp': 0,
                    'be_pct': 60.0,
                    'margen_objetivo_pct': 62.0,
                    'gap_venta': 0,
                    'estado': 'ROJO',
                    'recomendacion': 'Agregar datos'
                }
            else:
                # Calculate derived values
                presupuesto = float(objetivo.presupuesto_facturacion or 0)
                adjudicado = float(objetivo.adjudicado_facturacion or 0)
                margen_real = float(objetivo.margen_real_pct or 0)
                buffer_pp = float(objetivo.buffer_pp or 2.0)
                utilidad_objetivo = float(objetivo.utilidad_objetivo_clp or 0)
                
                gap_venta = presupuesto - adjudicado
                be_pct = self.required_margin(adjudicado)
                margen_objetivo_pct = self.calculate_objetivo_margin(
                    adjudicado, buffer_pp, utilidad_objetivo
                )
                
                estado = self.get_revenue_status(margen_real, margen_objetivo_pct)
                recomendacion = self.get_recommendations(gap_venta, margen_real, margen_objetivo_pct)
                
                mes_data = {
                    'id': objetivo.id,
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
                    'recomendacion': recomendacion
                }
            
            monthly_data.append(mes_data)
        
        return monthly_data
    
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
            objetivo = ObjetivoMensual(año=año, mes=mes)
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
                        Proyecto.estado_comercial == EstadoComercial.ADJUDICADO
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
                else:
                    margen_promedio = margen_instalacion
                
                total_facturacion += facturacion_proyecto
                total_margen_weighted += margen_promedio * facturacion_proyecto
        
        if total_facturacion > 0:
            return float(total_margen_weighted / total_facturacion)
        
        return 0.0