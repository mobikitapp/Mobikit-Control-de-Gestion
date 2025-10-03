from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import and_, or_, func, desc, asc
from models import (
    Cliente, Proyecto, Contrato, HitoEntrega, Despacho,
    OrdenFabricacion, DespachoOrdenFabricacion,
    EstadoHitoEntrega, EstadoOF, EstadoBodega, TipoDespacho, Area, AreaEstado, OrdenAreaProgreso
)
from schemas.despachos import (
    ClienteConProyectos, ProyectoConHitos, HitoEntregaDespacho,
    PlanificacionDespachosResponse
)
from app import db
import logging

logger = logging.getLogger(__name__)

class PlanificacionDespachosService:
    """Servicio para la planificación de despachos basada en hitos de entrega"""

    @staticmethod
    def get_vista_planificacion() -> PlanificacionDespachosResponse:
        """
        Obtiene la vista principal de planificación de despachos
        organizada por Cliente → Proyecto → Hitos de Entrega
        """
        try:
            # Obtener todos los contratos activos con sus proyectos y clientes
            from models import PlanEntrega, Contrato, EstadoContrato

            contratos_activos = db.session.query(Contrato).join(
                Proyecto, Contrato.proyecto_id == Proyecto.id
            ).join(
                Cliente, Proyecto.cliente_id == Cliente.id
            ).filter(
                Contrato.estado == EstadoContrato.VIGENTE
            ).options(
                selectinload(Contrato.proyecto).selectinload(Proyecto.cliente),
                selectinload(Contrato.plan_entrega).selectinload(PlanEntrega.hitos)
            ).order_by(
                Cliente.nombre,
                Proyecto.nombre
            ).all()

            # Organizar datos por cliente
            clientes_dict: Dict[int, Dict[str, Any]] = {}
            total_hitos_pendientes = 0
            total_hitos_proximos = 0
            fecha_limite_proximos = date.today() + timedelta(days=7)

            for contrato in contratos_activos:
                cliente = contrato.proyecto.cliente
                proyecto = contrato.proyecto

                # Organizar por cliente
                if cliente.id not in clientes_dict:
                    clientes_dict[cliente.id] = {
                        'id': cliente.id,
                        'nombre': cliente.nombre,
                        'proyectos': {}
                    }

                # Organizar por proyecto
                if proyecto.id not in clientes_dict[cliente.id]['proyectos']:
                    clientes_dict[cliente.id]['proyectos'][proyecto.id] = {
                        'id': proyecto.id,
                        'nombre': proyecto.nombre,
                        'hitos_entrega': []
                    }

                # Procesar hitos del plan de entrega si existe
                if contrato.plan_entrega and contrato.plan_entrega.hitos:
                    for hito in contrato.plan_entrega.hitos:
                        # Solo incluir hitos pendientes o atrasados
                        if hito.estado in [EstadoHitoEntrega.PENDIENTE, EstadoHitoEntrega.ATRASADO]:
                            # Contar totales
                            total_hitos_pendientes += 1
                            if hito.fecha_programada <= fecha_limite_proximos:
                                total_hitos_proximos += 1

                            # Verificar si ya tiene despacho creado
                            despacho_creado = False
                            despacho_id = None

                            if hasattr(hito, 'despachos') and hito.despachos:
                                despacho_creado = len(hito.despachos) > 0
                                if despacho_creado and hito.despachos:
                                    despacho_id = hito.despachos[0].id

                            # Obtener OFs disponibles para este hito
                            ofs_disponibles = PlanificacionDespachosService._get_ofs_disponibles_para_hito(hito.id)

                            # Crear datos del hito
                            hito_data = {
                                'id': hito.id,
                                'contrato_id': contrato.id,
                                'contrato_numero_oc': contrato.numero_oc,
                                'descripcion': hito.descripcion or hito.titulo,
                                'fecha_entrega': hito.fecha_programada,
                                'estado': hito.estado.value,
                                'despacho_creado': despacho_creado,
                                'despacho_id': despacho_id,
                                'ordenes_fabricacion_disponibles': ofs_disponibles
                            }

                            clientes_dict[cliente.id]['proyectos'][proyecto.id]['hitos_entrega'].append(hito_data)

                # Si no hay plan de entrega pero sí fecha comprometida, crear hito virtual
                elif contrato.fecha_entrega_comprometida:
                    # Verificar si ya tiene despacho para esta fecha comprometida
                    despachos_contrato = db.session.query(Despacho).filter_by(contrato_id=contrato.id).all()
                    despacho_creado = len(despachos_contrato) > 0
                    despacho_id = despachos_contrato[0].id if despachos_contrato else None

                    # Obtener OFs disponibles para este contrato
                    ofs_disponibles = PlanificacionDespachosService.get_ofs_disponibles_para_contrato(contrato.id)

                    # Crear hito virtual basado en fecha comprometida
                    hito_virtual = {
                        'id': f"virtual_{contrato.id}",
                        'contrato_id': contrato.id,
                        'contrato_numero_oc': contrato.numero_oc,
                        'descripcion': f"Entrega comprometida - {contrato.numero_oc}",
                        'fecha_entrega': contrato.fecha_entrega_comprometida,
                        'estado': 'PENDIENTE',
                        'despacho_creado': despacho_creado,
                        'despacho_id': despacho_id,
                        'ordenes_fabricacion_disponibles': ofs_disponibles,
                        'es_virtual': True  # Flag para identificar hitos virtuales
                    }

                    # Contar como hito pendiente
                    total_hitos_pendientes += 1
                    if contrato.fecha_entrega_comprometida <= fecha_limite_proximos:
                        total_hitos_proximos += 1

                    clientes_dict[cliente.id]['proyectos'][proyecto.id]['hitos_entrega'].append(hito_virtual)

            # Convertir a formato de respuesta
            clientes_response = []
            for cliente_data in clientes_dict.values():
                proyectos_response = []
                for proyecto_data in cliente_data['proyectos'].values():
                    # Solo incluir proyectos que tengan hitos
                    if proyecto_data['hitos_entrega']:
                        # Ordenar hitos por fecha
                        hitos_ordenados = sorted(proyecto_data['hitos_entrega'],
                                               key=lambda x: x['fecha_entrega'])

                        proyectos_response.append({
                            'id': proyecto_data['id'],
                            'nombre': proyecto_data['nombre'],
                            'hitos_entrega': hitos_ordenados
                        })

                if proyectos_response:  # Solo incluir clientes con proyectos que tengan hitos
                    clientes_response.append({
                        'id': cliente_data['id'],
                        'nombre': cliente_data['nombre'],
                        'proyectos': proyectos_response
                    })

            return {
                'clientes': clientes_response,
                'total_hitos_pendientes': total_hitos_pendientes,
                'total_hitos_proximos': total_hitos_proximos
            }

        except Exception as e:
            logger.error(f"Error obteniendo vista de planificación: {str(e)}")
            raise Exception(f"Error obteniendo vista de planificación: {str(e)}")

    @staticmethod
    def _get_ofs_disponibles_para_hito(hito_id: int) -> List[Dict[str, Any]]:
        """
        Obtiene las órdenes de fabricación disponibles para un hito específico
        """
        try:
            # Obtener el hito con sus relaciones
            from models import PlanEntrega, Contrato
            hito = db.session.query(HitoEntrega).options(
                selectinload(HitoEntrega.plan_entrega).selectinload(PlanEntrega.contrato).selectinload(Contrato.proyecto)
            ).filter_by(id=hito_id).first()
            if not hito:
                return []

            # Primero obtener todas las OFs del proyecto
            from models import EstadoOF
            ofs_proyecto = db.session.query(OrdenFabricacion).filter(
                OrdenFabricacion.proyecto_id == hito.plan_entrega.contrato.proyecto_id
            ).all()

            ofs_disponibles = []
            for of in ofs_proyecto:
                try:
                    # Verificar si la OF está en estado que permite despacho
                    # Buscar primero en el sistema de áreas
                    progreso_actual = db.session.query(OrdenAreaProgreso).filter_by(
                        orden_fabricacion_id=of.id,
                        es_actual=True
                    ).first()

                    # Determinar si está lista para despacho
                    lista_para_despacho = False
                    estado_descripcion = 'Sin estado'

                    if progreso_actual and progreso_actual.area and progreso_actual.estado:
                        # Si está en área BODEGA con estado 'listo_para_despacho'
                        if (progreso_actual.area.tipo == TipoArea.BODEGA and
                            progreso_actual.estado.codigo == 'listo_para_despacho'):
                            lista_para_despacho = True
                            estado_descripcion = progreso_actual.estado.nombre or 'Listo para despacho'
                    else:
                        # Fallback: verificar por estado tradicional de OF
                        if hasattr(of, 'estado') and of.estado:
                            if of.estado == EstadoOF.COMPLETADO or of.estado == EstadoOF.LISTO_EMBALAJE:
                                lista_para_despacho = True
                                estado_descripcion = of.estado.value if hasattr(of.estado, 'value') else str(of.estado)

                    # Si está lista para despacho, calcular cantidades
                    if lista_para_despacho:
                        cantidad_total = PlanificacionDespachosService._calcular_cantidad_total_of(of.id)
                        cantidad_despachada = PlanificacionDespachosService._calcular_cantidad_despachada_of(of.id)
                        cantidad_disponible = cantidad_total - cantidad_despachada

                        # Solo incluir si hay cantidad disponible
                        if cantidad_disponible > 0:
                            ofs_disponibles.append({
                                'id': of.id,
                                'codigo': of.codigo,
                                'descripcion': of.descripcion or 'Sin descripción',
                                'cantidad_total': float(cantidad_total),
                                'cantidad_despachada': float(cantidad_despachada),
                                'cantidad_disponible': float(cantidad_disponible),
                                'estado': estado_descripcion,
                                'fecha_entrega_of': of.fecha_entrega_fabrica.isoformat() if of.fecha_entrega_fabrica else None
                            })

                except Exception as of_error:
                    logger.warning(f"Error procesando OF {of.id}: {str(of_error)}")
                    continue

            logger.info(f"Encontradas {len(ofs_disponibles)} OFs disponibles para hito {hito_id}")
            return ofs_disponibles

        except Exception as e:
            logger.error(f"Error obteniendo OFs disponibles para hito {hito_id}: {str(e)}")
            return []

    @staticmethod
    def get_ofs_disponibles_para_contrato(contrato_id: int) -> List[Dict[str, Any]]:
        """
        Obtiene las órdenes de fabricación disponibles para un contrato específico
        NUEVA LÓGICA: Mostrar todas las OFs excepto las asignadas TOTALMENTE
        """
        try:
            # Usar el servicio de fabricación que ya tiene la nueva lógica
            from services.fabricacion_service import FabricacionService
            fabricacion_service = FabricacionService()

            ofs_disponibles_obj = fabricacion_service.get_ofs_disponibles_para_despacho(contrato_id)

            # Convertir a formato dict para compatibilidad con la API
            ofs_disponibles = []
            for of in ofs_disponibles_obj:
                try:
                    ofs_disponibles.append({
                        'id': of.id,
                        'codigo': of.codigo,
                        'descripcion': of.descripcion or 'Sin descripción',
                        'cantidad_total': float(of.cantidad_tableros or 0),
                        'cantidad_despachada': float(getattr(of, 'cantidad_despachada_previa', 0)),
                        'cantidad_disponible': float(getattr(of, 'cantidad_disponible_despacho', of.cantidad_tableros or 0)),
                        'estado': getattr(of, 'estado_actual_nombre', 'Sin estado'),
                        'area': getattr(of, 'area_actual_nombre', 'Sin área'),
                        'tiene_despachos_parciales': getattr(of, 'tiene_despachos_parciales', False),
                        'fecha_entrega_of': of.fecha_entrega_fabrica.isoformat() if of.fecha_entrega_fabrica else None
                    })
                except Exception as of_error:
                    logger.warning(f"Error procesando OF {of.id}: {str(of_error)}")
                    continue

            logger.info(f"Encontradas {len(ofs_disponibles)} OFs disponibles para contrato {contrato_id}")
            return ofs_disponibles

        except Exception as e:
            logger.error(f"Error obteniendo OFs disponibles para contrato {contrato_id}: {str(e)}")
            return []


    @staticmethod
    def _calcular_cantidad_total_of(of_id: int) -> float:
        """Calcula la cantidad total de una OF basada en sus items o cantidad_tableros"""
        try:
            # Primero intentar con OrdenFabricacionItem
            from models import OrdenFabricacionItem
            total_items = db.session.query(func.sum(OrdenFabricacionItem.cantidad)).filter_by(
                of_id=of_id
            ).scalar()

            if total_items and total_items > 0:
                return float(total_items)

            # Fallback: usar cantidad_tableros de la OF directamente
            of = db.session.query(OrdenFabricacion).filter_by(id=of_id).first()
            if of and of.cantidad_tableros:
                return float(of.cantidad_tableros)

            # Último fallback
            return 1.0

        except Exception as e:
            logger.warning(f"Error calculando cantidad total para OF {of_id}: {str(e)}")
            return 1.0

    @staticmethod
    def _calcular_cantidad_despachada_of(of_id: int) -> float:
        """Calcula la cantidad ya despachada de una OF"""
        try:
            total = db.session.query(func.sum(DespachoOrdenFabricacion.cantidad_despachada)).filter_by(
                orden_fabricacion_id=of_id
            ).scalar() or 0
            return float(total)
        except Exception as e:
            logger.warning(f"Error calculando cantidad despachada para OF {of_id}: {str(e)}")
            return 0.0

    @staticmethod
    def get_hitos_proximos_vencimiento(dias: int = 30) -> List[Dict[str, Any]]:
        """
        Obtiene hitos próximos a vencer en los próximos N días
        """
        try:
            fecha_limite = date.today() + timedelta(days=dias)

            from models import PlanEntrega, Contrato

            # Mejorar la consulta con joinedload para evitar problemas de lazy loading
            hitos = db.session.query(HitoEntrega).join(
                PlanEntrega, HitoEntrega.plan_entrega_id == PlanEntrega.id
            ).join(
                Contrato, PlanEntrega.contrato_id == Contrato.id
            ).join(
                Proyecto, Contrato.proyecto_id == Proyecto.id
            ).join(
                Cliente, Proyecto.cliente_id == Cliente.id
            ).filter(
                HitoEntrega.fecha_programada <= fecha_limite,
                HitoEntrega.estado.in_([EstadoHitoEntrega.PENDIENTE, EstadoHitoEntrega.ATRASADO])
            ).options(
                joinedload(HitoEntrega.plan_entrega)
                .joinedload(PlanEntrega.contrato)
                .joinedload(Contrato.proyecto)
                .joinedload(Proyecto.cliente),
                selectinload(HitoEntrega.despachos)
            ).order_by(
                HitoEntrega.fecha_programada.asc()
            ).all()

            logger.info(f"Encontrados {len(hitos)} hitos próximos en los próximos {dias} días")

            hitos_proximos = []
            for hito in hitos:
                try:
                    dias_restantes = (hito.fecha_programada - date.today()).days
                    urgente = dias_restantes <= 2

                    # Verificar si ya tiene despacho creado
                    despacho_creado = False
                    despacho_id = None

                    # Buscar despachos asociados a este hito
                    despachos_hito = db.session.query(Despacho).filter_by(
                        hito_entrega_id=hito.id
                    ).all()

                    if despachos_hito:
                        despacho_creado = True
                        despacho_id = despachos_hito[0].id

                    # Obtener descripción del hito
                    descripcion = hito.descripcion or hito.titulo or f"Hito {hito.orden}"
                    cliente_nombre = hito.plan_entrega.contrato.proyecto.cliente.nombre
                    proyecto_nombre = hito.plan_entrega.contrato.proyecto.nombre
                    contrato_numero_oc = hito.plan_entrega.contrato.numero_oc

                    hito_data = {
                        'id': hito.id,
                        'plan_entrega_id': hito.plan_entrega_id,
                        'contrato_id': hito.plan_entrega.contrato_id if hito.plan_entrega else None,
                        'titulo': hito.titulo,
                        'descripcion': hito.descripcion,
                        'fecha_entrega': hito.fecha_programada,
                        'estado': hito.estado.value,
                        'dias_restantes': dias_restantes,
                        'urgente': urgente,
                        'cliente_nombre': cliente_nombre,
                        'proyecto_nombre': proyecto_nombre,
                        'contrato_numero_oc': contrato_numero_oc
                    }

                    hitos_proximos.append(hito_data)

                except Exception as hito_error:
                    logger.warning(f"Error procesando hito {hito.id}: {str(hito_error)}")
                    continue

            logger.info(f"Procesados {len(hitos_proximos)} hitos próximos correctamente")
            return hitos_proximos

        except Exception as e:
            logger.error(f"Error obteniendo hitos próximos: {str(e)}")
            return []  # Retornar lista vacía en lugar de excepción para evitar errores en la vista

    @staticmethod
    def get_estadisticas_planificacion() -> Dict[str, Any]:
        """
        Obtiene estadísticas generales de la planificación de despachos
        """
        try:
            # Total de hitos pendientes
            total_pendientes = db.session.query(HitoEntrega).filter(
                HitoEntrega.estado == EstadoHitoEntrega.PENDIENTE
            ).count()

            # Hitos atrasados
            total_atrasados = db.session.query(HitoEntrega).filter(
                HitoEntrega.estado == EstadoHitoEntrega.ATRASADO
            ).count()

            # Hitos próximos (7 días)
            fecha_limite = date.today() + timedelta(days=7)
            total_proximos = db.session.query(HitoEntrega).filter(
                HitoEntrega.fecha_programada <= fecha_limite,
                HitoEntrega.estado == EstadoHitoEntrega.PENDIENTE
            ).count()

            # Despachos programados este mes
            inicio_mes = date.today().replace(day=1)
            despachos_mes = db.session.query(Despacho).filter(
                func.date(Despacho.fecha_programada) >= inicio_mes
            ).count()

            # OFs listas para despacho (usando sistema de áreas)
            ofs_listas = db.session.query(OrdenFabricacion).join(
                OrdenAreaProgreso, OrdenFabricacion.id == OrdenAreaProgreso.orden_fabricacion_id
            ).join(
                Area, OrdenAreaProgreso.area_id == Area.id
            ).join(
                AreaEstado, OrdenAreaProgreso.estado_id == AreaEstado.id
            ).filter(
                OrdenAreaProgreso.es_actual == True,
                Area.tipo == TipoArea.BODEGA,
                AreaEstado.codigo == 'listo_para_despacho'
            ).count()

            return {
                'total_hitos_pendientes': total_pendientes,
                'total_hitos_atrasados': total_atrasados,
                'total_hitos_proximos': total_proximos,
                'despachos_programados_mes': despachos_mes,
                'ofs_listas_despacho': ofs_listas,
                'fecha_consulta': date.today().isoformat()
            }

        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {str(e)}")
            raise Exception(f"Error obteniendo estadísticas: {str(e)}")