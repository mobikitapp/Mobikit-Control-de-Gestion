from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from sqlalchemy import and_, or_, case, desc, asc
from sqlalchemy.orm import joinedload

from app import db
from models import (
    OrdenFabricacion, Proyecto, Cliente, User, OrdenAreaProgreso, 
    TipoArea, EstadoPendientesFabricacion, EstadoFabrica,
    PrioridadOrden
)
from services.planificacion_operacional_service import PlanificacionOperacionalService


class PlanificacionPrioridadesService:
    """Servicio para la planificación y gestión de prioridades de producción"""
    
    def __init__(self):
        self.planificacion_service = PlanificacionOperacionalService()
    
    def get_ofs_en_produccion(self, incluir_solo_con_fechas: bool = False) -> List[Dict[str, Any]]:
        """
        Obtiene todas las OFs que están en estados de 'Pendiente de Fabricación' o 'Enviado a Fabricar'
        con información completa para la matriz de planificación
        """
        try:
            # Estados que nos interesan para la planificación
            estados_pendientes = [
                'pendiente_aprobacion_diseño',
                'aprobado'
            ]
            estados_fabrica = [
                'enviado_a_fabricacion'
            ]
            
            # Query principal para obtener OFs con su progreso actual
            query = (db.session.query(OrdenFabricacion, OrdenAreaProgreso, Proyecto, Cliente)
                    .join(OrdenAreaProgreso, 
                          and_(OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                               OrdenAreaProgreso.es_actual == True))
                    .join(Proyecto, OrdenFabricacion.proyecto_id == Proyecto.id)
                    .join(Cliente, Proyecto.cliente_id == Cliente.id)
                    )
            
            # Filtrar por áreas y estados específicos usando joins explícitos
            from models import Area, AreaEstado
            query = query.join(Area, OrdenAreaProgreso.area_id == Area.id) \
                         .join(AreaEstado, OrdenAreaProgreso.estado_id == AreaEstado.id)
            
            query = query.filter(
                or_(
                    # Pendientes de Fabricación
                    and_(Area.tipo == 'pendientes_fabricacion',
                         AreaEstado.estado.in_(estados_pendientes)),
                    # En Fábrica - Enviado a Fabricar
                    and_(Area.tipo == 'fabrica',
                         AreaEstado.estado.in_(estados_fabrica))
                )
            )
            
            # Si solo queremos OFs con fechas planificadas
            if incluir_solo_con_fechas:
                query = query.filter(OrdenFabricacion.fecha_planificada.isnot(None))
            
            # Ordenar por prioridad y fecha planificada
            query = query.order_by(
                case(
                    (OrdenFabricacion.prioridad == PrioridadOrden.P1, 1),
                    (OrdenFabricacion.prioridad == PrioridadOrden.URGENTE, 1),
                    (OrdenFabricacion.prioridad == PrioridadOrden.P2, 2),
                    (OrdenFabricacion.prioridad == PrioridadOrden.ALTA, 2),
                    (OrdenFabricacion.prioridad == PrioridadOrden.P3, 3),
                    (OrdenFabricacion.prioridad == PrioridadOrden.MEDIA, 3),
                    (OrdenFabricacion.prioridad == PrioridadOrden.P4, 4),
                    (OrdenFabricacion.prioridad == PrioridadOrden.BAJA, 4),
                    else_=5
                ).asc(),
                OrdenFabricacion.fecha_planificada.asc().nullslast(),
                OrdenFabricacion.created_at.asc()
            )
            
            resultados = query.all()
            
            # Procesar resultados y calcular información adicional
            ofs_procesadas = []
            for of, progreso, proyecto, cliente in resultados:
                # Calcular tiempos estimados basados en cantidad de tableros
                tiempo_fabrica = self.planificacion_service.calcular_tiempo_estimado_fabrica(
                    of.cantidad_tableros or 0
                )
                tiempo_embalaje = self.planificacion_service.calcular_tiempo_estimado_embalaje(
                    of.cantidad_tableros or 0
                )
                
                # Calcular fechas estimadas si hay fecha planificada
                fecha_estimada_fabricacion = None
                fecha_estimada_embalaje = None
                
                if of.fecha_planificada:
                    # Fecha estimada de finalización de fabricación
                    fecha_estimada_fabricacion = of.fecha_planificada + timedelta(days=int(tiempo_fabrica))
                    # Fecha estimada de finalización de embalaje
                    fecha_estimada_embalaje = fecha_estimada_fabricacion + timedelta(days=int(tiempo_embalaje))
                
                # Calcular días hasta entrega
                dias_hasta_entrega = None
                if of.fecha_entrega_embalaje:
                    dias_hasta_entrega = (of.fecha_entrega_embalaje - date.today()).days
                
                of_data = {
                    'of': of,
                    'progreso_actual': progreso,
                    'proyecto': proyecto,
                    'cliente': cliente,
                    'tiempo_estimado_fabrica': tiempo_fabrica,
                    'tiempo_estimado_embalaje': tiempo_embalaje,
                    'fecha_estimada_fabricacion': fecha_estimada_fabricacion,
                    'fecha_estimada_embalaje': fecha_estimada_embalaje,
                    'dias_hasta_entrega': dias_hasta_entrega,
                    'tiene_fechas_completas': all([
                        of.fecha_planificada,
                        of.fecha_entrega_fabrica,
                        of.fecha_entrega_embalaje
                    ])
                }
                
                ofs_procesadas.append(of_data)
            
            return ofs_procesadas
            
        except Exception as e:
            print(f"Error obteniendo OFs en producción: {str(e)}")
            return []
    
    def get_matriz_planificacion_prioridades(self) -> Dict[str, Any]:
        """
        Genera la matriz completa para la vista de planificación y prioridades
        Agrupa por proyectos y calcula consolidados
        """
        try:
            # Obtener todas las OFs en producción
            ofs_data = self.get_ofs_en_produccion()
            
            # Agrupar por proyecto
            proyectos_agrupados = {}
            estadisticas = {
                'total_ofs': len(ofs_data),
                'ofs_sin_fecha_planificada': 0,
                'ofs_con_prioridad_alta': 0,
                'total_tableros': 0,
                'tiempo_total_fabrica': 0,
                'tiempo_total_embalaje': 0
            }
            
            for of_info in ofs_data:
                proyecto_id = of_info['proyecto'].id
                
                # Inicializar proyecto si no existe
                if proyecto_id not in proyectos_agrupados:
                    proyectos_agrupados[proyecto_id] = {
                        'proyecto': of_info['proyecto'],
                        'cliente': of_info['cliente'],
                        'ofs': [],
                        'total_tableros': 0,
                        'tiempo_total_fabrica': 0,
                        'tiempo_total_embalaje': 0,
                        'prioridad_maxima': PrioridadOrden.P4,  # Menor prioridad por defecto
                        'fecha_entrega_mas_proxima': None
                    }
                
                # Agregar OF al proyecto
                proyectos_agrupados[proyecto_id]['ofs'].append(of_info)
                
                # Actualizar totales del proyecto
                if of_info['of'].cantidad_tableros:
                    proyectos_agrupados[proyecto_id]['total_tableros'] += of_info['of'].cantidad_tableros
                    
                proyectos_agrupados[proyecto_id]['tiempo_total_fabrica'] += of_info['tiempo_estimado_fabrica']
                proyectos_agrupados[proyecto_id]['tiempo_total_embalaje'] += of_info['tiempo_estimado_embalaje']
                
                # Actualizar prioridad máxima del proyecto (menor número = mayor prioridad)
                if PrioridadOrden.get_orden_valor(of_info['of'].prioridad) < PrioridadOrden.get_orden_valor(proyectos_agrupados[proyecto_id]['prioridad_maxima']):
                    proyectos_agrupados[proyecto_id]['prioridad_maxima'] = of_info['of'].prioridad
                
                # Actualizar fecha de entrega más próxima del proyecto
                if of_info['of'].fecha_entrega_embalaje:
                    if (proyectos_agrupados[proyecto_id]['fecha_entrega_mas_proxima'] is None or 
                        of_info['of'].fecha_entrega_embalaje < proyectos_agrupados[proyecto_id]['fecha_entrega_mas_proxima']):
                        proyectos_agrupados[proyecto_id]['fecha_entrega_mas_proxima'] = of_info['of'].fecha_entrega_embalaje
                
                # Actualizar estadísticas generales
                if not of_info['of'].fecha_planificada:
                    estadisticas['ofs_sin_fecha_planificada'] += 1
                    
                if of_info['of'].prioridad in [PrioridadOrden.P1, PrioridadOrden.P2, PrioridadOrden.URGENTE, PrioridadOrden.ALTA]:
                    estadisticas['ofs_con_prioridad_alta'] += 1
                    
                if of_info['of'].cantidad_tableros:
                    estadisticas['total_tableros'] += of_info['of'].cantidad_tableros
                    
                estadisticas['tiempo_total_fabrica'] += of_info['tiempo_estimado_fabrica']
                estadisticas['tiempo_total_embalaje'] += of_info['tiempo_estimado_embalaje']
            
            # Ordenar proyectos por prioridad máxima y fecha de entrega
            proyectos_ordenados = sorted(
                proyectos_agrupados.values(),
                key=lambda p: (
                    PrioridadOrden.get_orden_valor(p['prioridad_maxima']),
                    p['fecha_entrega_mas_proxima'] or date(2099, 12, 31)
                )
            )
            
            return {
                'proyectos': proyectos_ordenados,
                'estadisticas': estadisticas,
                'fecha_actualizacion': datetime.now()
            }
            
        except Exception as e:
            print(f"Error generando matriz de planificación: {str(e)}")
            return {
                'proyectos': [],
                'estadisticas': {
                    'total_ofs': 0,
                    'ofs_sin_fecha_planificada': 0,
                    'ofs_con_prioridad_alta': 0,
                    'total_tableros': 0,
                    'tiempo_total_fabrica': 0,
                    'tiempo_total_embalaje': 0
                },
                'fecha_actualizacion': datetime.now()
            }
    
    def actualizar_fechas_of(self, of_id: int, fecha_planificada: Optional[date] = None, 
                            fecha_entrega_fabrica: Optional[date] = None, 
                            fecha_entrega_embalaje: Optional[date] = None) -> bool:
        """
        Actualiza las fechas de una Orden de Fabricación
        """
        try:
            of = db.session.get(OrdenFabricacion, of_id)
            if not of:
                return False
            
            if fecha_planificada:
                of.fecha_planificada = fecha_planificada
                
            if fecha_entrega_fabrica:
                of.fecha_entrega_fabrica = fecha_entrega_fabrica
                
            if fecha_entrega_embalaje:
                of.fecha_entrega_embalaje = fecha_entrega_embalaje
            
            db.session.commit()
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"Error actualizando fechas de OF {of_id}: {str(e)}")
            return False
    
    def actualizar_prioridad_of(self, of_id: int, nueva_prioridad: PrioridadOrden) -> bool:
        """
        Actualiza la prioridad de una Orden de Fabricación
        """
        try:
            of = db.session.get(OrdenFabricacion, of_id)
            if not of:
                return False
            
            of.prioridad = nueva_prioridad
            db.session.commit()
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"Error actualizando prioridad de OF {of_id}: {str(e)}")
            return False