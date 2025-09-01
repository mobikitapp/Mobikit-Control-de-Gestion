from typing import List, Dict, Any, Optional
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
from sqlalchemy import and_, or_, func, extract, case
from decimal import Decimal
import calendar

from app import db
from models import (
    Proyecto, Cliente, User, TareaComercial, ObjetivoMensual,
    EstadoComercial, RolUsuario
)


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

    def get_planificacion_comercial(self, año, cliente_id=None, estado_filter='todos'):
        """Get commercial planning matrix by year"""

        # Build query for projects with proper joins
        query = (db.session.query(Proyecto)
                .join(Cliente)
                .filter(Proyecto.activo == True))

        # Filter by year (projects with dates in the year)
        fecha_inicio = date(año, 1, 1)
        fecha_fin = date(año, 12, 31)

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

        # Get projects as model objects
        proyectos = query.all()

        # Build monthly matrix
        matriz = self._construir_matriz_mensual(proyectos, año)

        # Calculate totals per month
        totales_mes = self._calcular_totales_mensuales(matriz)

        # Get monthly objectives
        objetivos = self._get_objetivos_año(año)

        # Get filter options
        clientes = db.session.query(Cliente).filter_by(activo=True).order_by(Cliente.nombre).all()

        return {
            'año': año,
            'matriz': matriz,
            'totales_mes': totales_mes,
            'objetivos': objetivos,
            'proyectos': proyectos,
            'clientes': clientes,
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

        return stats

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
                'margen_promedio_provision': Decimal('0')
            }

        for proyecto in proyectos:
            # Determine which months this project affects
            meses_proyecto = self._obtener_meses_proyecto(proyecto, año)

            for mes in meses_proyecto:
                if mes in matriz:
                    # Calculate prorated values
                    meses_duracion = len(meses_proyecto)

                    valor_provision_mes = Decimal('0')
                    valor_instalacion_mes = Decimal('0')

                    if proyecto.monto_provision_presupuestado:
                        valor_provision_mes = proyecto.monto_provision_presupuestado / meses_duracion

                    if proyecto.monto_instalacion_presupuestado:
                        valor_instalacion_mes = proyecto.monto_instalacion_presupuestado / meses_duracion

                    proyecto_mes = {
                        'proyecto': proyecto,
                        'valor_provision_mes': valor_provision_mes,
                        'valor_instalacion_mes': valor_instalacion_mes,
                        'margen_provision': proyecto.margen_venta_provision or Decimal('0')
                    }

                    matriz[mes]['proyectos'].append(proyecto_mes)
                    matriz[mes]['valor_provision'] += valor_provision_mes
                    matriz[mes]['valor_instalacion'] += valor_instalacion_mes

        # Calculate average margins per month
        for mes in matriz:
            proyectos_mes = matriz[mes]['proyectos']
            if proyectos_mes:
                margenes = [p['margen_provision'] for p in proyectos_mes if p['margen_provision'] > 0]
                if margenes:
                    matriz[mes]['margen_promedio_provision'] = sum(margenes) / len(margenes)

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

    def _calcular_totales_mensuales(self, matriz):
        """Calculate monthly totals from matrix"""
        totales = {}

        for mes in range(1, 13):
            totales[mes] = {
                'valor_provision': matriz[mes]['valor_provision'],
                'valor_instalacion': matriz[mes]['valor_instalacion'],
                'margen_promedio_provision': matriz[mes]['margen_promedio_provision'],
                'proyectos_count': len(matriz[mes]['proyectos'])
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