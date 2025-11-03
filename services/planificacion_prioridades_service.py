from typing import List, Dict, Any, Optional
from datetime import datetime, date, timedelta
from sqlalchemy import and_, or_, case, desc, asc
from sqlalchemy.orm import joinedload

from app import db
from models import (
    OrdenFabricacion, Proyecto, Cliente, User, OrdenAreaProgreso, 
    Area, AreaEstado, TipoArea, EstadoPendientesFabricacion, EstadoFabrica,
    PrioridadOrden, Contrato, PlanEntrega, HitoEntrega, EstadoHitoEntrega
)
from services.planificacion_operacional_service import PlanificacionOperacionalService


class PlanificacionPrioridadesService:
    """Servicio para la planificación y gestión de prioridades de producción"""

    def __init__(self):
        self.planificacion_service = PlanificacionOperacionalService()

    def get_hitos_entrega_proyecto(self, proyecto_id: int) -> Dict[str, Any]:
        """
        Obtiene todos los hitos de entrega de un proyecto a través de sus contratos
        """
        try:
            # Obtener contratos del proyecto con sus planes de entrega y hitos
            contratos = (db.session.query(Contrato)
                        .filter(Contrato.proyecto_id == proyecto_id)
                        .join(PlanEntrega, Contrato.id == PlanEntrega.contrato_id, isouter=True)
                        .join(HitoEntrega, PlanEntrega.id == HitoEntrega.plan_entrega_id, isouter=True)
                        .all())

            hitos_pendientes = []
            hitos_todos = []
            hoy = date.today()

            # Obtener todos los hitos del proyecto
            for contrato in contratos:
                if contrato.plan_entrega and contrato.plan_entrega.hitos:
                    for hito in contrato.plan_entrega.hitos:
                        hito_data = {
                            'id': hito.id,
                            'titulo': hito.titulo,
                            'fecha_programada': hito.fecha_programada,
                            'estado': hito.estado,
                            'contrato': contrato,
                            'dias_restantes': (hito.fecha_programada - hoy).days if hito.fecha_programada >= hoy else 0
                        }

                        hitos_todos.append(hito_data)

                        # Solo agregar hitos pendientes futuros o de hoy
                        if hito.estado == EstadoHitoEntrega.PENDIENTE and hito.fecha_programada >= hoy:
                            hitos_pendientes.append(hito_data)

            # Ordenar hitos pendientes por fecha
            hitos_pendientes.sort(key=lambda x: x['fecha_programada'])

            # Encontrar próximo hito
            proximo_hito = hitos_pendientes[0] if hitos_pendientes else None

            return {
                'hitos_todos': sorted(hitos_todos, key=lambda x: x['fecha_programada']),
                'hitos_pendientes': hitos_pendientes,
                'proximo_hito': proximo_hito,
                'dias_proximo_hito': proximo_hito['dias_restantes'] if proximo_hito else None
            }

        except Exception as e:
            print(f"Error obteniendo hitos de entrega del proyecto {proyecto_id}: {str(e)}")
            return {
                'hitos_todos': [],
                'hitos_pendientes': [],
                'proximo_hito': None,
                'dias_proximo_hito': None
            }

    def get_ofs_en_produccion(self, incluir_solo_con_fechas: bool = False) -> List[Dict[str, Any]]:
        """
        Obtiene todas las OFs que están en estados de 'Pendiente de Fabricación' o 'Enviado a Fabricar'
        con información completa para la matriz de planificación
        """
        try:
            # Estados que nos interesan para la planificación (hasta Listo Embalaje)
            estados_pendientes = [
                'pendiente_aprobacion_diseño',
                'aprobado'
            ]
            estados_fabrica = [
                'enviado_a_fabricacion',
                'seccionando',
                'enchapando', 
                'mecanizando',
                'fabricacion_completa'
            ]
            estados_embalaje = [
                'pendiente_de_embalar',
                'embalando',
                'embalaje_listo'
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
            query = query.join(Area, OrdenAreaProgreso.area_id == Area.id) \
                         .join(AreaEstado, OrdenAreaProgreso.estado_id == AreaEstado.id)

            query = query.filter(
                and_(
                    # Excluir explícitamente área de Bodega y Despacho
                    Area.tipo.notin_(['BODEGA', 'DESPACHO']),
                    # Incluir estados específicos hasta Listo Embalaje
                    or_(
                        # Pendientes de Fabricación
                        and_(Area.tipo == 'PENDIENTES_FABRICACION',
                             AreaEstado.codigo.in_(estados_pendientes)),
                        # En Fábrica - Todos los estados
                        and_(Area.tipo == 'FABRICA',
                             AreaEstado.codigo.in_(estados_fabrica)),
                        # En Embalaje - Todos los estados hasta Listo
                        and_(Area.tipo == 'EMBALAJE',
                             AreaEstado.codigo.in_(estados_embalaje))
                    )
                )
            )

            # Si solo queremos OFs con fechas planificadas
            if incluir_solo_con_fechas:
                query = query.filter(OrdenFabricacion.fecha_planificada.isnot(None))

            # Ordenar por prioridad numérica (1=mayor prioridad) y fecha planificada
            query = query.order_by(
                OrdenFabricacion.prioridad_numerica.asc().nullslast(),
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

                # Calcular días hasta entrega (usar la fecha más próxima disponible)
                dias_hasta_entrega = None
                fecha_referencia = None

                # Priorizar fecha de entrega embalaje, luego fábrica, luego planificada
                if of.fecha_entrega_embalaje:
                    fecha_referencia = of.fecha_entrega_embalaje
                elif of.fecha_entrega_fabrica:
                    fecha_referencia = of.fecha_entrega_fabrica
                elif of.fecha_planificada:
                    # Si solo hay fecha planificada, estimar fecha de entrega
                    if tiempo_fabrica and tiempo_embalaje:
                        fecha_referencia = of.fecha_planificada + timedelta(days=int(tiempo_fabrica + tiempo_embalaje))
                    else:
                        fecha_referencia = of.fecha_planificada

                if fecha_referencia:
                    dias_hasta_entrega = (fecha_referencia - date.today()).days

                # Calcular tiempos reales si hay fechas definidas
                tiempo_real_fabrica = None
                tiempo_real_embalaje = None
                desviacion_fabrica = None
                desviacion_embalaje = None
                porcentaje_desviacion_fabrica = None
                porcentaje_desviacion_embalaje = None

                if of.fecha_planificada and of.fecha_entrega_fabrica:
                    tiempo_real_fabrica = (of.fecha_entrega_fabrica - of.fecha_planificada).days
                    desviacion_fabrica = tiempo_real_fabrica - tiempo_fabrica
                    if tiempo_fabrica > 0:
                        porcentaje_desviacion_fabrica = (desviacion_fabrica / tiempo_fabrica) * 100

                if of.fecha_entrega_fabrica and of.fecha_entrega_embalaje:
                    tiempo_real_embalaje = (of.fecha_entrega_embalaje - of.fecha_entrega_fabrica).days
                    desviacion_embalaje = tiempo_real_embalaje - tiempo_embalaje
                    if tiempo_embalaje > 0:
                        porcentaje_desviacion_embalaje = (desviacion_embalaje / tiempo_embalaje) * 100

                # Obtener información de tiempos de procesamiento por área
                tiempos_info = self.get_tiempos_procesamiento_of(of.id)

                of_data = {
                    'of': of,
                    'progreso_actual': progreso,
                    'proyecto': proyecto,
                    'cliente': cliente,
                    'tiempo_estimado_fabrica': tiempo_fabrica,
                    'tiempo_estimado_embalaje': tiempo_embalaje,
                    'tiempo_real_fabrica': tiempo_real_fabrica,
                    'tiempo_real_embalaje': tiempo_real_embalaje,
                    'desviacion_fabrica': desviacion_fabrica,
                    'desviacion_embalaje': desviacion_embalaje,
                    'porcentaje_desviacion_fabrica': porcentaje_desviacion_fabrica,
                    'porcentaje_desviacion_embalaje': porcentaje_desviacion_embalaje,
                    'fecha_estimada_fabricacion': fecha_estimada_fabricacion,
                    'fecha_estimada_embalaje': fecha_estimada_embalaje,
                    'dias_hasta_entrega': dias_hasta_entrega,
                    'tiene_fechas_completas': all([
                        of.fecha_planificada,
                        of.fecha_entrega_fabrica,
                        of.fecha_entrega_embalaje
                    ]),
                    # Información de tiempos por área
                    'tiempos_procesamiento': tiempos_info,
                    'area_actual': tiempos_info.get('area_actual', {}),
                    'tiempo_total_procesamiento': tiempos_info.get('tiempo_total_procesamiento', 0),
                    'areas_completadas': tiempos_info.get('areas_completadas', 0)
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
                    # Obtener hitos de entrega del proyecto
                    hitos_info = self.get_hitos_entrega_proyecto(proyecto_id)

                    proyectos_agrupados[proyecto_id] = {
                        'proyecto': of_info['proyecto'],
                        'cliente': of_info['cliente'],
                        'ofs': [],
                        'total_tableros': 0,
                        'tiempo_total_fabrica': 0,
                        'tiempo_total_embalaje': 0,
                        'prioridad_maxima': PrioridadOrden.P4,  # Menor prioridad por defecto
                        'prioridad_numerica_min': 99,  # Menor prioridad numérica por defecto
                        'fecha_entrega_mas_proxima': None,
                        'hitos_entrega': hitos_info['hitos_todos'],
                        'hitos_pendientes': hitos_info['hitos_pendientes'],
                        'proximo_hito': hitos_info['proximo_hito'],
                        'dias_proximo_hito': hitos_info['dias_proximo_hito']
                    }

                # Agregar OF al proyecto
                proyectos_agrupados[proyecto_id]['ofs'].append(of_info)

                # Actualizar totales del proyecto
                if of_info['of'].cantidad_tableros:
                    proyectos_agrupados[proyecto_id]['total_tableros'] += of_info['of'].cantidad_tableros

                proyectos_agrupados[proyecto_id]['tiempo_total_fabrica'] += of_info['tiempo_estimado_fabrica']
                proyectos_agrupados[proyecto_id]['tiempo_total_embalaje'] += of_info['tiempo_estimado_embalaje']

                # Actualizar prioridad máxima del proyecto (menor número = mayor prioridad)
                prioridad_actual = of_info['of'].prioridad_numerica or 99
                prioridad_proyecto = proyectos_agrupados[proyecto_id]['prioridad_numerica_min'] or 99
                if prioridad_actual < prioridad_proyecto:
                    proyectos_agrupados[proyecto_id]['prioridad_numerica_min'] = prioridad_actual
                    proyectos_agrupados[proyecto_id]['prioridad_maxima'] = of_info['of'].prioridad

                # Actualizar fecha de entrega más próxima del proyecto
                if of_info['of'].fecha_entrega_embalaje:
                    if (proyectos_agrupados[proyecto_id]['fecha_entrega_mas_proxima'] is None or 
                        of_info['of'].fecha_entrega_embalaje < proyectos_agrupados[proyecto_id]['fecha_entrega_mas_proxima']):
                        proyectos_agrupados[proyecto_id]['fecha_entrega_mas_proxima'] = of_info['of'].fecha_entrega_embalaje

                # Actualizar estadísticas generales
                if not of_info['of'].fecha_planificada:
                    estadisticas['ofs_sin_fecha_planificada'] += 1

                # Contar prioridades altas (P1-P5 o equivalentes legacy)
                prioridad_num = of_info['of'].prioridad_numerica or 99
                if prioridad_num <= 5 or of_info['of'].prioridad in [PrioridadOrden.P1, PrioridadOrden.P2, PrioridadOrden.URGENTE, PrioridadOrden.ALTA]:
                    estadisticas['ofs_con_prioridad_alta'] += 1

                if of_info['of'].cantidad_tableros:
                    estadisticas['total_tableros'] += of_info['of'].cantidad_tableros

                estadisticas['tiempo_total_fabrica'] += of_info['tiempo_estimado_fabrica']
                estadisticas['tiempo_total_embalaje'] += of_info['tiempo_estimado_embalaje']

            # Calcular días restantes mínimos por proyecto basado en sus OFs
            for proyecto_id, proyecto_data in proyectos_agrupados.items():
                dias_restantes_ofs = []
                for of_info in proyecto_data['ofs']:
                    if of_info['dias_hasta_entrega'] is not None:
                        dias_restantes_ofs.append(of_info['dias_hasta_entrega'])

                # Si hay OFs con días hasta entrega, usar el mínimo, sino usar días próximo hito
                if dias_restantes_ofs:
                    proyecto_data['dias_restantes_min'] = min(dias_restantes_ofs)
                else:
                    proyecto_data['dias_restantes_min'] = proyecto_data['dias_proximo_hito'] or 999

            # Ordenar proyectos por días restantes mínimos (menor a mayor)
            proyectos_ordenados = sorted(
                proyectos_agrupados.values(),
                key=lambda p: p['dias_restantes_min']
            )

            # Crear datos para el gantt de proyectos (simplificado usando los mismos datos)
            proyectos_gantt = []
            hoy = date.today()
            fecha_fin_gantt = hoy + timedelta(weeks=6)

            for proyecto_data in proyectos_ordenados:
                # Filtrar hitos que caen dentro del rango de 6 semanas del gantt
                hitos_en_gantt = []
                for hito in proyecto_data['hitos_entrega']:
                    if hoy <= hito['fecha_programada'] <= fecha_fin_gantt:
                        # Calcular posición porcentual dentro del rango de 6 semanas
                        dias_desde_inicio = (hito['fecha_programada'] - hoy).days
                        posicion_porcentual = (dias_desde_inicio / (6 * 7)) * 100  # 6 semanas = 42 días

                        hitos_en_gantt.append({
                            'titulo': hito['titulo'],
                            'fecha_programada': hito['fecha_programada'].isoformat() if hito['fecha_programada'] else None,
                            'dias_restantes': hito['dias_restantes'],
                            'posicion_porcentual': max(0, min(100, posicion_porcentual)),  # Clamp 0-100%
                            'contrato_id': hito['contrato'].id if hito.get('contrato') else None
                        })

                # Convert OFs data to serializable format for Gantt chart
                ofs_serializadas = []
                for of_info in proyecto_data['ofs']:
                    try:
                        # Debug: Check if of_info has the expected structure
                        if not isinstance(of_info, dict):
                            print(f"Error: of_info is not a dict: {type(of_info)} - {of_info}")
                            continue

                        if 'of' not in of_info:
                            print(f"Error: 'of' key not found in of_info. Keys: {list(of_info.keys())}")
                            continue

                        # Access the OF object from the of_info dictionary
                        of_obj = of_info['of']

                        if not hasattr(of_obj, 'id'):
                            print(f"Error: of_obj doesn't have expected attributes: {type(of_obj)} - {of_obj}")
                            continue

                        of_serializable = {
                            'id': of_obj.id,
                            'codigo': of_obj.codigo,
                            'cantidad_tableros': of_obj.cantidad_tableros or 0,
                            'fecha_planificada': of_obj.fecha_planificada.isoformat() if of_obj.fecha_planificada else None,
                            'fecha_entrega_fabrica': of_obj.fecha_entrega_fabrica.isoformat() if of_obj.fecha_entrega_fabrica else None,
                            'fecha_entrega_embalaje': of_obj.fecha_entrega_embalaje.isoformat() if of_obj.fecha_entrega_embalaje else None,
                            'prioridad_numerica': of_obj.prioridad_numerica or 99,
                            'tiempo_estimado_fabrica': of_info.get('tiempo_estimado_fabrica', 0),
                            'tiempo_estimado_embalaje': of_info.get('tiempo_estimado_embalaje', 0)
                        }
                        ofs_serializadas.append(of_serializable)

                    except Exception as e:
                        print(f"Error processing OF for Gantt chart: {str(e)}")
                        print(f"of_info type: {type(of_info)}")
                        print(f"of_info content: {of_info}")
                        continue

                gantt_proyecto = {
                    'nombre': proyecto_data['proyecto'].nombre,
                    'cliente_nombre': proyecto_data['cliente'].nombre,
                    'ofs_activas': len(proyecto_data['ofs']),
                    'total_tableros': proyecto_data['total_tableros'],
                    'ofs': ofs_serializadas,
                    'hitos_entrega': hitos_en_gantt,
                    'dias_proximo_hito': proyecto_data['dias_proximo_hito']
                }
                proyectos_gantt.append(gantt_proyecto)

            # Obtener estadísticas generales de tiempos por área
            estadisticas_tiempos = self.get_estadisticas_tiempos_por_area()

            # Obtener configuración de capacidad para el gráfico
            from services.configuraciones_service import ConfiguracionesService
            config_service = ConfiguracionesService()
            config_capacidad = config_service.get_parametros_operacionales()
            capacidad_semanal = config_capacidad.get('capacidad_maxima_tableros_semana', 100)

            return {
                'proyectos': proyectos_ordenados,
                'proyectos_gantt': proyectos_gantt,
                'estadisticas': estadisticas,
                'estadisticas_tiempos': estadisticas_tiempos,
                'capacidad_semanal': capacidad_semanal,
                'fecha_actualizacion': datetime.now(),
                'timedelta': timedelta,
                'today': datetime.now().date()
            }

        except Exception as e:
            print(f"Error generando matriz de planificación: {str(e)}")
            return {
                'proyectos': [],
                'proyectos_gantt': [],
                'estadisticas': {
                    'total_ofs': 0,
                    'ofs_sin_fecha_planificada': 0,
                    'ofs_con_prioridad_alta': 0,
                    'total_tableros': 0,
                    'tiempo_total_fabrica': 0,
                    'tiempo_total_embalaje': 0
                },
                'estadisticas_tiempos': {'success': False, 'estadisticas_por_area': {}, 'total_areas_con_datos': 0},
                'fecha_actualizacion': datetime.now(),
                'timedelta': timedelta,
                'today': datetime.now().date()
            }

    def actualizar_fechas_of(self, of_id: int, fecha_planificada: Optional[date] = None, 
                            fecha_entrega_fabrica: Optional[date] = None, 
                            fecha_entrega_embalaje: Optional[date] = None) -> bool:
        """
        Actualiza las fechas de una Orden de Fabricación con validaciones
        """
        try:
            of = db.session.get(OrdenFabricacion, of_id)
            if not of:
                print(f"OF {of_id} no encontrada")
                return False

            cambios_realizados = False

            # Actualizar fecha planificada
            if fecha_planificada is not None:
                of.fecha_planificada = fecha_planificada
                cambios_realizados = True
                print(f"Actualizada fecha_planificada de OF {of_id}: {fecha_planificada}")

            # Actualizar fecha entrega fábrica
            if fecha_entrega_fabrica is not None:
                of.fecha_entrega_fabrica = fecha_entrega_fabrica
                cambios_realizados = True
                print(f"Actualizada fecha_entrega_fabrica de OF {of_id}: {fecha_entrega_fabrica}")

            # Actualizar fecha entrega embalaje
            if fecha_entrega_embalaje is not None:
                of.fecha_entrega_embalaje = fecha_entrega_embalaje
                cambios_realizados = True
                print(f"Actualizada fecha_entrega_embalaje de OF {of_id}: {fecha_entrega_embalaje}")

            if cambios_realizados:
                # Actualizar timestamp de modificación
                of.updated_at = datetime.now()

                # Commit explícito
                db.session.commit()
                print(f"Fechas actualizadas correctamente para OF {of_id}")
                return True
            else:
                print(f"No se proporcionaron fechas para actualizar en OF {of_id}")
                return False

        except Exception as e:
            db.session.rollback()
            print(f"Error actualizando fechas de OF {of_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def asignar_prioridades_automaticas(self) -> Dict[str, Any]:
        """
        Asigna prioridades automáticamente a todas las OFs en producción
        desde P1 hasta P{cantidad_total} basado en fechas más próximas de entrega
        """
        try:
            from datetime import date, timedelta

            # Obtener todas las OFs en producción sin ordenar primero
            ofs_query = (db.session.query(OrdenFabricacion)
                        .join(OrdenAreaProgreso, 
                              and_(OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                                   OrdenAreaProgreso.es_actual == True))
                        .join(Area, OrdenAreaProgreso.area_id == Area.id)
                        .join(AreaEstado, OrdenAreaProgreso.estado_id == AreaEstado.id)
                        .filter(
                            and_(
                                # Excluir explícitamente área de Bodega y Despacho
                                Area.tipo.notin_(['BODEGA', 'DESPACHO']),
                                # Incluir estados específicos hasta Listo Embalaje
                                or_(
                                    # Pendientes de Fabricación
                                    and_(Area.tipo == 'PENDIENTES_FABRICACION',
                                         AreaEstado.codigo.in_(['pendiente_aprobacion_diseño', 'aprobado'])),
                                    # En Fábrica - Todos los estados
                                    and_(Area.tipo == 'FABRICA',
                                         AreaEstado.codigo.in_(['enviado_a_fabricacion', 'seccionando', 'enchapando', 'mecanizando', 'fabricacion_completa'])),
                                    # En Embalaje - Todos los estados hasta Listo
                                    and_(Area.tipo == 'EMBALAJE',
                                         AreaEstado.codigo.in_(['pendiente_de_embalar', 'embalando', 'embalaje_listo']))
                                )
                            )
                        )
                        .all())

            # Función auxiliar para calcular fecha de entrega dinámica
            def calcular_fecha_entrega_dinamica(of):
                """Calcula la fecha de entrega más apropiada para una OF"""
                hoy = date.today()

                # Prioridad 1: Fecha de entrega embalaje si existe
                if of.fecha_entrega_embalaje:
                    return of.fecha_entrega_embalaje, 1

                # Prioridad 2: Fecha de entrega fábrica si existe
                if of.fecha_entrega_fabrica:
                    return of.fecha_entrega_fabrica, 2

                # Prioridad 3: Fecha planificada + tiempo estimado
                if of.fecha_planificada:
                    tiempo_fabrica = self.planificacion_service.calcular_tiempo_estimado_fabrica(
                        of.cantidad_tableros or 0
                    )
                    tiempo_embalaje = self.planificacion_service.calcular_tiempo_estimado_embalaje(
                        of.cantidad_tableros or 0
                    )
                    fecha_estimada = of.fecha_planificada + timedelta(days=int(tiempo_fabrica + tiempo_embalaje))
                    return fecha_estimada, 3

                # Prioridad 4: Fecha muy lejana para OFs sin fechas (baja prioridad)
                return hoy + timedelta(days=9999), 4

            # Ordenar OFs por fecha de entrega más próxima
            ofs_con_fechas = []
            for of in ofs_query:
                fecha_entrega, tipo_fecha = calcular_fecha_entrega_dinamica(of)
                ofs_con_fechas.append({
                    'of': of,
                    'fecha_entrega': fecha_entrega,
                    'tipo_fecha': tipo_fecha,
                    'dias_hasta_entrega': (fecha_entrega - date.today()).days
                })

            # Ordenar por fecha de entrega (más próxima primero)
            # Criterios de ordenación:
            # 1. Fecha de entrega (ASC) - más próxima primero
            # 2. Tipo de fecha (ASC) - fechas reales antes que estimadas
            # 3. Fecha de creación (ASC) - más antigua primero en caso de empate
            ofs_ordenadas = sorted(ofs_con_fechas, key=lambda x: (
                x['fecha_entrega'],
                x['tipo_fecha'],
                x['of'].created_at
            ))

            # Asignar prioridades de P1 a P{total}
            total_actualizadas = 0
            for i, of_data in enumerate(ofs_ordenadas, 1):
                of = of_data['of']
                if of.prioridad_numerica != i:
                    of.prioridad_numerica = i
                    total_actualizadas += 1
                    print(f"OF {of.codigo}: P{i} - Entrega: {of_data['fecha_entrega'].strftime('%d/%m/%Y')} ({of_data['dias_hasta_entrega']} días)")

            db.session.commit()

            return {
                'success': True,
                'total_ofs': len(ofs_ordenadas),
                'total_actualizadas': total_actualizadas,
                'rango_prioridades': f"P1 - P{len(ofs_ordenadas)}",
                'criterio_ordenacion': 'Fechas más próximas de entrega'
            }

        except Exception as e:
            db.session.rollback()
            print(f"Error en asignación automática de prioridades: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'success': False, 'message': str(e)}

    def actualizar_prioridades_al_pasar_bodega(self, of_id: int) -> Dict[str, Any]:
        """
        Actualiza las prioridades cuando una OF pasa a bodega
        P2→P1, P3→P2, P4→P3, etc.
        """
        try:
            # Obtener la OF que pasó a bodega
            of_completada = db.session.query(OrdenFabricacion).filter_by(id=of_id).first()
            if not of_completada or not of_completada.prioridad_numerica:
                return {'success': False, 'message': 'OF no encontrada o sin prioridad'}

            prioridad_completada = of_completada.prioridad_numerica

            # Obtener todas las OFs con prioridad mayor (números más altos)
            ofs_a_actualizar = (db.session.query(OrdenFabricacion)
                              .join(OrdenAreaProgreso, 
                                    and_(OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                                         OrdenAreaProgreso.es_actual == True))
                              .join(Area, OrdenAreaProgreso.area_id == Area.id)
                              .filter(
                                  and_(
                                      Area.tipo.in_(['PENDIENTES_FABRICACION', 'FABRICA']),
                                      OrdenFabricacion.prioridad_numerica > prioridad_completada
                                  )
                              )
                              .all())

            # Reducir en 1 la prioridad de cada OF (mejor prioridad = número menor)
            total_actualizadas = 0
            for of in ofs_a_actualizar:
                of.prioridad_numerica -= 1
                total_actualizadas += 1

            db.session.commit()

            return {
                'success': True,
                'of_completada': of_completada.codigo,
                'total_actualizadas': total_actualizadas
            }

        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': str(e)}

    def get_rango_prioridades_disponible(self) -> Dict[str, Any]:
        """
        Obtiene el rango de prioridades disponible basado en la cantidad actual de OFs
        """
        try:
            total_ofs = (db.session.query(OrdenFabricacion)
                        .join(OrdenAreaProgreso, 
                              and_(OrdenAreaProgreso.orden_fabricacion_id == OrdenFabricacion.id,
                                   OrdenAreaProgreso.es_actual == True))
                        .join(Area, OrdenAreaProgreso.area_id == Area.id)
                        .join(AreaEstado, OrdenAreaProgreso.estado_id == AreaEstado.id)
                        .filter(
                            or_(
                                and_(Area.tipo == 'PENDIENTES_FABRICACION',
                                     AreaEstado.codigo.in_(['pendiente_aprobacion_diseño', 'aprobado'])),
                                and_(Area.tipo == 'FABRICA',
                                     AreaEstado.codigo.in_(['enviado_a_fabricacion']))
                            )
                        )
                        .count())

            max_prioridad = max(total_ofs, 1)  # Mínimo P1

            return {
                'success': True,
                'total_ofs': total_ofs,
                'rango_min': 1,
                'rango_max': max_prioridad,
                'opciones_prioridad': [f"P{i}" for i in range(1, max_prioridad + 1)]
            }

        except Exception as e:
            return {'success': False, 'message': str(e)}

    def actualizar_prioridad_of(self, of_id: int, nueva_prioridad_numerica: int) -> bool:
        """
        Actualiza la prioridad numérica de una Orden de Fabricación
        """
        try:
            of = db.session.get(OrdenFabricacion, of_id)
            if not of:
                return False

            of.prioridad_numerica = nueva_prioridad_numerica
            # Mantener compatibilidad con enum legacy
            if nueva_prioridad_numerica == 1:
                of.prioridad = PrioridadOrden.P1
            elif nueva_prioridad_numerica == 2:
                of.prioridad = PrioridadOrden.P2
            elif nueva_prioridad_numerica == 3:
                of.prioridad = PrioridadOrden.P3
            elif nueva_prioridad_numerica == 4:
                of.prioridad = PrioridadOrden.P4
            else:
                of.prioridad = PrioridadOrden.MEDIA

            db.session.commit()
            return True

        except Exception as e:
            db.session.rollback()
            print(f"Error actualizando prioridad de OF {of_id}: {str(e)}")
            return False

    def get_tiempos_procesamiento_of(self, of_id: int) -> Dict[str, Any]:
        """
        Obtiene el histórico de tiempos de procesamiento por área para una OF específica
        """
        try:
            # Obtener todo el historial de progreso de la OF (no solo el actual)
            from sqlalchemy.orm import joinedload
            historial_progreso = (db.session.query(OrdenAreaProgreso)
                                 .options(
                                     joinedload(OrdenAreaProgreso.area),
                                     joinedload(OrdenAreaProgreso.estado)
                                 )
                                 .filter(OrdenAreaProgreso.orden_fabricacion_id == of_id)
                                 .order_by(OrdenAreaProgreso.fecha_ingreso_area.asc())
                                 .all())

            tiempos_por_area = []
            tiempo_total_procesamiento = 0.0

            for progreso in historial_progreso:
                # Calcular tiempo en área dinámicamente
                tiempo_real_horas = None
                tiempo_transcurrido_actual = None

                if progreso.es_actual:
                    # Si es actual, calcular tiempo transcurrido hasta ahora
                    from datetime import datetime
                    ahora = datetime.now()
                    tiempo_transcurrido = ahora - progreso.fecha_ingreso_area
                    tiempo_transcurrido_actual = round(tiempo_transcurrido.total_seconds() / 3600, 2)
                else:
                    # Si no es actual, calcular tiempo que estuvo en el área
                    # Buscar el siguiente progreso para saber cuándo salió del área
                    siguiente_progreso = (db.session.query(OrdenAreaProgreso)
                                         .filter(
                                             OrdenAreaProgreso.orden_fabricacion_id == progreso.orden_fabricacion_id,
                                             OrdenAreaProgreso.fecha_ingreso_area > progreso.fecha_ingreso_area
                                         )
                                         .order_by(OrdenAreaProgreso.fecha_ingreso_area.asc())
                                         .first())

                    if siguiente_progreso:
                        tiempo_en_area = siguiente_progreso.fecha_ingreso_area - progreso.fecha_ingreso_area
                        tiempo_real_horas = round(tiempo_en_area.total_seconds() / 3600, 2)
                        tiempo_total_procesamiento += tiempo_real_horas

                area_info = {
                    'area_nombre': progreso.area.nombre,
                    'area_tipo': progreso.area.tipo.value,
                    'fecha_ingreso': progreso.fecha_ingreso_area,
                    'tiempo_estimado_horas': float(progreso.tiempo_estimado_horas) if progreso.tiempo_estimado_horas else None,
                    'tiempo_real_horas': tiempo_real_horas,
                    'tiempo_transcurrido_actual': tiempo_transcurrido_actual,
                    'es_actual': progreso.es_actual,
                    'estado_actual': progreso.estado.nombre if progreso.es_actual else None
                }

                tiempos_por_area.append(area_info)

            return {
                'success': True,
                'of_id': of_id,
                'tiempos_por_area': tiempos_por_area,
                'tiempo_total_procesamiento': tiempo_total_procesamiento,
                'areas_completadas': len([t for t in tiempos_por_area if not t['es_actual']]),
                'area_actual': next((t for t in tiempos_por_area if t['es_actual']), None)
            }

        except Exception as e:
            return {'success': False, 'message': str(e)}

    def get_estadisticas_tiempos_por_area(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas promedio de tiempos de procesamiento por área
        """
        try:
            # Obtener todos los progresos completados (no actuales) para calcular estadísticas
            from sqlalchemy.orm import joinedload
            progresos_completados = (db.session.query(OrdenAreaProgreso)
                                   .options(joinedload(OrdenAreaProgreso.area))
                                   .filter(OrdenAreaProgreso.es_actual == False)
                                   .all())

            estadisticas_areas = {}
            for progreso in progresos_completados:
                # Calcular tiempo dinámicamente para estadísticas
                siguiente_progreso = (db.session.query(OrdenAreaProgreso)
                                     .filter(
                                         OrdenAreaProgreso.orden_fabricacion_id == progreso.orden_fabricacion_id,
                                         OrdenAreaProgreso.fecha_ingreso_area > progreso.fecha_ingreso_area
                                     )
                                     .order_by(OrdenAreaProgreso.fecha_ingreso_area.asc())
                                     .first())

                if not siguiente_progreso:
                    continue  # Skip si no podemos calcular el tiempo

                tiempo_en_area = siguiente_progreso.fecha_ingreso_area - progreso.fecha_ingreso_area
                tiempo_real = round(tiempo_en_area.total_seconds() / 3600, 2)

                if tiempo_real <= 0:
                    continue  # Skip tiempos inválidos

                area_tipo = progreso.area.tipo.value

                if area_tipo not in estadisticas_areas:
                    estadisticas_areas[area_tipo] = {
                        'area_nombre': progreso.area.nombre,
                        'tiempos': [],
                        'total_ofs': 0
                    }

                estadisticas_areas[area_tipo]['tiempos'].append(tiempo_real)
                estadisticas_areas[area_tipo]['total_ofs'] += 1

            # Calcular promedios y estadísticas
            for area_tipo, datos in estadisticas_areas.items():
                tiempos = datos['tiempos']
                datos['tiempo_promedio'] = round(sum(tiempos) / len(tiempos), 2)
                datos['tiempo_minimo'] = round(min(tiempos), 2)
                datos['tiempo_maximo'] = round(max(tiempos), 2)
                del datos['tiempos']  # Remove raw data to reduce payload

            return {
                'success': True,
                'estadisticas_por_area': estadisticas_areas,
                'total_areas_con_datos': len(estadisticas_areas)
            }

        except Exception as e:
            return {'success': False, 'message': str(e)}