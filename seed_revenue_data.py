#!/usr/bin/env python3
"""
Script para poblar datos semilla de Revenue Management
"""

import os
import sys
from datetime import datetime, date
from decimal import Decimal

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app, db
from models import ObjetivoMensual
from services.revenue_service import RevenueService

def create_sample_revenue_data():
    """Create sample revenue management data for testing"""
    
    with app.app_context():
        print("Creating Revenue Management sample data...")
        
        # Sample data for 6 months as specified in the original plan
        sample_data = [
            {
                'año': 2025,
                'mes': 3,
                'presupuesto_facturacion': 180000000,  # 180MM
                'adjudicado_facturacion': 170000000,   # 170MM
                'margen_real_pct': 36.0,
                'buffer_pp': 2.0,
                'utilidad_objetivo_clp': 10000000      # 10MM
            },
            {
                'año': 2025,
                'mes': 4,
                'presupuesto_facturacion': 190000000,  # 190MM
                'adjudicado_facturacion': 200000000,   # 200MM
                'margen_real_pct': 35.0,
                'buffer_pp': 2.0,
                'utilidad_objetivo_clp': 8000000       # 8MM
            },
            {
                'año': 2025,
                'mes': 5,
                'presupuesto_facturacion': 150000000,  # 150MM
                'adjudicado_facturacion': 140000000,   # 140MM
                'margen_real_pct': 44.0,
                'buffer_pp': 2.0,
                'utilidad_objetivo_clp': 5000000       # 5MM
            },
            {
                'año': 2025,
                'mes': 6,
                'presupuesto_facturacion': 210000000,  # 210MM
                'adjudicado_facturacion': 190000000,   # 190MM
                'margen_real_pct': 40.0,
                'buffer_pp': 3.0,
                'utilidad_objetivo_clp': 12000000      # 12MM
            },
            {
                'año': 2025,
                'mes': 7,
                'presupuesto_facturacion': 200000000,  # 200MM
                'adjudicado_facturacion': 220000000,   # 220MM
                'margen_real_pct': 33.0,
                'buffer_pp': 2.0,
                'utilidad_objetivo_clp': 6000000       # 6MM
            },
            {
                'año': 2025,
                'mes': 8,
                'presupuesto_facturacion': 170000000,  # 170MM
                'adjudicado_facturacion': 160000000,   # 160MM
                'margen_real_pct': 39.0,
                'buffer_pp': 2.0,
                'utilidad_objetivo_clp': 7000000       # 7MM
            }
        ]
        
        service = RevenueService()
        created_count = 0
        
        for data in sample_data:
            try:
                # Check if objective already exists
                existing = (db.session.query(ObjetivoMensual)
                           .filter_by(año=data['año'], mes=data['mes'])
                           .first())
                
                if existing:
                    print(f"  Actualizando objetivo {data['año']}-{data['mes']:02d}")
                    # Update existing
                    for field, value in data.items():
                        if field not in ['año', 'mes'] and hasattr(existing, field):
                            setattr(existing, field, Decimal(str(value)) if isinstance(value, (int, float)) else value)
                else:
                    print(f"  Creando objetivo {data['año']}-{data['mes']:02d}")
                    # Create new
                    objetivo = ObjetivoMensual(
                        año=data['año'],
                        mes=data['mes'],
                        presupuesto_facturacion=Decimal(str(data['presupuesto_facturacion'])),
                        adjudicado_facturacion=Decimal(str(data['adjudicado_facturacion'])),
                        margen_real_pct=Decimal(str(data['margen_real_pct'])),
                        buffer_pp=Decimal(str(data['buffer_pp'])),
                        utilidad_objetivo_clp=Decimal(str(data['utilidad_objetivo_clp']))
                    )
                    db.session.add(objetivo)
                
                created_count += 1
                
            except Exception as e:
                print(f"  Error procesando {data['año']}-{data['mes']:02d}: {str(e)}")
        
        # Commit all changes
        db.session.commit()
        print(f"Procesados {created_count} objetivos mensuales")
        
        # Test the service calculations
        print("\nTesting Revenue Service calculations...")
        monthly_data = service.get_monthly_data(2025)
        kpis = service.calculate_kpis(2025)
        
        print(f"KPIs 2025:")
        print(f"  Total Presupuesto: ${kpis['total_presupuesto']:,.0f}")
        print(f"  Total Adjudicado: ${kpis['total_adjudicado']:,.0f}")
        print(f"  Gap de Venta: ${kpis['total_gap']:,.0f}")
        print(f"  BE% Promedio: {kpis['avg_be_pct']:.1f}%")
        print(f"  Margen Real Promedio: {kpis['avg_margen_real_pct']:.1f}%")
        print(f"  Meses en Verde: {kpis['meses_verde']}/{kpis['total_meses']} ({kpis['porcentaje_meses_verde']:.1f}%)")
        
        print("\nEstados por mes:")
        for mes in monthly_data[:6]:  # Show only the 6 months with data
            if mes['adjudicado_facturacion'] > 0:
                print(f"  {mes['mes_nombre']}: {mes['estado']} - {mes['recomendacion']}")
        
        # Test break even curve
        print(f"\nTesting Break Even curve:")
        test_amounts = [100000000, 150000000, 200000000, 250000000]
        for amount in test_amounts:
            be_margin = service.required_margin(amount)
            print(f"  ${amount/1000000:.0f}M CLP -> {be_margin:.1f}% BE margin")
        
        # Test simulation
        print(f"\nTesting simulation:")
        sim_result = service.simulate_scenario(
            adjudicado_base=180000000,
            adjudicado_extra=20000000,
            margen_sim_pct=38.0,
            buffer_pp=2.5,
            utilidad_objetivo_clp=8000000
        )
        print(f"  Simulación: {sim_result['estado']} - {sim_result['recomendacion']}")
        print(f"  Total: ${sim_result['adjudicado_total']/1000000:.0f}M")
        print(f"  BE: {sim_result['be_pct']:.1f}% | Objetivo: {sim_result['margen_objetivo_pct']:.1f}%")
        
        print("\n✅ Revenue Management data created successfully!")

if __name__ == "__main__":
    create_sample_revenue_data()