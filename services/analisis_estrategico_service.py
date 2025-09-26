from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, date
from sqlalchemy import and_, or_, func
import calendar
from dateutil.relativedelta import relativedelta
import logging

from app import db
from models import (
    EventoEntrega, Proyecto, Despacho, Cliente, RolUsuario, TipoEvento, EstadoEvento, 
    PrioridadEvento, HitoEntrega, EstadoHitoEntrega, PlanEntrega, Contrato, EstadoDespacho
)

logger = logging.getLogger(__name__)

class AnalisisEstrategicoService:
    """Service layer for strategic analysis with unified monthly and weekly modes"""

    def get_analisis_estrategico(self, modo_analisis: str, year: int, month: int, day: Optional[int] = None, 
                                usuario_id: Optional[str] = None, rol_usuario: Optional[RolUsuario] = None,
                                filtros: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Unified strategic analysis method that works for both monthly and weekly modes
        
        Args:
            modo_analisis: 'mensual' or 'semanal'
            year: Year for analysis
            month: Month for analysis  
            day: Day for weekly analysis (required only for weekly mode)
            usuario_id: User ID for access control
            rol_usuario: User role for access control
            filtros: Additional filters to apply
        
        Returns:
            Dict with unified strategic analysis structure
        """
        
        if modo_analisis == 'mensual':
            return self.get_analisis_mensual(year, month, usuario_id, rol_usuario, filtros)
        elif modo_analisis == 'semanal':
            if day is None:
                raise ValueError("Day parameter is required for weekly analysis")
            return self.get_analisis_semanal(year, month, day, usuario_id, rol_usuario, filtros)
        else:
            raise ValueError("Modo de análisis debe ser 'mensual' o 'semanal'")

    def get_analisis_mensual(self, year: int, month: int, usuario_id: Optional[str], rol_usuario: Optional[RolUsuario],
                            filtros: Optional[Dict] = None) -> Dict[str, Any]:
        """Strategic monthly analysis with unified field structure"""
        
        # Create date range for the month
        primer_dia = date(year, month, 1)
        if month == 12:
            ultimo_dia = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            ultimo_dia = date(year, month + 1, 1) - timedelta(days=1)
        
        # Get data sources - provide defaults if None
        user_id = usuario_id or ''
        user_role = rol_usuario or RolUsuario.OPERACIONES
        despachos = self._get_despachos_rango_fechas(primer_dia, ultimo_dia, user_id, user_role, filtros)
        hitos = self._get_hitos_rango_fechas(primer_dia, ultimo_dia, user_id, user_role)
        
        # Generate calendar structure
        cal = calendar.Calendar(firstweekday=0)  # Monday = 0
        dias_mes = list(cal.itermonthdays2(year, month))
        
        # Strategic analysis by periods (weeks within month)
        analisis_periodos = self._generar_analisis_semanal_en_mes(primer_dia, ultimo_dia, despachos, hitos)
        
        # Strategic KPIs and metrics
        kpis_estrategicos = self._calcular_kpis_estrategicos(despachos, hitos, 'mensual')
        
        # Navigation dates
        mes_anterior = primer_dia - relativedelta(months=1)
        mes_siguiente = primer_dia + relativedelta(months=1)
        
        # Unified strategic analysis structure
        return {
            'modo_analisis': 'mensual',
            'periodo_info': {
                'year': year,
                'month': month,
                'nombre_periodo': primer_dia.strftime('%B %Y'),
                'fecha_inicio': primer_dia,
                'fecha_fin': ultimo_dia,
                'dias_periodo': dias_mes
            },
            'navegacion': {
                'anterior': mes_anterior,
                'siguiente': mes_siguiente,
                'actual': primer_dia
            },
            'kpis_estrategicos': kpis_estrategicos,
            'analisis_periodos': analisis_periodos,
            'resumen_ejecutivo': self._generar_resumen_ejecutivo(kpis_estrategicos, 'mensual'),
            'tendencias': self._analizar_tendencias(despachos, hitos, 'mensual'),
            'alertas_estrategicas': self._identificar_alertas_estrategicas(despachos, hitos),
            'datos_detalle': {
                'total_registros': len(despachos) + len(hitos),
                'filtros_aplicados': filtros or {},
                'periodo_analisis_dias': (ultimo_dia - primer_dia).days + 1
            }
        }

    def get_analisis_semanal(self, year: int, month: int, day: int, usuario_id: Optional[str], rol_usuario: Optional[RolUsuario],
                           filtros: Optional[Dict] = None) -> Dict[str, Any]:
        """Strategic weekly analysis with unified field structure"""
        
        # Create date for the selected day
        fecha_referencia = date(year, month, day)
        
        # Calculate start of week (Monday)
        dias_desde_lunes = fecha_referencia.weekday()
        inicio_semana = fecha_referencia - timedelta(days=dias_desde_lunes)
        fin_semana = inicio_semana + timedelta(days=6)
        
        # Get data sources - provide defaults if None
        user_id = usuario_id or ''
        user_role = rol_usuario or RolUsuario.OPERACIONES
        despachos = self._get_despachos_rango_fechas(inicio_semana, fin_semana, user_id, user_role, filtros)
        hitos = self._get_hitos_rango_fechas(inicio_semana, fin_semana, user_id, user_role)
        
        # Strategic analysis by periods (days within week)
        analisis_periodos = self._generar_analisis_diario_en_semana(inicio_semana, fin_semana, despachos, hitos)
        
        # Strategic KPIs and metrics
        kpis_estrategicos = self._calcular_kpis_estrategicos(despachos, hitos, 'semanal')
        
        # Navigation dates
        semana_anterior = inicio_semana - timedelta(days=7)
        semana_siguiente = inicio_semana + timedelta(days=7)
        
        # Unified strategic analysis structure
        return {
            'modo_analisis': 'semanal',
            'periodo_info': {
                'year': year,
                'month': month,
                'day': day,
                'nombre_periodo': f"Semana del {inicio_semana.strftime('%d')} al {fin_semana.strftime('%d de %B %Y')}",
                'fecha_inicio': inicio_semana,
                'fecha_fin': fin_semana,
                'fecha_referencia': fecha_referencia
            },
            'navegacion': {
                'anterior': semana_anterior,
                'siguiente': semana_siguiente,
                'actual': inicio_semana
            },
            'kpis_estrategicos': kpis_estrategicos,
            'analisis_periodos': analisis_periodos,
            'resumen_ejecutivo': self._generar_resumen_ejecutivo(kpis_estrategicos, 'semanal'),
            'tendencias': self._analizar_tendencias(despachos, hitos, 'semanal'),
            'alertas_estrategicas': self._identificar_alertas_estrategicas(despachos, hitos),
            'datos_detalle': {
                'total_registros': len(despachos) + len(hitos),
                'filtros_aplicados': filtros or {},
                'periodo_analisis_dias': 7
            }
        }

    def _calcular_kpis_estrategicos(self, despachos: List[Despacho], hitos: List[HitoEntrega], modo: str) -> Dict[str, Any]:
        """Calculate strategic KPIs unified for both modes"""
        
        # Core metrics
        total_despachos = len(despachos)
        total_hitos = len(hitos)
        
        # Despacho analysis
        despachos_programados = len([d for d in despachos if d.estado.name == 'PROGRAMADO'])
        despachos_en_transporte = len([d for d in despachos if d.estado.name == 'EN_TRANSPORTE'])
        despachos_entregados = len([d for d in despachos if d.estado.name == 'ENTREGADO'])
        despachos_observados = len([d for d in despachos if d.estado.name == 'OBSERVADO'])
        
        # Hito analysis
        hitos_pendientes = len([h for h in hitos if h.estado == EstadoHitoEntrega.PENDIENTE])
        hitos_completados = len([h for h in hitos if h.estado == EstadoHitoEntrega.COMPLETADO])
        hitos_atrasados = len([h for h in hitos if h.estado == EstadoHitoEntrega.ATRASADO])
        
        # Strategic performance metrics
        tasa_cumplimiento_despachos = (despachos_entregados / total_despachos * 100) if total_despachos > 0 else 0
        tasa_cumplimiento_hitos = (hitos_completados / total_hitos * 100) if total_hitos > 0 else 0
        
        # Risk indicators
        riesgo_operacional = despachos_observados + hitos_atrasados
        indicador_eficiencia = ((despachos_entregados + hitos_completados) / (total_despachos + total_hitos) * 100) if (total_despachos + total_hitos) > 0 else 0
        
        # Project analysis
        proyectos_involucrados = set()
        for despacho in despachos:
            if hasattr(despacho, 'proyecto') and despacho.proyecto:
                proyectos_involucrados.add(despacho.proyecto.id)
        for hito in hitos:
            if (hasattr(hito, 'plan_entrega') and hito.plan_entrega and 
                hasattr(hito.plan_entrega, 'contrato') and hito.plan_entrega.contrato and 
                hasattr(hito.plan_entrega.contrato, 'proyecto') and hito.plan_entrega.contrato.proyecto):
                proyectos_involucrados.add(hito.plan_entrega.contrato.proyecto.id)
        
        return {
            'volumenes': {
                'total_actividades': total_despachos + total_hitos,
                'total_despachos': total_despachos,
                'total_hitos': total_hitos,
                'proyectos_activos': len(proyectos_involucrados)
            },
            'estado_despachos': {
                'programados': despachos_programados,
                'en_transporte': despachos_en_transporte,  
                'entregados': despachos_entregados,
                'observados': despachos_observados
            },
            'estado_hitos': {
                'pendientes': hitos_pendientes,
                'completados': hitos_completados,
                'atrasados': hitos_atrasados
            },
            'indicadores_rendimiento': {
                'tasa_cumplimiento_despachos': round(tasa_cumplimiento_despachos, 1),
                'tasa_cumplimiento_hitos': round(tasa_cumplimiento_hitos, 1),
                'indicador_eficiencia_global': round(indicador_eficiencia, 1),
                'nivel_riesgo_operacional': riesgo_operacional
            },
            'clasificacion_rendimiento': self._clasificar_rendimiento(indicador_eficiencia, riesgo_operacional)
        }

    def _generar_analisis_semanal_en_mes(self, inicio: date, fin: date, despachos: List[Despacho], hitos: List[HitoEntrega]) -> List[Dict[str, Any]]:
        """Generate weekly analysis within month for strategic view"""
        
        semanas = []
        fecha_actual = inicio
        
        while fecha_actual <= fin:
            # Find start of week
            dias_desde_lunes = fecha_actual.weekday()
            inicio_semana = fecha_actual - timedelta(days=dias_desde_lunes)
            fin_semana = inicio_semana + timedelta(days=6)
            
            # Limit to month boundaries
            inicio_periodo = max(inicio_semana, inicio)
            fin_periodo = min(fin_semana, fin)
            
            # Filter data for this week
            despachos_semana = [d for d in despachos if inicio_periodo <= d.fecha_programada <= fin_periodo]
            hitos_semana = [h for h in hitos if inicio_periodo <= h.fecha_programada <= fin_periodo]
            
            # Strategic metrics for this week
            actividades_totales = len(despachos_semana) + len(hitos_semana)
            
            semana_info = {
                'periodo': f"Semana {inicio_periodo.strftime('%d')} - {fin_periodo.strftime('%d')}",
                'fecha_inicio': inicio_periodo,
                'fecha_fin': fin_periodo,
                'actividades_totales': actividades_totales,
                'despachos_count': len(despachos_semana),
                'hitos_count': len(hitos_semana),
                'carga_trabajo': self._evaluar_carga_trabajo(actividades_totales),
                'criticidad': self._evaluar_criticidad_periodo(despachos_semana, hitos_semana)
            }
            
            semanas.append(semana_info)
            
            # Move to next week
            fecha_actual = fin_semana + timedelta(days=1)
            if fecha_actual > fin:
                break
                
        return semanas

    def _generar_analisis_diario_en_semana(self, inicio: date, fin: date, despachos: List[Despacho], hitos: List[HitoEntrega]) -> List[Dict[str, Any]]:
        """Generate daily analysis within week for strategic view"""
        
        dias = []
        
        for i in range(7):
            dia_actual = inicio + timedelta(days=i)
            
            # Filter data for this day
            despachos_dia = [d for d in despachos if d.fecha_programada == dia_actual]
            hitos_dia = [h for h in hitos if h.fecha_programada == dia_actual]
            
            actividades_totales = len(despachos_dia) + len(hitos_dia)
            
            dia_info = {
                'periodo': dia_actual.strftime('%A %d'),
                'fecha': dia_actual,
                'numero_dia': dia_actual.day,
                'nombre_dia': dia_actual.strftime('%A'),
                'nombre_dia_corto': dia_actual.strftime('%a'),
                'es_hoy': dia_actual == date.today(),
                'actividades_totales': actividades_totales,
                'despachos_count': len(despachos_dia),
                'hitos_count': len(hitos_dia),
                'carga_trabajo': self._evaluar_carga_trabajo(actividades_totales),
                'criticidad': self._evaluar_criticidad_periodo(despachos_dia, hitos_dia)
            }
            
            dias.append(dia_info)
            
        return dias

    def _generar_resumen_ejecutivo(self, kpis: Dict[str, Any], modo: str) -> Dict[str, Any]:
        """Generate executive summary for strategic analysis"""
        
        eficiencia = kpis['indicadores_rendimiento']['indicador_eficiencia_global']
        riesgo = kpis['indicadores_rendimiento']['nivel_riesgo_operacional']
        actividades = kpis['volumenes']['total_actividades']
        
        # Determine status
        if eficiencia >= 90:
            estado_general = 'excelente'
            mensaje = f"Rendimiento excepcional con {eficiencia}% de eficiencia"
        elif eficiencia >= 70:
            estado_general = 'bueno'
            mensaje = f"Buen rendimiento con {eficiencia}% de eficiencia"
        elif eficiencia >= 50:
            estado_general = 'regular'
            mensaje = f"Rendimiento regular con {eficiencia}% de eficiencia - requiere atención"
        else:
            estado_general = 'critico'
            mensaje = f"Rendimiento crítico con {eficiencia}% de eficiencia - acción urgente requerida"
        
        return {
            'estado_general': estado_general,
            'mensaje_principal': mensaje,
            'actividades_periodo': actividades,
            'eficiencia_global': eficiencia,
            'nivel_riesgo': riesgo,
            'recomendacion_accion': self._generar_recomendacion(estado_general, riesgo)
        }

    def _analizar_tendencias(self, despachos: List[Despacho], hitos: List[HitoEntrega], modo: str) -> Dict[str, Any]:
        """Analyze trends for strategic insights"""
        
        # This is a simplified trend analysis - in real implementation you'd compare with previous periods
        return {
            'volumen_actividades': 'estable',  # Would compare with previous period
            'tasa_cumplimiento': 'mejorando',  # Based on historical data
            'riesgo_operacional': 'controlado',  # Based on current indicators
            'proyeccion': f'Mantener ritmo actual para el próximo {modo.lower()}'
        }

    def _identificar_alertas_estrategicas(self, despachos: List[Despacho], hitos: List[HitoEntrega]) -> List[Dict[str, Any]]:
        """Identify strategic alerts that require attention"""
        
        alertas = []
        
        # Check for overdue dispatches
        despachos_vencidos = [d for d in despachos if d.fecha_programada < date.today() and d.estado.name == 'PROGRAMADO']
        if despachos_vencidos:
            alertas.append({
                'tipo': 'despachos_vencidos',
                'nivel': 'alto',
                'cantidad': len(despachos_vencidos),
                'mensaje': f"{len(despachos_vencidos)} despachos vencidos requieren atención inmediata"
            })
        
        # Check for overdue milestones
        hitos_vencidos = [h for h in hitos if h.fecha_programada < date.today() and h.estado == EstadoHitoEntrega.PENDIENTE]
        if hitos_vencidos:
            alertas.append({
                'tipo': 'hitos_vencidos', 
                'nivel': 'alto',
                'cantidad': len(hitos_vencidos),
                'mensaje': f"{len(hitos_vencidos)} hitos vencidos impactan compromisos con clientes"
            })
        
        # Check for observed dispatches
        despachos_observados = [d for d in despachos if d.estado.name == 'OBSERVADO']
        if despachos_observados:
            alertas.append({
                'tipo': 'despachos_observados',
                'nivel': 'medio',
                'cantidad': len(despachos_observados),
                'mensaje': f"{len(despachos_observados)} despachos con observaciones necesitan revisión"
            })
        
        return alertas

    def _evaluar_carga_trabajo(self, actividades: int) -> str:
        """Evaluate workload level"""
        if actividades == 0:
            return 'libre'
        elif actividades <= 2:
            return 'baja'
        elif actividades <= 5:
            return 'media'
        elif actividades <= 8:
            return 'alta'
        else:
            return 'critica'

    def _evaluar_criticidad_periodo(self, despachos: List[Despacho], hitos: List[HitoEntrega]) -> str:
        """Evaluate period criticality"""
        
        criticidad_score = 0
        
        # Add points for various factors
        for despacho in despachos:
            if despacho.estado.name == 'OBSERVADO':
                criticidad_score += 3
            elif despacho.estado.name == 'EN_TRANSPORTE':
                criticidad_score += 1
        
        for hito in hitos:
            if hito.estado == EstadoHitoEntrega.ATRASADO:
                criticidad_score += 3
            elif hito.estado == EstadoHitoEntrega.PENDIENTE:
                criticidad_score += 1
        
        if criticidad_score == 0:
            return 'baja'
        elif criticidad_score <= 2:
            return 'media'
        elif criticidad_score <= 5:
            return 'alta'
        else:
            return 'critica'

    def _clasificar_rendimiento(self, eficiencia: float, riesgo: int) -> str:
        """Classify performance level"""
        if eficiencia >= 90 and riesgo == 0:
            return 'excelente'
        elif eficiencia >= 70 and riesgo <= 2:
            return 'bueno'
        elif eficiencia >= 50:
            return 'regular'
        else:
            return 'critico'

    def _generar_recomendacion(self, estado: str, riesgo: int) -> str:
        """Generate action recommendation"""
        if estado == 'excelente':
            return 'Mantener el excelente desempeño actual'
        elif estado == 'bueno':
            return 'Continuar con las prácticas actuales, monitorear tendencias'
        elif estado == 'regular':
            return 'Revisar procesos y identificar oportunidades de mejora'
        else:
            return 'Acción correctiva inmediata requerida - revisar operaciones críticas'

    # Helper methods - reuse from CalendarioService with access control
    
    def _get_despachos_rango_fechas(self, fecha_inicio: date, fecha_fin: date, usuario_id: str, rol_usuario: RolUsuario, 
                                   filtros: Optional[Dict] = None) -> List[Despacho]:
        """Get despachos for date range with user access control"""
        
        # Build base query with access control  
        if rol_usuario == RolUsuario.ADMIN:
            query = db.session.query(Despacho)
        elif rol_usuario == RolUsuario.VENTAS:
            # Sales can only see their own clients' despachos
            query = (db.session.query(Despacho)
                    .join(Proyecto)
                    .join(Cliente)
                    .filter(Cliente.vendedor_id == usuario_id))
        else:
            # Operations, Production, Logistics can see all despachos
            query = db.session.query(Despacho)

        # Apply date filters
        query = query.filter(
            and_(
                Despacho.fecha_programada >= fecha_inicio,
                Despacho.fecha_programada <= fecha_fin
            )
        )

        # Apply additional filters if provided
        if filtros:
            if filtros.get('estado'):
                try:
                    estado_enum = EstadoDespacho(filtros['estado'])
                    query = query.filter(Despacho.estado == estado_enum)
                except (ValueError, AttributeError):
                    pass

            if filtros.get('responsable_nombre'):
                query = query.filter(Despacho.responsable_nombre.ilike(f"%{filtros['responsable_nombre']}%"))

            if filtros.get('numero_despacho'):
                query = query.filter(Despacho.numero_despacho.ilike(f"%{filtros['numero_despacho']}%"))

            if filtros.get('proyecto_id'):
                query = query.filter(Despacho.proyecto_id == filtros['proyecto_id'])

        # Join with proyecto and cliente for additional info
        query = query.options(
            db.selectinload(Despacho.proyecto).selectinload(Proyecto.cliente)
        )

        return query.order_by(Despacho.fecha_programada).all()

    def _get_hitos_rango_fechas(self, fecha_inicio: date, fecha_fin: date, usuario_id: str, rol_usuario: RolUsuario) -> List[HitoEntrega]:
        """Get hitos de entrega for date range with user access control"""
        
        # Build base query with access control
        if rol_usuario == RolUsuario.ADMIN:
            query = db.session.query(HitoEntrega)
        elif rol_usuario == RolUsuario.VENTAS:
            # Sales can only see their own clients' hitos
            query = (db.session.query(HitoEntrega)
                    .join(PlanEntrega)
                    .join(Contrato)
                    .join(Proyecto)
                    .join(Cliente)
                    .filter(Cliente.vendedor_id == usuario_id))
        else:
            # Operations, Production, Logistics can see all hitos
            query = db.session.query(HitoEntrega)

        # Apply date filters
        query = query.filter(
            and_(
                HitoEntrega.fecha_programada >= fecha_inicio,
                HitoEntrega.fecha_programada <= fecha_fin
            )
        )

        # Join with plan_entrega, contrato, proyecto for additional info
        query = query.options(
            db.selectinload(HitoEntrega.plan_entrega).selectinload(PlanEntrega.contrato).selectinload(Contrato.proyecto).selectinload(Proyecto.cliente)
        )

        return query.order_by(HitoEntrega.fecha_programada).all()