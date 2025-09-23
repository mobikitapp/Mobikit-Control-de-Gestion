from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, date, time
from sqlalchemy import and_, or_, func, desc, asc
import calendar
from dateutil.relativedelta import relativedelta

from app import db
from models import EventoEntrega, Proyecto, Despacho, Cliente, RolUsuario, TipoEvento, EstadoEvento, PrioridadEvento, HitoEntrega, EstadoHitoEntrega


class CalendarioService:
    """Service layer for calendar and events management"""

    def get_calendario_mensual(self, year: int, month: int, usuario_id: str, rol_usuario: RolUsuario, 
                              filtros_despachos: Optional[Dict] = None) -> Dict[str, Any]:
        """Get monthly calendar data with events"""
        
        # Create date range for the month
        primer_dia = date(year, month, 1)
        if month == 12:
            ultimo_dia = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            ultimo_dia = date(year, month + 1, 1) - timedelta(days=1)
        
        # Get events for the month
        eventos_mes = self._get_eventos_rango_fechas(primer_dia, ultimo_dia, usuario_id, rol_usuario)
        
        # Get despachos for the month with filters
        despachos_mes = self._get_despachos_rango_fechas(primer_dia, ultimo_dia, usuario_id, rol_usuario, filtros_despachos)
        
        # Get hitos as events for the month
        hitos_eventos = self._get_hitos_como_eventos(primer_dia, ultimo_dia, usuario_id, rol_usuario)
        
        # Generate calendar structure
        cal = calendar.Calendar(firstweekday=0)  # Monday = 0
        dias_mes = list(cal.itermonthdays2(year, month))
        
        # Organize events by day
        eventos_por_dia = {}
        despachos_por_dia = {}
        
        # Add despachos
        for despacho in despachos_mes:
            dia = despacho.fecha_programada.day
            if dia not in despachos_por_dia:
                despachos_por_dia[dia] = []
            despachos_por_dia[dia].append({
                'id': despacho.id,
                'numero_despacho': despacho.numero_despacho,
                'estado': despacho.estado.value,
                'cliente': despacho.proyecto.cliente.nombre if hasattr(despacho, 'proyecto') and despacho.proyecto and hasattr(despacho.proyecto, 'cliente') and despacho.proyecto.cliente else 'Sin cliente',
                'fecha_envio': despacho.fecha_envio.strftime('%H:%M') if despacho.fecha_envio else None,
                'color': self._get_color_despacho(despacho.estado)
            })
        
        # Add regular events
        for evento in eventos_mes:
            dia = evento.fecha_evento.day
            if dia not in eventos_por_dia:
                eventos_por_dia[dia] = []
            eventos_por_dia[dia].append({
                'id': evento.id,
                'titulo': evento.titulo,
                'tipo': evento.tipo_evento.value,
                'estado': evento.estado.value,
                'prioridad': evento.prioridad.value,
                'hora': evento.hora_evento.strftime('%H:%M') if evento.hora_evento else None,
                'proyecto': evento.proyecto.nombre if hasattr(evento, 'proyecto') and evento.proyecto else None
            })
        
        # Add hitos as events
        for hito_evento in hitos_eventos:
            dia = hito_evento['fecha_evento'].day
            if dia not in eventos_por_dia:
                eventos_por_dia[dia] = []
            eventos_por_dia[dia].append({
                'id': hito_evento['id'],
                'titulo': hito_evento['titulo'],
                'tipo': hito_evento['tipo'],
                'estado': hito_evento['estado'],
                'prioridad': hito_evento['prioridad'],
                'hora': None,
                'proyecto': hito_evento['proyecto'],
                'plan_entrega': hito_evento['plan_entrega'],
                'contrato': hito_evento['contrato']
            })
        
        # Get navigation dates
        mes_anterior = primer_dia - relativedelta(months=1)
        mes_siguiente = primer_dia + relativedelta(months=1)
        
        # Calculate total events including hitos
        total_eventos = len(eventos_mes) + len(hitos_eventos)
        eventos_pendientes = len([e for e in eventos_mes if e.estado == EstadoEvento.PENDIENTE]) + len([h for h in hitos_eventos if h['estado'] == 'pendiente'])
        eventos_completados = len([e for e in eventos_mes if e.estado == EstadoEvento.COMPLETADO]) + len([h for h in hitos_eventos if h['estado'] == 'completado'])
        
        # Calculate despachos statistics
        total_despachos = len(despachos_mes)
        despachos_programados = len([d for d in despachos_mes if d.estado.name == 'PROGRAMADO'])
        
        return {
            'year': year,
            'month': month,
            'nombre_mes': primer_dia.strftime('%B'),
            'dias_mes': dias_mes,
            'eventos_por_dia': eventos_por_dia,
            'despachos_por_dia': despachos_por_dia,
            'mes_anterior': mes_anterior,
            'mes_siguiente': mes_siguiente,
            'total_eventos': total_eventos,
            'eventos_pendientes': eventos_pendientes,
            'eventos_completados': eventos_completados,
            'total_despachos': total_despachos,
            'despachos_programados': despachos_programados,
            'total_hitos': len(hitos_eventos)
        }

    def get_calendario_semanal(self, year: int, month: int, day: int, usuario_id: str, rol_usuario: RolUsuario,
                              filtros_despachos: Optional[Dict] = None) -> Dict[str, Any]:
        """Get weekly calendar data with events"""
        
        # Create date for the selected day
        fecha_referencia = date(year, month, day)
        
        # Calculate start of week (Monday)
        dias_desde_lunes = fecha_referencia.weekday()
        inicio_semana = fecha_referencia - timedelta(days=dias_desde_lunes)
        fin_semana = inicio_semana + timedelta(days=6)
        
        # Get events for the week
        eventos_semana = self._get_eventos_rango_fechas(inicio_semana, fin_semana, usuario_id, rol_usuario)
        
        # Get despachos for the week
        despachos_semana = self._get_despachos_rango_fechas(inicio_semana, fin_semana, usuario_id, rol_usuario, filtros_despachos)
        
        # Get hitos for the week
        hitos_semana = self._get_hitos_rango_fechas(inicio_semana, fin_semana, usuario_id, rol_usuario)
        
        # Generate week structure (7 days)
        dias_semana = []
        for i in range(7):
            dia_actual = inicio_semana + timedelta(days=i)
            dias_semana.append({
                'fecha': dia_actual,
                'numero': dia_actual.day,
                'nombre_dia': dia_actual.strftime('%A'),
                'nombre_dia_corto': dia_actual.strftime('%a'),
                'es_hoy': dia_actual == date.today(),
                'es_mes_actual': dia_actual.month == month,
                'eventos': [],
                'despachos': [],
                'hitos': []
            })
        
        # Organize events by day
        for evento in eventos_semana:
            dia_index = (evento.fecha_evento - inicio_semana).days
            if 0 <= dia_index <= 6:
                dias_semana[dia_index]['eventos'].append({
                    'id': evento.id,
                    'titulo': evento.titulo,
                    'tipo': evento.tipo_evento.value,
                    'estado': evento.estado.value,
                    'prioridad': evento.prioridad.value,
                    'hora': evento.hora_evento.strftime('%H:%M') if evento.hora_evento else None,
                    'proyecto': evento.proyecto.nombre if hasattr(evento, 'proyecto') and evento.proyecto else None,
                    'color': self._get_color_evento(evento.tipo_evento, evento.estado)
                })
        
        # Organize despachos by day
        for despacho in despachos_semana:
            if despacho.fecha_programada:
                dia_index = (despacho.fecha_programada - inicio_semana).days
                if 0 <= dia_index <= 6:
                    dias_semana[dia_index]['despachos'].append({
                        'id': despacho.id,
                        'numero_despacho': despacho.numero_despacho,
                        'estado': despacho.estado.value,
                        'cliente': despacho.proyecto.cliente.nombre if despacho.proyecto and despacho.proyecto.cliente else 'Sin cliente',
                        'proyecto': despacho.proyecto.nombre if despacho.proyecto else 'Sin proyecto',
                        'color': self._get_color_despacho(despacho.estado)
                    })
        
        # Organize hitos by day  
        for hito in hitos_semana:
            dia_index = (hito.fecha_programada - inicio_semana).days
            if 0 <= dia_index <= 6:
                dias_semana[dia_index]['hitos'].append({
                    'id': hito.id,
                    'titulo': hito.titulo,
                    'descripcion': hito.descripcion,
                    'estado': hito.estado.value,
                    'plan_entrega': hito.plan_entrega.nombre if hito.plan_entrega else 'Sin plan',
                    'contrato': hito.plan_entrega.contrato.numero_oc if hito.plan_entrega and hito.plan_entrega.contrato else 'Sin contrato',
                    'color': self._get_color_hito(hito.estado)
                })
        
        # Get navigation dates
        semana_anterior = inicio_semana - timedelta(days=7)
        semana_siguiente = inicio_semana + timedelta(days=7)
        
        return {
            'year': year,
            'month': month,
            'day': day,
            'inicio_semana': inicio_semana,
            'fin_semana': fin_semana,
            'nombre_mes': fecha_referencia.strftime('%B'),
            'dias_semana': dias_semana,
            'semana_anterior': semana_anterior,
            'semana_siguiente': semana_siguiente,
            'total_eventos': len(eventos_semana),
            'total_despachos': len(despachos_semana),
            'total_hitos': len(hitos_semana),
            'eventos_pendientes': len([e for e in eventos_semana if e.estado == EstadoEvento.PENDIENTE]),
            'despachos_programados': len([d for d in despachos_semana if d.estado.name == 'PROGRAMADO']),
            'hitos_pendientes': len([h for h in hitos_semana if h.estado == EstadoHitoEntrega.PENDIENTE])
        }

    def get_calendario_diario(self, year: int, month: int, day: int, usuario_id: str, rol_usuario: RolUsuario,
                             filtros_despachos: Optional[Dict] = None) -> Dict[str, Any]:
        """Get daily calendar data with events focused on dispatches"""
        
        # Create date for the selected day
        fecha_dia = date(year, month, day)
        
        # Get events for the day
        eventos_dia = self._get_eventos_rango_fechas(fecha_dia, fecha_dia, usuario_id, rol_usuario)
        
        # Get despachos for the day
        despachos_dia = self._get_despachos_rango_fechas(fecha_dia, fecha_dia, usuario_id, rol_usuario, filtros_despachos)
        
        # Get hitos for the day
        hitos_dia = self._get_hitos_rango_fechas(fecha_dia, fecha_dia, usuario_id, rol_usuario)
        
        # Get ordenes de fabricacion linked to despachos for the day
        ordenes_fabricacion = []
        for despacho in despachos_dia:
            if hasattr(despacho, 'ordenes_fabricacion_detalle') and despacho.ordenes_fabricacion_detalle:
                detalle_list = list(despacho.ordenes_fabricacion_detalle) if hasattr(despacho.ordenes_fabricacion_detalle, '__iter__') else despacho.ordenes_fabricacion_detalle
                for detalle in detalle_list:
                    ordenes_fabricacion.append({
                    'id': detalle.orden_fabricacion.id,
                    'codigo': detalle.orden_fabricacion.codigo,
                    'descripcion': detalle.orden_fabricacion.descripcion or 'Sin descripción',
                    'cantidad_total': detalle.cantidad_total,
                    'cantidad_despachada': detalle.cantidad_despachada,
                    'porcentaje_despachado': detalle.porcentaje_despachado,
                    'despacho_id': despacho.id,
                    'despacho_numero': despacho.numero_despacho,
                    'tipo_despacho': detalle.tipo_despacho.value,
                    'estado_area': detalle.orden_fabricacion.area_actual.nombre if detalle.orden_fabricacion.area_actual else 'Sin área',
                    'estado_progreso': detalle.orden_fabricacion.estado_actual.nombre if detalle.orden_fabricacion.estado_actual else 'Sin estado'
                })
        
        # Format events with enhanced details
        eventos_formateados = []
        for evento in eventos_dia:
            eventos_formateados.append({
                'id': evento.id,
                'titulo': evento.titulo,
                'descripcion': evento.descripcion,
                'tipo': evento.tipo_evento.value,
                'estado': evento.estado.value,
                'prioridad': evento.prioridad.value,
                'hora': evento.hora_evento.strftime('%H:%M') if evento.hora_evento else None,
                'proyecto': evento.proyecto.nombre if hasattr(evento, 'proyecto') and evento.proyecto else None,
                'proyecto_id': evento.proyecto_id,
                'color': self._get_color_evento(evento.tipo_evento, evento.estado),
                'notas': evento.notas
            })
        
        # Format despachos with enhanced details
        despachos_formateados = []
        for despacho in despachos_dia:
            despachos_formateados.append({
                'id': despacho.id,
                'numero_despacho': despacho.numero_despacho,
                'estado': despacho.estado.value,
                'cliente': despacho.proyecto.cliente.nombre if hasattr(despacho, 'proyecto') and despacho.proyecto and hasattr(despacho.proyecto, 'cliente') and despacho.proyecto.cliente else 'Sin cliente',
                'proyecto': despacho.proyecto.nombre if hasattr(despacho, 'proyecto') and despacho.proyecto else 'Sin proyecto',
                'destino': despacho.destino,
                'contacto_destino': despacho.contacto_destino,
                'telefono_contacto': despacho.telefono_contacto,
                'observaciones': despacho.observaciones,
                'responsable_nombre': despacho.responsable_nombre,
                'fecha_envio': despacho.fecha_envio.strftime('%H:%M') if despacho.fecha_envio else None,
                'fecha_entrega': despacho.fecha_entrega.strftime('%H:%M') if despacho.fecha_entrega else None,
                'color': self._get_color_despacho(despacho.estado),
                'num_ordenes': len(list(despacho.ordenes_fabricacion_detalle)) if hasattr(despacho, 'ordenes_fabricacion_detalle') and despacho.ordenes_fabricacion_detalle else 0
            })
        
        # Format hitos with enhanced details
        hitos_formateados = []
        for hito in hitos_dia:
            hitos_formateados.append({
                'id': hito.id,
                'titulo': hito.titulo,
                'descripcion': hito.descripcion,
                'estado': hito.estado.value,
                'plan_entrega': hito.plan_entrega.nombre if hasattr(hito, 'plan_entrega') and hito.plan_entrega else 'Sin plan',
                'contrato': hito.plan_entrega.contrato.numero_oc if hasattr(hito, 'plan_entrega') and hito.plan_entrega and hasattr(hito.plan_entrega, 'contrato') and hito.plan_entrega.contrato else 'Sin contrato',
                'monto_total': hito.plan_entrega.contrato.monto_total if hasattr(hito, 'plan_entrega') and hito.plan_entrega and hasattr(hito.plan_entrega, 'contrato') and hito.plan_entrega.contrato else None,
                'proyecto': hito.plan_entrega.contrato.proyecto.nombre if hasattr(hito, 'plan_entrega') and hito.plan_entrega and hasattr(hito.plan_entrega, 'contrato') and hito.plan_entrega.contrato and hasattr(hito.plan_entrega.contrato, 'proyecto') and hito.plan_entrega.contrato.proyecto else 'Sin proyecto',
                'color': self._get_color_hito(hito.estado)
            })
        
        # Get navigation dates
        dia_anterior = fecha_dia - timedelta(days=1)
        dia_siguiente = fecha_dia + timedelta(days=1)
        
        # Calculate statistics
        total_actividades = len(eventos_dia) + len(despachos_dia) + len(hitos_dia)
        actividades_pendientes = (
            len([e for e in eventos_dia if e.estado == EstadoEvento.PENDIENTE]) +
            len([d for d in despachos_dia if d.estado.name == 'PROGRAMADO']) +
            len([h for h in hitos_dia if h.estado == EstadoHitoEntrega.PENDIENTE])
        )
        
        return {
            'year': year,
            'month': month,
            'day': day,
            'fecha_dia': fecha_dia,
            'nombre_dia': fecha_dia.strftime('%A'),
            'nombre_mes': fecha_dia.strftime('%B'),
            'es_hoy': fecha_dia == date.today(),
            'dia_anterior': dia_anterior,
            'dia_siguiente': dia_siguiente,
            'eventos': eventos_formateados,
            'despachos': despachos_formateados,
            'hitos': hitos_formateados,
            'ordenes_fabricacion': ordenes_fabricacion,
            'total_eventos': len(eventos_dia),
            'total_despachos': len(despachos_dia),
            'total_hitos': len(hitos_dia),
            'total_actividades': total_actividades,
            'actividades_pendientes': actividades_pendientes,
            'eventos_pendientes': len([e for e in eventos_dia if e.estado == EstadoEvento.PENDIENTE]),
            'despachos_programados': len([d for d in despachos_dia if d.estado.name == 'PROGRAMADO']),
            'hitos_pendientes': len([h for h in hitos_dia if h.estado == EstadoHitoEntrega.PENDIENTE])
        }

    def get_eventos_lista(self, fecha_inicio=None, fecha_fin=None, estado=None, tipo_evento=None, 
                         usuario_id=None, rol_usuario=None) -> Dict[str, Any]:
        """Get filtered list of events including hitos"""
        
        # Build base query with user filtering
        query = self._build_eventos_query(usuario_id, rol_usuario)
        
        # Apply date filters
        if fecha_inicio:
            query = query.filter(EventoEntrega.fecha_evento >= fecha_inicio)
        if fecha_fin:
            query = query.filter(EventoEntrega.fecha_evento <= fecha_fin)
        
        # Apply status filter
        if estado:
            try:
                estado_enum = EstadoEvento(estado)
                query = query.filter(EventoEntrega.estado == estado_enum)
            except ValueError:
                pass
        
        # Apply event type filter
        if tipo_evento and tipo_evento != 'hito_entrega':
            try:
                tipo_enum = TipoEvento(tipo_evento)
                query = query.filter(EventoEntrega.tipo_evento == tipo_enum)
            except ValueError:
                pass
        
        # Get events ordered by date
        eventos_regulares = query.order_by(asc(EventoEntrega.fecha_evento), 
                                          asc(EventoEntrega.hora_evento)).all()
        
        # Get hitos as events if not filtering by specific type or if filtering by hito_entrega
        eventos_hitos_raw = []
        if not tipo_evento or tipo_evento == 'hito_entrega':
            # Set wide date range if not specified
            fecha_inicio_hitos = fecha_inicio or date(2020, 1, 1)
            fecha_fin_hitos = fecha_fin or date(2030, 12, 31)
            
            eventos_hitos_raw = self._get_hitos_como_eventos(fecha_inicio_hitos, fecha_fin_hitos, usuario_id, rol_usuario)
            
            # Apply estado filter to hitos if specified
            if estado:
                eventos_hitos_raw = [h for h in eventos_hitos_raw if h['estado'] == estado]
        
        # Convert hitos to EventoEntrega-like objects for template compatibility
        class HitoComoEvento:
            def __init__(self, hito_data):
                self.id = hito_data['id']
                self.titulo = hito_data['titulo']
                self.descripcion = hito_data['descripcion']
                self.fecha_evento = hito_data['fecha_evento']
                self.hora_evento = None
                self.tipo_evento = type('obj', (object,), {'value': hito_data['tipo']})()
                self.estado = type('obj', (object,), {'value': hito_data['estado']})()
                self.prioridad = type('obj', (object,), {'value': hito_data['prioridad']})()
                self.proyecto = type('obj', (object,), {'nombre': hito_data['proyecto']})() if hito_data['proyecto'] else None
                self.plan_entrega_nombre = hito_data['plan_entrega']
                self.contrato_numero = hito_data['contrato']
                
        eventos_hitos = [HitoComoEvento(h) for h in eventos_hitos_raw]
        
        # Combine and sort all events
        todos_eventos = list(eventos_regulares) + eventos_hitos
        todos_eventos.sort(key=lambda x: (x.fecha_evento, x.hora_evento or time(0, 0)))
        
        # Update tipos disponibles to include hitos
        tipos_disponibles = list(TipoEvento) + [type('obj', (object,), {'value': 'hito_entrega'})()]
        
        return {
            'eventos': todos_eventos,
            'filtros': {
                'fecha_inicio': fecha_inicio,
                'fecha_fin': fecha_fin,
                'estado': estado,
                'tipo_evento': tipo_evento
            },
            'total_eventos': len(todos_eventos),
            'tipos_disponibles': tipos_disponibles,
            'estados_disponibles': list(EstadoEvento),
            'prioridades_disponibles': list(PrioridadEvento)
        }

    def get_evento_by_id(self, evento_id: str, usuario_id: str, rol_usuario: RolUsuario) -> Optional[EventoEntrega]:
        """Get event by ID with user access control"""
        
        query = self._build_eventos_query(usuario_id, rol_usuario)
        return query.filter(EventoEntrega.id == evento_id).first()

    def get_proyectos_disponibles(self, usuario_id: str, rol_usuario: RolUsuario) -> List[Proyecto]:
        """Get projects available for creating events"""
        
        # Build query with user access control
        if rol_usuario == RolUsuario.ADMIN:
            # Admin can see all projects
            query = db.session.query(Proyecto)
        elif rol_usuario == RolUsuario.VENTAS:
            # Sales can only see their own clients' projects  
            query = (db.session.query(Proyecto)
                    .join(Cliente)
                    .filter(getattr(Cliente, 'vendedor_id', None) == usuario_id))
        else:
            # Operations, Production, Logistics can see all projects
            query = db.session.query(Proyecto)
        
        return query.order_by(Proyecto.nombre).all()

    def crear_evento(self, datos_evento: Dict[str, Any], created_by: str) -> Tuple[bool, str]:
        """Create a new event"""
        try:
            # Parse date and time
            fecha_str = datos_evento['fecha_evento']
            fecha_evento = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            
            hora_evento = None
            if datos_evento.get('hora_evento'):
                hora_str = datos_evento['hora_evento']
                hora_evento = datetime.strptime(hora_str, '%H:%M').time()
            
            # Create event instance
            nuevo_evento = EventoEntrega()
            nuevo_evento.id = self._generate_evento_id()
            nuevo_evento.titulo = datos_evento['titulo']
            nuevo_evento.descripcion = datos_evento.get('descripcion')
            nuevo_evento.fecha_evento = fecha_evento
            nuevo_evento.hora_evento = hora_evento
            nuevo_evento.tipo_evento = TipoEvento(datos_evento['tipo_evento'])
            nuevo_evento.prioridad = PrioridadEvento(datos_evento.get('prioridad', 'media'))
            nuevo_evento.estado = EstadoEvento.PENDIENTE
            nuevo_evento.recordatorio_dias = datos_evento.get('recordatorio_dias', 1)
            nuevo_evento.notas = datos_evento.get('notas')
            nuevo_evento.created_by = created_by
            
            # Link to project if provided
            if datos_evento.get('proyecto_id'):
                proyecto = db.session.query(Proyecto).filter_by(id=datos_evento['proyecto_id']).first()
                if proyecto:
                    nuevo_evento.proyecto_id = proyecto.id
            
            db.session.add(nuevo_evento)
            db.session.commit()
            
            return True, "Evento creado exitosamente"
            
        except Exception as e:
            db.session.rollback()
            return False, str(e)

    def actualizar_evento(self, evento_id: str, datos_evento: Dict[str, Any], updated_by: str) -> Tuple[bool, str]:
        """Update existing event"""
        try:
            evento = db.session.query(EventoEntrega).filter_by(id=evento_id).first()
            if not evento:
                return False, "Evento no encontrado"
            
            # Parse date and time
            fecha_str = datos_evento['fecha_evento']
            fecha_evento = datetime.strptime(fecha_str, '%Y-%m-%d').date()
            
            hora_evento = None
            if datos_evento.get('hora_evento'):
                hora_str = datos_evento['hora_evento']
                hora_evento = datetime.strptime(hora_str, '%H:%M').time()
            
            # Update event fields
            evento.titulo = datos_evento['titulo']
            evento.descripcion = datos_evento.get('descripcion')
            evento.fecha_evento = fecha_evento
            evento.hora_evento = hora_evento
            evento.tipo_evento = TipoEvento(datos_evento['tipo_evento'])
            evento.prioridad = PrioridadEvento(datos_evento.get('prioridad', 'media'))
            evento.recordatorio_dias = datos_evento.get('recordatorio_dias', 1)
            evento.notas = datos_evento.get('notas')
            evento.updated_at = datetime.now()
            
            # Update project link
            if datos_evento.get('proyecto_id'):
                proyecto = db.session.query(Proyecto).filter_by(id=datos_evento['proyecto_id']).first()
                if proyecto:
                    evento.proyecto_id = proyecto.id
            else:
                evento.proyecto_id = None
            
            db.session.commit()
            
            return True, "Evento actualizado exitosamente"
            
        except Exception as e:
            db.session.rollback()
            return False, str(e)

    def completar_evento(self, evento_id: str, completed_by: str) -> Tuple[bool, str]:
        """Mark event as completed"""
        try:
            evento = db.session.query(EventoEntrega).filter_by(id=evento_id).first()
            if not evento:
                return False, "Evento no encontrado"
            
            if evento.estado == EstadoEvento.COMPLETADO:
                return False, "El evento ya está marcado como completado"
            
            evento.estado = EstadoEvento.COMPLETADO
            evento.fecha_completado = datetime.now()
            evento.completado_por = completed_by
            evento.updated_at = datetime.now()
            
            db.session.commit()
            
            return True, f"Evento '{evento.titulo}' marcado como completado"
            
        except Exception as e:
            db.session.rollback()
            return False, str(e)

    def get_calendario_dashboard(self, usuario_id: str, rol_usuario: RolUsuario) -> Dict[str, Any]:
        """Get calendar dashboard data including hitos"""
        
        # Get events for current month
        today = date.today()
        primer_dia = date(today.year, today.month, 1)
        if today.month == 12:
            ultimo_dia = date(today.year + 1, 1, 1) - timedelta(days=1)
        else:
            ultimo_dia = date(today.year, today.month + 1, 1) - timedelta(days=1)
        
        eventos_mes = self._get_eventos_rango_fechas(primer_dia, ultimo_dia, usuario_id, rol_usuario)
        
        # Get hitos as events for current month
        hitos_eventos_mes = self._get_hitos_como_eventos(primer_dia, ultimo_dia, usuario_id, rol_usuario)
        
        # Get upcoming events (next 7 days)
        eventos_proximos = self._get_eventos_rango_fechas(today, today + timedelta(days=7), usuario_id, rol_usuario)
        hitos_proximos = self._get_hitos_como_eventos(today, today + timedelta(days=7), usuario_id, rol_usuario)
        
        # Get overdue events
        eventos_vencidos = self._get_eventos_rango_fechas(
            date(2020, 1, 1), today - timedelta(days=1), usuario_id, rol_usuario
        )
        eventos_vencidos = [e for e in eventos_vencidos if e.estado == EstadoEvento.PENDIENTE]
        
        # Get overdue hitos
        hitos_vencidos = self._get_hitos_como_eventos(
            date(2020, 1, 1), today - timedelta(days=1), usuario_id, rol_usuario
        )
        hitos_vencidos = [h for h in hitos_vencidos if h['estado'] == 'pendiente']
        
        # Combine events and hitos for stats
        total_eventos_mes = len(eventos_mes) + len(hitos_eventos_mes)
        total_pendientes = len([e for e in eventos_mes if e.estado == EstadoEvento.PENDIENTE]) + len([h for h in hitos_eventos_mes if h['estado'] == 'pendiente'])
        total_completados = len([e for e in eventos_mes if e.estado == EstadoEvento.COMPLETADO]) + len([h for h in hitos_eventos_mes if h['estado'] == 'completado'])
        
        # Statistics
        stats = {
            'eventos_mes': total_eventos_mes,
            'eventos_pendientes': total_pendientes,
            'eventos_completados': total_completados,
            'eventos_proximos': len(eventos_proximos) + len(hitos_proximos),
            'eventos_vencidos': len(eventos_vencidos) + len(hitos_vencidos)
        }
        
        # Events by type (including hitos)
        eventos_por_tipo = {}
        for tipo in TipoEvento:
            eventos_por_tipo[tipo.value] = len([e for e in eventos_mes if e.tipo_evento == tipo])
        eventos_por_tipo['hito_entrega'] = len(hitos_eventos_mes)
        
        # Create event-like objects for upcoming events
        class EventoProxy:
            def __init__(self, data, es_hito=False):
                if es_hito:
                    self.id = data['id']
                    self.titulo = data['titulo']
                    self.fecha_evento = data['fecha_evento']
                    self.proyecto = type('obj', (object,), {'nombre': data['proyecto']})() if data['proyecto'] else None
                    self.contrato = type('obj', (object,), {'numero_oc': data['contrato']})() if data['contrato'] else None
                    self.tipo_evento = type('obj', (object,), {'value': data['tipo']})()
                else:
                    self.id = data.id
                    self.titulo = data.titulo
                    self.fecha_evento = data.fecha_evento
                    self.proyecto = data.proyecto
                    self.contrato = data.contrato if hasattr(data, 'contrato') else None
                    self.tipo_evento = data.tipo_evento
        
        # Combine upcoming events
        eventos_proximos_combined = ([EventoProxy(e) for e in eventos_proximos] + 
                                   [EventoProxy(h, es_hito=True) for h in hitos_proximos])
        eventos_proximos_combined.sort(key=lambda x: x.fecha_evento)
        
        # Combine overdue events  
        eventos_vencidos_combined = ([EventoProxy(e) for e in eventos_vencidos] + 
                                   [EventoProxy(h, es_hito=True) for h in hitos_vencidos])
        eventos_vencidos_combined.sort(key=lambda x: x.fecha_evento)
        
        return {
            'stats': stats,
            'eventos_proximos': eventos_proximos_combined[:5],  # Limit to 5
            'eventos_vencidos': eventos_vencidos_combined[:5],  # Limit to 5
            'eventos_por_tipo': eventos_por_tipo,
            'mes_actual': today.strftime('%B %Y'),
            'entregas_proximas': eventos_proximos_combined[:5],  # Alias for template compatibility
            'entregas_vencidas': eventos_vencidos_combined[:5]   # Alias for template compatibility
        }

    def get_eventos_mes(self, year: int, month: int, usuario_id: str, rol_usuario: RolUsuario) -> List[Dict[str, Any]]:
        """Get events for a specific month (for API)"""
        
        primer_dia = date(year, month, 1)
        if month == 12:
            ultimo_dia = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            ultimo_dia = date(year, month + 1, 1) - timedelta(days=1)
        
        eventos = self._get_eventos_rango_fechas(primer_dia, ultimo_dia, usuario_id, rol_usuario)
        
        return [{
            'id': evento.id,
            'titulo': evento.titulo,
            'fecha': evento.fecha_evento.isoformat(),
            'hora': evento.hora_evento.strftime('%H:%M') if evento.hora_evento else None,
            'tipo': evento.tipo_evento.value,
            'estado': evento.estado.value,
            'prioridad': evento.prioridad.value,
            'proyecto': evento.proyecto.nombre if hasattr(evento, 'proyecto') and evento.proyecto else None
        } for evento in eventos]

    def get_eventos_proximos(self, usuario_id: str, rol_usuario: RolUsuario, dias: int = 7) -> List[EventoEntrega]:
        """Get upcoming events"""
        
        today = date.today()
        fecha_fin = today + timedelta(days=dias)
        
        return self._get_eventos_rango_fechas(today, fecha_fin, usuario_id, rol_usuario)

    def toggle_recordatorio(self, evento_id: str, usuario_id: str) -> Tuple[bool, str]:
        """Toggle event reminder"""
        try:
            evento = db.session.query(EventoEntrega).filter_by(id=evento_id).first()
            if not evento:
                return False, "Evento no encontrado"
            
            # Toggle reminder (for now, just set/unset recordatorio_dias)
            if evento.recordatorio_dias:
                evento.recordatorio_dias = None
                mensaje = "Recordatorio desactivado"
            else:
                evento.recordatorio_dias = 1
                mensaje = "Recordatorio activado"
            
            evento.updated_at = datetime.now()
            db.session.commit()
            
            return True, mensaje
            
        except Exception as e:
            db.session.rollback()
            return False, str(e)

    # Private helper methods
    
    def _build_eventos_query(self, usuario_id: str, rol_usuario: RolUsuario):
        """Build base query for delivery events only with user access control"""
        
        query = (db.session.query(EventoEntrega)
                .filter(EventoEntrega.tipo_evento == TipoEvento.ENTREGA)
                .join(Proyecto, EventoEntrega.proyecto_id == Proyecto.id, isouter=True))
        
        if rol_usuario == RolUsuario.ADMIN:
            # Admin can see all events
            pass
        elif rol_usuario == RolUsuario.VENTAS:
            # Sales can only see events for their clients' projects
            query = query.join(Cliente, Proyecto.cliente_id == Cliente.id).filter(
                getattr(Cliente, 'vendedor_id', None) == usuario_id
            )
        else:
            # Operations, Production, Logistics can see all events
            pass
        
        return query

    def _get_hitos_como_eventos(self, fecha_inicio: date, fecha_fin: date, usuario_id: str, rol_usuario: RolUsuario) -> List[Dict[str, Any]]:
        """Get hitos de entrega as calendar events"""
        from models import PlanEntrega, Contrato
        
        # Build base query with access control
        if rol_usuario == RolUsuario.ADMIN:
            query = db.session.query(HitoEntrega)
        elif rol_usuario == RolUsuario.VENTAS:
            # Sales can only see their own clients' hitos
            query = (db.session.query(HitoEntrega)
                    .join(PlanEntrega, HitoEntrega.plan_entrega_id == PlanEntrega.id)
                    .join(Contrato, PlanEntrega.contrato_id == Contrato.id)
                    .join(Proyecto, Contrato.proyecto_id == Proyecto.id)
                    .join(Cliente, Proyecto.cliente_id == Cliente.id)
                    .filter(getattr(Cliente, 'vendedor_id', None) == usuario_id))
        else:
            # Operations, Production, Logistics can see all hitos
            query = db.session.query(HitoEntrega)
        
        # Apply date filters
        hitos = query.filter(
            and_(
                HitoEntrega.fecha_programada >= fecha_inicio,
                HitoEntrega.fecha_programada <= fecha_fin
            )
        ).options(
            db.selectinload(HitoEntrega.plan_entrega).selectinload(PlanEntrega.contrato).selectinload(Contrato.proyecto)
        ).order_by(HitoEntrega.fecha_programada).all()
        
        # Convert hitos to event-like objects
        eventos_hitos = []
        for hito in hitos:
            eventos_hitos.append({
                'id': f"hito_{hito.id}",
                'titulo': f"Hito: {hito.titulo}",
                'descripcion': hito.descripcion,
                'fecha_evento': hito.fecha_programada,
                'hora_evento': None,
                'tipo': 'hito_entrega',
                'estado': 'completado' if hito.estado == EstadoHitoEntrega.COMPLETADO else 'pendiente',
                'prioridad': 'alta' if hito.estado == EstadoHitoEntrega.ATRASADO else 'media',
                'proyecto': hito.plan_entrega.contrato.proyecto.nombre if hito.plan_entrega and hito.plan_entrega.contrato and hito.plan_entrega.contrato.proyecto else None,
                'plan_entrega': hito.plan_entrega.nombre if hito.plan_entrega else None,
                'contrato': hito.plan_entrega.contrato.numero_oc if hito.plan_entrega and hito.plan_entrega.contrato else None
            })
        
        return eventos_hitos

    def _get_eventos_rango_fechas(self, fecha_inicio: date, fecha_fin: date, usuario_id: str, rol_usuario: RolUsuario) -> List[EventoEntrega]:
        """Get events within date range with user access control"""
        
        query = self._build_eventos_query(usuario_id, rol_usuario)
        return query.filter(
            and_(
                EventoEntrega.fecha_evento >= fecha_inicio,
                EventoEntrega.fecha_evento <= fecha_fin
            )
        ).order_by(EventoEntrega.fecha_evento, EventoEntrega.hora_evento).all()
    
    def _get_despachos_rango_fechas(self, fecha_inicio: date, fecha_fin: date, usuario_id: str, rol_usuario: RolUsuario, 
                                   filtros: Optional[Dict] = None) -> List[Despacho]:
        """Get despachos for date range with user access control"""
        
        # Build base query with access control  
        if rol_usuario == RolUsuario.ADMIN:
            query = db.session.query(Despacho)
        elif rol_usuario == RolUsuario.VENTAS:
            # Sales can only see their own clients' despachos
            query = (db.session.query(Despacho)
                    .join(Proyecto, Despacho.proyecto_id == Proyecto.id)
                    .join(Cliente, Proyecto.cliente_id == Cliente.id)
                    .filter(getattr(Cliente, 'vendedor_id', None) == usuario_id))
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
                    from models import EstadoDespacho
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
            
            if filtros.get('fecha_desde'):
                try:
                    from datetime import datetime
                    fecha_desde = datetime.strptime(filtros['fecha_desde'], '%Y-%m-%d').date()
                    query = query.filter(Despacho.fecha_programada >= fecha_desde)
                except (ValueError, TypeError):
                    pass
            
            if filtros.get('fecha_hasta'):
                try:
                    from datetime import datetime
                    fecha_hasta = datetime.strptime(filtros['fecha_hasta'], '%Y-%m-%d').date()
                    query = query.filter(Despacho.fecha_programada <= fecha_hasta)
                except (ValueError, TypeError):
                    pass
            
            if filtros.get('con_ordenes'):
                query = query.filter(Despacho.ordenes_fabricacion_detalle.any())
        
        # Join with proyecto and cliente for additional info
        query = query.options(
            db.selectinload(Despacho.proyecto).selectinload(Proyecto.cliente)
        )
        
        return query.order_by(Despacho.fecha_programada).all()
    
    def _get_hitos_rango_fechas(self, fecha_inicio: date, fecha_fin: date, usuario_id: str, rol_usuario: RolUsuario) -> List[HitoEntrega]:
        """Get hitos de entrega for date range with user access control"""
        from models import PlanEntrega, Contrato
        
        # Build base query with access control
        if rol_usuario == RolUsuario.ADMIN:
            query = db.session.query(HitoEntrega)
        elif rol_usuario == RolUsuario.VENTAS:
            # Sales can only see their own clients' hitos
            query = (db.session.query(HitoEntrega)
                    .join(PlanEntrega, HitoEntrega.plan_entrega_id == PlanEntrega.id)
                    .join(Contrato, PlanEntrega.contrato_id == Contrato.id)
                    .join(Proyecto, Contrato.proyecto_id == Proyecto.id)
                    .join(Cliente, Proyecto.cliente_id == Cliente.id)
                    .filter(getattr(Cliente, 'vendedor_id', None) == usuario_id))
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
    
    def _get_color_evento(self, tipo_evento: TipoEvento, estado: EstadoEvento) -> str:
        """Get color for event based on type and status"""
        if estado == EstadoEvento.COMPLETADO:
            return 'success'
        elif estado == EstadoEvento.CANCELADO:
            return 'secondary'
        elif tipo_evento == TipoEvento.ENTREGA:
            return 'primary'
        else:
            return 'info'
    
    def _get_color_despacho(self, estado) -> str:
        """Get color for despacho based on status"""
        estado_name = estado.name if hasattr(estado, 'name') else str(estado)
        
        if estado_name == 'PROGRAMADO':
            return 'warning'
        elif estado_name == 'EN_TRANSPORTE':
            return 'info'
        elif estado_name == 'ENTREGADO':
            return 'success'
        elif estado_name == 'OBSERVADO':
            return 'danger'
        else:
            return 'secondary'
    
    def _get_color_hito(self, estado: EstadoHitoEntrega) -> str:
        """Get color for hito based on status"""
        if estado == EstadoHitoEntrega.COMPLETADO:
            return 'success'
        elif estado == EstadoHitoEntrega.ATRASADO:
            return 'danger'
        elif estado == EstadoHitoEntrega.PENDIENTE:
            return 'warning'
        else:
            return 'secondary'

    def _generate_evento_id(self) -> str:
        """Generate unique event ID"""
        timestamp = str(int(datetime.now().timestamp()))
        return f"evt_{timestamp}"