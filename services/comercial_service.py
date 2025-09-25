from typing import List, Dict, Any, Optional
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, or_, func, extract, case
from sqlalchemy.orm import joinedload
from decimal import Decimal
import calendar

from app import db
from models import (
    Proyecto, Cliente, User, TareaComercial, ObjetivoMensual,
    EstadoComercial, RolUsuario
)
from services.revenue_service import RevenueService


class ComercialService:
    """Service layer for commercial operations"""

    def get_centro_vendedores_data(self, current_user_id, cliente_id=None, vendedor_id=None, estado_comercial=None):
        """Get data for sales center dashboard"""
        from flask_login import current_user

        # Build base query
        query = db.session.query(Proyecto).join(Cliente)

        # For non-admin users, only show their own projects
        if current_user.rol.value != 'admin':
            query = query.filter(Proyecto.vendedor_id == current_user_id)

        # Apply filters
        if cliente_id:
            query = query.filter(Proyecto.cliente_id == cliente_id)

        if vendedor_id and current_user.rol.value == 'admin':
            query = query.filter(Proyecto.vendedor_id == vendedor_id)

        if estado_comercial:
            query = query.filter(Proyecto.estado_comercial == EstadoComercial(estado_comercial))

        # Get projects
        proyectos = query.order_by(Proyecto.updated_at.desc()).all()

        # Get filter options
        clientes = db.session.query(Cliente).filter_by(activo=True).order_by(Cliente.nombre).all()
        vendedores = self._get_vendedores()

        # Calculate statistics
        stats = self._calcular_estadisticas_centro(proyectos)

        # Group projects by commercial state
        proyectos_por_estado = self._agrupar_proyectos_por_estado(proyectos)

        return {
            'proyectos': proyectos,
            'proyectos_por_estado': proyectos_por_estado,
            'clientes': clientes,
            'vendedores': vendedores,
            'estadios_comerciales': EstadoComercial,
            'stats': stats,
            'filtros': {
                'cliente_id': cliente_id,
                'vendedor_id': vendedor_id,
                'estado_comercial': estado_comercial
            }
        }

    def get_vendedores_estadisticas(self):
        """Get salespeople with their statistics"""
        vendedores = self._get_vendedores()

        vendedores_stats = []
        for vendedor in vendedores:
            stats = self._calcular_estadisticas_vendedor(vendedor.id)
            vendedores_stats.append({
                'vendedor': vendedor,
                'stats': stats
            })

        return vendedores_stats

    def get_vendedor_detalle(self, vendedor_id):
        """Get detailed information for a specific salesperson"""
        vendedor = db.session.get(User, vendedor_id)
        if not vendedor:
            return None

        # Get salesperson's projects
        proyectos = (db.session.query(Proyecto)
                    .join(Cliente)
                    .filter(Proyecto.vendedor_id == vendedor_id)
                    .order_by(Proyecto.updated_at.desc())
                    .all())

        # Get pending tasks
        tareas_pendientes = (db.session.query(TareaComercial)
                           .filter_by(vendedor_id=vendedor_id, completada=False)
                           .order_by(TareaComercial.fecha_limite.asc())
                           .all())

        # Calculate statistics
        stats = self._calcular_estadisticas_vendedor(vendedor_id)

        return {
            'vendedor': vendedor,
            'proyectos': proyectos,
            'tareas_pendientes': tareas_pendientes,
            'stats': stats
        }

    def get_proyecto_comercial_data(self, proyecto_id):
        """Get commercial data for a specific project"""
        proyecto = (db.session.query(Proyecto)
                   .join(Cliente)
                   .filter(Proyecto.id == proyecto_id)
                   .first())

        if not proyecto:
            return None

        # Get project's commercial tasks
        tareas = (db.session.query(TareaComercial)
                 .filter_by(proyecto_id=proyecto_id)
                 .order_by(TareaComercial.created_at.desc())
                 .all())

        # Get available salespeople
        vendedores = self._get_vendedores()

        return {
            'proyecto': proyecto,
            'tareas': tareas,
            'vendedores': vendedores,
            'estados_comerciales': EstadoComercial
        }

    def actualizar_comercial_proyecto(self, proyecto_id, data, user_id):
        """Update commercial information for a project"""
        try:
            proyecto = db.session.get(Proyecto, proyecto_id)
            if not proyecto:
                return False

            # Update fields
            if data.get('vendedor_id'):
                proyecto.vendedor_id = data['vendedor_id']

            if data.get('estado_comercial'):
                nuevo_estado = EstadoComercial(data['estado_comercial'])
                # If state changes to PRESUPUESTADO or ADJUDICADO, set date
                if nuevo_estado != proyecto.estado_comercial:
                    proyecto.estado_comercial = nuevo_estado

                    if nuevo_estado == EstadoComercial.PRESUPUESTADO and not proyecto.fecha_presupuesto:
                        proyecto.fecha_presupuesto = date.today()
                    elif nuevo_estado == EstadoComercial.ADJUDICADO and not proyecto.fecha_adjudicacion:
                        proyecto.fecha_adjudicacion = date.today()

            # Update commercial values
            if data.get('valor_presupuestado_provision'):
                proyecto.monto_provision_presupuestado = Decimal(data['valor_presupuestado_provision'])

            if data.get('margen_venta_provision'):
                proyecto.margen_venta_provision = Decimal(data['margen_venta_provision'])

            # Handle both possible field names for backward compatibility
            instalacion_value = data.get('monto_instalacion_presupuestado') or data.get('valor_instalacion')
            if instalacion_value:
                proyecto.monto_instalacion_presupuestado = Decimal(instalacion_value)

            if data.get('margen_venta_instalacion'):
                proyecto.margen_venta_instalacion = Decimal(data['margen_venta_instalacion'])

            # Update dates if provided
            if data.get('fecha_presupuesto'):
                proyecto.fecha_presupuesto = datetime.strptime(data['fecha_presupuesto'], '%Y-%m-%d').date()

            if data.get('fecha_adjudicacion'):
                proyecto.fecha_adjudicacion = datetime.strptime(data['fecha_adjudicacion'], '%Y-%m-%d').date()

            if data.get('notas_comerciales'):
                proyecto.notas_comerciales = data['notas_comerciales']

            # Create automatic commercial task if needed
            self._crear_tarea_automatica(proyecto, user_id)

            db.session.commit()
            return True

        except Exception as e:
            db.session.rollback()
            raise e

    def get_tareas_comerciales(self, vendedor_id=None, estado=None):
        """Get commercial tasks with filters"""
        query = db.session.query(TareaComercial).join(Proyecto).join(Cliente)

        if vendedor_id:
            query = query.filter(TareaComercial.vendedor_id == vendedor_id)

        if estado == 'pendientes':
            query = query.filter(TareaComercial.completada == False)
        elif estado == 'completadas':
            query = query.filter(TareaComercial.completada == True)

        tareas = query.order_by(TareaComercial.fecha_limite.asc()).all()

        return {
            'tareas': tareas,
            'vendedores': self._get_vendedores(),
            'filtros': {
                'vendedor_id': vendedor_id,
                'estado': estado
            }
        }

    def completar_tarea(self, tarea_id, user_id, notas=None):
        """Mark a task as completed"""
        try:
            tarea = db.session.get(TareaComercial, tarea_id)
            if not tarea:
                return False

            tarea.completada = True
            tarea.fecha_completada = datetime.now()

            if notas:
                tarea.notas = notas

            db.session.commit()
            return True

        except Exception as e:
            db.session.rollback()
            raise e

    def crear_tarea_comercial(self, data, user_id):
        """Create a new commercial task"""
        try:
            tarea = TareaComercial()
            tarea.proyecto_id = data['proyecto_id']
            tarea.vendedor_id = data['vendedor_id']
            tarea.titulo = data['titulo']
            tarea.descripcion = data.get('descripcion')
            tarea.fecha_limite = datetime.strptime(data['fecha_limite'], '%Y-%m-%d').date() if data.get('fecha_limite') else None
            tarea.created_by = user_id

            db.session.add(tarea)
            db.session.commit()
            return tarea

        except Exception as e:
            db.session.rollback()
            raise e

    def get_planificacion_comercial(self, año, mes_inicio=1, cliente_id=None, estado_filter='todos'):
        """Get commercial planning matrix by year or 12-month rolling period"""

        # Build query for projects with proper joins and eager loading
        query = (db.session.query(Proyecto)
                .options(
                    joinedload(Proyecto.cliente),
                    joinedload(Proyecto.vendedor_user)
                )
                .join(Cliente)
                .filter(Proyecto.activo == True))

        # Calculate date range for 12 months starting from mes_inicio
        if mes_inicio == 1:
            # Traditional year view (January to December)
            fecha_inicio = date(año, 1, 1)
            fecha_fin = date(año, 12, 31)
        else:
            # Rolling 12-month view
            fecha_inicio = date(año, mes_inicio, 1)
            # Calculate end date (12 months from start)
            if mes_inicio <= 12:
                if mes_inicio + 11 <= 12:
                    fecha_fin = date(año, mes_inicio + 11, calendar.monthrange(año, mes_inicio + 11)[1])
                else:
                    # Cross into next year
                    mes_fin = (mes_inicio + 11) % 12
                    if mes_fin == 0:
                        mes_fin = 12
                    año_fin = año + 1 if mes_inicio + 11 > 12 else año
                    fecha_fin = date(año_fin, mes_fin, calendar.monthrange(año_fin, mes_fin)[1])
            else:
                fecha_fin = date(año + 1, mes_inicio - 1, calendar.monthrange(año + 1, mes_inicio - 1)[1])

        query = query.filter(
            or_(
                and_(Proyecto.fecha_inicio.isnot(None), 
                     Proyecto.fecha_inicio <= fecha_fin,
                     or_(Proyecto.fecha_fin_estimada.is_(None),
                         Proyecto.fecha_fin_estimada >= fecha_inicio)),
                and_(Proyecto.fecha_fin_estimada.isnot(None), 
                     Proyecto.fecha_fin_estimada >= fecha_inicio,
                     Proyecto.fecha_fin_estimada <= fecha_fin),
                # Include projects with commercial info but no dates
                and_(Proyecto.fecha_inicio.is_(None),
                     Proyecto.fecha_fin_estimada.is_(None),
                     or_(Proyecto.monto_provision_presupuestado.isnot(None),
                         Proyecto.monto_instalacion_presupuestado.isnot(None)))
            )
        )

        # Apply additional filters
        if cliente_id:
            query = query.filter(Proyecto.cliente_id == cliente_id)

        if estado_filter == 'presupuestado':
            query = query.filter(Proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO)
        elif estado_filter == 'adjudicado':
            query = query.filter(Proyecto.estado_comercial == EstadoComercial.ADJUDICADO)
        elif estado_filter != 'todos':
            query = query.filter(Proyecto.estado_comercial.in_([
                EstadoComercial.PRESUPUESTADO, 
                EstadoComercial.ADJUDICADO
            ]))

        # Get projects as model objects - force explicit object loading
        proyectos_query_result = query.all()

        # Verify we have proper Proyecto objects
        proyectos = []
        for item in proyectos_query_result:
            if isinstance(item, Proyecto):
                proyectos.append(item)
            else:
                print(f"WARNING: Query returned non-Proyecto object: {type(item)}")
                # Try to get the actual Proyecto object if this is a tuple or other structure
                if hasattr(item, 'Proyecto'):
                    proyectos.append(item.Proyecto)
                elif isinstance(item, (tuple, list)) and len(item) > 0:
                    if isinstance(item[0], Proyecto):
                        proyectos.append(item[0])

        print(f"DEBUG: Final proyectos count: {len(proyectos)}, types: {[type(p) for p in proyectos[:3]]}")

        # Build monthly matrix for 12-month period
        matriz = self._construir_matriz_mensual_periodo(proyectos, año, mes_inicio)

        # Calculate totals per month
        totales_mes = self._calcular_totales_mensuales(matriz)

        # Get monthly objectives for the period
        objetivos = self._get_objetivos_periodo(año, mes_inicio)

        # Get filter options
        clientes = db.session.query(Cliente).filter_by(activo=True).order_by(Cliente.nombre).all()

        # Calculate grand totals
        # Calculate grand totals with the new structure
        gran_totales = self._calcular_gran_totales_nueva_estructura(matriz, objetivos)

        return {
            'año': año,
            'mes_inicio': mes_inicio,
            'matriz': matriz,
            'totales_mes': totales_mes,
            'objetivos': objetivos,
            'proyectos': proyectos,
            'clientes': clientes,
            'gran_totales': gran_totales,
            'filtros': {
                'cliente_id': cliente_id,
                'estado_filter': estado_filter
            }
        }

    def get_objetivos_mensuales(self, año):
        """Get monthly objectives for a year"""
        objetivos = (db.session.query(ObjetivoMensual)
                    .filter_by(año=año)
                    .order_by(ObjetivoMensual.mes)
                    .all())

        # Create objectives dict by month
        objetivos_dict = {}
        for obj in objetivos:
            objetivos_dict[obj.mes] = obj

        return {
            'año': año,
            'objetivos': objetivos_dict,
            'meses': [(i, calendar.month_name[i]) for i in range(1, 13)]
        }

    def actualizar_objetivos_mensuales(self, año, objetivos_data, user_id):
        """Update monthly objectives"""
        try:
            for data in objetivos_data:
                mes = data['mes']

                # Find or create objective
                objetivo = (db.session.query(ObjetivoMensual)
                           .filter_by(año=año, mes=mes)
                           .first())

                if not objetivo:
                    objetivo = ObjetivoMensual()
                    objetivo.año = año
                    objetivo.mes = mes
                    objetivo.created_by = user_id
                    db.session.add(objetivo)

                # Update values
                if data.get('objetivo_provision'):
                    objetivo.objetivo_provision = Decimal(data['objetivo_provision'])

                if data.get('objetivo_instalacion'):
                    objetivo.objetivo_instalacion = Decimal(data['objetivo_instalacion'])

            db.session.commit()
            return True

        except Exception as e:
            db.session.rollback()
            raise e

    # Private helper methods

    def _get_vendedores(self):
        """Get users with sales role"""
        return (db.session.query(User)
                .filter(User.rol.in_([RolUsuario.VENTAS, RolUsuario.ADMIN]))
                .filter_by(activo=True)
                .order_by(User.first_name, User.last_name)
                .all())

    def _calcular_estadisticas_centro(self, proyectos):
        """Calculate statistics for sales center"""
        total = len(proyectos)

        stats = {
            'total_proyectos': total,
            'pendiente_presupuesto': 0,
            'presupuestado': 0,
            'adjudicado': 0,
            'terminado': 0,
            'valor_total_provision': Decimal('0'),
            'valor_total_instalacion': Decimal('0'),
            'margen_promedio_provision': Decimal('0'),
            'margen_promedio_instalacion': Decimal('0')
        }

        if not proyectos:
            return stats

        valores_provision = []
        valores_instalacion = []
        margenes_provision = []
        margenes_instalacion = []

        for proyecto in proyectos:
            # Count by state
            estado = proyecto.estado_comercial
            if estado == EstadoComercial.PENDIENTE_PRESUPUESTO:
                stats['pendiente_presupuesto'] += 1
            elif estado == EstadoComercial.PRESUPUESTADO:
                stats['presupuestado'] += 1
            elif estado == EstadoComercial.ADJUDICADO:
                stats['adjudicado'] += 1
            elif estado == EstadoComercial.TERMINADO:
                stats['terminado'] += 1

            # Accumulate values
            if proyecto.monto_provision_presupuestado:
                stats['valor_total_provision'] += proyecto.monto_provision_presupuestado
                valores_provision.append(proyecto.monto_provision_presupuestado)

                if proyecto.margen_venta_provision:
                    margenes_provision.append(proyecto.margen_venta_provision)

            if proyecto.monto_instalacion_presupuestado:
                stats['valor_total_instalacion'] += proyecto.monto_instalacion_presupuestado
                valores_instalacion.append(proyecto.monto_instalacion_presupuestado)

                if proyecto.margen_venta_instalacion:
                    margenes_instalacion.append(proyecto.margen_venta_instalacion)

        # Calculate average margins
        if margenes_provision:
            stats['margen_promedio_provision'] = sum(margenes_provision) / len(margenes_provision)

        if margenes_instalacion:
            stats['margen_promedio_instalacion'] = sum(margenes_instalacion) / len(margenes_instalacion)

        return stats

    def _calcular_estadisticas_vendedor(self, vendedor_id):
        """Calculate statistics for a specific salesperson"""
        proyectos = (db.session.query(Proyecto)
                    .filter_by(vendedor_id=vendedor_id)
                    .all())

        tareas_pendientes = (db.session.query(TareaComercial)
                           .filter_by(vendedor_id=vendedor_id, completada=False)
                           .count())

        stats = self._calcular_estadisticas_centro(proyectos)
        stats['tareas_pendientes'] = tareas_pendientes

        # Calcular estadísticas de éxito
        stats_exito = self._calcular_estadisticas_exito(vendedor_id)
        stats.update(stats_exito)

        # Calcular comisiones mensuales
        stats['comisiones_mensuales'] = self._calcular_comisiones_mensuales(vendedor_id)

        # Calcular comisiones potenciales
        stats['comisiones_potenciales'] = self._calcular_comisiones_potenciales(vendedor_id)

        return stats

    def _calcular_estadisticas_exito(self, vendedor_id):
        """Calculate success statistics for a salesperson"""
        # Estadísticas generales
        total_proyectos = (db.session.query(Proyecto)
                          .filter_by(vendedor_id=vendedor_id, activo=True)
                          .count())

        adjudicados = (db.session.query(Proyecto)
                      .filter_by(vendedor_id=vendedor_id, activo=True)
                      .filter(Proyecto.estado_comercial.in_([
                          EstadoComercial.ADJUDICADO,
                          EstadoComercial.EN_DESARROLLO,
                          EstadoComercial.TERMINADO
                      ]))
                      .count())

        porcentaje_exito_general = (adjudicados / total_proyectos * 100) if total_proyectos > 0 else 0

        # Estadísticas por cliente
        exito_por_cliente = []
        clientes_query = (db.session.query(Cliente.id, Cliente.nombre,
                                          func.count(Proyecto.id).label('total_proyectos'),
                                          func.sum(case((Proyecto.estado_comercial.in_([
                                              EstadoComercial.ADJUDICADO,
                                              EstadoComercial.EN_DESARROLLO,
                                              EstadoComercial.TERMINADO
                                          ]), 1), else_=0)).label('adjudicados'))
                         .join(Proyecto)
                         .filter(Proyecto.vendedor_id == vendedor_id, Proyecto.activo == True)
                         .group_by(Cliente.id, Cliente.nombre)
                         .all())

        for cliente_id, nombre_cliente, total, adjudicados_cliente in clientes_query:
            porcentaje_exito_cliente = (adjudicados_cliente / total * 100) if total > 0 else 0
            exito_por_cliente.append({
                'cliente_id': cliente_id,
                'nombre_cliente': nombre_cliente,
                'total_proyectos': total,
                'adjudicados': adjudicados_cliente,
                'porcentaje_exito': porcentaje_exito_cliente
            })

        return {
            'total_proyectos_vendedor': total_proyectos,
            'adjudicados_vendedor': adjudicados,
            'porcentaje_exito_general': porcentaje_exito_general,
            'exito_por_cliente': exito_por_cliente
        }

    def _calcular_comisiones_mensuales(self, vendedor_id, year=None):
        """Calculate monthly commissions for a salesperson"""
        from services.configuraciones_service import ConfiguracionesService
        from datetime import datetime
        import calendar

        if year is None:
            year = datetime.now().year

        config_service = ConfiguracionesService()
        comision_config = config_service.get_comision_vendedor(vendedor_id)

        if not comision_config:
            return []

        comisiones_mensuales = []

        for mes in range(1, 13):
            # Obtener proyectos que generan comisiones adjudicadas
            # Estados: ADJUDICADO, EN_DESARROLLO, TERMINADO
            proyectos_mes = (db.session.query(Proyecto)
                           .filter(
                               Proyecto.vendedor_id == vendedor_id,
                               Proyecto.estado_comercial.in_([
                                   EstadoComercial.ADJUDICADO,
                                   EstadoComercial.EN_DESARROLLO,
                                   EstadoComercial.TERMINADO
                               ]),
                               Proyecto.activo == True
                           )
                           .filter(
                               or_(
                                   # Proyectos con fecha de adjudicación en este mes/año
                                   and_(
                                       Proyecto.fecha_adjudicacion.isnot(None),
                                       extract('year', Proyecto.fecha_adjudicacion) == year,
                                       extract('month', Proyecto.fecha_adjudicacion) == mes
                                   ),
                                   # Proyectos sin fecha de adjudicación pero en estado correcto (asignar al mes actual)
                                   and_(
                                       Proyecto.fecha_adjudicacion.is_(None),
                                       mes == datetime.now().month,
                                       year == datetime.now().year
                                   )
                               )
                           )
                           .all())

            comision_provision_mes = Decimal('0')
            comision_instalacion_mes = Decimal('0')
            total_proyectos_mes = len(proyectos_mes)

            for proyecto in proyectos_mes:
                if proyecto.monto_provision_presupuestado:
                    comision_provision_mes += (proyecto.monto_provision_presupuestado * 
                                              comision_config.comision_provision_pct / 100)

                if proyecto.monto_instalacion_presupuestado:
                    comision_instalacion_mes += (proyecto.monto_instalacion_presupuestado * 
                                                comision_config.comision_instalacion_pct / 100)

            comision_total_mes = comision_provision_mes + comision_instalacion_mes

            comisiones_mensuales.append({
                'mes': mes,
                'mes_nombre': calendar.month_name[mes],
                'comision_provision': float(comision_provision_mes),
                'comision_instalacion': float(comision_instalacion_mes),
                'comision_total': float(comision_total_mes),
                'proyectos_adjudicados': total_proyectos_mes
            })

        return comisiones_mensuales

    def _calcular_comisiones_potenciales(self, vendedor_id):
        """Calculate potential commissions from budgeted projects"""
        from services.configuraciones_service import ConfiguracionesService

        config_service = ConfiguracionesService()
        comision_config = config_service.get_comision_vendedor(vendedor_id)

        if not comision_config:
            return {
                'comision_provision_potencial': 0,
                'comision_instalacion_potencial': 0,
                'comision_total_potencial': 0,
                'proyectos_presupuestados': 0
            }

        # Obtener proyectos presupuestados (no adjudicados aún)
        proyectos_presupuestados = (db.session.query(Proyecto)
                                  .filter_by(vendedor_id=vendedor_id, activo=True)
                                  .filter(Proyecto.estado_comercial == EstadoComercial.PRESUPUESTADO)
                                  .all())

        comision_provision_potencial = Decimal('0')
        comision_instalacion_potencial = Decimal('0')

        for proyecto in proyectos_presupuestados:
            if proyecto.monto_provision_presupuestado:
                comision_provision_potencial += (proyecto.monto_provision_presupuestado * 
                                                comision_config.comision_provision_pct / 100)

            if proyecto.monto_instalacion_presupuestado:
                comision_instalacion_potencial += (proyecto.monto_instalacion_presupuestado * 
                                                  comision_config.comision_instalacion_pct / 100)

        return {
            'comision_provision_potencial': float(comision_provision_potencial),
            'comision_instalacion_potencial': float(comision_instalacion_potencial),
            'comision_total_potencial': float(comision_provision_potencial + comision_instalacion_potencial),
            'proyectos_presupuestados': len(proyectos_presupuestados)
        }

    def _agrupar_proyectos_por_estado(self, proyectos):
        """Group projects by commercial state"""
        grupos = {}

        for estado in EstadoComercial:
            grupos[estado.value] = {
                'estado': estado,
                'proyectos': [p for p in proyectos if p.estado_comercial == estado]
            }

        return grupos

    def _crear_tarea_automatica(self, proyecto, user_id):
        """Create automatic commercial task based on project state"""
        if not proyecto.vendedor_id:
            return

        # Check if we need to create tasks based on commercial state
        estado = proyecto.estado_comercial

        if estado == EstadoComercial.PENDIENTE_PRESUPUESTO:
            # Check if task already exists
            existing = (db.session.query(TareaComercial)
                       .filter_by(proyecto_id=proyecto.id, 
                                 titulo="Agregar información comercial")
                       .filter_by(completada=False)
                       .first())

            if not existing:
                tarea = TareaComercial()
                tarea.proyecto_id = proyecto.id
                tarea.vendedor_id = proyecto.vendedor_id
                tarea.titulo = "Agregar información comercial"
                tarea.descripcion = "Completar valor de provisión, margen de venta y valor de instalación (si aplica)"
                tarea.created_by = user_id
                db.session.add(tarea)

    def _construir_matriz_mensual_periodo(self, proyectos, año, mes_inicio=1):
        """Build monthly matrix with project data for 12-month period"""
        matriz = {}

        # Build 12 months starting from mes_inicio
        for i in range(12):
            mes_actual = mes_inicio + i
            año_actual = año

            # Handle year rollover
            if mes_actual > 12:
                mes_actual = mes_actual - 12
                año_actual = año + 1

            matriz[f"{año_actual}-{mes_actual:02d}"] = {
                'mes': mes_actual,
                'año': año_actual,
                'mes_nombre': calendar.month_name[mes_actual],
                'periodo_label': f"{calendar.month_name[mes_actual][:3]} {año_actual}",
                'proyectos': [],
                'valor_provision': Decimal('0'),
                'valor_instalacion': Decimal('0'),
                'margen_ponderado': Decimal('0'),
                'margen_break_even': Decimal('0'),
                'ganancias': Decimal('0')
            }

        # Process projects and distribute them across the months
        proyectos_por_mes = {}
        for proyecto in proyectos:
            # Ensure we have a proper Proyecto object
            if not isinstance(proyecto, Proyecto):
                continue

            if not hasattr(proyecto, 'monto_provision_presupuestado'):
                continue

            # Get days for this project in the 12-month period
            dias_proyecto = self._obtener_dias_proyecto_periodo(proyecto, año, mes_inicio)

            for dia_info in dias_proyecto:
                periodo_key = dia_info['periodo_key']
                dias_en_mes = dia_info['dias']
                total_dias_periodo = sum(d['dias'] for d in dias_proyecto if d['periodo_key'] in matriz) # Sum only days within the 12-month matrix

                if periodo_key in matriz and total_dias_periodo > 0:
                    # Calculate daily proration factor
                    factor_prorreo = Decimal(str(dias_en_mes)) / Decimal(str(total_dias_periodo))

                    valor_provision_mes = Decimal('0')
                    valor_instalacion_mes = Decimal('0')
                    ganancia_provision_mes = Decimal('0')
                    ganancia_instalacion_mes = Decimal('0')

                    if proyecto.monto_provision_presupuestado:
                        valor_provision_mes = proyecto.monto_provision_presupuestado * factor_prorreo
                        if proyecto.margen_venta_provision:
                            ganancia_provision_mes = valor_provision_mes * (proyecto.margen_venta_provision / Decimal('100'))

                    if proyecto.monto_instalacion_presupuestado:
                        valor_instalacion_mes = proyecto.monto_instalacion_presupuestado * factor_prorreo
                        if proyecto.margen_venta_instalacion:
                            ganancia_instalacion_mes = valor_instalacion_mes * (proyecto.margen_venta_instalacion / Decimal('100'))

                    ganancia_total_mes = ganancia_provision_mes + ganancia_instalacion_mes

                    if periodo_key not in proyectos_por_mes:
                        proyectos_por_mes[periodo_key] = []

                    proyectos_por_mes[periodo_key].append({
                        'proyecto_id': proyecto.id, # Store project ID
                        'valor_provision': valor_provision_mes,
                        'valor_instalacion': valor_instalacion_mes,
                        'ganancia_provision': ganancia_provision_mes,
                        'ganancia_instalacion': ganancia_instalacion_mes,
                        'ganancia_total': ganancia_total_mes,
                        'margen_provision': proyecto.margen_venta_provision or Decimal('0'),
                        'margen_instalacion': proyecto.margen_venta_instalacion or Decimal('0'),
                        'dias_en_mes': dias_en_mes,
                        'factor_prorreo': factor_prorreo
                    })

        # Populate the matrix with calculated values and actual project objects
        revenue_service = RevenueService()

        for mes_key in matriz:
            # Get projects for this month key
            proyectos_mes_data = proyectos_por_mes.get(mes_key, [])

            # Calculate totals for this month
            provision_mes = sum(p.get('valor_provision_mes', Decimal('0')) for p in proyectos_mes_data)
            instalacion_mes = sum(p.get('valor_instalacion_mes', Decimal('0')) for p in proyectos_mes_data)
            total_mes = provision_mes + instalacion_mes

            # Calculate weighted margin
            margen_ponderado = Decimal('0')
            if total_mes > 0:
                for p in proyectos_mes_data:
                    valor_proyecto_mes = p.get('valor_provision_mes', Decimal('0')) + p.get('valor_instalacion_mes', Decimal('0'))
                    if valor_proyecto_mes > 0:
                        peso = valor_proyecto_mes / total_mes
                        margen_provision_contrib = Decimal('0')
                        if p.get('valor_provision_mes', Decimal('0')) > 0:
                             margen_provision_contrib = (p.get('valor_provision_mes', Decimal('0')) / valor_proyecto_mes) * p.get('margen_provision', Decimal('0'))
                        margen_instalacion_contrib = Decimal('0')
                        if p.get('valor_instalacion_mes', Decimal('0')) > 0:
                            margen_instalacion_contrib = (p.get('valor_instalacion_mes', Decimal('0')) / valor_proyecto_mes) * p.get('margen_instalacion', Decimal('0'))
                        
                        margen_ponderado += peso * (margen_provision_contrib + margen_instalacion_contrib)


            # Calculate break even margin
            margen_break_even_ponderado = Decimal('0')
            if total_mes > 0:
                 for p in proyectos_mes_data:
                    valor_proyecto_mes = p.get('valor_provision_mes', Decimal('0')) + p.get('valor_instalacion_mes', Decimal('0'))
                    if valor_proyecto_mes > 0:
                        peso = valor_proyecto_mes / total_mes
                        # Calculate break even margin for this project value
                        margen_be_proyecto = Decimal(str(revenue_service.required_margin(float(valor_proyecto_mes))))
                        margen_break_even_ponderado += peso * margen_be_proyecto


            # Get actual project objects for template display
            proyecto_ids = [p.get('proyecto_id') for p in proyectos_mes_data if p.get('proyecto_id')]
            proyectos_objetos = (db.session.query(Proyecto)
                               .options(joinedload(Proyecto.cliente))
                               .filter(Proyecto.id.in_(proyecto_ids))
                               .all()) if proyecto_ids else []

            matriz[mes_key]['proyectos'] = proyectos_objetos  # Use actual project objects
            matriz[mes_key]['valor_provision'] = provision_mes
            matriz[mes_key]['valor_instalacion'] = instalacion_mes
            matriz[mes_key]['ganancias'] = sum(p.get('ganancia_total', Decimal('0')) for p in proyectos_mes_data)
            matriz[mes_key]['margen_ponderado'] = margen_ponderado
            matriz[mes_key]['margen_break_even'] = margen_break_even_ponderado
            matriz[mes_key]['count'] = len(proyectos_mes_data)

        return matriz


    def _construir_matriz_mensual(self, proyectos, año):
        """Build monthly matrix with project data"""
        matriz = {}

        for mes in range(1, 13):
            matriz[mes] = {
                'mes': mes,
                'mes_nombre': calendar.month_name[mes],
                'proyectos': [],
                'valor_provision': Decimal('0'),
                'valor_instalacion': Decimal('0'),
                'margen_ponderado': Decimal('0'),
                'margen_break_even': Decimal('0'),
                'ganancias': Decimal('0')
            }

        # Process projects and distribute them across the months
        proyectos_por_mes = {}
        for proyecto in proyectos:
            # Ensure we have a proper Proyecto object
            if not isinstance(proyecto, Proyecto):
                continue

            if not hasattr(proyecto, 'monto_provision_presupuestado'):
                continue

            # Get days for this project in the year
            dias_proyecto = self._obtener_dias_proyecto(proyecto, año)

            for dia_info in dias_proyecto:
                mes = dia_info['mes']
                dias_en_mes = dia_info['dias']
                total_dias_año = sum(d['dias'] for d in dias_proyecto) # Sum of days project is active in the year

                if mes in matriz and total_dias_año > 0:
                    # Calculate daily proration factor
                    factor_prorreo = Decimal(str(dias_en_mes)) / Decimal(str(total_dias_año))

                    valor_provision_mes = Decimal('0')
                    valor_instalacion_mes = Decimal('0')
                    ganancia_provision_mes = Decimal('0')
                    ganancia_instalacion_mes = Decimal('0')

                    if proyecto.monto_provision_presupuestado:
                        valor_provision_mes = proyecto.monto_provision_presupuestado * factor_prorreo
                        if proyecto.margen_venta_provision:
                            ganancia_provision_mes = valor_provision_mes * (proyecto.margen_venta_provision / Decimal('100'))

                    if proyecto.monto_instalacion_presupuestado:
                        valor_instalacion_mes = proyecto.monto_instalacion_presupuestado * factor_prorreo
                        if proyecto.margen_venta_instalacion:
                            ganancia_instalacion_mes = valor_instalacion_mes * (proyecto.margen_venta_instalacion / Decimal('100'))

                    ganancia_total_mes = ganancia_provision_mes + ganancia_instalacion_mes

                    if mes not in proyectos_por_mes:
                        proyectos_por_mes[mes] = []

                    proyectos_por_mes[mes].append({
                        'proyecto': proyecto,  # Store complete project object
                        'valor_provision_mes': valor_provision_mes,
                        'valor_instalacion_mes': valor_instalacion_mes,
                        'ganancia_provision_mes': ganancia_provision_mes,
                        'ganancia_instalacion_mes': ganancia_instalacion_mes,
                        'ganancia_total_mes': ganancia_total_mes,
                        'margen_provision': proyecto.margen_venta_provision or Decimal('0'),
                        'margen_instalacion': proyecto.margen_venta_instalacion or Decimal('0'),
                        'dias_en_mes': dias_en_mes,
                        'factor_prorreo': factor_prorreo
                    })

        # Calculate weighted average margin and break even margin per month
        revenue_service = RevenueService()

        for mes in matriz:
            # Get projects for this month
            proyectos_mes_data = proyectos_por_mes.get(mes, [])

            # Calculate totals for this month
            provision_mes = sum(p.get('valor_provision_mes', Decimal('0')) for p in proyectos_mes_data)
            instalacion_mes = sum(p.get('valor_instalacion_mes', Decimal('0')) for p in proyectos_mes_data)
            total_mes = provision_mes + instalacion_mes

            # Calculate weighted margin
            margen_ponderado = Decimal('0')
            if total_mes > 0:
                for p in proyectos_mes_data:
                    valor_proyecto_mes = p.get('valor_provision_mes', Decimal('0')) + p.get('valor_instalacion_mes', Decimal('0'))
                    if valor_proyecto_mes > 0:
                        peso = valor_proyecto_mes / total_mes
                        margen_provision_contrib = Decimal('0')
                        if p.get('valor_provision_mes', Decimal('0')) > 0:
                             margen_provision_contrib = (p.get('valor_provision_mes', Decimal('0')) / valor_proyecto_mes) * p.get('margen_provision', Decimal('0'))
                        margen_instalacion_contrib = Decimal('0')
                        if p.get('valor_instalacion_mes', Decimal('0')) > 0:
                            margen_instalacion_contrib = (p.get('valor_instalacion_mes', Decimal('0')) / valor_proyecto_mes) * p.get('margen_instalacion', Decimal('0'))
                        
                        margen_ponderado += peso * (margen_provision_contrib + margen_instalacion_contrib)


            # Calculate break even margin
            margen_break_even_ponderado = Decimal('0')
            if total_mes > 0:
                 for p in proyectos_mes_data:
                    valor_proyecto_mes = p.get('valor_provision_mes', Decimal('0')) + p.get('valor_instalacion_mes', Decimal('0'))
                    if valor_proyecto_mes > 0:
                        peso = valor_proyecto_mes / total_mes
                        # Calculate break even margin for this project value
                        margen_be_proyecto = Decimal(str(revenue_service.required_margin(float(valor_proyecto_mes))))
                        margen_break_even_ponderado += peso * margen_be_proyecto

            # Use the project data we already have (includes project objects)
            matriz[mes]['proyectos'] = proyectos_mes_data
            matriz[mes]['valor_provision'] = provision_mes
            matriz[mes]['valor_instalacion'] = instalacion_mes
            matriz[mes]['ganancias'] = sum(p.get('ganancia_total_mes', Decimal('0')) for p in proyectos_mes_data)
            matriz[mes]['margen_ponderado'] = margen_ponderado
            matriz[mes]['margen_break_even'] = margen_break_even_ponderado
            matriz[mes]['count'] = len(proyectos_mes_data)

        return matriz


    def _obtener_meses_proyecto(self, proyecto, año):
        """Get months affected by a project in the given year"""

        # If project has both start and end dates, use them
        if proyecto.fecha_inicio and proyecto.fecha_fin_estimada:
            inicio = max(proyecto.fecha_inicio, date(año, 1, 1))
            fin = min(proyecto.fecha_fin_estimada, date(año, 12, 31))

            if inicio > date(año, 12, 31) or fin < date(año, 1, 1):
                return []

            meses = []
            fecha_actual = date(inicio.year, inicio.month, 1)
            fecha_limite = date(fin.year, fin.month, 1)

            while fecha_actual <= fecha_limite:
                if fecha_actual.year == año:
                    meses.append(fecha_actual.month)
                fecha_actual += relativedelta(months=1)

            return meses

        # If project has only start date, include it if in the year
        elif proyecto.fecha_inicio:
            if proyecto.fecha_inicio.year == año:
                return [proyecto.fecha_inicio.month]
            else:
                return []

        # If project has commercial data but no dates, spread across year
        elif (proyecto.monto_provision_presupuestado or 
              proyecto.monto_instalacion_presupuestado):
            # For projects without dates but with commercial data, 
            # distribute across the entire year
            return list(range(1, 13))

        # If no dates and no commercial data, use current month if in year
        else:
            return [datetime.now().month] if datetime.now().year == año else []

    def _obtener_dias_proyecto(self, proyecto, año):
        """Get days affected by a project in the given year, grouped by month"""

        # If project has both start and end dates, use them
        if proyecto.fecha_inicio and proyecto.fecha_fin_estimada:
            # Limit dates to the specified year
            inicio = max(proyecto.fecha_inicio, date(año, 1, 1))
            fin = min(proyecto.fecha_fin_estimada, date(año, 12, 31))

            if inicio > date(año, 12, 31) or fin < date(año, 1, 1):
                return []

            dias_por_mes = []
            fecha_actual = inicio

            while fecha_actual <= fin:
                mes = fecha_actual.month

                # Calculate days in this month for the project
                inicio_mes = max(fecha_actual, date(año, mes, 1))
                fin_mes = min(fin, date(año, mes, calendar.monthrange(año, mes)[1]))

                dias_en_mes = (fin_mes - inicio_mes).days + 1
                
                # Check if we already have this month
                mes_existente = next((d for d in dias_por_mes if d['mes'] == mes), None)
                if mes_existente:
                    mes_existente['dias'] += dias_en_mes
                else:
                    dias_por_mes.append({
                        'mes': mes,
                        'dias': dias_en_mes
                    })

                # Move to next month
                if fecha_actual.month == 12:
                    fecha_actual = date(fecha_actual.year + 1, 1, 1)
                else:
                    fecha_actual = date(fecha_actual.year, fecha_actual.month + 1, 1)

            return dias_por_mes

        # If project has only start date, assign 30 days to that month
        elif proyecto.fecha_inicio and proyecto.fecha_inicio.year == año:
            return [{
                'mes': proyecto.fecha_inicio.month,
                'dias': 30
            }]

        # If project has commercial data but no dates, distribute equally across year
        elif (proyecto.monto_provision_presupuestado or 
              proyecto.monto_instalacion_presupuestado):
            # Distribute across 365 days of the year (30.4 days per month average)
            dias_por_mes = []
            for mes in range(1, 13):
                dias_en_mes = calendar.monthrange(año, mes)[1]
                dias_por_mes.append({
                    'mes': mes,
                    'dias': dias_en_mes
                })
            return dias_por_mes

        # If no dates and no commercial data, assign to current month
        else:
            mes_actual = datetime.now().month if datetime.now().year == año else 1
            return [{
                'mes': mes_actual,
                'dias': 30
            }]

    def _calcular_totales_mensuales(self, matriz):
        """Calculate monthly totals from matrix"""
        totales = {}

        for periodo_key, mes_data in matriz.items():
            totales[periodo_key] = {
                'valor_provision': mes_data['valor_provision'],
                'valor_instalacion': mes_data['valor_instalacion'],
                'margen_ponderado': mes_data['margen_ponderado'],
                'margen_break_even': mes_data['margen_break_even'],
                'ganancias': mes_data['ganancias'],
                'proyectos_count': mes_data['count']
            }

        return totales

    def _get_objetivos_año(self, año):
        """Get yearly objectives"""
        objetivos = (db.session.query(ObjetivoMensual)
                    .filter_by(año=año)
                    .order_by(ObjetivoMensual.mes)
                    .all())

        objetivos_dict = {}
        for obj in objetivos:
            objetivos_dict[obj.mes] = obj

        return objetivos_dict

    def _obtener_dias_proyecto_periodo(self, proyecto, año, mes_inicio=1):
        """Get days affected by a project in a 12-month period, grouped by month"""

        # Calculate the 12-month period
        periodo_inicio = date(año, mes_inicio, 1)
        if mes_inicio + 11 <= 12:
            periodo_fin = date(año, mes_inicio + 11, calendar.monthrange(año, mes_inicio + 11)[1])
        else:
            año_fin = año + 1
            mes_fin = (mes_inicio + 11) % 12
            if mes_fin == 0:
                mes_fin = 12
            periodo_fin = date(año_fin, mes_fin, calendar.monthrange(año_fin, mes_fin)[1])

        # If project has both start and end dates, use them
        if proyecto.fecha_inicio and proyecto.fecha_fin_estimada:
            # Limit dates to the specified period
            inicio = max(proyecto.fecha_inicio, periodo_inicio)
            fin = min(proyecto.fecha_fin_estimada, periodo_fin)

            if inicio > periodo_fin or fin < periodo_inicio:
                return []

            dias_por_mes = []
            fecha_actual = inicio

            while fecha_actual <= fin:
                mes = fecha_actual.month
                año_actual = fecha_actual.year

                # Calculate days in this month for the project
                inicio_mes = max(fecha_actual, date(año_actual, mes, 1))
                fin_mes = min(fin, date(año_actual, mes, calendar.monthrange(año_actual, mes)[1]))

                dias_en_mes = (fin_mes - inicio_mes).days + 1
                periodo_key = f"{año_actual}-{mes:02d}"

                # Check if we already have this month
                mes_existente = next((d for d in dias_por_mes if d['periodo_key'] == periodo_key), None)
                if mes_existente:
                    mes_existente['dias'] += dias_en_mes
                else:
                    dias_por_mes.append({
                        'periodo_key': periodo_key,
                        'mes': mes,
                        'año': año_actual,
                        'dias': dias_en_mes
                    })

                # Move to next month
                if fecha_actual.month == 12:
                    fecha_actual = date(fecha_actual.year + 1, 1, 1)
                else:
                    fecha_actual = date(fecha_actual.year, fecha_actual.month + 1, 1)

            return dias_por_mes

        # If project has only start date, assign 30 days to that month if within period
        elif proyecto.fecha_inicio:
            if periodo_inicio <= proyecto.fecha_inicio <= periodo_fin:
                return [{
                    'periodo_key': f"{proyecto.fecha_inicio.year}-{proyecto.fecha_inicio.month:02d}",
                    'mes': proyecto.fecha_inicio.month,
                    'año': proyecto.fecha_inicio.year,
                    'dias': 30
                }]
            else:
                return []

        # If project has commercial data but no dates, distribute equally across period
        elif (proyecto.monto_provision_presupuestado or 
              proyecto.monto_instalacion_presupuestado):
            dias_por_mes = []

            # Distribute across the 12-month period
            for i in range(12):
                mes_actual = mes_inicio + i
                año_actual = año

                if mes_actual > 12:
                    mes_actual = mes_actual - 12
                    año_actual = año + 1

                dias_en_mes = calendar.monthrange(año_actual, mes_actual)[1]
                dias_por_mes.append({
                    'periodo_key': f"{año_actual}-{mes_actual:02d}",
                    'mes': mes_actual,
                    'año': año_actual,
                    'dias': dias_en_mes
                })
            return dias_por_mes

        # If no dates and no commercial data, assign to current month if within period
        else:
            now = datetime.now()
            if periodo_inicio <= now.date() <= periodo_fin:
                return [{
                    'periodo_key': f"{now.year}-{now.month:02d}",
                    'mes': now.month,
                    'año': now.year,
                    'dias': 30
                }]
            else:
                return []

    def _get_objetivos_periodo(self, año, mes_inicio=1):
        """Get objectives for 12-month period"""
        objetivos_dict = {}

        # Get objectives for the 12-month period
        for i in range(12):
            mes_actual = mes_inicio + i
            año_actual = año

            if mes_actual > 12:
                mes_actual = mes_actual - 12
                año_actual = año + 1

            objetivo = (db.session.query(ObjetivoMensual)
                       .filter_by(año=año_actual, mes=mes_actual)
                       .first())

            if objetivo:
                objetivos_dict[f"{año_actual}-{mes_actual:02d}"] = objetivo

        return objetivos_dict

    def _calcular_gran_totales_nueva_estructura(self, matriz, objetivos):
        """Calculate grand totals with the new data structure"""
        total_provision = Decimal('0')
        total_instalacion = Decimal('0')
        total_ganancias = Decimal('0')
        total_proyectos = 0
        objetivo_total_provision = Decimal('0')
        objetivo_total_instalacion = Decimal('0')

        # Sum up matrix values (which come from proyectos_por_mes)
        for periodo_key, mes_data in matriz.items():
            total_provision += mes_data.get('valor_provision', Decimal('0'))
            total_instalacion += mes_data.get('valor_instalacion', Decimal('0'))
            total_ganancias += mes_data.get('ganancias', Decimal('0'))
            total_proyectos += len(mes_data.get('proyectos', []))

        # Sum up objectives
        for periodo_key, objetivo_mes in objetivos.items():
            if objetivo_mes:
                if objetivo_mes.objetivo_provision:
                    objetivo_total_provision += objetivo_mes.objetivo_provision
                if objetivo_mes.objetivo_instalacion:
                    objetivo_total_instalacion += objetivo_mes.objetivo_instalacion

        # Calculate overall margin
        total_ventas = total_provision + total_instalacion
        margen_global = Decimal('0')
        if total_ventas > 0:
            margen_global = (total_ganancias / total_ventas) * Decimal('100')

        # Calculate objective percentage
        porcentaje_objetivo = Decimal('0')
        if objetivo_total_provision > 0:
            porcentaje_objetivo = (total_provision / objetivo_total_provision) * Decimal('100')

        return {
            'total_provision': total_provision,
            'total_instalacion': total_instalacion,
            'total_ganancias': total_ganancias,
            'total_ventas': total_ventas,
            'total_proyectos': total_proyectos,
            'margen_global': margen_global,
            'objetivo_total_provision': objetivo_total_provision,
            'objetivo_total_instalacion': objetivo_total_instalacion,
            'porcentaje_objetivo': porcentaje_objetivo
        }

    def _calcular_gran_totales(self, matriz, objetivos):
        """Calculate grand totals for the entire period"""
        total_provision = Decimal('0')
        total_instalacion = Decimal('0')
        total_ganancias = Decimal('0')
        total_proyectos = 0
        objetivo_total_provision = Decimal('0')
        objetivo_total_instalacion = Decimal('0')

        # Sum up monthly values - iterate over actual matriz keys
        for periodo_key, mes_data in matriz.items():
            total_provision += mes_data['valor_provision']
            total_instalacion += mes_data['valor_instalacion']
            total_ganancias += mes_data['ganancias']
            total_proyectos += mes_data['count']

        # Sum up objectives - iterate over actual objetivos keys
        for periodo_key, objetivo_mes in objetivos.items():
            if objetivo_mes:
                if objetivo_mes.objetivo_provision:
                    objetivo_total_provision += objetivo_mes.objetivo_provision
                if objetivo_mes.objetivo_instalacion:
                    objetivo_total_instalacion += objetivo_mes.objetivo_instalacion

        # Calculate overall margin
        total_ventas = total_provision + total_instalacion
        margen_global = Decimal('0')
        if total_ventas > 0:
            margen_global = (total_ganancias / total_ventas) * Decimal('100')

        # Calculate objective percentage
        porcentaje_objetivo = Decimal('0')
        if objetivo_total_provision > 0:
            porcentaje_objetivo = (total_provision / objetivo_total_provision) * Decimal('100')

        # Calculate average margins for provision and installation
        margen_provision_promedio = Decimal('0')
        margen_instalacion_promedio = Decimal('0')
        proyectos_con_provision = Decimal('0')
        proyectos_con_instalacion = Decimal('0')
        total_margen_provision_ponderado = Decimal('0')
        total_margen_instalacion_ponderado = Decimal('0')

        for periodo_key, mes_data in matriz.items():
            for proyecto_mes in mes_data['proyectos']:
                if proyecto_mes.get('valor_provision_mes', Decimal('0')) > 0:
                    total_margen_provision_ponderado += proyecto_mes.get('margen_provision', Decimal('0')) * proyecto_mes.get('valor_provision_mes', Decimal('0'))
                    proyectos_con_provision += proyecto_mes.get('valor_provision_mes', Decimal('0'))

                if proyecto_mes.get('valor_instalacion_mes', Decimal('0')) > 0:
                    total_margen_instalacion_ponderado += proyecto_mes.get('margen_instalacion', Decimal('0')) * proyecto_mes.get('valor_instalacion_mes', Decimal('0'))
                    proyectos_con_instalacion += proyecto_mes.get('valor_instalacion_mes', Decimal('0'))

        if proyectos_con_provision > 0:
            margen_provision_promedio = total_margen_provision_ponderado / proyectos_con_provision

        if proyectos_con_instalacion > 0:
            margen_instalacion_promedio = total_margen_instalacion_ponderado / proyectos_con_instalacion

        return {
            'total_provision': total_provision,
            'total_instalacion': total_instalacion,
            'total_ganancias': total_ganancias,
            'total_ventas': total_ventas,
            'total_proyectos': total_proyectos,
            'margen_global': margen_global,
            'margen_provision_promedio': margen_provision_promedio,
            'margen_instalacion_promedio': margen_instalacion_promedio,
            'objetivo_total_provision': objetivo_total_provision,
            'objetivo_total_instalacion': objetivo_total_instalacion,
            'porcentaje_objetivo': porcentaje_objetivo
        }